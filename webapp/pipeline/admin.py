from django.contrib.admin import ModelAdmin, register
from .models import AcquisitionSession


@register(AcquisitionSession)
class AcquisitionSessionAdmin(ModelAdmin):
    list_display  = ("name", "mode", "status", "total_channels", "created_at", "duration_str")
    list_filter   = ("mode", "status")
    search_fields = ("name", "description")
    readonly_fields = ("created_at", "started_at", "ended_at", "packets_sent", "log_output")
    fieldsets = (
        ("Identity",      {"fields": ("name", "description", "mode", "status")}),
        ("Network",       {"fields": ("atlas_ip", "pegasus_ip", "dhn_ip",
                                      "dhn_interface", "dhn_ssh_user", "broadcast_ip")}),
        ("Pegasus/Replay",{"fields": ("nrd_file", "relay_port")}),
        ("DHN-AQ",        {"fields": ("data_dir", "n_macro", "n_micro",
                                      "macro_decimation_hz", "micro_decimation_hz", "compression")}),
        ("MATLAB",        {"fields": ("matlab_enabled", "timestamps_file")}),
        ("Runtime",       {"fields": ("created_at", "started_at", "ended_at",
                                      "packets_sent", "log_output", "error_message"),
                           "classes": ("collapse",)}),
    )
