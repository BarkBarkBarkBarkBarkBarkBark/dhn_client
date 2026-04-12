"""Session configuration dataclasses for the orchestrator.

These are the typed, validated config objects that drive a full
acquisition or NRD replay session.  Source of truth: configs/example_session.yaml.
"""

from __future__ import annotations

from enum import Enum
from pathlib import Path
from typing import Optional

from pydantic import BaseModel, Field, field_validator


class SessionMode(str, Enum):
    LIVE     = "live"       # Live ATLAS acquisition → DHN-AQ
    REPLAY   = "replay"     # NRD file replay → relay bridge → DHN-AQ


class NetworkConfig(BaseModel):
    """Network addresses for all nodes."""
    atlas_ip:           str = "192.168.3.10"
    atlas_port:         int = 26090
    pegasus_ip:         str = "192.168.3.100"     # Pegasus PC on hardware subnet
    pegasus_netcom_server: str = "localhost"       # for NetCom TCP (often localhost)
    dhn_ip:             str = "192.168.3.50"
    dhn_ssh_user:       str = "dhn"
    dhn_ssh_key:        Optional[str] = None
    dhn_interface:      str = "eno1"
    broadcast_ip:       str = "192.168.3.255"


class PegasusConfig(BaseModel):
    """Pegasus runtime settings."""
    executable:         str = r"C:\Program Files\Neuralynx\Pegasus\Pegasus.exe"
    config_file:        str = r"nrdReplay\Replay_Atlas_generic.cfg"
    nrd_file:           Optional[str] = None      # required for replay mode
    replay_speed:       str = "slowest"
    auto_start:         bool = True               # send -StartAcquisition via NetCom
    netcom_dll:         str = r"nrdReplay\neuralynxNetcom201\MatlabNetComClient2_x64.dll"


class DHNConfig(BaseModel):
    """DHN-AQ runtime settings."""
    executable:         str = "/opt/DHN/DHN_Acq"
    rc_file:            str = "/home/dhn/DHN_Acq_rc.txt"
    cs_file:            str = "/home/dhn/DHN_Acq_cs.csv"
    data_dir:           str = "/mnt/dhndev/recordings"
    session_name:       str = "session"
    n_channels:         int = 512
    macro_channels:     int = 256
    micro_channels:     int = 256
    macro_decimation_hz: float = 2000.0
    micro_decimation_hz: float = 0.0
    compression:        str = "PRED"
    receive_as_broadcast: bool = True
    subject_id:         Optional[str] = None
    xvfb_display:       int = 99
    sudo_password:      Optional[str] = None


class MATLABConfig(BaseModel):
    """MATLAB script runner settings (optional)."""
    enabled:            bool = False
    matlab_exe:         str = r"C:\Program Files\MATLAB\R2024b\bin\matlab.exe"
    script_path:        str = r"nrdReplay\NetCom_expStarter_ATLAS_AC.m"
    addpath:            list[str] = Field(
        default_factory=lambda: [r"nrdReplay\neuralynxNetcom201"]
    )
    variables:          dict[str, str] = Field(default_factory=dict)


class SessionConfig(BaseModel):
    """Top-level session configuration."""
    mode:               SessionMode = SessionMode.REPLAY
    session_name:       str = "unnamed_session"
    description:        str = ""

    network:            NetworkConfig   = Field(default_factory=NetworkConfig)
    pegasus:            PegasusConfig   = Field(default_factory=PegasusConfig)
    dhn:                DHNConfig       = Field(default_factory=DHNConfig)
    matlab:             MATLABConfig    = Field(default_factory=MATLABConfig)

    # Relay bridge (replay mode only)
    relay_port:         int  = 26090
    relay_poll_ms:      float = 20.0

    @field_validator("dhn", mode="before")
    @classmethod
    def _sync_session_name(cls, v: object, info: object) -> object:
        return v

    @classmethod
    def from_yaml(cls, path: str | Path) -> "SessionConfig":
        """Load a session config from a YAML file."""
        try:
            import yaml  # type: ignore
        except ImportError:
            raise ImportError("PyYAML required: pip install pyyaml")
        with open(path) as f:
            data = yaml.safe_load(f)
        return cls.model_validate(data)

    def to_yaml(self, path: str | Path) -> None:
        """Save config to YAML."""
        try:
            import yaml  # type: ignore
        except ImportError:
            raise ImportError("PyYAML required: pip install pyyaml")
        with open(path, "w") as f:
            yaml.dump(self.model_dump(), f, default_flow_style=False)
