"""Pre-flight diagnostics for the DHN-AQ + Pegasus pipeline.

Run this before starting an acquisition or replay session to catch
connectivity and configuration problems early.

Usage::

    python -m darkhorse_neuralynx.dhn_client.diagnose

Or as a library::

    from darkhorse_neuralynx.dhn_client.diagnose import Diagnostics
    diag = Diagnostics(atlas_ip="192.168.3.10", dhn_ip="192.168.3.50")
    diag.run_all()
"""

from __future__ import annotations

import os
import platform
import socket
import subprocess
import sys
import time
from dataclasses import dataclass, field
from typing import Optional

# ---------------------------------------------------------------------------

ATLAS_IP_DEFAULT         = "192.168.3.10"
PEGASUS_IP_DEFAULT       = "192.168.3.100"
ATLAS_PORT_DEFAULT       = 26090
DHN_BOX_SSH_PORT_DEFAULT = 22

ANSI_GREEN  = "\033[92m"
ANSI_YELLOW = "\033[93m"
ANSI_RED    = "\033[91m"
ANSI_RESET  = "\033[0m"
ANSI_BOLD   = "\033[1m"


def _icon(ok: Optional[bool]) -> str:
    if ok is True:
        return f"{ANSI_GREEN}✓{ANSI_RESET}"
    if ok is False:
        return f"{ANSI_RED}✗{ANSI_RESET}"
    return f"{ANSI_YELLOW}?{ANSI_RESET}"


@dataclass
class CheckResult:
    name: str
    ok: Optional[bool]
    message: str
    fix: str = ""


