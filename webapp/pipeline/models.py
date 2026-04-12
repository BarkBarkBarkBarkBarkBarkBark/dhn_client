"""AcquisitionSession model — one row per recording session."""

from django.db import models
from django.utils import timezone


class AcquisitionSession(models.Model):

    # ── Mode ──────────────────────────────────────────────────────────────────
    MODE_LIVE   = "live"
    MODE_REPLAY = "replay"
    MODE_CHOICES = [
        (MODE_LIVE,   "Live ATLAS Acquisition"),
        (MODE_REPLAY, "NRD File Replay"),
    ]

    # ── Status ────────────────────────────────────────────────────────────────
    STATUS_IDLE      = "idle"
    STATUS_STARTING  = "starting"
    STATUS_RECORDING = "recording"
    STATUS_STOPPING  = "stopping"
    STATUS_COMPLETED = "completed"
    STATUS_ERROR     = "error"
    STATUS_CHOICES = [
        (STATUS_IDLE,      "Idle"),
        (STATUS_STARTING,  "Starting"),
        (STATUS_RECORDING, "Recording"),
        (STATUS_STOPPING,  "Stopping"),
        (STATUS_COMPLETED, "Completed"),
        (STATUS_ERROR,     "Error"),
    ]

    # ── Identity ──────────────────────────────────────────────────────────────
    name        = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    mode        = models.CharField(max_length=10, choices=MODE_CHOICES, default=MODE_REPLAY)
    status      = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_IDLE)

    # ── Timestamps ────────────────────────────────────────────────────────────
    created_at = models.DateTimeField(auto_now_add=True)
    started_at = models.DateTimeField(null=True, blank=True)
    ended_at   = models.DateTimeField(null=True, blank=True)

    # ── Network ───────────────────────────────────────────────────────────────
    atlas_ip      = models.CharField(max_length=40, default="192.168.3.10")
    pegasus_ip    = models.CharField(max_length=40, default="192.168.3.100")
    dhn_ip        = models.CharField(max_length=40, default="192.168.3.50")
    dhn_interface = models.CharField(max_length=20, default="eno1")
    dhn_ssh_user  = models.CharField(max_length=50, default="dhn")
    broadcast_ip  = models.CharField(max_length=40, default="192.168.3.255")

    # ── Replay / Pegasus ──────────────────────────────────────────────────────
    nrd_file   = models.CharField(max_length=500, blank=True,
                                  help_text="Full path to RawData.nrd (replay mode only)")
    relay_port = models.IntegerField(default=26090)

    # ── DHN-AQ ────────────────────────────────────────────────────────────────
    data_dir            = models.CharField(max_length=500, default="/mnt/dhndev/recordings")
    n_macro             = models.IntegerField(default=256, help_text="Macro channels (1-N)")
    n_micro             = models.IntegerField(default=256, help_text="Micro channels (N+1–total)")
    macro_decimation_hz = models.FloatField(default=2000.0,
                                            help_text="Decimation frequency for macro channels (Hz)")
    micro_decimation_hz = models.FloatField(default=0.0,
                                            help_text="0 = no decimation (full 32 kHz)")
    compression = models.CharField(
        max_length=10, default="PRED",
        choices=[
            ("PRED", "PRED — lossless (recommended)"),
            ("RED",  "RED  — lossless (faster, larger files)"),
            ("MBE",  "MBE  — lossless (fallthrough)"),
            ("VDS",  "VDS  — lossy (maximum compression)"),
        ],
    )

    # ── MATLAB ────────────────────────────────────────────────────────────────
    matlab_enabled  = models.BooleanField(default=False)
    timestamps_file = models.CharField(max_length=500, blank=True,
                                       help_text="Path to timestampsInclude.txt for expStarter")

    # ── Runtime state ─────────────────────────────────────────────────────────
    log_output    = models.TextField(default="")
    error_message = models.TextField(default="")
    packets_sent  = models.IntegerField(default=0)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"{self.name} ({self.get_mode_display()}) — {self.get_status_display()}"

    # ── Computed properties ───────────────────────────────────────────────────
    @property
    def status_color(self) -> str:
        return {
            "idle":      "secondary",
            "starting":  "warning",
            "recording": "success",
            "stopping":  "warning",
            "completed": "info",
            "error":     "danger",
        }.get(self.status, "secondary")

    @property
    def is_active(self) -> bool:
        return self.status in ("starting", "recording", "stopping")

    @property
    def duration_str(self) -> str:
        if self.started_at and self.ended_at:
            d = self.ended_at - self.started_at
            m, s = divmod(int(d.total_seconds()), 60)
            return f"{m}m {s}s"
        if self.started_at and self.is_active:
            d = timezone.now() - self.started_at
            m, s = divmod(int(d.total_seconds()), 60)
            return f"{m}m {s}s (running)"
        return "—"

    @property
    def total_channels(self) -> int:
        return self.n_macro + self.n_micro

    # ── Helpers ───────────────────────────────────────────────────────────────
    def append_log(self, line: str) -> None:
        """Append a timestamped line to log_output and save."""
        ts = timezone.now().strftime("%H:%M:%S")
        self.log_output = self.log_output + f"[{ts}]  {line}\n"
        self.save(update_fields=["log_output"])
