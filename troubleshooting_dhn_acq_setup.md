# DHN_Acq Setup Troubleshooting Log
**Date:** April 17, 2026  
**Goal:** Get DHN_Acq recording live data from Pegasus (Windows) via relay.py forwarding ATLAS-format UDP to this Linux machine.

---

## System Overview

| Role | Machine | IP |
|---|---|---|
| Acquisition (Pegasus) | Windows | `192.168.1.55` (wifi) |
| Recording (DHN_Acq) | Linux (DHN-1) | `192.168.1.48` (wifi `wls3f3`) |

**Data flow:**  
`Pegasus → NetCom → relay.py (Windows) → UDP 26090 → DHN_Acq (Linux)`

---

## What Was Confirmed Working ✓

### UDP Data Stream
- relay.py successfully polls Pegasus via NetCom DLL and re-broadcasts ATLAS-format UDP packets
- **2.3 million packets received** on `192.168.1.48:26090` in ~30 seconds — the data stream is healthy
- Packet format confirmed: 1052 bytes, STX `0x00000800`, 512 × int16 samples + header/footer
- Source: `192.168.1.55:55498` (Windows wifi adapter)
- `adc_gain=2500` in relay.py matches `SetInputRange 2500` in Pegasus config ✓
- MAC `e0:2e:0b:6d:48:a9` (Windows wifi) confirmed via ARP ✓

### Config File Updates Made
`/home/dhn/DHN/DHN_Acq/DHN_Acq_rc.txt` was updated:

| Field | Old Value | New Value |
|---|---|---|
| `Receiving Local EN Interface Name` | `eno1` | `wls3f3` |
| `Receiving Local IP Address` | `192.168.1.49` | `192.168.1.48` |
| `Receiving Server IP Address` | `192.168.1.55` | `192.168.1.55` (unchanged) |
| `Neuralynx PC MAC Address` | `e0:2e:0b:6d:48:a9` | `e0:2e:0b:6d:48:a9` (confirmed correct) |
| `Receive As Broadcast` | `YES` | `YES` |
| `Use Watchdog Service` | `DEFAULT` (YES) | `NO` |

---

## What Didn't Work / Root Causes Found

### 1. Wrong Interface (`eno1`)
**Problem:** DHN_Acq was configured to use `eno1` which was unplugged/DOWN.  
**Symptom:** `system_m12() failed: ifconfig eno1 mtu 42` → `exiting program`  
**Fix:** Changed interface to `wls3f3` in config.

### 2. Direct Ethernet Link (USB Adapter)
**Attempted:** USB ethernet adapter (`enxe01aeaa4bc22`) for direct Linux↔Windows connection.  
**Problem:** Windows couldn't set `192.168.2.55` on its ethernet adapter because `192.168.1.55` was already on wifi — had to use different subnet (`192.168.2.x`). Even after configuration, the adapter stayed `NO-CARRIER` (physical link never came up — cable or driver issue).  
**Status:** Abandoned in favor of wifi for now.

### 3. DHN_Acq TCP Handshake Timeout — `TR_connect_m12()`
**Problem:** DHN_Acq makes a **TCP connection to `dhnsrv.com:49155`** (`129.222.100.21`) for license/data stream validation. This port is **unreachable** from the local network.  
**Confirmed via tcpdump:** SYN packets sent to `129.222.100.21:49155` repeatedly with no response.  
**Confirmed via netcat:** `nc -zv -w3 dhnsrv.com 49155` → timed out.  
**This is the blocking issue.** DHN_Acq exits after failing this TCP handshake.

### 4. Windows Firewall (TCP back to Windows)
TCP connections from Linux to `192.168.1.55` all returned `EAGAIN` (err 11). Firewall rule added on Windows but did not resolve — likely because DHN_Acq's TCP handshake goes to `dhnsrv.com`, not back to the Windows machine.

---

## Next Steps / Things to Try

### Priority 1: Fix `dhnsrv.com:49155` connectivity
This is the blocking issue. Options:
1. **Check router:** Log into Netgear router at `192.168.1.1` → Advanced → Security → confirm outbound TCP port `49155` is not blocked
2. **Test on hotspot:** Connect Linux machine to phone hotspot and retry `nc -zv -w3 dhnsrv.com 49155` — if it works on hotspot, the Netgear router is blocking it
3. **Contact DHN:** Email `contact@darkhorseneuro.com` — confirm `dhnsrv.com:49155` is operational and whether a firewall exception is needed
4. **Check if watchdog=NO helps:** Already set in config — re-test DHN_Acq to see if disabling watchdog bypasses the `dhnsrv.com` check entirely

### Priority 2: Direct Ethernet Link (when needed for latency/reliability)
1. Confirm Windows USB ethernet adapter driver is properly installed (`devmgmt.msc`)
2. Set Windows ethernet adapter to static `192.168.2.55 / 255.255.255.0` (separate subnet from wifi `192.168.1.x`)
3. Linux side is already configured: `192.168.2.49` on `enxe01aeaa4bc22`
4. Update `DHN_Acq_rc.txt` back to `192.168.2.x` values if switching to ethernet
5. Update relay.py `--dest` to `192.168.2.49`
6. Make Linux IP persistent (NetworkManager or `/etc/network/interfaces`) — current assignment is temporary and lost on reboot

### Priority 3: Make IP Assignment Persistent (Linux)
Current `192.168.2.49` assignment on `enxe01aeaa4bc22` is lost on reboot. To persist:
```bash
# Option: nmcli
nmcli con add type ethernet ifname enxe01aeaa4bc22 ip4 192.168.2.49/24
```

### Priority 4: relay.py on Windows
- Clone `dhn_client` repo to Windows machine
- Run relay.py natively on Windows (requires Python 3 + `MatlabNetComClient2_x64.dll` in path)
- Command: `python relay.py --server localhost --dll path\to\MatlabNetComClient2_x64.dll --dest 192.168.1.48 --port 26090`
- The DLL is in `nrdReplay/neuralynxNetcom201/` (as `.thunk` + `.dll` pair)

---

## Key Commands Reference

```bash
# Check UDP packets arriving on wifi
python3 -c "
import socket, time
sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
sock.bind(('192.168.1.48', 26090))
sock.settimeout(3.0)
count = 0
try:
    while True:
        data, addr = sock.recvfrom(65535)
        count += 1
except socket.timeout:
    pass
sock.close()
print(f'{count} packets')
"

# Test DHN server reachability
nc -zv -w3 dhnsrv.com 49155

# Check DHN_Acq crash logs
journalctl -n 100 --no-pager | grep "DHN_Acq"

# Assign IP to USB ethernet adapter (temporary)
sudo ip addr add 192.168.2.49/24 dev enxe01aeaa4bc22
sudo ip link set enxe01aeaa4bc22 up

# Capture TCP SYN packets to see what DHN_Acq connects to
sudo tcpdump -i any -n 'tcp[tcpflags] & tcp-syn != 0 or udp port 53'
```
