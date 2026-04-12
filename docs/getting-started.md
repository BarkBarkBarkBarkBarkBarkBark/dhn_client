---
layout: default
title: Getting Started
nav_order: 2
description: "Install darkhorse_neuralynx and run your first session in under 10 minutes."
---

# Getting Started
{: .no_toc }

Install the library, launch the Django web app, and run your first replay session.
{: .fs-5 .fw-300 }

## Table of contents
{: .no_toc .text-delta }

1. TOC
{:toc}

---

## Prerequisites

| Requirement | Details |
|------------|---------|
| **Python 3.10+** | On the machine running this software (macOS, Linux, or Windows) |
| **Pegasus PC** | Windows PC running Neuralynx Pegasus 2.3.1+ with NetCom enabled |
| **DHN-AQ Linux box** | Ubuntu 20.04+ with DHN-AQ installed, SSH enabled, `xvfb` and `xdotool` installed |
| **192.168.3.0/24 subnet** | Dedicated NIC on Pegasus + dedicated NIC on DHN box |
| **Neuralynx NetCom DLL** | `MatlabNetComClient2_x64.dll` (already in `nrdReplay/neuralynxNetcom201/`) |

{: .note }
> The Django web app and Python orchestrator can run on **any** machine — your laptop, a lab
> server, or the DHN box itself. Only the NetCom relay bridge requires Windows (it loads the
> `.dll`). For live ATLAS mode, no relay is needed at all.

---

## Step 1 — Clone the repository

```bash
git clone https://github.com/BarkBarkBarkBarkBarkBarkBark/dhn_client
cd dhn_client
```

---

## Step 2 — Install the Python library

```bash
# Create a virtual environment (recommended)
python -m venv .venv
source .venv/bin/activate      # Windows: .venv\Scripts\activate

# Install in editable mode — also registers CLI commands
pip install -e .
```

This gives you two CLI commands:

| Command | Purpose |
|---------|---------|
| `dhn-orchestrate --config session.yaml` | Run a full session from the command line |
| `dhn-diagnose` | Run pre-flight network checks |

---

## Step 3 — Install the DHN-AQ prerequisites on the Linux box

SSH into the DHN-AQ Ubuntu machine and run:

```bash
sudo apt update
sudo apt install -y xvfb xdotool openssh-server
```

Verify:

```bash
which xvfb-run   # → /usr/bin/xvfb-run
which xdotool    # → /usr/bin/xdotool
```

---

## Step 4 — Assign a static IP to the DHN box NIC

The DHN-AQ app listens for UDP on whatever NIC faces the ATLAS subnet. Assign a static IP on
the 192.168.3.0/24 network:

```bash
# Example using nmcli (adjust interface name as needed)
sudo nmcli con mod "Wired connection 1" \
  ipv4.method manual \
  ipv4.addresses 192.168.3.50/24 \
  ipv4.gateway ""
sudo nmcli con up "Wired connection 1"
```

Check with `ip addr show eno1` — you should see `192.168.3.50`.

---

## Step 5 — Launch the web app

```bash
cd webapp
pip install -r requirements.txt

# Create the SQLite database
python manage.py migrate

# Optional: create a superuser for the /admin panel
python manage.py createsuperuser

# Start the development server
python manage.py runserver
```

Open [http://localhost:8000](http://localhost:8000) in your browser. You should see the
darkhorse dashboard.

---

## Step 6 — Run diagnostics

Before your first session, click **Diagnostics** in the sidebar (or run `dhn-diagnose` in the
terminal). This runs 8 checks:

1. ✅ ATLAS ping (192.168.3.10)
2. ✅ Pegasus ping (192.168.3.100)
3. ✅ DHN box ping (192.168.3.50)
4. ✅ DHN SSH login
5. ✅ Same /24 subnet
6. ✅ `xvfb-run` installed on DHN
7. ✅ `xdotool` installed on DHN
8. ✅ ATLAS UDP port 26090 reachable

Fix any failures before proceeding. See [Troubleshooting]({{ site.baseurl }}/troubleshooting) for
solutions to common issues.

---

## Step 7 — Create your first session

1. Click **New Session** in the sidebar
2. Choose **NRD Replay** or **Live ATLAS** mode
3. Fill in the network IPs (defaults match the standard lab topology)
4. Set the NRD file path (replay mode) or leave it empty (live mode)
5. Configure channels and compression
6. Click **Save Session**

You'll be taken to the session detail page where you can press **▶ Start** to begin.

---

## CLI usage (no web app needed)

You can also run sessions entirely from the command line:

```bash
# Edit the example config
cp configs/example_session.yaml configs/my_session.yaml
nano configs/my_session.yaml

# Run
dhn-orchestrate --config configs/my_session.yaml
```

Or from Python:

```python
from darkhorse_neuralynx.orchestrator.run import SessionOrchestrator

orchestrator = SessionOrchestrator.from_yaml("configs/my_session.yaml")
orchestrator.run()
```