@dataclass
class Diagnostics:
    """Run pre-flight checks for the DHN-AQ acquisition pipeline.

    Parameters
    ----------
    atlas_ip:       ATLAS amplifier IP (hardware, 192.168.3.10 by default)
    pegasus_ip:     Pegasus Windows PC IP on the hardware subnet
    dhn_ip:         DHN Linux box IP
    dhn_ssh_port:   SSH port on DHN box (default 22)
    check_relay:    Also check relay bridge port (for NRD replay)
    relay_ip:       IP where the NRD relay bridge is broadcasting
    relay_port:     UDP port the relay bridge is using
    """

    atlas_ip: str       = ATLAS_IP_DEFAULT
    pegasus_ip: str     = PEGASUS_IP_DEFAULT
    dhn_ip: str         = "192.168.3.50"
    dhn_ssh_port: int   = DHN_BOX_SSH_PORT_DEFAULT
    check_relay: bool   = False
    relay_ip: str       = PEGASUS_IP_DEFAULT
    relay_port: int     = ATLAS_PORT_DEFAULT

    _results: list[CheckResult] = field(default_factory=list, init=False, repr=False)

    # ------------------------------------------------------------------
    def _ping(self, ip: str, count: int = 2, timeout: int = 2) -> bool:
        """Return True if *ip* responds to ping."""
        flag = "-n" if platform.system().lower() == "windows" else "-c"
        w_flag = ["-W", str(timeout)] if platform.system().lower() != "windows" else ["-w", str(timeout * 1000)]
        cmd = ["ping", flag, str(count)] + w_flag + [ip]
        try:
            result = subprocess.run(cmd, capture_output=True, timeout=timeout * count + 2)
            return result.returncode == 0
        except Exception:
            return False

    def _tcp_probe(self, ip: str, port: int, timeout: float = 3.0) -> bool:
        """Return True if a TCP connection to ip:port succeeds."""
        try:
            with socket.create_connection((ip, port), timeout=timeout):
                return True
        except (socket.timeout, ConnectionRefusedError, OSError):
            return False

    def _local_nics(self) -> list[str]:
        """Return list of local IP addresses on this machine."""
        ips: list[str] = []
        try:
            for info in socket.getaddrinfo(socket.gethostname(), None):
                ips.append(str(info[4][0]))
        except Exception:
            pass
        # Also try connecting to a public address to find the default route IP
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("8.8.8.8", 80))
            ips.append(s.getsockname()[0])
            s.close()
        except Exception:
            pass
        return list(set(ips))

    # ------------------------------------------------------------------
    def check_ping_atlas(self) -> CheckResult:
        ok = self._ping(self.atlas_ip)
        return CheckResult(
            name="Ping ATLAS amplifier",
            ok=ok,
            message=f"{self.atlas_ip} {'reachable' if ok else 'UNREACHABLE'}",
            fix=(
                "Ensure the Pegasus PC and DHN Linux box NICs are configured on "
                f"192.168.3.0/24 and connected to the ATLAS switch. "
                f"Check: sudo ip addr add 192.168.3.50/24 dev eno1"
            ) if not ok else "",
        )

    def check_ping_pegasus(self) -> CheckResult:
        ok = self._ping(self.pegasus_ip)
        return CheckResult(
            name="Ping Pegasus PC",
            ok=ok,
            message=f"{self.pegasus_ip} {'reachable' if ok else 'UNREACHABLE'}",
            fix=(
                f"Pegasus PC must have a static IP {self.pegasus_ip} on its "
                f"dedicated NIC. Check Windows ipconfig /all."
            ) if not ok else "",
        )

    def check_ping_dhn(self) -> CheckResult:
        ok = self._ping(self.dhn_ip)
        return CheckResult(
            name="Ping DHN Linux box",
            ok=ok,
            message=f"{self.dhn_ip} {'reachable' if ok else 'UNREACHABLE'}",
            fix=(
                f"Assign a static IP to the DHN Linux box on 192.168.3.0/24: "
                f"sudo ip addr add {self.dhn_ip}/24 dev eno1"
            ) if not ok else "",
        )

    def check_dhn_ssh(self) -> CheckResult:
        ok = self._tcp_probe(self.dhn_ip, self.dhn_ssh_port)
        return CheckResult(
            name="SSH reachable on DHN box",
            ok=ok,
            message=f"{self.dhn_ip}:{self.dhn_ssh_port} {'open' if ok else 'CLOSED'}",
            fix=(
                "Ensure SSH daemon is running on DHN box: sudo systemctl start sshd"
            ) if not ok else "",
        )

    def check_atlas_port(self) -> CheckResult:
        """Check that the ATLAS broadcast port is accessible (UDP — best-effort TCP probe)."""
        # UDP cannot be probed with a TCP connect, but we can check if
        # something on the Pegasus PC is listening on that port via TCP.
        ok = self._tcp_probe(self.pegasus_ip, ATLAS_PORT_DEFAULT, timeout=2.0)
        # This will often fail (UDP vs TCP) but is a best-effort indicator
        return CheckResult(
            name=f"ATLAS port {ATLAS_PORT_DEFAULT} on Pegasus PC (best-effort TCP probe)",
            ok=None,   # indeterminate for UDP
            message=(
                f"Port {ATLAS_PORT_DEFAULT} TCP {'responded' if ok else 'no response (expected for UDP)'}"
            ),
            fix=(
                "This check is informational only — ATLAS uses UDP broadcast. "
                "If DHN-AQ stalls, check Windows Firewall: ensure UDP 26090 inbound is allowed."
            ),
        )

    def check_local_subnet(self) -> CheckResult:
        """Verify this machine has an IP on the 192.168.3.0/24 subnet."""
        nics = self._local_nics()
        on_subnet = any(ip.startswith("192.168.3.") for ip in nics)
        return CheckResult(
            name="Local NIC on 192.168.3.0/24",
            ok=on_subnet,
            message=f"Local IPs: {nics}",
            fix=(
                "Add a 192.168.3.x IP to your NIC: "
                "sudo ip addr add 192.168.3.50/24 dev eno1"
            ) if not on_subnet else "",
        )

    def check_xvfb_available(self) -> CheckResult:
        """Check that xvfb-run is installed on this machine (if Linux)."""
        if platform.system().lower() != "linux":
            return CheckResult(
                name="xvfb-run (headless display)",
                ok=None,
                message="Not Linux — xvfb check skipped",
            )
        path = subprocess.run(["which", "xvfb-run"], capture_output=True).returncode == 0
        return CheckResult(
            name="xvfb-run installed",
            ok=path,
            message="xvfb-run found" if path else "xvfb-run NOT found",
            fix="sudo apt install xvfb" if not path else "",
        )

    def check_xdotool_available(self) -> CheckResult:
        """Check that xdotool is installed."""
        if platform.system().lower() != "linux":
            return CheckResult(
                name="xdotool (GUI automation)",
                ok=None,
                message="Not Linux — xdotool check skipped",
            )
        found = subprocess.run(["which", "xdotool"], capture_output=True).returncode == 0
        return CheckResult(
            name="xdotool installed",
            ok=found,
            message="xdotool found" if found else "xdotool NOT found",
            fix="sudo apt install xdotool" if not found else "",
        )

    def check_relay_port(self) -> CheckResult:
        """Check that the NRD relay bridge is broadcasting (TCP probe on relay port)."""
        ok = self._tcp_probe(self.relay_ip, self.relay_port, timeout=2.0)
        return CheckResult(
            name=f"NRD relay bridge at {self.relay_ip}:{self.relay_port}",
            ok=None,  # UDP — indeterminate from TCP probe
            message=(
                f"Relay {self.relay_ip}:{self.relay_port} "
                f"{'TCP responded' if ok else 'no TCP response (UDP relay — check process)'}"
            ),
            fix=(
                "Start the relay on the Pegasus PC: "
                "python -m darkhorse_neuralynx.pegasus_bridge.nrd_stream "
                f"--nrd C:\\path\\to\\RawData.nrd --port {self.relay_port}"
            ) if not ok else "",
        )

    # ------------------------------------------------------------------
    def run_all(self) -> bool:
        """Run all checks and print a summary table. Returns True if no hard failures."""
        checks = [
            self.check_ping_atlas,
            self.check_ping_pegasus,
            self.check_ping_dhn,
            self.check_dhn_ssh,
            self.check_local_subnet,
            self.check_xvfb_available,
            self.check_xdotool_available,
            self.check_atlas_port,
        ]
        if self.check_relay:
            checks.append(self.check_relay_port)

        print(f"\n{ANSI_BOLD}DHN-AQ / Pegasus Pre-flight Diagnostics{ANSI_RESET}")
        print("=" * 60)

        self._results.clear()
        hard_failures = 0
        for check_fn in checks:
            result = check_fn()
            self._results.append(result)
            icon = _icon(result.ok)
            print(f"  {icon}  {result.name}")
            print(f"       {result.message}")
            if result.fix:
                print(f"       {ANSI_YELLOW}FIX: {result.fix}{ANSI_RESET}")
            if result.ok is False:
                hard_failures += 1

        print("=" * 60)
        if hard_failures == 0:
            print(f"{ANSI_GREEN}All checks passed (or indeterminate).{ANSI_RESET}\n")
            return True
        else:
            print(
                f"{ANSI_RED}{hard_failures} check(s) failed. "
                f"Resolve before starting acquisition.{ANSI_RESET}\n"
            )
            return False


# ---------------------------------------------------------------------------
def main() -> None:
    """CLI entry point: dhn-diagnose"""
    import argparse

    parser = argparse.ArgumentParser(
        description="Pre-flight diagnostics for DHN-AQ + Pegasus pipeline"
    )
    parser.add_argument("--atlas-ip",   default=ATLAS_IP_DEFAULT)
    parser.add_argument("--pegasus-ip", default=PEGASUS_IP_DEFAULT)
    parser.add_argument("--dhn-ip",     default="192.168.3.50")
    parser.add_argument("--relay",      action="store_true", help="Also check NRD relay")
    parser.add_argument("--relay-ip",   default=PEGASUS_IP_DEFAULT)
    parser.add_argument("--relay-port", type=int, default=ATLAS_PORT_DEFAULT)
    args = parser.parse_args()

    diag = Diagnostics(
        atlas_ip=args.atlas_ip,
        pegasus_ip=args.pegasus_ip,
        dhn_ip=args.dhn_ip,
        check_relay=args.relay,
        relay_ip=args.relay_ip,
        relay_port=args.relay_port,
    )
    ok = diag.run_all()
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
