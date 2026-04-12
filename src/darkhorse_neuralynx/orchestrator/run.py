"""Session orchestrator — top-level entry point for the pipeline.

Orchestrates a complete acquisition or NRD replay session:

  Live acquisition:
    1. Run diagnostics (optional)
    2. Generate DHN RC + CS config files
    3. Launch DHN-AQ headlessly on Linux box (SSH + xvfb + xdotool)
    4. Wait for DHN-AQ to be recording
    5. (Optional) Run MATLAB expStarter script for Pegasus timing control
    6. Wait for session end / handle keyboard interrupt
    7. Gracefully terminate DHN-AQ

  NRD replay:
    1. Run diagnostics
    2. Generate DHN RC + CS config files (pointing at relay bridge)
    3. Launch DHN-AQ headlessly
    4. Start NRD relay bridge on Windows Pegasus PC
    5. (Optional) Run MATLAB expStarter
    6. Wait / cleanup

Usage::

    # From Python
    from darkhorse_neuralynx.orchestrator.run import SessionOrchestrator
    session = SessionOrchestrator.from_yaml("configs/my_session.yaml")
    session.run()

    # From CLI
    dhn-orchestrate --config configs/my_session.yaml
"""

from __future__ import annotations

import logging
import sys
import tempfile
import time
from pathlib import Path
from typing import Optional

log = logging.getLogger(__name__)


