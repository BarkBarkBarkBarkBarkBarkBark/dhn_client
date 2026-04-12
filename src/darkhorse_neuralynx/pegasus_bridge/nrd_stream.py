"""NRD file UDP relay bridge — makes Pegasus NRD replay visible to DHN-AQ.

PROBLEM
-------
During Pegasus NRD replay, the ATLAS amplifier is absent.  DHN-AQ
receives raw UDP packets from the ATLAS amplifier on 192.168.3.0/24 and
stalls when no packets arrive.

SOLUTION
--------
This module:
  1. Connects to Pegasus via NetCom (using netcom.NetComClient) to receive
     CSC data from the NRD replay.
  2. Re-packages the CSC samples into ATLAS-compatible UDP broadcast packets.
  3. Broadcasts them on the 192.168.3.x subnet so DHN-AQ can receive them
     as if they were coming from live hardware.

DHN-AQ RC file settings for relay mode:
    Receive As Broadcast:        YES
    Receiving Server IP Address: <this PC's IP, e.g. 192.168.3.100>
    Receiving Port Number:       26090   (or whatever port you configure)
    Receiving Local IP Address:  <DHN box IP, e.g. 192.168.3.50>

USAGE
-----
On the Windows Pegasus PC, after starting Pegasus NRD replay:

    from darkhorse_neuralynx.pegasus_bridge.nrd_stream import NRDRelayBridge

    bridge = NRDRelayBridge(
        pegasus_server="localhost",
        broadcast_ip="192.168.3.255",
        broadcast_port=26090,
    )
    bridge.start()   # non-blocking background thread
    # ... run session ...
    bridge.stop()

Or as CLI:
    python -m darkhorse_neuralynx.pegasus_bridge.nrd_stream \\
        --pegasus localhost \\
        --broadcast-ip 192.168.3.255 \\
        --port 26090

ATLAS PACKET FORMAT NOTE
------------------------
The exact byte layout of Neuralynx ATLAS UDP broadcast packets is not
publicly documented by Neuralynx.  This module implements a best-effort
reconstruction based on:
  - Observed NRD file structure (32-bit header per packet)
  - Neuralynx community documentation
  - The known fields: packet_type, channel_number, timestamp, sample_count,
    samples (int16 × N)

If the format turns out to be incompatible with a specific DHN-AQ version,
the packet builder can be updated in _build_atlas_packet() below.
"""

from __future__ import annotations

import argparse
import logging
import socket
import struct
import threading
import time
from dataclasses import dataclass, field
from typing import Optional

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# ATLAS UDP packet constants (best-effort reconstruction)
# ---------------------------------------------------------------------------
#
# Neuralynx NRD / ATLAS packet structure (observed):
#   Bytes  0-3   : STX marker  0x00000800  (ATLAS continuous sample packet)
#   Bytes  4-7   : Packet ID   (uint32, sequential)
#   Bytes  8-15  : Timestamp   (int64, µs)
#   Bytes 16-17  : Channel     (uint16)
#   Bytes 18-19  : Sample count (uint16)
#   Bytes 20-21  : ADC gain     (uint16) — set to 0 if unknown
#   Bytes 22-23  : Threshold    (uint16) — set to 0
#   Bytes 24..   : Samples      (int16 × sample_count)
#   Last 4 bytes : ETX marker  0x00000800

_STX       = 0x00000800
_ETX       = 0x00000800
_PACKET_ID_MAX = 0xFFFFFFFF


def _build_atlas_packet(
    packet_id: int,
    channel_number: int,
    timestamp_us: int,
    samples: list[int],
    adc_gain: int = 1,
) -> bytes:
    """Pack a CSC record into an ATLAS-compatible UDP payload.

    This format is based on reverse-engineering of NRD file contents
    and may need adjustment for specific DHN-AQ versions.
    """
    n_samples = len(samples)
    # Header: STX, pkt_id, timestamp, channel, n_samples, gain, threshold
    header = struct.pack(
        "<IIqHHHH",
        _STX,
        packet_id & _PACKET_ID_MAX,
        timestamp_us,
        channel_number,
        n_samples,
        adc_gain,
        0,          # threshold
    )
    # Sample data: int16 little-endian
    sample_bytes = struct.pack(f"<{n_samples}h", *samples)
    # Footer
    footer = struct.pack("<I", _ETX)
    return header + sample_bytes + footer


