# darkhorse_neuralynx

**A Python orchestration layer for recording Neuralynx ATLAS/Pegasus data directly into [MED format](https://github.com/MEDFormat/MED) via [DHN-AQ](https://darkhorseneuro.com) — including programmatic NRD file replay without a monitor.**

---

## What This Repo Does

Neuralynx's **Pegasus** software runs on a Windows PC and acquires from the **ATLAS amplifier** over a dedicated private subnet (`192.168.3.x`).  
**DHN-AQ** (Dark Horse Neuro Acquisition) runs on a Linux box, receives the same raw ATLAS broadcast independently of Pegasus, and writes it into the compressed, encryptable **MED format**.

This repo provides:

| Component | What it does |
|-----------|-------------|
| **Orchestrator** (`src/orchestrator/`) | Single entry point — wires together DHN-AQ + Pegasus for live acquisition or NRD replay; can invoke MATLAB scripts natively |
| **DHN Client** (`src/dhn_client/`) | Headless launch of DHN-AQ on the Linux box via SSH + virtual display; programmatic RC/CS config file generation |
| **Pegasus Bridge** (`src/pegasus_bridge/`) | Windows-side: NetCom `ctypes` wrapper for `MatlabNetComClient2_x64.dll`; NRD file UDP relay for replay |
| **Diagnostics** (`src/dhn_client/diagnose.py`) | Pre-flight checks — network reachability, subnet membership, DHN-AQ process state |
| **Config Templates** (`configs/`) | Ready-to-use RC and CS files; machine-parseable session YAML |
| **API Reference** (`docs/dhn_api_reference.yaml`) | Every RC and CS field from the DHN manual, structured for programmatic use |

---

## The Network Picture

There are **three distinct network layers** — confusing them is the source of almost every setup problem:

```
┌──────────────────────────────────────────────────────────────────────┐
│  LAYER 1 – ATLAS ↔ Pegasus hardware link  (192.168.3.0/24 private)  │
│                                                                      │
│   ATLAS Amplifier                   Pegasus Windows PC              │
│   192.168.3.10  :26011  ──────────►  192.168.3.100 :26090           │
│                                                                      │
│  This subnet is factory-fixed.  Do not touch during normal use.      │
│  ATLAS IP is burned into hardware firmware.                          │
│  Pegasus PC has a STATIC IP on this NIC (dedicated 2nd NIC).         │
│  During NRD REPLAY the ATLAS box is absent — no packets on this link.│
└──────────────────────────────────────────────────────────────────────┘

┌──────────────────────────────────────────────────────────────────────┐
│  LAYER 2 – DHN-AQ reception  (same 192.168.3.0/24 OR relay subnet)  │
│                                                                      │
│  DHN-AQ receives the SAME raw UDP broadcast that Pegasus receives.   │
│  It is NOT a NetCom TCP client.  Both Pegasus and DHN listen to ATLAS│
│  simultaneously.                                                     │
│                                                                      │
│  ► Live acquisition:                                                  │
│      DHN Linux box NIC must be on 192.168.3.0/24                    │
│      RC:  Receiving Server IP = 192.168.3.10  (ATLAS)               │
│           Receiving Port      = 26090          (ATLAS, hard-coded)  │
│           Receive As Broadcast = YES  (MAC address not required)    │
│                                                                      │
│  ► NRD replay  (ATLAS absent):                                       │
│      Run nrd_relay.py on the Pegasus PC (or any Windows box).        │
│      It reads NRD packets and re-broadcasts them as if ATLAS were    │
│      transmitting.  Point DHN RC at the relay server IP/port.        │
└──────────────────────────────────────────────────────────────────────┘

┌──────────────────────────────────────────────────────────────────────┐
│  LAYER 3 – NetCom  (lab LAN, any subnet)                             │
│                                                                      │
│  Pegasus runs a NetCom TCP server.  MATLAB and Python can connect    │
│  from any machine on the lab LAN.  Used by the orchestrator to:      │
│    • send -StartRecording / -StopRecording commands                  │
│    • stream CSC data to the NRD relay bridge during replay           │
│                                                                      │
│  MATLAB:   NlxConnectToServer('192.168.x.x')                         │
│  Python:   pegasus_bridge.netcom.NetComClient('192.168.x.x')         │
└──────────────────────────────────────────────────────────────────────┘
```

### Why the IP Is "Always" That Address

The `192.168.3.10` and `192.168.3.100` addresses you see in `.cfg` files are:

- `192.168.3.10` — The **ATLAS amplifier's factory IP** (burned in firmware; requires Neuralynx support to change).  
- `192.168.3.100` — The **Pegasus PC's static IP** on its dedicated second NIC.  These are not DHCP addresses. You assign this IP once during initial lab setup.

These are **hardware transport addresses only** — they are irrelevant to NetCom client connections or DHN-AQ on the lab LAN.

---

## Why DHN-AQ Stalls at Connection

If DHN-AQ stalls at the connection step, work through this checklist:

| # | Check | Fix |
|---|-------|-----|
| 1 | **Wrong mode**: running NRD replay but DHN pointed at `192.168.3.10` | Start `nrd_relay.py` and point RC at relay IP |
| 2 | **DHN Linux NIC not on `192.168.3.0/24`** | `sudo ip addr add 192.168.3.50/24 dev eno1` |
| 3 | **Wrong interface name** in RC (`eno1` ≠ your NIC name) | Run `ip link show`; update `Receiving Local EN Interface Name` |
| 4 | **Pegasus not in ACQ state** | Pegasus must show green ACQ before DHN can receive |
| 5 | **Windows Firewall blocking port 26090** | Add inbound UDP rule for port 26090 |
| 6 | **`Receive As Broadcast: NO` + wrong MAC** | Set `YES` for broadcast mode (no MAC needed) |
| 7 | **RC has `PROMPT` values** | Replace all `PROMPT` with real values for headless use |

---

## Minimum Steps: NRD Replay → DHN-AQ Archive

### Prerequisites

**Windows PC (Pegasus)**
- Pegasus v2.3.1 installed (installer in `nrdReplay/`)
- Python 3.10+ with this package installed (`pip install -e .`)
- `nrdReplay/neuralynxNetcom201/MatlabNetComClient2_x64.dll` accessible

**Linux Box (DHN-AQ)**
- DHN-AQ installed and licensed
- Python 3.10+ (for orchestrator SSH commands)
- NIC configured on `192.168.3.0/24` (or relay subnet)
- `xvfb`, `xdotool` installed: `sudo apt install xvfb xdotool`

---

### Step 1 — Prepare the replay config

Edit `nrdReplay/Replay_Atlas_generic.cfg`:
```
-SetDataDirectory "C:\dataReplay\MySession"
-CreateHardwareSubSystem "AcqSystem1" RawDataFile "C:\path\to\RawData.nrd"
-SetDmaBuffers "AcqSystem1" 64 40
-SetContinuousRawDataFilePlayback "AcqSystem1" Off
```
Remove all hardware-only lines between `-SetNetComDataBufferSize Events 3000` and the first `-CreateCscAcqEnt`.

### Step 2 — Generate DHN config files

```python
from darkhorse_neuralynx.dhn_client.rc_writer import RCWriter
from darkhorse_neuralynx.dhn_client.cs_writer import CSWriter

rc = RCWriter.from_template("configs/base_rc.yaml")
rc.set("Primary Data Directory", "/mnt/dhndev/recordings")
rc.set("Receiving Server IP Address", "192.168.3.10")   # or relay IP for replay
rc.set("Receiving Local IP Address", "192.168.3.50")    # DHN box IP
rc.set("Receive As Broadcast", "YES")
rc.write("/home/dhn/DHN_Acq_rc.txt")

cs = CSWriter.from_channel_count(512, sample_freq=32000, decimation_freq=2000)
cs.write("/home/dhn/DHN_Acq_cs.csv")
```

### Step 3 — Start the relay bridge (NRD replay only)

On the Windows Pegasus PC:
```python
from darkhorse_neuralynx.pegasus_bridge.nrd_stream import NRDRelayBridge

bridge = NRDRelayBridge(
    nrd_path=r"C:\path\to\RawData.nrd",
    broadcast_ip="192.168.3.255",
    broadcast_port=26090,
)
bridge.start()   # non-blocking; broadcasts ATLAS-format UDP packets
```

### Step 4 — Launch DHN-AQ headlessly

From the orchestrator (macOS/Linux with SSH access to the DHN box):
```python
from darkhorse_neuralynx.dhn_client.launcher import DHNLauncher

launcher = DHNLauncher(
    host="192.168.3.50",       # DHN Linux box IP
    ssh_user="dhn",
    dhn_executable="/opt/DHN/DHN_Acq",
    session_name="MySession_2026-04-12",
    rc_path="/home/dhn/DHN_Acq_rc.txt",
    cs_path="/home/dhn/DHN_Acq_cs.csv",
)
launcher.launch()           # deploys RC/CS, starts DHN-AQ under xvfb, auto-fills dialog
launcher.wait_for_ready()   # blocks until DHN is recording
```

### Step 5 — Run Pegasus replay + MATLAB timing script

```python
from darkhorse_neuralynx.orchestrator.run import SessionOrchestrator

session = SessionOrchestrator.from_yaml("configs/my_session.yaml")
session.run()
# Internally: start Pegasus replay → run MATLAB expStarter → wait → stop
```

Or run the MATLAB script directly:
```python
from darkhorse_neuralynx.orchestrator.matlab import MATLABRunner
runner = MATLABRunner(matlab_exe=r"C:\Program Files\MATLAB\R2024b\bin\matlab.exe")
runner.run_script(r"nrdReplay\NetCom_expStarter_ATLAS_AC.m")
```

### Step 6 — Stop and verify

```python
session.stop()          # sends -StopRecording to Pegasus, shuts relay bridge
launcher.terminate()    # graceful DHN-AQ shutdown
```

---

## Repo Structure

```
darkhorse_neuralynx/
├── README.md
├── pyproject.toml
├── .context/
│   └── repo.yaml                   # machine-readable architecture context
├── docs/
│   ├── dhn_api_reference.yaml      # full RC/CS field reference from DHN manual
│   └── network_topology.md         # detailed IP/port diagram + troubleshooting
├── configs/
│   ├── base_rc.yaml                # base RC template (Python-friendly)
│   ├── example_session.yaml        # example session config
│   └── example_cs.csv              # example CS file (512 ch, 2 kHz decimated)
├── nrdReplay/                      # Neuralynx-provided files (MATLAB + configs)
│   ├── nrd_replay.txt
│   ├── Replay_Atlas_generic.cfg
│   ├── 512csc_modified.cfg
│   ├── NetCom_expStarter_ATLAS_AC.m
│   └── neuralynxNetcom201/         # Neuralynx NetCom MATLAB DLL wrappers
└── src/
    └── darkhorse_neuralynx/
        ├── orchestrator/
        │   ├── run.py              # SessionOrchestrator — main entry point
        │   ├── config.py           # Pydantic session config dataclasses
        │   └── matlab.py           # MATLAB subprocess runner
        ├── pegasus_bridge/
        │   ├── netcom.py           # ctypes wrapper for MatlabNetComClient2_x64.dll
        │   └── nrd_stream.py       # NRD file UDP relay broadcaster (replay → DHN)
        └── dhn_client/
            ├── launcher.py         # Headless DHN-AQ launch via SSH + xvfb + xdotool
            ├── rc_writer.py        # Generate DHN RC files from Python
            ├── cs_writer.py        # Generate DHN CS CSV files from Python
            └── diagnose.py         # Pre-flight network + process diagnostics
```

---

## Installation

```bash
pip install -e ".[dev]"
```

Requirements:
- `paramiko` — SSH to DHN Linux box
- `pydantic` — session config validation
- `pdfplumber` — PDF ingestion (dev/docs only)

On the DHN Linux box:
```bash
sudo apt install xvfb xdotool
```

---

## MATLAB Interop

The orchestrator can natively invoke MATLAB scripts on the Windows Pegasus PC:

```python
from darkhorse_neuralynx.orchestrator.matlab import MATLABRunner

runner = MATLABRunner(
    matlab_exe=r"C:\Program Files\MATLAB\R2024b\bin\matlab.exe",
    addpath=[r"nrdReplay\neuralynxNetcom201"],
)
runner.run_script(
    r"nrdReplay\NetCom_expStarter_ATLAS_AC.m",
    variables={"fname": r"C:\timestamps.txt", "serverName": "localhost"},
)
```

This invokes MATLAB as a subprocess (`matlab -batch "..."`), injects variable overrides, and streams stdout/stderr back to the Python orchestrator in real time.

---

## Contributing

This repo is purpose-built for the UC Davis ATLAS/Pegasus + DHN-AQ pipeline.  
Pull requests welcome for:
- Additional hardware targets (Digital Lynx, OpenEphys)
- MED file post-processing utilities
- Cloud archive integration

---

*Built with respect for the scientists spending their nights debugging lab networks so that patients and animals can benefit from better brain recordings.*
