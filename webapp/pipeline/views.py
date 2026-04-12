"""Views for the pipeline app.

All Django "heavy lifting" lives here:
  - Dashboard  – list sessions, show active one
  - New/Edit   – form-based session creation
  - Detail     – live log tail + start/stop controls
  - Status API – JSON polled every 2 s by pipeline.js
  - Diagnostics – run pre-flight checks via AJAX
  - RC Preview  – return rendered RC file content
"""

from __future__ import annotations

import threading
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from .forms import SessionForm
from .models import AcquisitionSession

# ── module-level thread registry (survives request lifetime) ──────────────────
_active_threads: dict[int, threading.Thread] = {}
_stop_events:    dict[int, threading.Event]   = {}


# ─────────────────────────────────────────────────────────────────────────────
# Dashboard
# ─────────────────────────────────────────────────────────────────────────────
def dashboard(request):
    sessions = AcquisitionSession.objects.all()[:30]
    active   = next(
        (s for s in sessions if s.is_active), None
    )
    return render(request, "pipeline/dashboard.html", {
        "sessions":       sessions,
        "active_session": active,
    })


# ─────────────────────────────────────────────────────────────────────────────
# Create / Edit session
# ─────────────────────────────────────────────────────────────────────────────
def session_new(request):
    if request.method == "POST":
        form = SessionForm(request.POST)
        if form.is_valid():
            session = form.save()
            return redirect("session_detail", pk=session.pk)
    else:
        form = SessionForm()
    return render(request, "pipeline/session_form.html", {
        "form":  form,
        "title": "New Session",
    })


def session_edit(request, pk):
    session = get_object_or_404(AcquisitionSession, pk=pk)
    if request.method == "POST":
        form = SessionForm(request.POST, instance=session)
        if form.is_valid():
            form.save()
            return redirect("session_detail", pk=pk)
    else:
        form = SessionForm(instance=session)
    return render(request, "pipeline/session_form.html", {
        "form":    form,
        "session": session,
        "title":   f"Edit — {session.name}",
    })


# ─────────────────────────────────────────────────────────────────────────────
# Session detail page
# ─────────────────────────────────────────────────────────────────────────────
def session_detail(request, pk):
    session = get_object_or_404(AcquisitionSession, pk=pk)
    return render(request, "pipeline/session_detail.html", {"session": session})


# ─────────────────────────────────────────────────────────────────────────────
# Start / Stop (AJAX POST)
# ─────────────────────────────────────────────────────────────────────────────
@require_POST
def session_start(request, pk):
    session = get_object_or_404(AcquisitionSession, pk=pk)
    if session.is_active:
        return JsonResponse({"error": "Session is already running."}, status=400)

    stop_event = threading.Event()
    _stop_events[pk] = stop_event

    thread = threading.Thread(
        target=_run_session_thread,
        args=(pk, stop_event),
        daemon=True,
        name=f"session-{pk}",
    )
    _active_threads[pk] = thread

    # Reset state
    session.status      = AcquisitionSession.STATUS_STARTING
    session.started_at  = timezone.now()
    session.ended_at    = None
    session.log_output  = ""
    session.packets_sent = 0
    session.error_message = ""
    session.save()

    thread.start()
    return JsonResponse({"status": "started", "session_id": pk})


@require_POST
def session_stop(request, pk):
    session = get_object_or_404(AcquisitionSession, pk=pk)
    if pk in _stop_events:
        _stop_events[pk].set()
    session.status = AcquisitionSession.STATUS_STOPPING
    session.save(update_fields=["status"])
    return JsonResponse({"status": "stopping"})


# ─────────────────────────────────────────────────────────────────────────────
# Status JSON  (polled by pipeline.js)
# ─────────────────────────────────────────────────────────────────────────────
def session_status(request, pk):
    session = get_object_or_404(AcquisitionSession, pk=pk)

    # Only return the last 4 000 chars to avoid huge responses
    log_tail = session.log_output[-4000:] if session.log_output else ""

    return JsonResponse({
        "status":        session.status,
        "status_label":  session.get_status_display(),
        "status_color":  session.status_color,
        "log_tail":      log_tail,
        "packets_sent":  session.packets_sent,
        "duration":      session.duration_str,
        "error":         session.error_message,
        "is_active":     session.is_active,
    })


