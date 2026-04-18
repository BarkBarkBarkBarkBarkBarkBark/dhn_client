"""
UDP relay: polls Pegasus via NetCom and re-broadcasts as ATLAS-format UDP.
Run this on the Windows machine alongside Pegasus.

Usage:
    python relay.py --server localhost --dll path\to\MatlabNetComClient2_x64.dll
                    --dest 192.168.1.49 --port 26090

Requirements:
    - Python 3.x on Windows (64-bit)
    - MatlabNetComClient2_x64.dll (from neuralynxNetcom201/)
    - Pegasus running with NetCom buffering enabled on all channels
"""

import argparse
import ctypes
import socket
import struct
import time
import threading

# ---------------------------------------------------------------------------
# NetCom DLL wrapper (minimal — only what we need)
# ---------------------------------------------------------------------------

class NetComClient:
    def __init__(self, dll_path, server="localhost", buffer_size=3000):
        self.server = server
        self.buffer_size = buffer_size
        self._dll = ctypes.cdll.LoadLibrary(dll_path)
        self._configure()

    def _configure(self):
        d = self._dll
        d.NlxConnectToServer.restype = ctypes.c_int
        d.NlxConnectToServer.argtypes = [ctypes.c_char_p]

        d.NlxDisconnectFromServer.restype = ctypes.c_int
        d.NlxDisconnectFromServer.argtypes = []

        d.NlxSetApplicationName.restype = ctypes.c_int
        d.NlxSetApplicationName.argtypes = [ctypes.c_char_p]

        d.NlxGetCheetahObjectsAndTypes.restype = ctypes.c_int
        d.NlxGetCheetahObjectsAndTypes.argtypes = [
            ctypes.POINTER(ctypes.c_int),
            ctypes.POINTER(ctypes.POINTER(ctypes.c_char_p)),
            ctypes.POINTER(ctypes.POINTER(ctypes.c_char_p)),
        ]

        d.NlxOpenStream.restype = ctypes.c_int
        d.NlxOpenStream.argtypes = [ctypes.c_char_p]

        d.NlxCloseStream.restype = ctypes.c_int
        d.NlxCloseStream.argtypes = [ctypes.c_char_p]

        d.NlxGetNewCSCData.restype = ctypes.c_int
        d.NlxGetNewCSCData.argtypes = [
            ctypes.c_char_p,                         # object name
            ctypes.c_int,                            # max records
            ctypes.POINTER(ctypes.c_int),            # num returned
            ctypes.POINTER(ctypes.c_int),            # num dropped
            ctypes.POINTER(ctypes.c_longlong),       # timestamps
            ctypes.POINTER(ctypes.c_int),            # channel numbers
            ctypes.POINTER(ctypes.c_int),            # sampling freqs
            ctypes.POINTER(ctypes.c_int),            # num valid samples
            ctypes.POINTER(ctypes.c_int),            # samples (512 * max_records)
        ]

    def connect(self):
        ok = self._dll.NlxConnectToServer(self.server.encode())
        if ok != 1:
            raise RuntimeError(f"Failed to connect to NetCom server: {self.server}")
        self._dll.NlxSetApplicationName(b"DHN_relay")

    def disconnect(self):
        self._dll.NlxDisconnectFromServer()

    def get_csc_channels(self):
        """Return list of CSC channel name strings."""
        count = ctypes.c_int(0)
        names_ptr = ctypes.POINTER(ctypes.c_char_p)()
        types_ptr = ctypes.POINTER(ctypes.c_char_p)()
        ok = self._dll.NlxGetCheetahObjectsAndTypes(
            ctypes.byref(count),
            ctypes.byref(names_ptr),
            ctypes.byref(types_ptr),
        )
        if ok != 1:
            raise RuntimeError("Failed to get Cheetah objects")
        channels = []
        for i in range(count.value):
            name = names_ptr[i].decode() if names_ptr[i] else ""
            typ  = types_ptr[i].decode() if types_ptr[i] else ""
            if name.upper().startswith("CSC"):
                channels.append(name)
        return channels

    def open_stream(self, name):
        return self._dll.NlxOpenStream(name.encode()) == 1

    def close_stream(self, name):
        self._dll.NlxCloseStream(name.encode())

    def poll(self, name, max_records=None):
        """Returns list of (timestamp_us, channel_num, samples[]) tuples."""
        mr = max_records or self.buffer_size
        num_returned = ctypes.c_int(0)
        num_dropped  = ctypes.c_int(0)
        timestamps   = (ctypes.c_longlong * mr)()
        chan_nums     = (ctypes.c_int * mr)()
        samp_freqs   = (ctypes.c_int * mr)()
        num_valid    = (ctypes.c_int * mr)()
        samples      = (ctypes.c_int * (512 * mr))()

        ok = self._dll.NlxGetNewCSCData(
            name.encode(), mr,
            ctypes.byref(num_returned), ctypes.byref(num_dropped),
            timestamps, chan_nums, samp_freqs, num_valid, samples,
        )
        if ok != 1 or num_returned.value == 0:
            return []

        records = []
        for i in range(num_returned.value):
            s = list(samples[i * 512 : i * 512 + num_valid.value[i]])
            records.append((timestamps[i], chan_nums[i], s))
        return records


