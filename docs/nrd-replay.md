---
layout: default
title: NRD File Replay
nav_order: 4
description: "Step-by-step guide to replaying an NRD file from Pegasus and recording with DHN-AQ."
---

# NRD File Replay
{: .no_toc }

Replay a `.nrd` file from Pegasus while recording with DHN-AQ — no ATLAS hardware needed.
{: .fs-5 .fw-300 }

## Table of contents
{: .no_toc .text-delta }

1. TOC
{:toc}

---

## How it works

```
Pegasus ─NetCom─► Python NRDRelayBridge ─UDP─► DHN-AQ
  (reads NRD file)   (re-broadcasts as          (records to MED)
                      ATLAS-format packets)
```

The relay bridge is the key insight: DHN-AQ has no idea it's receiving replayed data. It sees
the same UDP packet format as live ATLAS — only the source IP differs (relay bridge vs real
amplifier).

---

## Step 1 — Configure Pegasus for replay

On the Pegasus PC, open the NRD replay config template:

```
nrdReplay/Replay_Atlas_generic.cfg
```

Set `RawDataFile` to the full path of your `.nrd` file, then start the replay in Pegasus:
**File → Open Replay…**

Or use the `NetCom_expStarter_ATLAS_AC.m` script which drives the replay automatically.

{: .note }
> The NRD file must have been recorded with ATLAS (not Cheetah). The data rate and channel
> layout must match what you configure in DHN-AQ's CS file.

---

## Step 2 — Create a replay session (web app)

1. Open [http://localhost:8000](http://localhost:8000)
2. Click **New Session**
3. Select **NRD File Replay**
4. Fill in the form:

| Field | Value |
|-------|-------|
| NRD file path | Full Windows path, e.g. `C:\Pegasus\Data\Session01\RawData.nrd` |
| Replay port | `26090` (do not change) |
| Broadcast IP | `192.168.3.255` (subnet broadcast) |
| Macro channels | Match the recording (usually 256) |
| Micro channels | Match the recording (usually 256) |
| Macro decimation | `2000` Hz for LFP storage |
| Micro decimation | `0` for full 32 kHz spike sorting |
| Compression | `PRED` (lossless, recommended) |

5. Click **Save Session**, then press **▶ Start**

---

## Step 3 — What happens when you press Start

The orchestrator runs these steps in sequence:

```
1. Generate DHN_Acq_rc.txt  ← RCWriter.for_nrd_relay()
   Generate DHN_Acq_cs.csv  ← CSWriter.from_atlas_layout()

2. Upload both files to DHN box via SSH (paramiko)

3. Launch DHN-AQ headless:
   ssh dhn@192.168.3.50
   xvfb-run -a /opt/DHN/DHN_Acq &
   xdotool  (fill Initialize dialog fields + click OK)

4. Start NRDRelayBridge:
   Loop: GetNewCSCData() → pack → UDP broadcast → 192.168.3.255:26090

5. Wait for Stop signal

6. Stop relay bridge
   Terminate DHN-AQ
```

---

## Step 4 — Monitor the session

On the session detail page you can see:
- **Status badge** — Starting → Recording → Completed
- **Live log** — timestamped messages from each step (auto-scrolling)
- **Packets sent** — relay bridge packet counter (updates every 2 s)
- **RC file preview** — exact content of the config uploaded to DHN box

---

## Step 5 — Stop and verify

Click **■ Stop** when the replay is done. The orchestrator will:
1. Signal the relay bridge thread to stop
2. Call `xdotool` to close DHN-AQ cleanly
3. Mark the session as **Completed**

DHN-AQ writes MED format files to the configured `data_dir` on the Linux box.
Verify with:

```bash
ssh dhn@192.168.3.50
ls /mnt/dhndev/recordings/<session_name>/
# → Subject_001.medd/  (MED directory)
```

---

## CLI usage

```bash
dhn-orchestrate --config configs/example_session.yaml
```

Or build the config in Python:

```python
from darkhorse_neuralynx.orchestrator.config import SessionConfig, SessionMode

cfg = SessionConfig(
    session_name="P60CS_Jie_replay",
    mode=SessionMode.REPLAY,
    network=NetworkConfig(
        atlas_ip="192.168.3.10",
        pegasus_ip="192.168.3.100",
        dhn_ip="192.168.3.50",
    ),
    pegasus=PegasusConfig(
        nrd_file=r"C:\Pegasus\Data\P60CS_Jie\RawData.nrd",
    ),
    dhn=DHNConfig(
        data_dir="/mnt/dhndev/recordings/P60CS_Jie",
        n_macro=256,
        n_micro=256,
    ),
)

from darkhorse_neuralynx.orchestrator.run import SessionOrchestrator
SessionOrchestrator(cfg).run()
```

---

## Troubleshooting replay

### DHN-AQ stalls at "Waiting for data source…"

The relay bridge started **after** DHN-AQ. Start order matters:
1. Launch DHN-AQ first (`launcher.launch()`)
2. Wait for ready (`launcher.wait_for_ready()`)
3. *Then* start the relay bridge

The orchestrator does this automatically, but if you're running manually, order matters.

### Relay bridge shows 0 packets sent

Check that Pegasus has the NRD file loaded and replay is running. The relay bridge polls
`GetNewCSCData()` — if Pegasus isn't streaming, there's nothing to relay.

### DHN-AQ Initialize dialog doesn't close

`xdotool` needs a window to exist before it can interact. Try increasing the
`wait_for_dialog` timeout in `DHNLauncher`. Also ensure `xvfb` started successfully
(`ps aux | grep Xvfb`).

### Data directory not found on DHN box

Create it before starting:
```bash
ssh dhn@192.168.3.50 mkdir -p /mnt/dhndev/recordings/my_session
```
