---
layout: default
title: Live ATLAS Acquisition
nav_order: 5
description: "Use darkhorse_neuralynx with real ATLAS hardware — no relay bridge needed."
---

# Live ATLAS Acquisition
{: .no_toc }

When ATLAS hardware is physically connected, DHN-AQ receives UDP packets directly — no relay
bridge needed.
{: .fs-5 .fw-300 }

## Table of contents
{: .no_toc .text-delta }

1. TOC
{:toc}

---

## Is this compatible with real ATLAS hardware?

**Yes — fully compatible.** Live ATLAS mode is the primary, simpler case. The relay bridge
is only needed for offline NRD replay when no hardware is present.

In live mode the data flow is:

```
ATLAS Amplifier (192.168.3.10)
    │
    │  UDP broadcast → 192.168.3.255:26090
    │
    ├──► Pegasus (192.168.3.100)  — records .nrd file
    │
    └──► DHN-AQ (192.168.3.50)   — records MED files
```

Both Pegasus and DHN-AQ receive the **same raw UDP stream simultaneously** directly from the
amplifier. No software relay is involved.

---

## What changes in live mode

When you set `mode: live` in a session config (or select **Live ATLAS** in the web form),
the orchestrator:

1. Calls `RCWriter.for_live_acquisition()` instead of `for_nrd_relay()`
   — this sets `DataSource = ATLAS` and points at `192.168.3.10` in the RC file
2. **Skips the relay bridge entirely** — `NRDRelayBridge` is not started
3. DHN-AQ connects to the ATLAS UDP stream on its own

Everything else (headless launch, SSH config upload, log streaming) is identical.

---

## Setting up a live session

### Via the web app

1. Click **New Session**
2. Select **📡 Live ATLAS Acquisition**
3. The **NRD file / relay settings** section disappears — you don't need it
4. Fill in network IPs (defaults are correct for standard lab topology)
5. Configure channels and compression
6. Press **▶ Start**

### Via config YAML

```yaml
# configs/my_live_session.yaml
session_name: P60CS_live_01
mode: live

network:
  atlas_ip:      "192.168.3.10"
  pegasus_ip:    "192.168.3.100"
  dhn_ip:        "192.168.3.50"
  dhn_interface: "eno1"
  dhn_ssh_user:  "dhn"

dhn:
  data_dir:             "/mnt/dhndev/recordings/P60CS_live_01"
  n_macro:              256
  n_micro:              256
  macro_decimation_hz:  2000.0
  micro_decimation_hz:  0.0
  compression:          "PRED"
```

```bash
dhn-orchestrate --config configs/my_live_session.yaml
```

---

## Verifying the ATLAS connection

Before starting a session, run diagnostics:

```bash
dhn-diagnose
```

Key checks for live mode:

| Check | What to look for |
|-------|-----------------|
| ATLAS ping | 192.168.3.10 responds (amplifier is on and connected) |
| DHN subnet | DHN box has a 192.168.3.x address on the right NIC |
| DHN SSH | SSH login works (needed to upload RC/CS and launch DHN-AQ) |

---

## RC file generated for live mode

Here's what `RCWriter.for_live_acquisition()` produces (key fields):

```ini
DataSource = ATLAS
ATLASAddress = 192.168.3.10
ATLASPort = 26090
RecordingInterface = eno1
LocalIPAddress = 192.168.3.50
DataOutputDirectory = /mnt/dhndev/recordings/P60CS_live_01
```

The `DataSource = ATLAS` line tells DHN-AQ to listen for real ATLAS UDP, not a relay.

---

## Differences between live and replay mode

| Aspect | Live ATLAS | NRD Replay |
|--------|-----------|-----------|
| Hardware required | ✅ Yes | ❌ No |
| Relay bridge | ❌ Not started | ✅ Required |
| RC `DataSource` | `ATLAS` | `RELAY` (or equivalent) |
| Pegasus running | Optional (can record independently) | ✅ Required (provides data via NetCom) |
| Data fidelity | 100% original | Best-effort (packet reconstruction) |
| Timing | Real-time hardware clock | Determined by Pegasus replay speed |

---

## Using MATLAB expStarter with live acquisition

The `NetCom_expStarter_ATLAS_AC.m` script sends timing/trigger commands to Pegasus during
live recording. Enable it in the session config:

```yaml
matlab:
  enabled:         true
  script_path:     "nrdReplay/NetCom_expStarter_ATLAS_AC.m"
  timestamps_file: "C:\\Pegasus\\timestampsInclude.txt"
```

The orchestrator launches MATLAB after DHN-AQ is confirmed recording:

```python
# Equivalent Python
from darkhorse_neuralynx.orchestrator.matlab import MATLABRunner

runner = MATLABRunner(matlab_path="matlab")
runner.run_script_async(
    script_path="nrdReplay/NetCom_expStarter_ATLAS_AC.m",
    variables={"TIMESTAMPS_FILE": r"C:\Pegasus\timestampsInclude.txt"},
)
```
