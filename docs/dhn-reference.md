---
layout: default
title: DHN-AQ Reference
nav_order: 6
description: "Complete reference for DHN-AQ RC (run-control) and CS (channel spec) file fields."
---

# DHN-AQ Configuration Reference
{: .no_toc }

Full reference for the two config files DHN-AQ reads at startup: the RC (run-control) text
file and the CS (channel spec) CSV.
{: .fs-5 .fw-300 }

## Table of contents
{: .no_toc .text-delta }

1. TOC
{:toc}

---

## Overview

DHN-AQ reads two plain-text config files at startup — it does not expose a CLI, API, or
config UI (the GUI dialog *is* the interface). This library generates both files programmatically
and uploads them via SSH before launching DHN-AQ.

| File | Class | Purpose |
|------|-------|---------|
| `DHN_Acq_rc.txt` | `RCWriter` | Run-control: data source, network, recording options |
| `DHN_Acq_cs.csv` | `CSWriter` | Channel spec: one row per channel, sample rate, compression |

{: .warning }
> If any field is set to `PROMPT`, DHN-AQ opens a dialog box and waits for user input. This
> **stalls headless operation**. The library replaces all `PROMPT` defaults with real values.

---

## RC file — `DHN_Acq_rc.txt`

### Data source

| Field | Type | Options | Default | Notes |
|-------|------|---------|---------|-------|
| `DataSource` | string | `ATLAS`, `RELAY`, `SIMULATE` | `ATLAS` | Set to `RELAY` for NRD replay |
| `ATLASAddress` | IP | — | `192.168.3.10` | Factory-fixed amplifier IP |
| `ATLASPort` | int | — | `26090` | ATLAS UDP broadcast port |
| `RelayAddress` | IP | — | — | Relay bridge broadcast IP (replay mode) |
| `RelayPort` | int | — | `26090` | Must match relay bridge port |

### Network

| Field | Type | Notes |
|-------|------|-------|
| `LocalIPAddress` | IP | DHN box IP on ATLAS subnet (e.g. `192.168.3.50`) |
| `RecordingInterface` | string | Linux NIC name: `eno1`, `eth1`, etc. |

### Recording

| Field | Type | Options | Notes |
|-------|------|---------|-------|
| `DataOutputDirectory` | path | — | Where MED files are written |
| `SessionName` | string | — | Becomes the MED directory name |
| `EncryptData` | bool | `true`/`false` | Default `false`; requires encryption key |
| `EncryptionPassword` | string | — | Required if `EncryptData = true` |
| `ChannelSpecFile` | path | — | Full path to the CS CSV file |

### Acquisition

| Field | Type | Default | Notes |
|-------|------|---------|-------|
| `SamplingFrequency` | int | `32000` | Must match ATLAS firmware (32 kHz) |
| `NumberOfChannels` | int | — | Total channels (macro + micro) |
| `BitDepth` | int | `24` | ATLAS is always 24-bit |

---

## CS file — `DHN_Acq_cs.csv`

One row per channel. Column order matters.

| Column | Type | Options | Notes |
|--------|------|---------|-------|
| `channel_index` | int | 1-based | Sequential channel number |
| `channel_name` | string | — | e.g. `macro_001`, `micro_257` |
| `electrode_type` | string | `macro`, `micro` | Affects display/filtering |
| `decimation_hz` | float | ≥ 0 | 0 = no decimation (full 32 kHz) |
| `compression` | string | `PRED`, `RED`, `MBE`, `VDS` | Per-channel; usually uniform |
| `enabled` | bool | `true`/`false` | Disabled channels not recorded |

### Compression algorithms

| Algorithm | Type | Typical ratio | When to use |
|-----------|------|--------------|-------------|
| `PRED` | Lossless | ~3× | **Default** — predictive, best for neural signals |
| `RED` | Lossless | ~2× | Faster encoding, larger files |
| `MBE` | Lossless | ~2× | Minimum block entropy fallback |
| `VDS` | **Lossy** | ~10× | Only for storage-critical situations; loses spike shape |

{: .important }
> **Do not use VDS for spike sorting data.** The lossy compression discards high-frequency
> content that distinguishes spike waveforms.

### Example CS file

```csv
channel_index,channel_name,electrode_type,decimation_hz,compression,enabled
1,macro_001,macro,2000.0,PRED,true
2,macro_002,macro,2000.0,PRED,true
...
256,macro_256,macro,2000.0,PRED,true
257,micro_001,micro,0.0,PRED,true
258,micro_002,micro,0.0,PRED,true
...
512,micro_256,micro,0.0,PRED,true
```

Generate it programmatically:

```python
from darkhorse_neuralynx.dhn_client.cs_writer import CSWriter

cs = CSWriter.from_atlas_layout(
    n_macro=256,
    n_micro=256,
    macro_decimation_hz=2000.0,
    micro_decimation_hz=0.0,
    compression="PRED",
)
cs.write("/tmp/DHN_Acq_cs.csv")
```

---

## Generating configs programmatically

### Live ATLAS mode

```python
from darkhorse_neuralynx.dhn_client.rc_writer import RCWriter

rc = RCWriter.for_live_acquisition(
    data_dir="/mnt/dhndev/recordings/session_01",
    local_ip="192.168.3.50",
    interface="eno1",
    atlas_ip="192.168.3.10",
)
print(rc.render())   # preview
rc.write("/tmp/DHN_Acq_rc.txt")
```

### NRD replay mode

```python
rc = RCWriter.for_nrd_relay(
    data_dir="/mnt/dhndev/recordings/session_01",
    local_ip="192.168.3.50",
    relay_ip="192.168.3.255",
    relay_port=26090,
    interface="eno1",
)
```

### Custom fields

```python
rc = RCWriter.for_live_acquisition(...)
rc.set("EncryptData", "true")
rc.set("EncryptionPassword", "my_secret_key_2024")
rc.set("SessionName", "P60CS_Jie_01")
```

---

## Headless launch constraints

DHN-AQ's Initialize dialog asks for:
1. Session name
2. CS file path
3. RC file path

The `DHNLauncher` class uses `xdotool` to fill and submit this dialog. It depends on:
- `xvfb-run` for a virtual framebuffer
- `xdotool` for keystroke injection
- All RC/CS paths uploaded to the DHN box **before** launch
- All RC fields resolved — no `PROMPT` values
