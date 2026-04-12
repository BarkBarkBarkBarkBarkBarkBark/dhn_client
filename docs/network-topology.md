---
layout: default
title: Network Topology
nav_order: 3
description: "The IP address mystery explained — why ATLAS uses 192.168.3.10 and how all three machines communicate."
---

# Network Topology
{: .no_toc }

Everything you need to know about the three machines, two network layers, and the infamous
192.168.3.10 IP address.
{: .fs-5 .fw-300 }

## Table of contents
{: .no_toc .text-delta }

1. TOC
{:toc}

---

## The big picture

```
══════════════════════════════════════════════════════════════════
  HARDWARE TRANSPORT LAYER       192.168.3.0/24
  (dedicated NIC on each machine — NOT your regular lab LAN)

  ┌──────────────────────────────────────────────────────────┐
  │                                                          │
  │   ATLAS Amplifier                                        │
  │   192.168.3.10  ← hardcoded in firmware                 │
  │   port 26011    ← control port (Pegasus only)            │
  │        │                                                  │
  │        │ UDP broadcast  →  192.168.3.255:26090            │
  │        │                                                  │
  │   ┌────┴──────────────────┐  ┌───────────────────────┐   │
  │   │  Pegasus PC           │  │  DHN-AQ Linux box     │   │
  │   │  192.168.3.100        │  │  192.168.3.50         │   │
  │   │  (static, dedicated   │  │  (user-assigned,      │   │
  │   │   NIC — Windows)      │  │   same /24 — Ubuntu)  │   │
  │   └─────────┬─────────────┘  └───────────────────────┘   │
  │             │                                              │
  └─────────────┼──────────────────────────────────────────── ┘
                │
  ══════════════╪══════════════════════════════════════════════
  LAB LAN LAYER │ (your regular campus / lab network)
                │
                │  NetCom TCP  ←─  Python orchestrator
                │                  (any machine on lab LAN)
                │
                └──────────────────────────────────────────────
```

---

## The "IP mystery" explained

If you've ever opened a Neuralynx config file and seen `192.168.3.10`, you've hit the mystery.
Here's what each address means:

### 192.168.3.10 — ATLAS Amplifier

This IP is **burned into the ATLAS firmware**. You cannot change it without a firmware
reflash (contact Neuralynx). Every Neuralynx lab in the world that uses ATLAS has this address.

The amplifier:
- Listens on **:26011** for control commands from Pegasus
- **Broadcasts** raw 24-bit neural data to **255.255.255.255:26090** or **192.168.3.255:26090**
  (subnet-directed broadcast)

### 192.168.3.100 — Pegasus PC

Pegasus receives the ATLAS broadcast. It also **runs a NetCom TCP server** on the same machine —
this is how MATLAB scripts and Python connect to it to send recording commands and read data
streams. The 192.168.3.x address is only for the dedicated ATLAS NIC; Pegasus also has a
normal NIC on your lab LAN.

### 192.168.3.50 — DHN-AQ Linux box

This IP is **user-assignable** — you set it in your Ubuntu network config. It just needs to be
on the same `/24` subnet so it receives the UDP broadcast. DHN-AQ never uses NetCom at all;
it only listens for raw ATLAS UDP.

---

## Two completely separate network layers

This is the most confusing part of the setup. There are **two separate communication paths**:

| Layer | Protocol | Purpose | Who uses it |
|-------|----------|---------|-------------|
| **Hardware transport** | Raw UDP broadcast (192.168.3.0/24) | Stream 24-bit neural samples at 32 kHz | ATLAS → Pegasus → DHN-AQ |
| **Lab LAN** | NetCom TCP | Send recording commands, read data programmatically | MATLAB, Python, this library |

DHN-AQ only uses the **hardware transport layer** (raw UDP). It has no NetCom client. This is
why it stalls during NRD replay — no hardware → no UDP → DHN-AQ waits forever.

---

## Port reference

| Port | Protocol | Direction | Description |
|------|----------|-----------|-------------|
| **26011** | UDP | PC → ATLAS | Pegasus control commands to ATLAS |
| **26090** | UDP broadcast | ATLAS → all | Raw neural data stream (32 kHz) |
| **26090** | UDP | Relay bridge → DHN | Replay: re-broadcast from relay bridge |
| **NetCom** | TCP | Client → Pegasus | Abstracted inside `MatlabNetComClient2_x64.dll` |

{: .warning }
> Port 26090 is **hardcoded in DHN-AQ firmware**. The relay bridge must broadcast on exactly
> this port for DHN-AQ to receive it.

---

## The replay problem and solution

During NRD replay:
1. ATLAS hardware is absent → no UDP packets on port 26090
2. DHN-AQ opens a socket and waits → **stalls indefinitely**

**Solution**: The `NRDRelayBridge` (in `src/darkhorse_neuralynx/pegasus_bridge/nrd_stream.py`):
1. Connects to Pegasus via **NetCom TCP** (Windows DLL wrapper)
2. Polls `GetNewCSCData()` in a loop
3. Packs samples into an **ATLAS-format UDP packet** (best-effort reconstruction)
4. Broadcasts to **192.168.3.255:26090** on the hardware NIC

DHN-AQ receives these synthetic packets and treats them as live ATLAS data. ✓

---

## Configuring the hardware NIC on each machine

### Pegasus (Windows)
Open **Control Panel → Network Adapters → [ATLAS NIC] → Properties → IPv4**:
- IP: `192.168.3.100`
- Subnet: `255.255.255.0`
- Gateway: *(leave blank)*

### DHN-AQ Linux box (Ubuntu, using nmcli)
```bash
# Find the NIC connected to the ATLAS switch (usually eno1 or eth1)
ip link show

# Assign static IP
sudo nmcli con mod "Wired connection 1" \
  ipv4.method manual \
  ipv4.addresses 192.168.3.50/24

sudo nmcli con up "Wired connection 1"
```

### Python orchestrator machine
No static IP needed — it connects to Pegasus via **NetCom TCP on the lab LAN**, not the
hardware subnet.
