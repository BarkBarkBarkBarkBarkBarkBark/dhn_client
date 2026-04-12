"""SessionForm — model form for creating / editing AcquisitionSession."""

from django import forms
from .models import AcquisitionSession


class SessionForm(forms.ModelForm):
    """
    A beginner-friendly form with grouped fields and helpful explanations.
    The template renders fields in accordion sections (Basic / Network / DHN / Advanced).
    """

    class Meta:
        model  = AcquisitionSession
        fields = [
            # Basic
            "name", "description", "mode",
            # Network
            "atlas_ip", "pegasus_ip", "dhn_ip",
            "dhn_interface", "dhn_ssh_user", "broadcast_ip",
            # Replay
            "nrd_file", "relay_port",
            # DHN-AQ
            "data_dir", "n_macro", "n_micro",
            "macro_decimation_hz", "micro_decimation_hz", "compression",
            # MATLAB
            "matlab_enabled", "timestamps_file",
        ]
        widgets = {
            "name": forms.TextInput(attrs={
                "class": "form-control",
                "placeholder": "e.g. P60CS_Jie_replay_01",
            }),
            "description": forms.Textarea(attrs={
                "class": "form-control", "rows": 2,
                "placeholder": "Optional — session notes",
            }),
            "mode": forms.RadioSelect(attrs={"class": "form-check-input"}),
            "atlas_ip":      forms.TextInput(attrs={"class": "form-control"}),
            "pegasus_ip":    forms.TextInput(attrs={"class": "form-control"}),
            "dhn_ip":        forms.TextInput(attrs={"class": "form-control"}),
            "dhn_interface": forms.TextInput(attrs={"class": "form-control"}),
            "dhn_ssh_user":  forms.TextInput(attrs={"class": "form-control"}),
            "broadcast_ip":  forms.TextInput(attrs={"class": "form-control"}),
            "nrd_file": forms.TextInput(attrs={
                "class": "form-control",
                "placeholder": "C:\\Pegasus\\Data\\Session01\\RawData.nrd",
            }),
            "relay_port": forms.NumberInput(attrs={"class": "form-control"}),
            "data_dir": forms.TextInput(attrs={
                "class": "form-control",
                "placeholder": "/mnt/dhndev/recordings/P60CS_Jie",
            }),
            "n_macro":             forms.NumberInput(attrs={"class": "form-control"}),
            "n_micro":             forms.NumberInput(attrs={"class": "form-control"}),
            "macro_decimation_hz": forms.NumberInput(attrs={
                "class": "form-control", "step": "0.1",
            }),
            "micro_decimation_hz": forms.NumberInput(attrs={
                "class": "form-control", "step": "0.1",
            }),
            "compression": forms.Select(attrs={"class": "form-select"}),
            "matlab_enabled": forms.CheckboxInput(attrs={"class": "form-check-input"}),
            "timestamps_file": forms.TextInput(attrs={
                "class": "form-control",
                "placeholder": "C:\\Pegasus\\timestampsInclude.txt",
            }),
        }
        labels = {
            "name":               "Session name",
            "description":        "Notes",
            "mode":               "Acquisition mode",
            "atlas_ip":           "ATLAS amplifier IP",
            "pegasus_ip":         "Pegasus PC IP",
            "dhn_ip":             "DHN-AQ Linux box IP",
            "dhn_interface":      "DHN network interface",
            "dhn_ssh_user":       "DHN SSH username",
            "broadcast_ip":       "UDP broadcast IP",
            "nrd_file":           "NRD file path (on Pegasus)",
            "relay_port":         "Relay UDP port",
            "data_dir":           "DHN recording directory",
            "n_macro":            "Macro electrode channels",
            "n_micro":            "Micro electrode channels",
            "macro_decimation_hz":"Macro decimation (Hz)",
            "micro_decimation_hz":"Micro decimation (Hz, 0 = full 32 kHz)",
            "compression":        "MED compression algorithm",
            "matlab_enabled":     "Launch MATLAB expStarter script",
            "timestamps_file":    "Timestamps file (for expStarter)",
        }
        help_texts = {
            "atlas_ip":           "Factory-fixed firmware IP — do not change.",
            "pegasus_ip":         "Static IP on dedicated 192.168.3.0/24 NIC.",
            "dhn_ip":             "Assign a static IP on the same /24 subnet.",
            "dhn_interface":      "Linux NIC name that faces the ATLAS subnet (ip link show).",
            "broadcast_ip":       "Usually the /24 broadcast: last octet = 255.",
            "nrd_file":           "Windows path as seen by Pegasus (replay mode only).",
            "relay_port":         "ATLAS UDP broadcast port — must be 26090 for DHN-AQ.",
            "macro_decimation_hz":"Recommended: 2000 Hz for LFP. Must divide evenly into 32 000.",
            "micro_decimation_hz":"Set to 0 to keep full 32 kHz (spike sorting).",
            "compression":        "PRED is recommended — lossless and ~3× smaller than raw.",
        }
