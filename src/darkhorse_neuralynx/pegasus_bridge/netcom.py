"""Pegasus NetCom client — ctypes wrapper for MatlabNetComClient2_x64.dll.

This module wraps the Neuralynx Windows DLL via ctypes so that Python
can connect to a running Pegasus instance and:
  • query acquisition entities (CSC channels, events, etc.)
  • subscribe to data streams
  • receive buffered CSC records
  • send commands (-StartRecording, -StopRecording, etc.)

IMPORTANT: This module is WINDOWS ONLY.  The DLL (MatlabNetComClient2_x64.dll)
is a 64-bit Windows binary and cannot be loaded on Linux or macOS.

Usage::

    from darkhorse_neuralynx.pegasus_bridge.netcom import NetComClient

    client = NetComClient(server="localhost")   # same PC as Pegasus
    client.connect()
    channels = client.get_objects()             # ["CSC1", "CSC2", ...]
    client.open_stream("CSC1")
    client.send_command("-StartAcquisition")

    while True:
        records = client.get_new_csc_data("CSC1")
        for r in records:
            print(r.timestamp_us, r.samples[:5])

    client.send_command("-StopAcquisition")
    client.close_stream("CSC1")
    client.disconnect()

DLL path:
    nrdReplay/neuralynxNetcom201/MatlabNetComClient2_x64.dll
    (shipped in this repo; also available from Neuralynx support)
"""

from __future__ import annotations

import ctypes
import logging
import os
import platform
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

log = logging.getLogger(__name__)

# Default DLL location relative to this repo root
_REPO_ROOT = Path(__file__).resolve().parents[4]
_DEFAULT_DLL_PATH = str(
    _REPO_ROOT / "nrdReplay" / "neuralynxNetcom201" / "MatlabNetComClient2_x64.dll"
)

# ---------------------------------------------------------------------------
# CSC record as returned by GetNewCSCData
# ---------------------------------------------------------------------------
@dataclass
class CSCRecord:
    """One CSC buffer record from Pegasus NetCom.

    Fields match the DLL's GetNewCSCData output.
    Timestamps are in Neuralynx 64-bit microsecond units.
    """
    timestamp_us: int          # 64-bit Nlx timestamp (µs since midnight Jan 1, 1970... ish)
    channel_number: int        # hardware channel number
    sample_freq_hz: int        # nominal sampling frequency
    num_valid_samples: int     # number of valid samples in this record
    samples: list[int]         # ADC counts (int16, up to 512 per record)


@dataclass
class EventRecord:
    timestamp_us: int
    event_id: int
    nttl: int
    extra_bits: int
    event_string: str


# ---------------------------------------------------------------------------
# ctypes structures
# ---------------------------------------------------------------------------
_MAX_CSC_SAMPLES = 512   # Neuralynx NetCom maximum per GetNewCSCData record


class _CSCDataRaw(ctypes.Structure):
    """Raw layout matching GetNewCSCData DLL output buffers."""
    pass  # Buffers allocated manually as ctypes arrays


