"""MATLAB subprocess runner.

Allows the Python orchestrator to invoke MATLAB scripts natively on
Windows — for example, running NetCom_expStarter_ATLAS_AC.m to control
Pegasus timing during NRD replay.

MATLAB is launched with ``matlab -batch "..."`` which runs a script
non-interactively and exits when complete.  stdout/stderr are streamed
back in real time to the Python orchestrator.
"""

from __future__ import annotations

import logging
import os
import shlex
import subprocess
import sys
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

log = logging.getLogger(__name__)


@dataclass
class MATLABRunner:
    """Run MATLAB scripts as subprocesses from Python.

    Parameters
    ----------
    matlab_exe:
        Full path to the MATLAB executable.
        Windows default: C:\\Program Files\\MATLAB\\R2024b\\bin\\matlab.exe
    addpath:
        List of directories to add to MATLAB's path before running the script.
        Include the neuralynxNetcom201 directory here.
    variables:
        Dict of MATLAB variable name → value to inject before the script runs.
        Values are injected as: ``varname = value;`` lines.
        Strings are auto-quoted; numbers are passed as-is.
    timeout:
        Maximum seconds to wait for MATLAB to finish (default: 3600 = 1 hour).
        Set to None for no timeout.
    """

    matlab_exe: str = r"C:\Program Files\MATLAB\R2024b\bin\matlab.exe"
    addpath: list[str] = field(default_factory=lambda: [r"nrdReplay\neuralynxNetcom201"])
    variables: dict[str, str] = field(default_factory=dict)
    timeout: Optional[float] = 3600.0

    # ------------------------------------------------------------------
    def _build_batch_command(
        self,
        script_path: str,
        extra_vars: Optional[dict[str, str]] = None,
    ) -> str:
        """Build the MATLAB -batch expression string."""
        lines: list[str] = []

        # 1. Add directories to path
        for p in self.addpath:
            # Use forward slashes (MATLAB accepts both on Windows)
            lines.append(f"addpath('{p.replace(chr(92), '/')}');")

        # 2. Inject variable overrides
        all_vars = {**self.variables, **(extra_vars or {})}
        for k, v in all_vars.items():
            # If the value looks numeric, don't quote; otherwise quote
            try:
                float(v)
                lines.append(f"{k} = {v};")
            except ValueError:
                # Escape single quotes for MATLAB strings
                safe_v = v.replace("'", "''")
                lines.append(f"{k} = '{safe_v}';")

        # 3. Run the script (use run() so the script sees base workspace vars)
        script_posix = script_path.replace("\\", "/")
        lines.append(f"run('{script_posix}');")

        return " ".join(lines)

    # ------------------------------------------------------------------
    def run_script(
        self,
        script_path: str,
        variables: Optional[dict[str, str]] = None,
        cwd: Optional[str] = None,
    ) -> int:
        """Run *script_path* in MATLAB -batch mode.

        Streams MATLAB stdout/stderr to Python's stdout in real time.

        Returns the exit code (0 = success).
        """
        if not Path(self.matlab_exe).exists():
            raise FileNotFoundError(
                f"MATLAB not found: {self.matlab_exe}\n"
                f"Update matlab_exe in your session config."
            )

        batch_expr = self._build_batch_command(script_path, variables)
        cmd = [self.matlab_exe, "-batch", batch_expr]

        log.info(f"[matlab] Launching MATLAB: {script_path}")
        log.debug(f"[matlab] batch expr: {batch_expr!r}")

        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            cwd=cwd or str(Path(script_path).parent),
        )

        # Stream output in real time
        assert proc.stdout is not None
        for line in proc.stdout:
            line = line.rstrip()
            log.info(f"[matlab] {line}")
            print(f"[matlab] {line}", flush=True)

        proc.wait(timeout=self.timeout)
        exit_code = proc.returncode
        if exit_code != 0:
            log.error(f"[matlab] Script exited with code {exit_code}")
        else:
            log.info("[matlab] Script completed successfully")
        return exit_code

    def run_script_async(
        self,
        script_path: str,
        variables: Optional[dict[str, str]] = None,
    ) -> subprocess.Popen:  # type: ignore[type-arg]
        """Start MATLAB in background and return the Popen object.

        Use this when you need MATLAB to run concurrently with DHN-AQ
        (e.g., expStarter controlling Pegasus while DHN-AQ records).
        """
        batch_expr = self._build_batch_command(script_path, variables)
        cmd = [self.matlab_exe, "-batch", batch_expr]
        log.info(f"[matlab] Starting MATLAB async: {script_path}")
        return subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            cwd=str(Path(script_path).parent),
        )
