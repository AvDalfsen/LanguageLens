from __future__ import annotations

import ctypes
from ctypes import wintypes
import sys


SW_RESTORE = 9
VK_ESCAPE = 0x1B
KEYEVENTF_KEYUP = 0x0002


def foreground_window() -> int | None:
    if sys.platform != "win32":
        return None
    handle = ctypes.windll.user32.GetForegroundWindow()
    return int(handle) if handle else None


def press_escape() -> None:
    if sys.platform != "win32":
        return
    user32 = ctypes.windll.user32
    user32.keybd_event(VK_ESCAPE, 0, 0, 0)
    user32.keybd_event(VK_ESCAPE, 0, KEYEVENTF_KEYUP, 0)


def restore_foreground(handle: int | None) -> bool:
    """Best-effort restoration of the window active before capture."""
    if sys.platform != "win32" or not handle:
        return False
    user32 = ctypes.windll.user32
    if not user32.IsWindow(wintypes.HWND(handle)):
        return False
    user32.ShowWindow(wintypes.HWND(handle), SW_RESTORE)
    return bool(user32.SetForegroundWindow(wintypes.HWND(handle)))

