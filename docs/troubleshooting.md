---
layout: default
title: Troubleshooting
nav_order: 7
description: "Diagnosis and fixes for every common failure mode — DHN-AQ stalls, network issues, xdotool problems."
---

# Troubleshooting
{: .no_toc }

Every common failure mode, what causes it, and how to fix it.
{: .fs-5 .fw-300 }

## Table of contents
{: .no_toc .text-delta }

1. TOC
{:toc}

---

## DHN-AQ stalls at "Waiting for data source…"

**Cause**: DHN-AQ opened its UDP socket on port 26090 but received no packets.

### In live mode

1. Is ATLAS powered on and connected to the same switch as the DHN box?
2. Does the DHN box have a 192.168.3.x IP? (`ip addr show eno1`)
3. Can you ping 192.168.3.10 from the DHN box? (`ping -c 4 192.168.3.10`)
4. Is there a firewall blocking UDP? (`sudo ufw status` — disable it on the ATLAS NIC)

### In replay mode

1. Is the relay bridge running **before** DHN-AQ?
   - The orchestrator handles ordering automatically. If running manually, start the relay
     bridge first, then launch DHN-AQ.
2. Is Pegasus actually replaying? Check that the NRD file path is correct and replay is
   running in Pegasus.
3. Is the relay bridge broadcasting on 192.168.3.255:26090?
   - Check with: `sudo tcpdump -i eno1 udp port 26090 -c 5` on the DHN box

---

## xdotool: no window found / DHN-AQ dialog doesn't close

**Cause**: `xdotool` couldn't find the DHN-AQ Initialize dialog in the virtual display.

**Fixes**:

1. **Wait longer** — DHN-AQ may take 5-15 seconds to show the dialog.
   Increase `wait_for_dialog` timeout in `DHNLauncher`.

2. **Check Xvfb is running**:
   ```bash
   ssh dhn@192.168.3.50
   ps aux | grep Xvfb
   ```

3. **Check DHN-AQ process is running**:
   ```bash
   ps aux | grep DHN_Acq
   ```

4. **Check DISPLAY is set**:
   ```bash
   # xdotool needs the same DISPLAY as the DHN-AQ process
   export DISPLAY=:99
   xdotool search --name "DHN"
   ```

5. **Try manually** on the DHN box:
   ```bash
   export DISPLAY=:99
   xvfb-run -n 99 -a /opt/DHN/DHN_Acq &
   # Wait for the dialog...
   xdotool search --onlyvisible --name ""   # list all windows
   ```

---

## SSH connection refused / timeout

**Cause**: Cannot reach the DHN box via SSH.

**Fixes**:
1. Verify the IP is correct: `ping 192.168.3.50`
2. Check sshd is running on DHN box: `systemctl status ssh`
3. Check the SSH user exists: `id dhn` on the DHN box
4. Check key-based auth or password auth is enabled in `/etc/ssh/sshd_config`
5. Try manually: `ssh dhn@192.168.3.50 echo ok`

---

## NetCom DLL fails to load

**Cause**: `MatlabNetComClient2_x64.dll` not found, or not running on Windows.

**Error message**: `OSError: [WinError 126] The specified module could not be found`

**Fixes**:
1. Confirm you're on Windows — the DLL is Windows-only
2. Check the DLL path in settings or use the default:
   `nrdReplay/neuralynxNetcom201/MatlabNetComClient2_x64.dll`
3. Install the Visual C++ Redistributable 2015-2022 (x64) if missing

{: .note }
> For live ATLAS mode, the relay bridge is not used — no DLL is needed. Only replay mode
> requires the NetCom DLL on Windows.

---

## "PROMPT" value in RC file causes hang

**Cause**: A field in the RC file has the value `PROMPT`, meaning DHN-AQ will ask the user
interactively. In headless mode, this blocks forever.

**Fix**: Use `RCWriter` — it replaces all `PROMPT` defaults with real values. Never write
RC files by hand unless you audit every field.

---

## Relay bridge shows 0 packets / very low packet rate

**Cause**: Pegasus is not streaming data via NetCom.

**Fixes**:
1. Confirm NRD replay is **running** in Pegasus (not paused)
2. Confirm the NetCom server is enabled in Pegasus settings
3. Try `NlxAreWeConnected()` manually in MATLAB from the Pegasus PC

---

## Django `manage.py migrate` fails

**Cause**: Usually a missing `pipeline` app or settings misconfiguration.

**Fix**:
```bash
cd webapp
python manage.py migrate --run-syncdb
```
If it still fails, delete `db.sqlite3` and try again.

---

## Session shows "Error" status immediately

**Cause**: The orchestrator background thread raised an exception.

**Fix**: Check the **Session Log** on the detail page. The last line will contain the exception.
Common causes:
- SSH key not accepted (add key to `~/.ssh/authorized_keys` on DHN box)
- DHN-AQ executable path wrong (`/opt/DHN/DHN_Acq` — adjust in `DHNLauncher`)
- `darkhorse_neuralynx` Python library not installed (`pip install -e .` from repo root)

---

## Packet format mismatch — DHN-AQ doesn't record

**Cause**: The relay bridge's ATLAS packet format doesn't exactly match what DHN-AQ expects.

**Background**: The ATLAS UDP packet format is not publicly documented. The `NRDRelayBridge`
uses a best-effort reconstruction. If your DHN-AQ version expects a slightly different header,
it may silently discard packets.

**Fixes**:
1. Enable debug logging in `NRDRelayBridge` to inspect packet bytes
2. Capture real ATLAS packets with `tcpdump` on the DHN box and compare headers:
   ```bash
   sudo tcpdump -i eno1 udp port 26090 -w /tmp/atlas.pcap -c 100
   ```
3. Contact Dark Horse Neuro (`contact@darkhorseneuro.com`) to confirm the expected UDP
   packet format for your DHN-AQ version.

---

## Running pre-flight checks

Use the built-in diagnostics before every session:

```bash
# Command line
dhn-diagnose

# Web app: click "Diagnostics" in the sidebar
```

Or from Python:

```python
from darkhorse_neuralynx.dhn_client.diagnose import Diagnostics

d = Diagnostics(atlas_ip="192.168.3.10", pegasus_ip="192.168.3.100", dhn_ip="192.168.3.50")
for check in [d.check_ping_atlas, d.check_ping_pegasus, d.check_ping_dhn,
              d.check_dhn_ssh, d.check_local_subnet,
              d.check_xvfb_available, d.check_xdotool_available]:
    r = check()
    icon = "✅" if r.ok else "❌"
    print(f"{icon}  {r.name}: {r.message}")
```