# ─────────────────────────────────────────────────────────────────────────────
# RC file preview  (AJAX GET)
# ─────────────────────────────────────────────────────────────────────────────
def preview_rc(request, pk):
    session = get_object_or_404(AcquisitionSession, pk=pk)
    try:
        from darkhorse_neuralynx.dhn_client.rc_writer import RCWriter

        if session.mode == AcquisitionSession.MODE_LIVE:
            rc = RCWriter.for_live_acquisition(
                data_dir=session.data_dir,
                local_ip=session.dhn_ip,
                interface=session.dhn_interface,
                atlas_ip=session.atlas_ip,
            )
        else:
            rc = RCWriter.for_nrd_relay(
                data_dir=session.data_dir,
                local_ip=session.dhn_ip,
                relay_ip=session.broadcast_ip,
                relay_port=session.relay_port,
                interface=session.dhn_interface,
            )
        return JsonResponse({"content": rc.render()})
    except Exception as exc:
        return JsonResponse({"error": str(exc)}, status=500)


# ─────────────────────────────────────────────────────────────────────────────
# Diagnostics page + AJAX runner
# ─────────────────────────────────────────────────────────────────────────────
def diagnostics(request):
    return render(request, "pipeline/diagnostics.html")


def run_diagnostics(request):
    atlas_ip   = request.GET.get("atlas_ip",   "192.168.3.10")
    pegasus_ip = request.GET.get("pegasus_ip", "192.168.3.100")
    dhn_ip     = request.GET.get("dhn_ip",     "192.168.3.50")

    try:
        from darkhorse_neuralynx.dhn_client.diagnose import Diagnostics

        diag = Diagnostics(
            atlas_ip=atlas_ip,
            pegasus_ip=pegasus_ip,
            dhn_ip=dhn_ip,
        )
        results = []
        for check_fn in [
            diag.check_ping_atlas,
            diag.check_ping_pegasus,
            diag.check_ping_dhn,
            diag.check_dhn_ssh,
            diag.check_local_subnet,
            diag.check_xvfb_available,
            diag.check_xdotool_available,
            diag.check_atlas_port,
        ]:
            r = check_fn()
            results.append({
                "name":    r.name,
                "ok":      r.ok,
                "message": r.message,
                "fix":     getattr(r, "fix", ""),
            })
        return JsonResponse({"results": results})
    except Exception as exc:
        return JsonResponse({"error": str(exc)}, status=500)