# ---------------------------------------------------------------------------
# ATLAS UDP packet builder
# ---------------------------------------------------------------------------

STX = 0x00000800
ETX = 0x00000800

def build_atlas_packet(packet_id, channel_number, timestamp_us, samples, adc_gain=2500):
    n = len(samples)
    header = struct.pack(
        "<IIqHHHH",
        STX,
        packet_id,
        timestamp_us,
        channel_number,
        n,
        adc_gain,
        0,          # threshold placeholder
    )
    payload = struct.pack(f"<{n}h", *samples)
    footer  = struct.pack("<I", ETX)
    return header + payload + footer


# ---------------------------------------------------------------------------
# Relay loop
# ---------------------------------------------------------------------------

def relay(client, dest_ip, dest_port, poll_interval_ms, stop_event):
    channels = client.get_csc_channels()
    if not channels:
        raise RuntimeError("No CSC channels found in Pegasus")
    print(f"Found {len(channels)} CSC channels: {channels[:5]}{'...' if len(channels) > 5 else ''}")

    for ch in channels:
        if not client.open_stream(ch):
            print(f"  WARNING: could not open stream for {ch}")

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)

    packet_id = 0
    packets_sent = 0
    interval = poll_interval_ms / 1000.0

    print(f"Relaying to {dest_ip}:{dest_port}  (Ctrl+C to stop)")
    try:
        while not stop_event.is_set():
            for ch in channels:
                for (ts, ch_num, samps) in client.poll(ch):
                    pkt = build_atlas_packet(packet_id, ch_num, ts, samps)
                    sock.sendto(pkt, (dest_ip, dest_port))
                    packet_id += 1
                    packets_sent += 1
            if packets_sent > 0 and packets_sent % 10000 == 0:
                print(f"  {packets_sent} packets sent")
            time.sleep(interval)
    finally:
        sock.close()
        for ch in channels:
            client.close_stream(ch)
        print(f"Relay stopped. Total packets sent: {packets_sent}")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Pegasus → ATLAS UDP relay")
    parser.add_argument("--server", default="localhost",
                        help="NetCom server hostname (default: localhost)")
    parser.add_argument("--dll",    required=True,
                        help="Path to MatlabNetComClient2_x64.dll")
    parser.add_argument("--dest",   required=True,
                        help="Destination IP for UDP broadcast (Linux machine IP)")
    parser.add_argument("--port",   type=int, default=26090,
                        help="Destination UDP port (default: 26090)")
    parser.add_argument("--poll",   type=int, default=20,
                        help="Poll interval in ms (default: 20)")
    args = parser.parse_args()

    client = NetComClient(dll_path=args.dll, server=args.server)
    client.connect()
    print(f"Connected to NetCom server: {args.server}")

    stop_event = threading.Event()
    try:
        relay(client, args.dest, args.port, args.poll, stop_event)
    except KeyboardInterrupt:
        print("\nStopping...")
        stop_event.set()
    finally:
        client.disconnect()


if __name__ == "__main__":
    main()
