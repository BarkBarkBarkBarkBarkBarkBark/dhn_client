"""Headless DHN-AQ launcher.

Launches DHN-AQ on a remote Linux box (or localhost) without a physical
monitor, using:

  • xvfb-run  — creates a virtual X display so the Qt GUI starts
  • xdotool   — types into the startup dialog and clicks Initialize

Prerequisites on the DHN Linux box:
    sudo apt install xvfb xdotool

The launcher:
1. Generates RC and CS files locally.
2. Uploads them to the DHN box via SSH/SFTP (or writes locally).
3. Starts DHN-AQ under xvfb-run in a background process.
4. Uses xdotool to wait for the startup dialog, fill in Session Name,
   RC file, CS file fields, and click Initialize.
5. Monitors the process to confirm recording has started.
"""

from __future__ import annotations

import logging
import re
import shlex
import time
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath
from typing import Optional

log = logging.getLogger(__name__)

# Optional SSH import — paramiko may not be available on Windows Pegasus PC
try:
    import paramiko  # type: ignore
    _PARAMIKO_AVAILABLE = True
except ImportError:
    _PARAMIKO_AVAILABLE = False


# ---------------------------------------------------------------------------
# xdotool automation script (runs on the DHN Linux box)
# ---------------------------------------------------------------------------
_XDOTOOL_SCRIPT = """\
#!/usr/bin/env bash
# Automate DHN-AQ startup dialog via xdotool.
# Called with: bash <script> <DISPLAY> <SESSION_NAME> <RC_PATH> <CS_PATH>
set -e
DISPLAY_NUM="$1"
SESSION_NAME="$2"
RC_PATH="$3"
CS_PATH="$4"
export DISPLAY=":${DISPLAY_NUM}"

# Wait for the DHN-AQ window to appear (timeout 60s)
for i in $(seq 1 60); do
    WID=$(xdotool search --name "DHN Acq" 2>/dev/null | head -1)
    [ -n "$WID" ] && break
    sleep 1
done
[ -z "$WID" ] && echo "ERROR: DHN-AQ window not found" && exit 1

# Bring window to front
xdotool windowactivate --sync "$WID"
sleep 0.5

# Clear & fill Session Name field (first field — Tab order)
xdotool key ctrl+a
xdotool type --clearmodifiers --delay 20 "$SESSION_NAME"
xdotool key Tab

# Fill CS File field
xdotool key ctrl+a
xdotool type --clearmodifiers --delay 20 "$CS_PATH"
xdotool key Tab

# Fill RC File field
xdotool key ctrl+a
xdotool type --clearmodifiers --delay 20 "$RC_PATH"
xdotool key Tab Tab Tab Tab Tab  # skip Name1, Name2, Name3, ID, AnonID

# Click Initialize button — find it by name
INIT_BTN=$(xdotool search --name "Initialize" 2>/dev/null | head -1)
if [ -n "$INIT_BTN" ]; then
    xdotool windowactivate --sync "$INIT_BTN"
    xdotool key Return
else
    # Fallback: activate main window and press Enter
    xdotool windowactivate --sync "$WID"
    xdotool key Return
fi

echo "DHN-AQ Initialize sent"
"""