# ---------------------------------------------------------------------------
class NetComClient:
    """Python interface to Pegasus via MatlabNetComClient2_x64.dll.

    Parameters
    ----------
    server:
        Hostname or IP of the Pegasus PC. Use ``"localhost"`` when running
        on the same Windows machine.
    dll_path:
        Absolute path to MatlabNetComClient2_x64.dll.
        Defaults to nrdReplay/neuralynxNetcom201/MatlabNetComClient2_x64.dll
        in this repo.
    buffer_size:
        Number of records to buffer per stream (default: 3000).
    """

    def __init__(
        self,
        server: str = "localhost",
        dll_path: Optional[str] = None,
        buffer_size: int = 3000,
    ) -> None:
        if platform.system().lower() != "windows":
            raise RuntimeError(
                "NetComClient requires Windows — the MatlabNetComClient2_x64.dll "
                "is a Windows-only binary. Use this on the Pegasus PC."
            )
        self.server = server
        self.dll_path = dll_path or _DEFAULT_DLL_PATH
        self.buffer_size = buffer_size
        self._dll: Optional[ctypes.WinDLL] = None  # type: ignore[type-arg]
        self._connected = False
        self._open_streams: set[str] = set()

    # ------------------------------------------------------------------
    def _load_dll(self) -> None:
        if self._dll is not None:
            return
        if not Path(self.dll_path).exists():
            raise FileNotFoundError(
                f"NetCom DLL not found: {self.dll_path}\n"
                f"Download from Neuralynx support or find in nrdReplay/neuralynxNetcom201/"
            )
        log.info(f"[netcom] Loading DLL: {self.dll_path}")
        # Add DLL directory to search path (required on Windows 10+)
        dll_dir = str(Path(self.dll_path).parent)
        os.add_dll_directory(dll_dir)  # type: ignore[attr-defined]
        self._dll = ctypes.WinDLL(self.dll_path)  # type: ignore[attr-defined]
        self._configure_prototypes()
        log.info("[netcom] DLL loaded")

    def _configure_prototypes(self) -> None:
        """Set ctypes argument and return types for each DLL function."""
        dll = self._dll
        assert dll is not None

        # int ConnectToServer(const char* serverName)
        dll.ConnectToServer.argtypes = [ctypes.c_char_p]
        dll.ConnectToServer.restype = ctypes.c_int

        # int DisconnectFromServer()
        dll.DisconnectFromServer.argtypes = []
        dll.DisconnectFromServer.restype = ctypes.c_int

        # int OpenStream(const char* cheetahObjectName)
        dll.OpenStream.argtypes = [ctypes.c_char_p]
        dll.OpenStream.restype = ctypes.c_int

        # int CloseStream(const char* cheetahObjectName)
        dll.CloseStream.argtypes = [ctypes.c_char_p]
        dll.CloseStream.restype = ctypes.c_int

        # int SetApplicationName(const char* name)
        dll.SetApplicationName.argtypes = [ctypes.c_char_p]
        dll.SetApplicationName.restype = ctypes.c_int

        # int AreWeConnected()
        dll.AreWeConnected.argtypes = []
        dll.AreWeConnected.restype = ctypes.c_int

        # GetNewCSCData:
        # int GetNewCSCData(
        #   const char* objectName,
        #   int64*  qwTimeStamps,
        #   int32*  dwChannelNumbers,
        #   int32*  dwSampleFrequencies,
        #   int32*  dwNumValidSamples,
        #   int16*  snSamples,
        #   int32*  numBytesTimestamp,
        #   int32*  numRecordsReturned
        # )
        dll.GetNewCSCData.argtypes = [
            ctypes.c_char_p,
            ctypes.POINTER(ctypes.c_int64),
            ctypes.POINTER(ctypes.c_int32),
            ctypes.POINTER(ctypes.c_int32),
            ctypes.POINTER(ctypes.c_int32),
            ctypes.POINTER(ctypes.c_int16),
            ctypes.POINTER(ctypes.c_int32),
            ctypes.POINTER(ctypes.c_int32),
        ]
        dll.GetNewCSCData.restype = ctypes.c_int

        # SendCommand:
        # int SendCommand(const char* command, char** reply, int* numBytesAvail)
        dll.SendCommand.argtypes = [
            ctypes.c_char_p,
            ctypes.POINTER(ctypes.c_char_p),
            ctypes.POINTER(ctypes.c_int32),
        ]
        dll.SendCommand.restype = ctypes.c_int

        # GetCheetahObjectsAndTypes:
        # int GetCheetahObjectsAndTypes(
        #   char** objects, char** types, int* bytesPerStr, int* numStrings
        # )
        dll.GetCheetahObjectsAndTypes.argtypes = [
            ctypes.POINTER(ctypes.c_char_p),
            ctypes.POINTER(ctypes.c_char_p),
            ctypes.POINTER(ctypes.c_int32),
            ctypes.POINTER(ctypes.c_int32),
        ]
        dll.GetCheetahObjectsAndTypes.restype = ctypes.c_int

    # ------------------------------------------------------------------
    def connect(self, app_name: str = "darkhorse_neuralynx") -> None:
        """Load DLL and connect to the Pegasus NetCom server."""
        self._load_dll()
        assert self._dll is not None
        log.info(f"[netcom] Connecting to {self.server!r}...")
        ret = self._dll.ConnectToServer(self.server.encode())
        if ret != 1:
            raise ConnectionError(
                f"NetCom ConnectToServer({self.server!r}) failed (ret={ret}). "
                f"Is Pegasus running and in ACQ state?"
            )
        self._connected = True
        log.info(f"[netcom] Connected to {self.server!r}")
        self._dll.SetApplicationName(app_name.encode())

    def disconnect(self) -> None:
        """Close all streams and disconnect from Pegasus."""
        if not self._connected:
            return
        assert self._dll is not None
        for name in list(self._open_streams):
            self.close_stream(name)
        self._dll.DisconnectFromServer()
        self._connected = False
        log.info("[netcom] Disconnected")

    def __enter__(self) -> "NetComClient":
        self.connect()
        return self

    def __exit__(self, *_: object) -> None:
        self.disconnect()

    # ------------------------------------------------------------------
    def is_connected(self) -> bool:
        if self._dll is None:
            return False
        return bool(self._dll.AreWeConnected())

    def get_objects(self) -> list[tuple[str, str]]:
        """Return list of (name, type) for all acquisition entities in Pegasus."""
        assert self._dll is not None and self._connected
        objects_buf = ctypes.c_char_p()
        types_buf   = ctypes.c_char_p()
        bytes_per   = ctypes.c_int32(0)
        num_strings = ctypes.c_int32(0)
        ret = self._dll.GetCheetahObjectsAndTypes(
            ctypes.byref(objects_buf),
            ctypes.byref(types_buf),
            ctypes.byref(bytes_per),
            ctypes.byref(num_strings),
        )
        if ret != 1:
            raise RuntimeError(f"GetCheetahObjectsAndTypes failed (ret={ret})")
        n = num_strings.value
        bps = bytes_per.value
        # Parse null-terminated fixed-width strings
        raw_obj = objects_buf.value or b""
        raw_typ = types_buf.value or b""
        result: list[tuple[str, str]] = []
        for i in range(n):
            obj = raw_obj[i * bps: (i + 1) * bps].rstrip(b"\x00").decode()
            typ = raw_typ[i * bps: (i + 1) * bps].rstrip(b"\x00").decode()
            result.append((obj, typ))
        return result

    def csc_channel_names(self) -> list[str]:
        """Return names of CSC channels only."""
        return [name for name, typ in self.get_objects() if "csc" in typ.lower()]

    def open_stream(self, object_name: str) -> None:
        """Subscribe to a data stream from *object_name* (e.g. 'CSC1')."""
        assert self._dll is not None and self._connected
        ret = self._dll.OpenStream(object_name.encode())
        if ret != 1:
            raise RuntimeError(f"OpenStream({object_name!r}) failed (ret={ret})")
        self._open_streams.add(object_name)
        log.debug(f"[netcom] Opened stream: {object_name}")

    def close_stream(self, object_name: str) -> None:
        assert self._dll is not None
        self._dll.CloseStream(object_name.encode())
        self._open_streams.discard(object_name)
        log.debug(f"[netcom] Closed stream: {object_name}")

    # ------------------------------------------------------------------
    def get_new_csc_data(
        self,
        object_name: str,
        max_records: int = 100,
    ) -> list[CSCRecord]:
        """Poll for buffered CSC records since the last call.

        Returns a (possibly empty) list of CSCRecord objects.
        Call this in a loop; sleep a few ms between calls to avoid
        spinning the CPU at 100%.
        """
        assert self._dll is not None and self._connected
        n = max_records
        timestamps     = (ctypes.c_int64  * n)()
        chan_numbers   = (ctypes.c_int32  * n)()
        sample_freqs   = (ctypes.c_int32  * n)()
        valid_samples  = (ctypes.c_int32  * n)()
        # Samples: n records × 512 int16 per record
        samples        = (ctypes.c_int16  * (n * _MAX_CSC_SAMPLES))()
        bytes_ts       = ctypes.c_int32(0)
        num_returned   = ctypes.c_int32(0)

        ret = self._dll.GetNewCSCData(
            object_name.encode(),
            timestamps,
            chan_numbers,
            sample_freqs,
            valid_samples,
            samples,
            ctypes.byref(bytes_ts),
            ctypes.byref(num_returned),
        )
        if ret not in (1, 2):
            log.debug(f"[netcom] GetNewCSCData ret={ret} (0=no data, 2=buffer ovfl)")

        records: list[CSCRecord] = []
        for i in range(num_returned.value):
            ns = valid_samples[i]
            rec_samples = list(samples[i * _MAX_CSC_SAMPLES: i * _MAX_CSC_SAMPLES + ns])
            records.append(CSCRecord(
                timestamp_us=timestamps[i],
                channel_number=chan_numbers[i],
                sample_freq_hz=sample_freqs[i],
                num_valid_samples=ns,
                samples=rec_samples,
            ))
        return records

    # ------------------------------------------------------------------
    def send_command(self, command: str) -> str:
        """Send a Pegasus command string and return the reply.

        Common commands:
            -StartAcquisition
            -StopAcquisition
            -StartRecording
            -StopRecording
            -PostEvent "label" <id> <nttl>
        """
        assert self._dll is not None and self._connected
        reply_buf  = ctypes.c_char_p()
        num_bytes  = ctypes.c_int32(0)
        ret = self._dll.SendCommand(
            command.encode(),
            ctypes.byref(reply_buf),
            ctypes.byref(num_bytes),
        )
        if ret != 1:
            raise RuntimeError(f"SendCommand({command!r}) failed (ret={ret})")
        reply = (reply_buf.value or b"").decode()
        log.debug(f"[netcom] Command {command!r} → {reply!r}")
        return reply
