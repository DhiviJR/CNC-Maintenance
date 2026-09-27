import os
import sys
import ctypes
from ctypes import c_ushort, c_short, c_long, c_char_p, POINTER, byref, Structure


DEFAULT_FOCAS_PATH = r"C:\Users\LENOVO\Downloads\fanuc-cnc-api-main\fanuc-cnc-api-main"


class ODBST(Structure):
    """
    FANUC FOCAS CNC status structure.
    """
    _fields_ = [
        ("dummy", c_short),
        ("aut", c_short),        # Auto/Manual mode
        ("run", c_short),        # Run status (0:STOP, 1:HOLD, 2:STaRT, 3:MSTR)
        ("motion", c_short),     # Axis motion status (0:Stop, 1:Motion, 2:Dwell)
        ("mstb", c_short),       # M, S, T, B function execution status
        ("emergency", c_short),  # Emergency stop flag (0:Normal, 1:Emergency)
        ("alarm", c_short),      # Alarm flag (0:Normal, 1:Alarm active)
        ("edit", c_short),       # Program edit status
    ]


class FanucFocasClient:
    """
    Python wrapper around FANUC FOCAS Ethernet API library (Fwlib64.dll).
    """

    def __init__(self, ip="192.168.1.101", port=8193, timeout=10, focas_path=None):
        self.ip = ip
        self.port = int(port)
        self.timeout = int(timeout)
        self.focas_path = focas_path or os.environ.get("FOCAS_PATH", DEFAULT_FOCAS_PATH)
        self.handle = c_ushort(0)
        self.is_connected = False
        self.fwlib = None
        self._init_library()

    def _init_library(self):
        """Loads Fwlib64.dll and binds argument types."""
        dll_file = os.path.join(self.focas_path, "Fwlib64.dll")
        if not os.path.exists(dll_file):
            raise FileNotFoundError(f"Fwlib64.dll not found at: {dll_file}")

        try:
            # Set directory so dependent dlls (fwlib32, etc.) can be loaded
            ctypes.windll.kernel32.SetDllDirectoryW(self.focas_path)
            self.fwlib = ctypes.WinDLL(dll_file)

            # Bind cnc_allclibhndl3
            self.fwlib.cnc_allclibhndl3.argtypes = [c_char_p, c_ushort, c_long, POINTER(c_ushort)]
            self.fwlib.cnc_allclibhndl3.restype = c_short

            # Bind cnc_freelibhndl
            self.fwlib.cnc_freelibhndl.argtypes = [c_ushort]
            self.fwlib.cnc_freelibhndl.restype = c_short

            # Bind cnc_statinfo
            self.fwlib.cnc_statinfo.argtypes = [c_ushort, POINTER(ODBST)]
            self.fwlib.cnc_statinfo.restype = c_short

        except Exception as e:
            raise RuntimeError(f"Failed to load FANUC FOCAS library: {e}")

    def connect(self):
        """
        Connects to the FANUC CNC controller via Ethernet.
        Returns (success: bool, error_code_or_handle)
        """
        if self.is_connected:
            return True, self.handle.value

        handle_var = c_ushort()
        ret = self.fwlib.cnc_allclibhndl3(
            self.ip.encode("ascii"),
            self.port,
            self.timeout,
            byref(handle_var)
        )

        if ret == 0:
            self.handle = handle_var
            self.is_connected = True
            return True, self.handle.value
        else:
            self.is_connected = False
            return False, ret

    def read_status(self):
        """
        Calls cnc_statinfo to query current machine execution flags.
        Returns (success: bool, ODBST or error_code)
        """
        if not self.is_connected:
            connected, err = self.connect()
            if not connected:
                return False, f"Connection failed (FOCAS code: {err})"

        stat = ODBST()
        ret = self.fwlib.cnc_statinfo(self.handle, byref(stat))

        if ret == 0:
            return True, stat
        else:
            # Check if connection dropped
            if ret in [-16, -8]:  # Socket error or invalid handle
                self.disconnect()
            return False, ret

    def disconnect(self):
        """Releases the FOCAS library handle."""
        if self.is_connected and self.handle.value != 0:
            try:
                self.fwlib.cnc_freelibhndl(self.handle)
            except Exception:
                pass
            self.is_connected = False
            self.handle = c_ushort(0)
            return True
        return False
