"""DHN-AQ Channel Specification (CS) file writer.

Generates a valid DHN_Acq_cs.csv from Python.

Reference: docs/dhn_api_reference.yaml — CS file section.

Column order (15 columns, 1-indexed):
  1  Channel Number
  2  Channel Name
  3  Decimation Frequency
  4  Block Samples
  5  Block Duration
  6  Compression Algorithm
  7  VDS Threshold
  8  VDS LFP Cutoff
  9  VDS Scale by Baseline
  10 Antialias Filter
  11 Line Noise Filter
  12 Line Noise Alerts
  13 Line Noise Alert Amplitude
  14 Line Noise Alert Duration
  15 Channel Description
"""

from __future__ import annotations

import csv
import io
from dataclasses import dataclass, field
from pathlib import Path

# Column names exactly as DHN-AQ expects them
_HEADER = [
    "Channel Number",
    "Channel Name",
    "Decimation Frequency",
    "Block Samples",
    "Block Duration",
    "Compression Algorithm",
    "VDS Threshold",
    "VDS LFP Cutoff",
    "VDS Scale by Baseline",
    "Antialias Filter",
    "Line Noise Filter",
    "Line Noise Alerts",
    "Line Noise Alert Amplitude",
    "Line Noise Alert Duration",
    "Channel Description",
]

# sentinel values
_USE_RC = 0         # use the RC file value for filter flags
_DISABLED = 0       # 0 = decimation disabled


@dataclass
class ChannelSpec:
    """Parameters for a single recorded channel."""

    channel_number: int                   # physical plug number (MED starts at 1)
    channel_name: str                     # base name, no extension
    decimation_frequency: float = 0.0     # Hz; 0 = no decimation
    block_samples: int = 0                # 0 = use block_duration or RC default
    block_duration: float = 0.0           # µs; 0 = use block_samples
    compression: str = ""                 # ""; empty = use RC default
    vds_threshold: float = 0.0
    vds_lfp_cutoff: float = 0.0
    vds_scale_by_baseline: int = 0        # -1=off, 0=RC, 1=on
    antialias_filter: int = 0             # -1=off, 0=RC, 1=on
    line_noise_filter: int = 0            # -1=off, 0=RC, 1=on
    line_noise_alerts: int = 0            # -1=off, 0=RC, 1=on
    line_noise_alert_amplitude: float = 0.0
    line_noise_alert_duration: float = 0.0
    description: str = ""

    def to_row(self) -> list[str]:
        return [
            str(self.channel_number),
            self.channel_name,
            str(self.decimation_frequency),
            str(self.block_samples),
            str(self.block_duration),
            self.compression,
            str(self.vds_threshold),
            str(self.vds_lfp_cutoff),
            str(self.vds_scale_by_baseline),
            str(self.antialias_filter),
            str(self.line_noise_filter),
            str(self.line_noise_alerts),
            str(self.line_noise_alert_amplitude),
            str(self.line_noise_alert_duration),
            self.description,
        ]


@dataclass
class CSWriter:
    """Build and write a DHN-AQ CS file from Python.

    Usage::

        # 512 channels, all at 32 kHz (no decimation)
        cs = CSWriter.from_channel_count(512, sample_freq=32000)
        cs.write("/home/dhn/DHN_Acq_cs.csv")

        # Mixed: channels 1-256 macro at 2 kHz, 257-512 micro at 32 kHz
        cs = CSWriter.from_atlas_layout(
            n_macro=256, n_micro=256,
            macro_decimation_hz=2000, micro_decimation_hz=0,
        )
        cs.write("/home/dhn/DHN_Acq_cs.csv")
    """

    channels: list[ChannelSpec] = field(default_factory=list)

    # ------------------------------------------------------------------
    @classmethod
    def from_channel_count(
        cls,
        n_channels: int,
        *,
        prefix: str = "CSC",
        sample_freq: float = 32000.0,
        decimation_freq: float = 0.0,
        compression: str = "PRED",
    ) -> "CSWriter":
        """Create a uniform CS file for *n_channels* channels."""
        channels = [
            ChannelSpec(
                channel_number=i + 1,
                channel_name=f"{prefix}{i + 1:04d}",
                decimation_frequency=decimation_freq,
                compression=compression,
                description=f"input {i + 1}",
            )
            for i in range(n_channels)
        ]
        return cls(channels=channels)

    @classmethod
    def from_atlas_layout(
        cls,
        *,
        n_macro: int = 256,
        n_micro: int = 256,
        macro_prefix: str = "MACRO",
        micro_prefix: str = "MICRO",
        macro_decimation_hz: float = 2000.0,
        micro_decimation_hz: float = 0.0,
        compression: str = "PRED",
    ) -> "CSWriter":
        """Create a CS file matching the UC Davis ATLAS layout.

        Channels 1..n_macro → macro channels (typically ~2 kHz, 10 kV range).
        Channels n_macro+1..n_macro+n_micro → micro channels (32 kHz, 3 mV range).
        """
        channels: list[ChannelSpec] = []
        for i in range(n_macro):
            channels.append(ChannelSpec(
                channel_number=i + 1,
                channel_name=f"{macro_prefix}{i + 1:04d}",
                decimation_frequency=macro_decimation_hz,
                compression=compression,
                description=f"macro electrode {i + 1}",
            ))
        for i in range(n_micro):
            idx = n_macro + i + 1
            channels.append(ChannelSpec(
                channel_number=idx,
                channel_name=f"{micro_prefix}{i + 1:04d}",
                decimation_frequency=micro_decimation_hz,
                compression=compression,
                description=f"micro electrode {i + 1}",
            ))
        return cls(channels=channels)

    # ------------------------------------------------------------------
    def add(self, spec: ChannelSpec) -> None:
        """Append a single channel spec."""
        self.channels.append(spec)

    def render(self) -> str:
        """Return the full CSV content as a string."""
        buf = io.StringIO()
        writer = csv.writer(buf)
        writer.writerow(_HEADER)
        for ch in self.channels:
            writer.writerow(ch.to_row())
        return buf.getvalue()

    def write(self, path: str | Path) -> None:
        """Write the CS CSV file to *path*."""
        dest = Path(path)
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(self.render(), encoding="utf-8", newline="")
        print(f"[cs_writer] Wrote CS file → {dest} ({len(self.channels)} channels)")
