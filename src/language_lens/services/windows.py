from __future__ import annotations

import ctypes
from ctypes import wintypes
import sys


SW_RESTORE = 9


def _user32():
    """Declare HWND-sized arguments/results rather than ctypes' default int."""
    user32 = ctypes.windll.user32
    user32.GetForegroundWindow.argtypes = []
    user32.GetForegroundWindow.restype = wintypes.HWND
    for name in ("IsWindow", "IsIconic", "SetForegroundWindow"):
        function = getattr(user32, name)
        function.argtypes = [wintypes.HWND]
        function.restype = wintypes.BOOL
    user32.ShowWindow.argtypes = [wintypes.HWND, ctypes.c_int]
    user32.ShowWindow.restype = wintypes.BOOL
    return user32


def foreground_window() -> int | None:
    if sys.platform != "win32":
        return None
    handle = _user32().GetForegroundWindow()
    return int(handle) if handle else None


def restore_foreground(handle: int | None) -> bool:
    """Best-effort restoration of the window active before capture."""
    if sys.platform != "win32" or not handle:
        return False
    user32 = _user32()
    window = wintypes.HWND(handle)
    if not user32.IsWindow(window):
        return False
    # SW_RESTORE also unmaximizes a visible window. Use it only if minimized.
    if user32.IsIconic(window):
        user32.ShowWindow(window, SW_RESTORE)
    return bool(user32.SetForegroundWindow(window))

