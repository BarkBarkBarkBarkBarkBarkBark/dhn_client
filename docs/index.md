---
layout: home
title: Home
nav_order: 1
description: "Python orchestration pipeline — replay Neuralynx NRD files and acquire with DHN-AQ, all from one repo."
permalink: /
---

# 🧠 darkhorse_neuralynx
{: .fs-9 }

One Python repo that bridges **Neuralynx Pegasus** → **DHN-AQ** for both live ATLAS acquisition and offline NRD file replay.
{: .fs-5 .fw-300 }

[Get started now]({{ site.baseurl }}/getting-started){: .btn .btn-primary .fs-5 .mb-4 .mb-md-0 .mr-2 }
[View on GitHub](https://github.com/BarkBarkBarkBarkBarkBarkBark/dhn_client){: .btn .fs-5 .mb-4 .mb-md-0 }

---

## What this project does

Neuralynx's ATLAS amplifier broadcasts raw 24-bit neural data as **UDP packets** on a dedicated
192.168.3.0/24 hardware subnet. DHN-AQ, the Dark Horse Neuro acquisition app, listens for exactly
those packets. When you replay an `.nrd` file from Pegasus, **no hardware is present → no UDP →
DHN-AQ stalls**.

This project fixes that, and goes further:

| Feature | Description |
|---------|-------------|
| 🔄 **NRD Relay Bridge** | Polls Pegasus via NetCom TCP, re-broadcasts as ATLAS-format UDP so DHN-AQ receives replay data as if hardware were live |
| 📡 **Live ATLAS Support** | Generates correct RC file pointing at 192.168.3.10 — no relay needed, DHN-AQ connects directly |
| 🖥️ **Headless DHN-AQ** | Launches DHN-AQ without a monitor via `xvfb-run` + `xdotool` (SSH from any machine) |
| 🌐 **Django Web UI** | Point-and-click pipeline control — create sessions, watch live logs, run diagnostics |
| 🔬 **Pre-flight Checks** | 8-point network diagnostic catches misconfigurations before you start recording |
| 🎯 **MATLAB interop** | Calls native `NetCom_expStarter_ATLAS_AC.m` as a subprocess — no MATLAB Engine API needed |

---

## Architecture at a glance

```
   192.168.3.0 / 24  ←── dedicated NIC on each machine ──→
   ┌─────────────────────────────────────────────────────────┐
   │                                                         │
   │  ATLAS Amplifier          Pegasus PC         DHN-AQ     │
   │  192.168.3.10             192.168.3.100       .50        │
   │  (factory IP)             (Windows)          (Ubuntu)   │
   │                                                         │
   │  ──UDP broadcast──►  ──────────────────────►           │
   │                       (live mode: direct)              │
   │                                                         │
   │                       NetCom TCP  ──►  Relay Bridge    │
   │                       (replay)         └─► UDP →  DHN  │
   └─────────────────────────────────────────────────────────┘
```

---

## Quick start

```bash
# 1. Clone
git clone https://github.com/BarkBarkBarkBarkBarkBarkBark/dhn_client
cd darkhorse_neuralynx

# 2. Install library
pip install -e .

# 3. Launch the web app
cd webapp
pip install -r requirements.txt
python manage.py migrate
python manage.py runserver
# → open http://localhost:8000
```

---

## What's in the repo

```
darkhorse_neuralynx/
├── src/darkhorse_neuralynx/   Python library
│   ├── dhn_client/            RC/CS file generation, headless launcher, diagnostics
│   ├── pegasus_bridge/        NetCom ctypes wrapper, NRD relay bridge
│   └── orchestrator/          SessionOrchestrator, YAML config, MATLAB runner
├── webapp/                    Django web application
│   ├── pipeline/              Main Django app
│   └── templates/ static/     UI templates and CSS/JS
├── docs/                      This GitHub Pages site
├── configs/                   Example session YAML + CS files
└── nrdReplay/                 Original lab MATLAB scripts + Neuralynx NetCom DLLs
```