class SessionOrchestrator:
    """Drives a complete DHN-AQ + Pegasus acquisition or replay session.

    Parameters
    ----------
    config:
        A SessionConfig instance (see orchestrator/config.py).
    skip_diagnostics:
        Skip the pre-flight network checks (faster startup for trusted setups).
    """

    def __init__(self, config: object, *, skip_diagnostics: bool = False) -> None:
        # Import here to avoid circular dependency
        from darkhorse_neuralynx.orchestrator.config import SessionConfig, SessionMode
        assert isinstance(config, SessionConfig), f"Expected SessionConfig, got {type(config)}"
        self.config: SessionConfig = config  # type: ignore[assignment]
        self._SessionMode = SessionMode
        self.skip_diagnostics = skip_diagnostics
        self._dhn_launcher: Optional[object] = None
        self._relay_bridge:  Optional[object] = None
        self._matlab_proc:   Optional[object] = None

    @classmethod
    def from_yaml(cls, path: str | Path, **kwargs: object) -> "SessionOrchestrator":
        from darkhorse_neuralynx.orchestrator.config import SessionConfig
        config = SessionConfig.from_yaml(path)
        return cls(config, **kwargs)  # type: ignore[arg-type]

    # ------------------------------------------------------------------
    def run(self) -> None:
        """Execute the full session lifecycle."""
        cfg = self.config
        log.info(f"[orchestrator] Starting session: {cfg.session_name!r} (mode={cfg.mode})")

        try:
            if not self.skip_diagnostics:
                self._run_diagnostics()

            self._write_dhn_configs()
            self._launch_dhn()

            if cfg.mode == self._SessionMode.REPLAY:
                self._start_relay_bridge()

            if cfg.matlab.enabled:
                self._start_matlab()

            self._wait_for_session_end()

        except KeyboardInterrupt:
            log.info("[orchestrator] Interrupted by user")
        except Exception as exc:
            log.error(f"[orchestrator] Error: {exc}", exc_info=True)
            raise
        finally:
            self._cleanup()

    # ------------------------------------------------------------------
    def _run_diagnostics(self) -> None:
        from darkhorse_neuralynx.dhn_client.diagnose import Diagnostics
        cfg = self.config
        diag = Diagnostics(
            atlas_ip=cfg.network.atlas_ip,
            pegasus_ip=cfg.network.pegasus_ip,
            dhn_ip=cfg.network.dhn_ip,
            check_relay=(cfg.mode == self._SessionMode.REPLAY),
            relay_ip=cfg.network.pegasus_ip,
            relay_port=cfg.relay_port,
        )
        ok = diag.run_all()
        if not ok:
            raise RuntimeError(
                "Pre-flight diagnostics failed. Resolve issues above before running."
            )

    # ------------------------------------------------------------------
    def _write_dhn_configs(self) -> None:
        """Generate RC and CS files and stage them for upload."""
        from darkhorse_neuralynx.dhn_client.rc_writer import RCWriter
        from darkhorse_neuralynx.dhn_client.cs_writer import CSWriter
        from darkhorse_neuralynx.orchestrator.config import SessionMode

        cfg = self.config
        net = cfg.network
        dhn = cfg.dhn

        log.info("[orchestrator] Writing DHN config files...")

        if cfg.mode == SessionMode.LIVE:
            rc = RCWriter.for_live_acquisition(
                data_dir=dhn.data_dir,
                local_ip=net.dhn_ip,
                interface=net.dhn_interface,
                atlas_ip=net.atlas_ip,
                cs_file=dhn.cs_file,
            )
        else:  # REPLAY
            rc = RCWriter.for_nrd_relay(
                data_dir=dhn.data_dir,
                local_ip=net.dhn_ip,
                relay_ip=net.pegasus_ip,
                relay_port=cfg.relay_port,
                interface=net.dhn_interface,
                cs_file=dhn.cs_file,
            )

        # Optional metadata
        if dhn.subject_id:
            rc.set("Session Description", cfg.session_name)
        rc.set("Compression Algorithm", dhn.compression)

        cs = CSWriter.from_atlas_layout(
            n_macro=dhn.macro_channels,
            n_micro=dhn.micro_channels,
            macro_decimation_hz=dhn.macro_decimation_hz,
            micro_decimation_hz=dhn.micro_decimation_hz,
            compression=dhn.compression,
        )

        # Write to temp dir for upload
        self._tmp_dir = tempfile.mkdtemp(prefix="dhn_configs_")
        rc_local = Path(self._tmp_dir) / "DHN_Acq_rc.txt"
        cs_local = Path(self._tmp_dir) / "DHN_Acq_cs.csv"
        rc.write(rc_local)
        cs.write(cs_local)
        self._rc_local = rc_local
        self._cs_local = cs_local
        log.info(f"[orchestrator] Config files staged in {self._tmp_dir}")

    # ------------------------------------------------------------------
    def _launch_dhn(self) -> None:
        from darkhorse_neuralynx.dhn_client.launcher import DHNLauncher
        cfg = self.config
        dhn = cfg.dhn
        net = cfg.network

        launcher = DHNLauncher(
            session_name=cfg.session_name,
            dhn_executable=dhn.executable,
            rc_path=dhn.rc_file,
            cs_path=dhn.cs_file,
            host=net.dhn_ip if net.dhn_ip != "localhost" else None,
            ssh_user=net.dhn_ssh_user,
            ssh_key_path=net.dhn_ssh_key,
            xvfb_display=dhn.xvfb_display,
            sudo_password=dhn.sudo_password,
        )

        log.info("[orchestrator] Uploading configs and launching DHN-AQ...")
        launcher.upload_configs(self._rc_local, self._cs_local)
        launcher.launch(wait_for_dialog=True)
        launcher.wait_for_ready(timeout=120.0)

        self._dhn_launcher = launcher
        log.info("[orchestrator] ✓ DHN-AQ is recording")

    # ------------------------------------------------------------------
    def _start_relay_bridge(self) -> None:
        from darkhorse_neuralynx.pegasus_bridge.nrd_stream import NRDRelayBridge
        cfg = self.config
        net = cfg.network

        bridge = NRDRelayBridge(
            pegasus_server=net.pegasus_netcom_server,
            broadcast_ip=net.broadcast_ip,
            broadcast_port=cfg.relay_port,
            poll_interval_ms=cfg.relay_poll_ms,
            dll_path=cfg.pegasus.netcom_dll,
        )
        bridge.start()
        self._relay_bridge = bridge
        log.info("[orchestrator] ✓ NRD relay bridge started")

    # ------------------------------------------------------------------
    def _start_matlab(self) -> None:
        from darkhorse_neuralynx.orchestrator.matlab import MATLABRunner
        cfg = self.config

        runner = MATLABRunner(
            matlab_exe=cfg.matlab.matlab_exe,
            addpath=cfg.matlab.addpath,
            variables=cfg.matlab.variables,
        )
        # Run MATLAB async (it will poll Pegasus and send timing commands)
        self._matlab_proc = runner.run_script_async(
            cfg.matlab.script_path,
        )
        log.info("[orchestrator] ✓ MATLAB expStarter running in background")

    # ------------------------------------------------------------------
    def _wait_for_session_end(self) -> None:
        """Block until MATLAB finishes or Ctrl+C."""
        if self._matlab_proc is not None:
            log.info("[orchestrator] Waiting for MATLAB script to complete...")
            proc = self._matlab_proc
            try:
                proc.wait()  # type: ignore[attr-defined]
                log.info("[orchestrator] MATLAB script completed")
            except KeyboardInterrupt:
                proc.terminate()  # type: ignore[attr-defined]
                raise
        else:
            log.info("[orchestrator] Session running. Press Ctrl+C to stop.")
            while True:
                time.sleep(1)

    # ------------------------------------------------------------------
    def _cleanup(self) -> None:
        log.info("[orchestrator] Cleaning up...")

        if self._relay_bridge is not None:
            try:
                self._relay_bridge.stop()  # type: ignore[attr-defined]
            except Exception as e:
                log.warning(f"[orchestrator] Relay bridge stop error: {e}")

        if self._dhn_launcher is not None:
            try:
                self._dhn_launcher.terminate()  # type: ignore[attr-defined]
                self._dhn_launcher.close()       # type: ignore[attr-defined]
            except Exception as e:
                log.warning(f"[orchestrator] DHN launcher cleanup error: {e}")

        log.info("[orchestrator] Session ended.")


# ---------------------------------------------------------------------------
def main() -> None:
    """CLI entry point: dhn-orchestrate"""
    import argparse

    parser = argparse.ArgumentParser(
        description="DHN-AQ + Pegasus session orchestrator"
    )
    parser.add_argument(
        "--config", required=True,
        help="Path to session YAML config file (see configs/example_session.yaml)",
    )
    parser.add_argument(
        "--skip-diagnostics", action="store_true",
        help="Skip pre-flight network checks",
    )
    parser.add_argument(
        "--log-level", default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
    )
    args = parser.parse_args()

    logging.basicConfig(
        level=args.log_level,
        format="%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
        datefmt="%H:%M:%S",
    )

    session = SessionOrchestrator.from_yaml(
        args.config,
        skip_diagnostics=args.skip_diagnostics,
    )
    session.run()


if __name__ == "__main__":
    main()