# ---------------------------------------------------------------------------
@dataclass
class DHNLauncher:
    """Launch DHN-AQ headlessly on the DHN Linux box.

    Parameters
    ----------
    session_name:
        MED session name (no .medd extension).
    dhn_executable:
        Path to the DHN-AQ binary on the remote box.
    rc_path:
        Remote path where the RC file will be written.
    cs_path:
        Remote path where the CS file will be written.
    host:
        IP or hostname of the DHN Linux box. If None, run locally.
    ssh_user:
        SSH username on the DHN box.
    ssh_key_path:
        Path to SSH private key (defaults to ~/.ssh/id_rsa).
    xvfb_display:
        X display number for xvfb (default: 99).
    sudo_password:
        Sudo password for DHN-AQ (saved encrypted on first launch if desired).
    """

    session_name: str
    dhn_executable: str = "/opt/DHN/DHN_Acq"
    rc_path: str = "/home/dhn/DHN_Acq_rc.txt"
    cs_path: str = "/home/dhn/DHN_Acq_cs.csv"
    host: Optional[str] = None
    ssh_user: str = "dhn"
    ssh_key_path: Optional[str] = None
    xvfb_display: int = 99
    sudo_password: Optional[str] = None

    _ssh: Optional[object] = field(default=None, init=False, repr=False)
    _pid: Optional[int] = field(default=None, init=False, repr=False)

    # ------------------------------------------------------------------
    def _connect_ssh(self) -> "paramiko.SSHClient":
        if not _PARAMIKO_AVAILABLE:
            raise RuntimeError(
                "paramiko is required for remote DHN launch. "
                "Install it: pip install paramiko"
            )
        if self._ssh is None:
            client = paramiko.SSHClient()
            client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            key_path = self.ssh_key_path or str(Path.home() / ".ssh" / "id_rsa")
            client.connect(
                self.host or "",
                username=self.ssh_user,
                key_filename=key_path if Path(key_path).exists() else None,
            )
            self._ssh = client
            log.info(f"[launcher] SSH connected to {self.host}")
        return self._ssh  # type: ignore[return-value]

    def _run_remote(self, cmd: str, *, get_output: bool = False) -> str:
        ssh = self._connect_ssh()
        stdin, stdout, stderr = ssh.exec_command(cmd)  # type: ignore[attr-defined]
        out = stdout.read().decode()
        err = stderr.read().decode()
        if err.strip():
            log.debug(f"[launcher] stderr: {err.strip()}")
        if get_output:
            return out
        return ""

    def _upload_file(self, local_path: Path, remote_path: str) -> None:
        ssh = self._connect_ssh()
        sftp = ssh.open_sftp()  # type: ignore[attr-defined]
        sftp.put(str(local_path), remote_path)
        sftp.close()
        log.info(f"[launcher] Uploaded {local_path} → {remote_path}")

    # ------------------------------------------------------------------
    def upload_configs(self, rc_local: Path, cs_local: Path) -> None:
        """Upload RC and CS files to the DHN box."""
        if self.host:
            self._upload_file(rc_local, self.rc_path)
            self._upload_file(cs_local, self.cs_path)
        else:
            # Local mode: just copy files to expected paths
            import shutil
            shutil.copy2(rc_local, self.rc_path)
            shutil.copy2(cs_local, self.cs_path)
            log.info(f"[launcher] Copied configs to {self.rc_path}, {self.cs_path}")

    # ------------------------------------------------------------------
    def launch(self, wait_for_dialog: bool = True) -> None:
        """Start DHN-AQ under xvfb and automate the Initialize dialog."""
        log.info(f"[launcher] Launching DHN-AQ (session={self.session_name!r})")

        # 1. Upload the xdotool automation script
        script_remote = "/tmp/dhn_init.sh"
        if self.host:
            sftp = self._connect_ssh().open_sftp()  # type: ignore[attr-defined]
            with sftp.open(script_remote, "w") as f:
                f.write(_XDOTOOL_SCRIPT)
            sftp.chmod(script_remote, 0o755)
            sftp.close()
        else:
            Path(script_remote).write_text(_XDOTOOL_SCRIPT)
            Path(script_remote).chmod(0o755)

        # 2. Launch DHN-AQ under xvfb-run in background
        xvfb_cmd = (
            f"xvfb-run -n {self.xvfb_display} -s '-screen 0 1280x1024x24' "
            f"{self.dhn_executable} &"
        )
        if self.host:
            self._run_remote(f"nohup {xvfb_cmd} > /tmp/dhn_acq.log 2>&1 &")
        else:
            import subprocess
            subprocess.Popen(
                f"nohup {xvfb_cmd} > /tmp/dhn_acq.log 2>&1 &",
                shell=True,
            )

        log.info("[launcher] DHN-AQ process started under xvfb")

        if not wait_for_dialog:
            return

        # 3. Wait a moment for the GUI to load, then run the xdotool script
        log.info("[launcher] Waiting 8 s for DHN-AQ dialog to load...")
        time.sleep(8)

        cs_path = shlex.quote(self.cs_path)
        rc_path = shlex.quote(self.rc_path)
        sess_name = shlex.quote(self.session_name)
        xdotool_cmd = (
            f"bash {script_remote} {self.xvfb_display} "
            f"{sess_name} {rc_path} {cs_path}"
        )

        if self.host:
            out = self._run_remote(
                f"DISPLAY=:{self.xvfb_display} {xdotool_cmd}",
                get_output=True,
            )
        else:
            import subprocess
            result = subprocess.run(
                xdotool_cmd, shell=True, capture_output=True, text=True
            )
            out = result.stdout

        if "Initialize sent" in out:
            log.info("[launcher] ✓ DHN-AQ Initialize dialog completed")
        else:
            log.warning(f"[launcher] xdotool output unexpected: {out!r}")

    # ------------------------------------------------------------------
    def wait_for_ready(self, timeout: float = 60.0, poll_interval: float = 3.0) -> None:
        """Block until DHN-AQ log shows recording has started (or timeout)."""
        log.info("[launcher] Waiting for DHN-AQ to begin recording...")
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            time.sleep(poll_interval)
            log_tail = self._get_log_tail(30)
            if any(kw in log_tail for kw in ["Recording started", "Acquisition started", "Recording"]):
                log.info("[launcher] ✓ DHN-AQ is recording")
                return
            log.debug(f"[launcher] DHN log tail: {log_tail[-200:]!r}")
        log.warning("[launcher] Timed out waiting for DHN-AQ recording state")

    def _get_log_tail(self, lines: int = 30) -> str:
        cmd = f"tail -{lines} /tmp/dhn_acq.log"
        if self.host:
            return self._run_remote(cmd, get_output=True)
        else:
            import subprocess
            return subprocess.run(cmd, shell=True, capture_output=True, text=True).stdout

    # ------------------------------------------------------------------
    def annotate(self, note: str) -> None:
        """Send an annotation to the running DHN-AQ session via xdotool."""
        # This clicks the Annotate button and types the note
        # (requires Annotate button to be visible in the main window)
        script = (
            f"export DISPLAY=:{self.xvfb_display}; "
            f"WID=$(xdotool search --name 'DHN Acq' | head -1); "
            f"xdotool windowactivate --sync $WID; "
            f"sleep 0.3; "
            f"BTN=$(xdotool search --name 'Annotate' | head -1); "
            f"[ -n \"$BTN\" ] && xdotool key Return; "
            f"sleep 0.5; "
            f"xdotool type --delay 20 {shlex.quote(note)}; "
            f"xdotool key Return"
        )
        if self.host:
            self._run_remote(script)
        else:
            import subprocess
            subprocess.run(script, shell=True)

    def segment(self) -> None:
        """Trigger a manual session segment."""
        script = (
            f"export DISPLAY=:{self.xvfb_display}; "
            f"WID=$(xdotool search --name 'DHN Acq' | head -1); "
            f"xdotool windowactivate --sync $WID; "
            f"sleep 0.3; "
            f"BTN=$(xdotool search --name 'Segment' | head -1); "
            f"[ -n \"$BTN\" ] && xdotool key Return"
        )
        if self.host:
            self._run_remote(script)
        else:
            import subprocess
            subprocess.run(script, shell=True)

    def terminate(self) -> None:
        """Gracefully stop DHN-AQ via the Terminate button."""
        log.info("[launcher] Sending Terminate to DHN-AQ...")
        script = (
            f"export DISPLAY=:{self.xvfb_display}; "
            f"WID=$(xdotool search --name 'DHN Acq' | head -1); "
            f"xdotool windowactivate --sync $WID; "
            f"sleep 0.3; "
            f"BTN=$(xdotool search --name 'Terminate' | head -1); "
            f"[ -n \"$BTN\" ] && xdotool key Return; sleep 1; xdotool key Return"
        )
        if self.host:
            self._run_remote(script)
        else:
            import subprocess
            subprocess.run(script, shell=True)

    def close(self) -> None:
        """Close the SSH connection."""
        if self._ssh:
            self._ssh.close()  # type: ignore[attr-defined]
            self._ssh = None
