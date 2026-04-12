"""DHN-AQ Runtime Configuration (RC) file writer.

Generates a valid DHN_Acq_rc.txt from Python — replacing every PROMPT
field with a real value so DHN-AQ can be launched headlessly.

Reference: docs/dhn_api_reference.yaml (all field names derived from the
DHN Acq Manual).
"""

from __future__ import annotations

import textwrap
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


# ---------------------------------------------------------------------------
# Default field table
# ---------------------------------------------------------------------------
# Derived from docs/dhn_api_reference.yaml.
# Each entry: (field_name, type_tag, options, default_value, notes)
_RC_DEFAULTS: list[tuple[str, str, str, str, str]] = [
    # Storage
    ("Primary Data Directory",            "string",  "",                           "PROMPT",               "Path does NOT include session directory"),
    ("Secondary Data Directory",          "string",  "",                           "NO ENTRY",             "Set to NO ENTRY if not using secondary storage"),
    ("Cloud Service Provider",            "string",  "GOOGLE, AMAZON",             "NO ENTRY",             "Only if secondary is cloud"),
    ("Cloud Utilities Directory",         "string",  "",                           "NO ENTRY",             ""),
    ("Channel Specification File",        "string",  "",                           "DHN_Acq_cs.csv",       "Relative or absolute path"),
    # Segmenting
    ("Allow Segmenting",                  "ternary", "YES, NO",                    "YES",                  "Requires more memory"),
    ("Auto-Segment Data",                 "ternary", "YES, NO",                    "YES",                  ""),
    ("Auto-Segment Interval",             "string",  "",                           "NO ENTRY",             "hh:mm format; supersedes Auto-Segment Time"),
    ("Auto-Segment Time",                 "string",  "SEGMENT AT MIDNIGHT",        "SEGMENT AT MIDNIGHT",  "24h local time hh:mm"),
    ("Auto-Copy Segments",                "ternary", "YES, NO",                    "YES",                  ""),
    ("Auto-Delete Copied Segments",       "ternary", "YES, NO",                    "NO",                   ""),
    ("Packet Buffer Seconds",             "float",   "",                           "15.0",                 "512ch: slow ext drive ~90s, fast SSD ~3s"),
    ("Session Exists Behavior",           "string",  "PROMPT IF EXISTS, OVERWRITE, QUIT", "PROMPT IF EXISTS", ""),
    ("Include Segmented Session Records", "ternary", "YES, NO",                    "YES",                  ""),
    ("Robust Mode",                       "ternary", "YES, NO",                    "NO",                   "NOT FULLY IMPLEMENTED"),
    # Compression / Blocks
    ("Block Samples",                     "integer", "USE BLOCK DURATION",         "50000",                "25000-75000 good; for VDS use USE BLOCK DURATION + 10s"),
    ("Block Duration",                    "float",   "USE BLOCK SAMPLES",          "USE BLOCK SAMPLES",    "seconds"),
    ("Session Description",               "string",  "",                           "NO ENTRY",             ""),
    ("Equipment Description",             "string",  "",                           "NO ENTRY",             ""),
    ("Reference Description",             "string",  "",                           "NO ENTRY",             ""),
    ("Compression Algorithm",             "string",  "RED, PRED, MBE, VDS",        "PRED",                 "PRED=lossless; VDS=lossy"),
    ("Compression Algorithm Fall Through","ternary", "YES, NO",                    "YES",                  "RED/PRED fall through to MBE when smaller"),
    ("VDS Threshold",                     "float",   "",                           "5.0",                  "0.0=lossless, 10.0=very lossy"),
    ("VDS LFP Filter Cutoff",             "float",   "USE HIGH FREQUENCY FILTER SETTING, NO FILTER", "USE HIGH FREQUENCY FILTER SETTING", "Hz"),
    ("VDS Scale by Baseline",             "ternary", "YES, NO",                    "NO",                   "~30% more compression, minor fidelity loss"),
    # Filters
    ("Antialias Filter",                  "ternary", "YES, NO",                    "YES",                  ""),
    ("Line Noise Filter",                 "ternary", "YES, NO",                    "NO",                   "Better with longer blocks >= 10s"),
    ("Line Noise Alerts",                 "ternary", "YES, NO",                    "NO",                   "NOT CURRENTLY ENABLED"),
    ("Line Noise Alert Amplitude Threshold","float", "",                           "20.0",                 "NOT CURRENTLY ENABLED"),
    ("Line Noise Alert Duration Threshold","float",  "",                           "60.0",                 "NOT CURRENTLY ENABLED; seconds"),
    ("Low Frequency Filter Setting",      "float",   "",                           "NO ENTRY",             "Hz"),
    ("High Frequency Filter Setting",     "float",   "",                           "9000.0",               "Hz; 9kHz = analog antialiasing cutoff"),
    ("Notch Filter Frequency Setting",    "float",   "",                           "NO ENTRY",             "Hz"),
    ("AC Line Frequency",                 "float",   "50.0, 60.0",                 "NO ENTRY",             "50=EU/Asia, 60=Americas"),
    # Units
    ("Amplitude Units Conversion Factor", "float",   "",                           "1.0",                  ""),
    ("Amplitude Units Description",       "string",  "",                           "microvolts",           ""),
    ("Time Base Units Conversion Factor", "float",   "",                           "1.0",                  ""),
    ("Time Base Units Description",       "string",  "",                           "microseconds",         ""),
    ("Apply Recording Time Offset",       "ternary", "YES, NO",                    "YES",                  ""),
    ("Standard Timezone Acronym",         "string",  "",                           "NO ENTRY",             "e.g. MST (not MT/MDT)"),
    ("Recording Country",                 "string",  "",                           "NO ENTRY",             ""),
    ("Recording Territory",               "string",  "",                           "NO ENTRY",             "US: 2-letter state for DST accuracy"),
    ("Recording Locality",                "string",  "",                           "NO ENTRY",             "city/township"),
    ("Recording Institution",             "string",  "",                           "NO ENTRY",             ""),
    # Encryption
    ("Metadata Section 2 Encryption Level","string", "LEVEL 0, LEVEL 1, LEVEL 2", "LEVEL 1",              "technical recording data"),
    ("Metadata Section 3 Encryption Level","string", "LEVEL 0, LEVEL 1, LEVEL 2", "LEVEL 2",              "subject identifying data"),
    ("Time Series Data Encryption Level", "string",  "LEVEL 0, LEVEL 1, LEVEL 2", "LEVEL 0",              ""),
    ("Segment Record Encryption Level",   "string",  "LEVEL 0, LEVEL 1, LEVEL 2", "LEVEL 1",              ""),
    ("Neuralynx Port Record Encryption Level","string","LEVEL 0, LEVEL 1, LEVEL 2","LEVEL 0",             ""),
    ("Annotation Record Encryption Level","string",  "LEVEL 0, LEVEL 1, LEVEL 2", "LEVEL 2",              ""),
    ("System Log Record Encryption Level","string",  "LEVEL 0, LEVEL 1, LEVEL 2", "LEVEL 0",              ""),
    ("Level 1 Password",                  "string",  "",                           "NO ENTRY",             ""),
    ("Level 1 Password Hint",             "string",  "",                           "NO ENTRY",             ""),
    ("Level 2 Password",                  "string",  "",                           "NO ENTRY",             ""),
    ("Level 2 Password Hint",             "string",  "",                           "NO ENTRY",             ""),
    ("Level 3 Password",                  "string",  "USE DHN L3 PW",              "NO ENTRY",             "USE DHN L3 PW = DHN can recover lost passwords"),
    ("Include Session-level Segment Records","ternary","YES, NO",                  "YES",                  "tiny footprint; improves search perf"),
    ("Include Channel-level Segment Records","ternary","YES, NO",                  "YES",                  ""),
    # Events
    ("Include Neuralynx Port Records",    "ternary", "YES, NO",                    "YES",                  ""),
    ("Neuralynx Port Trigger Mode",       "string",  "NO TRIGGER, ANY CHANGE, HIGH BIT SET", "HIGH BIT SET", ""),
    ("Neuralynx Port Zero is Reset",      "ternary", "YES, NO",                    "YES",                  ""),
    ("Number of Subports in Neuralynx Port","integer","1, 2, 4",                   "2",                    "1 = no subports (full 32 bits)"),
    # Notifications
    ("Remote Notification Email Address", "string",  "",                           "NO ENTRY",             ""),
    ("Remote Notification Email Addressee","string", "",                           "NO ENTRY",             ""),
    ("Remote Notification Text Number",   "string",  "",                           "NO ENTRY",             ""),
    ("Remote Notification for Alerts",    "ternary", "YES, NO",                    "NO",                   ""),
    ("Remote Alert Notification Medium",  "string",  "TEXT, EMAIL, TEXT AND EMAIL","TEXT AND EMAIL",       ""),
    ("Use Watchdog Service",              "ternary", "YES, NO",                    "YES",                  "Requires notification medium"),
    ("Remote Notification for Updates",   "ternary", "YES, NO",                    "NO",                   ""),
    ("Remote Update Notification Medium", "string",  "TEXT, EMAIL, TEXT AND EMAIL","EMAIL",                ""),
    ("Remote Update Notification Frequency","float", "",                           "1.0",                  "hours"),
    # ── NETWORK (critical) ──────────────────────────────────────────────
    # DHN-AQ receives raw ATLAS UDP broadcast, NOT NetCom TCP.
    # For live acquisition: Receiving Server IP = 192.168.3.10 (ATLAS).
    # For NRD relay:        Receiving Server IP = <relay bridge PC IP>.
    ("Neuralynx PC MAC Address",          "string",  "",                           "00:00:00:00:00:00",    "Run ipconfig /all on Windows PC; not needed in broadcast mode"),
    ("Receive As Broadcast",              "ternary", "YES, NO",                    "NO",                   "YES = broadcast (no MAC needed); NO = unicast"),
    ("Receiving Local EN Interface Name", "string",  "",                           "eno1",                 "Check with: ip link show"),
    ("Receiving Local IP Address",        "string",  "",                           "192.168.3.100",        "DHN box IP on Nlx/relay subnet"),
    ("Receiving Server IP Address",       "string",  "",                           "192.168.3.10",         "ATLAS IP (live) or relay bridge IP (replay)"),
    ("Receiving Port Number",             "integer", "",                           "26090",                "26090 = ATLAS hardware port (hard-coded); must match relay"),
    ("Receiving Subnet Mask",             "string",  "",                           "255.255.255.0",        ""),
    ("Forward Neuralynx Packets",         "ternary", "YES, NO",                    "NO",                   "Forward to second DHN box via second NIC"),
    ("Forward As Broadcast",              "ternary", "YES, NO",                    "NO",                   ""),
    ("Forwarding Local EN Interface Name","string",  "",                           "eno1",                 ""),
    ("Forwarding Local IP Address",       "string",  "",                           "192.168.1.10",         "Different subnet from Nlx input"),
    ("Forwarding Client IP Address",      "string",  "",                           "192.168.1.100",        "Not needed in broadcast forwarding mode"),
    ("Forwarding Port Number",            "integer", "",                           "26091",                "Cannot be 26090"),
    ("Forwarding Subnet Mask",            "string",  "",                           "255.255.255.0",        ""),
    ("Non-blocking Forwarding",           "ternary", "YES, NO",                    "NO",                   "YES recommended for high channel counts to prevent stall"),
]


