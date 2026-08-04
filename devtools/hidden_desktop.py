from __future__ import annotations

import ctypes
import os
import time
from ctypes import wintypes


def create_hidden_desktop() -> int:
    user32 = ctypes.WinDLL("user32", use_last_error=True)
    user32.CreateDesktopW.argtypes = [
        wintypes.LPCWSTR,
        wintypes.LPCWSTR,
        ctypes.c_void_p,
        wintypes.DWORD,
        wintypes.DWORD,
        ctypes.c_void_p,
    ]
    user32.CreateDesktopW.restype = wintypes.HANDLE
    user32.SetThreadDesktop.argtypes = [wintypes.HANDLE]
    user32.SetThreadDesktop.restype = wintypes.BOOL
    desktop_name = f"LineTrackerCapture-{os.getpid()}-{time.time_ns()}"
    desktop = user32.CreateDesktopW(desktop_name, None, None, 0, 0x10000000, None)
    if not desktop:
        raise ctypes.WinError(ctypes.get_last_error())
    if not user32.SetThreadDesktop(desktop):
        error = ctypes.WinError(ctypes.get_last_error())
        user32.CloseDesktop(desktop)
        raise error
    return int(desktop)


def close_hidden_desktop(desktop: int) -> None:
    user32 = ctypes.windll.user32
    user32.CloseDesktop.argtypes = [wintypes.HANDLE]
    user32.CloseDesktop.restype = wintypes.BOOL
    user32.CloseDesktop(desktop)