# ---------------------------------------------------------------------------
@dataclass
class NRDRelayBridge:
    """Relay NRD replay data from Pegasus to DHN-AQ via UDP broadcast.

    Parameters
    ----------
    pegasus_server:
        Hostname or IP of the Pegasus PC (use 'localhost' if running there).
    broadcast_ip:
        Broadcast address for the ATLAS subnet (e.g. '192.168.3.255').
    broadcast_port:
        UDP port to broadcast on (26090 = ATLAS default, matches DHN RC default).
    channels:
        List of Pegasus channel names to relay (e.g. ['CSC1', 'CSC2', ...]).
        If None, all CSC channels are discovered automatically.
    poll_interval_ms:
        How often to poll Pegasus for new records (ms). Lower = lower latency
        but higher CPU. 10–50 ms is typical.
    dll_path:
        Path to MatlabNetComClient2_x64.dll (optional override).
    """

    pegasus_server: str       = "localhost"
    broadcast_ip: str         = "192.168.3.255"
    broadcast_port: int       = 26090
    channels: Optional[list[str]] = None
    poll_interval_ms: float   = 20.0
    dll_path: Optional[str]   = None

    _thread: Optional[threading.Thread] = field(default=None, init=False, repr=False)
    _stop_event: threading.Event         = field(default_factory=threading.Event, init=False)
    _stats_packets_sent: int             = field(default=0, init=False, repr=False)

    # ------------------------------------------------------------------
    def _relay_loop(self) -> None:
        """Main relay loop — runs in background thread."""
        from darkhorse_neuralynx.pegasus_bridge.netcom import NetComClient

        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_SNDBUF, 4 * 1024 * 1024)

        packet_id = 0

        try:
            with NetComClient(server=self.pegasus_server, dll_path=self.dll_path) as client:
                # Discover channels if not specified
                ch_names = self.channels or client.csc_channel_names()
                if not ch_names:
                    raise RuntimeError("No CSC channels found in Pegasus.")
                log.info(f"[relay] Relaying {len(ch_names)} channels → {self.broadcast_ip}:{self.broadcast_port}")

                # Subscribe to all channels
                for ch in ch_names:
                    client.open_stream(ch)
                    log.debug(f"[relay] Subscribed to {ch}")

                client.send_command("-StartAcquisition")
                log.info("[relay] ▶ NRD relay started")

                while not self._stop_event.is_set():
                    for ch in ch_names:
                        records = client.get_new_csc_data(ch, max_records=50)
                        for rec in records:
                            pkt = _build_atlas_packet(
                                packet_id=packet_id,
                                channel_number=rec.channel_number,
                                timestamp_us=rec.timestamp_us,
                                samples=rec.samples,
                            )
                            sock.sendto(pkt, (self.broadcast_ip, self.broadcast_port))
                            packet_id = (packet_id + 1) & _PACKET_ID_MAX
                            self._stats_packets_sent += 1

                    time.sleep(self.poll_interval_ms / 1000.0)

                client.send_command("-StopAcquisition")
                log.info("[relay] ■ NRD relay stopped")

        except Exception as exc:
            log.error(f"[relay] Fatal error: {exc}", exc_info=True)
        finally:
            sock.close()

    # ------------------------------------------------------------------
    def start(self) -> None:
        """Start the relay in a background thread (non-blocking)."""
        if self._thread and self._thread.is_alive():
            log.warning("[relay] Already running")
            return
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._relay_loop, daemon=True, name="NRDRelay")
        self._thread.start()
        log.info("[relay] Background relay thread started")

    def stop(self, timeout: float = 5.0) -> None:
        """Signal the relay to stop and wait for the thread to finish."""
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=timeout)
        log.info(f"[relay] Stopped. Packets sent: {self._stats_packets_sent}")

    def __enter__(self) -> "NRDRelayBridge":
        self.start()
        return self

    def __exit__(self, *_: object) -> None:
        self.stop()

    @property
    def packets_sent(self) -> int:
        return self._stats_packets_sent


# ---------------------------------------------------------------------------
def main() -> None:
    """CLI entry point for the relay bridge."""
    parser = argparse.ArgumentParser(
        description="Relay Pegasus NRD replay data to DHN-AQ via UDP broadcast"
    )
    parser.add_argument("--pegasus",      default="localhost", help="Pegasus server IP/hostname")
    parser.add_argument("--broadcast-ip", default="192.168.3.255", help="UDP broadcast address")
    parser.add_argument("--port",         type=int, default=26090, help="UDP broadcast port")
    parser.add_argument("--channels",     nargs="+", help="Channel names (default: auto-discover)")
    parser.add_argument("--poll-ms",      type=float, default=20.0, help="Poll interval ms")
    parser.add_argument("--dll",          help="Path to MatlabNetComClient2_x64.dll")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    bridge = NRDRelayBridge(
        pegasus_server=args.pegasus,
        broadcast_ip=args.broadcast_ip,
        broadcast_port=args.port,
        channels=args.channels,
        poll_interval_ms=args.poll_ms,
        dll_path=args.dll,
    )

    bridge.start()
    print("Relay running. Press Ctrl+C to stop.")
    try:
        while True:
            time.sleep(5)
            print(f"  Packets sent: {bridge.packets_sent}")
    except KeyboardInterrupt:
        pass
    finally:
        bridge.stop()


if __name__ == "__main__":
    main()