@dataclass
class RCWriter:
    """Build and write a DHN-AQ RC file from Python.

    Usage::

        rc = RCWriter()
        rc.set("Primary Data Directory", "/mnt/dhndev/recordings")
        rc.set("Receive As Broadcast", "YES")
        rc.set("Receiving Server IP Address", "192.168.3.10")
        rc.set("Receiving Local IP Address",  "192.168.3.50")
        rc.write("/home/dhn/DHN_Acq_rc.txt")
    """

    _values: dict[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        # Seed all fields with their defaults (no PROMPT values remain)
        for fname, _, _, default, _ in _RC_DEFAULTS:
            self._values[fname] = default

    # ------------------------------------------------------------------
    @classmethod
    def for_live_acquisition(
        cls,
        *,
        data_dir: str,
        local_ip: str = "192.168.3.50",
        interface: str = "eno1",
        atlas_ip: str = "192.168.3.10",
        cs_file: str = "DHN_Acq_cs.csv",
    ) -> "RCWriter":
        """Return an RC writer pre-configured for live ATLAS acquisition."""
        rc = cls()
        rc.set("Primary Data Directory",        data_dir)
        rc.set("Channel Specification File",    cs_file)
        rc.set("Receive As Broadcast",          "YES")
        rc.set("Receiving Local EN Interface Name", interface)
        rc.set("Receiving Local IP Address",    local_ip)
        rc.set("Receiving Server IP Address",   atlas_ip)
        rc.set("Receiving Port Number",         "26090")
        rc.set("Session Exists Behavior",       "OVERWRITE")
        return rc

    @classmethod
    def for_nrd_relay(
        cls,
        *,
        data_dir: str,
        local_ip: str,
        relay_ip: str,
        relay_port: int = 26090,
        interface: str = "eno1",
        cs_file: str = "DHN_Acq_cs.csv",
    ) -> "RCWriter":
        """Return an RC writer pre-configured for NRD replay via relay bridge.

        The relay bridge (nrd_stream.NRDRelayBridge) re-broadcasts NRD packets
        as UDP on relay_ip:relay_port, acting as a virtual ATLAS amplifier.
        """
        rc = cls()
        rc.set("Primary Data Directory",        data_dir)
        rc.set("Channel Specification File",    cs_file)
        rc.set("Receive As Broadcast",          "YES")
        rc.set("Receiving Local EN Interface Name", interface)
        rc.set("Receiving Local IP Address",    local_ip)
        rc.set("Receiving Server IP Address",   relay_ip)
        rc.set("Receiving Port Number",         str(relay_port))
        rc.set("Session Exists Behavior",       "OVERWRITE")
        return rc

    # ------------------------------------------------------------------
    def set(self, field_name: str, value: Any) -> None:
        """Override a single RC field value."""
        # Validate field name
        known = {f for f, *_ in _RC_DEFAULTS}
        if field_name not in known:
            raise ValueError(
                f"Unknown RC field: {field_name!r}. "
                f"Check docs/dhn_api_reference.yaml for valid field names."
            )
        # Never allow PROMPT to remain — DHN-AQ would block headless launch
        if str(value).strip().upper() == "PROMPT":
            raise ValueError(
                f"Field {field_name!r} value cannot be 'PROMPT' — DHN-AQ "
                f"would block waiting for user input in headless mode. "
                f"Provide a real value or 'NO ENTRY'."
            )
        self._values[field_name] = str(value)

    def get(self, field_name: str) -> str:
        return self._values[field_name]

    # ------------------------------------------------------------------
    def render(self) -> str:
        """Return the full RC file content as a string."""
        lines: list[str] = [
            "% DHN-AQ Runtime Configuration File",
            "% Generated by darkhorse_neuralynx.dhn_client.rc_writer",
            "% All PROMPT fields replaced — safe for headless (xvfb) launch.",
            "%",
        ]

        for fname, ftype, opts, default, notes in _RC_DEFAULTS:
            value = self._values.get(fname, default)
            if notes:
                for note_line in textwrap.wrap(notes, width=78):
                    lines.append(f"%% NOTES: {note_line}")
            lines.append(f"%% FIELD: {fname}")
            lines.append(f"%% TYPE: {ftype}")
            if opts:
                lines.append(f"%% OPTIONS: {opts}")
            else:
                lines.append("%% OPTIONS:")
            lines.append(f"%% DEFAULT: {default}")
            lines.append(f"%% VALUE: {value}")
            lines.append("")

        return "\n".join(lines)

    def write(self, path: str | Path) -> None:
        """Write the RC file to *path*, creating parent directories as needed."""
        dest = Path(path)
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(self.render(), encoding="utf-8")
        print(f"[rc_writer] Wrote RC file → {dest}")