# ─────────────────────────────────────────────────────────────────────────────
# Background session runner
# ─────────────────────────────────────────────────────────────────────────────
def _run_session_thread(session_pk: int, stop_event: threading.Event) -> None:
    """
    Runs the full acquisition pipeline in a background thread.

    Steps (replay mode):
      1. Generate RC + CS config files
      2. Upload configs to DHN box via SSH
      3. Launch DHN-AQ headless
      4. Start NRD relay bridge (polls Pegasus NetCom → re-broadcasts UDP)
      5. Wait for stop signal
      6. Cleanup (stop relay, terminate DHN-AQ)

    In live mode, step 4 is skipped — DHN-AQ receives UDP directly from ATLAS.
    """
    # Each background thread needs its own DB connection.
    from django.db import connection as db_conn
    db_conn.close()

    def log(msg: str) -> None:
        s = AcquisitionSession.objects.get(pk=session_pk)
        s.append_log(msg)

    def set_status(st: str) -> None:
        AcquisitionSession.objects.filter(pk=session_pk).update(status=st)

    session = AcquisitionSession.objects.get(pk=session_pk)

    try:
        import tempfile
        from pathlib import Path

        log("▶ Session starting …")

        # ── 1. Generate config files ────────────────────────────────────────
        log("⚙  Generating DHN-AQ RC + CS config files …")
        from darkhorse_neuralynx.dhn_client.rc_writer import RCWriter
        from darkhorse_neuralynx.dhn_client.cs_writer import CSWriter

        tmp     = Path(tempfile.mkdtemp(prefix="dhn_"))
        rc_path = tmp / "DHN_Acq_rc.txt"
        cs_path = tmp / "DHN_Acq_cs.csv"

        if session.mode == AcquisitionSession.MODE_LIVE:
            rc = RCWriter.for_live_acquisition(
                data_dir=session.data_dir,
                local_ip=session.dhn_ip,
                interface=session.dhn_interface,
                atlas_ip=session.atlas_ip,
            )
            log(f"   Mode: LIVE   — DHN will receive UDP directly from ATLAS ({session.atlas_ip})")
        else:
            rc = RCWriter.for_nrd_relay(
                data_dir=session.data_dir,
                local_ip=session.dhn_ip,
                relay_ip=session.broadcast_ip,
                relay_port=session.relay_port,
                interface=session.dhn_interface,
            )
            log(f"   Mode: REPLAY — DHN will receive relay UDP from {session.broadcast_ip}:{session.relay_port}")

        cs = CSWriter.from_atlas_layout(
            n_macro=session.n_macro,
            n_micro=session.n_micro,
            macro_decimation_hz=session.macro_decimation_hz,
            micro_decimation_hz=session.micro_decimation_hz,
            compression=session.compression,
        )
        rc.write(rc_path)
        cs.write(cs_path)
        log(f"   Config staged at {tmp}")

        if stop_event.is_set():
            log("⚠  Stopped before DHN launch.")
            set_status("idle")
            return

        # ── 2 + 3. Launch DHN-AQ ────────────────────────────────────────────
        log(f"🖥  Launching DHN-AQ on {session.dhn_ip} (xvfb + xdotool headless) …")
        from darkhorse_neuralynx.dhn_client.launcher import DHNLauncher

        remote_home = f"/home/{session.dhn_ssh_user}"
        launcher = DHNLauncher(
            session_name=session.name,
            dhn_executable="/opt/DHN/DHN_Acq",
            rc_path=f"{remote_home}/DHN_Acq_rc.txt",
            cs_path=f"{remote_home}/DHN_Acq_cs.csv",
            host=session.dhn_ip,
            ssh_user=session.dhn_ssh_user,
        )

        launcher.upload_configs(rc_path, cs_path)
        log("   Config files uploaded to DHN box ✓")
        launcher.launch(wait_for_dialog=True)
        log("   DHN-AQ initialize dialog completed ✓")
        launcher.wait_for_ready(timeout=120.0)
        log("   DHN-AQ is recording ✓")

        set_status("recording")

        if stop_event.is_set():
            launcher.terminate()
            launcher.close()
            set_status("idle")
            return

        # ── 4. NRD relay bridge (replay only) ───────────────────────────────
        relay = None
        if session.mode == AcquisitionSession.MODE_REPLAY:
            log(f"📡  Starting NRD relay bridge → {session.broadcast_ip}:{session.relay_port} …")
            from darkhorse_neuralynx.pegasus_bridge.nrd_stream import NRDRelayBridge

            relay = NRDRelayBridge(
                pegasus_server="localhost",
                broadcast_ip=session.broadcast_ip,
                broadcast_port=session.relay_port,
            )
            relay.start()
            log("   Relay bridge started ✓  (polling Pegasus NetCom, re-broadcasting as ATLAS UDP)")
        else:
            log("ℹ  Live mode — no relay bridge needed; DHN-AQ receives ATLAS UDP directly.")

        # ── 5. Wait for stop signal ──────────────────────────────────────────
        import time
        log("⏺  Recording in progress. Use the Stop button to end the session.")
        while not stop_event.is_set():
            time.sleep(2)
            if relay:
                AcquisitionSession.objects.filter(pk=session_pk).update(
                    packets_sent=relay.packets_sent
                )

        # ── 6. Cleanup ───────────────────────────────────────────────────────
        log("⏹  Stopping session …")
        if relay:
            relay.stop()
            log(f"   Relay stopped — {relay.packets_sent:,} packets sent total.")

        launcher.terminate()
        log("   DHN-AQ terminated ✓")
        launcher.close()

        AcquisitionSession.objects.filter(pk=session_pk).update(
            status="completed",
            ended_at=timezone.now(),
        )
        log("✅  Session completed successfully.")

    except Exception as exc:
        AcquisitionSession.objects.filter(pk=session_pk).update(
            status="error",
            error_message=str(exc),
            ended_at=timezone.now(),
        )
        try:
            log(f"❌  ERROR: {exc}")
        except Exception:
            pass
