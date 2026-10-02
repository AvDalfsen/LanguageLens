from __future__ import annotations

import ctypes
from ctypes import wintypes
import sys
from threading import Event, Thread
from collections.abc import Callable


MOD_ALT = 0x0001
MOD_CONTROL = 0x0002
MOD_SHIFT = 0x0004
MOD_WIN = 0x0008
MOD_NOREPEAT = 0x4000
WM_HOTKEY = 0x0312
WM_QUIT = 0x0012
HOTKEY_ID = 0x474C


def parse_hotkey(value: str) -> tuple[int, int]:
    tokens = [token.strip().lower() for token in value.split("+") if token.strip()]
    modifiers = MOD_NOREPEAT
    key_token: str | None = None
    for token in tokens:
        if token in {"<ctrl>", "<control>"}:
            modifiers |= MOD_CONTROL
        elif token == "<shift>":
            modifiers |= MOD_SHIFT
        elif token == "<alt>":
            modifiers |= MOD_ALT
        elif token in {"<win>", "<cmd>"}:
            modifiers |= MOD_WIN
        else:
            if key_token is not None:
                raise ValueError(f"Hotkey has more than one non-modifier key: {value}")
            key_token = token

    if key_token is None:
        raise ValueError(f"Hotkey has no key: {value}")
    if len(key_token) == 1:
        virtual_key = ord(key_token.upper())
    elif key_token == "<space>":
        virtual_key = 0x20
    elif key_token.startswith("<f") and key_token.endswith(">"):
        number = int(key_token[2:-1])
        if not 1 <= number <= 24:
            raise ValueError(f"Unsupported function key: {key_token}")
        virtual_key = 0x70 + number - 1
    else:
        raise ValueError(f"Unsupported hotkey key: {key_token}")
    return modifiers, virtual_key


class WindowsHotkeyListener:
    """Register a true Windows global hotkey on a dedicated message-loop thread."""

    def __init__(self, hotkey: str, callback: Callable[[], None]) -> None:
        if sys.platform != "win32":
            raise RuntimeError("Global hotkeys are currently implemented for Windows only.")
        self.hotkey = hotkey
        self.callback = callback
        self._thread: Thread | None = None
        self._thread_id: int | None = None
        self._ready = Event()
        self._error: str | None = None

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._ready.clear()
        self._error = None
        self._thread = Thread(target=self._run, name="language-lens-hotkey", daemon=True)
        self._thread.start()
        if not self._ready.wait(timeout=3):
            raise RuntimeError("Timed out while registering the global hotkey.")
        if self._error:
            raise RuntimeError(self._error)

    def stop(self) -> None:
        if self._thread_id is not None:
            ctypes.windll.user32.PostThreadMessageW(self._thread_id, WM_QUIT, 0, 0)
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2)
        self._thread = None
        self._thread_id = None

    def _run(self) -> None:
        user32 = ctypes.WinDLL("user32", use_last_error=True)
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        modifiers, virtual_key = parse_hotkey(self.hotkey)
        self._thread_id = int(kernel32.GetCurrentThreadId())
        if not user32.RegisterHotKey(None, HOTKEY_ID, modifiers, virtual_key):
            code = ctypes.get_last_error()
            self._error = (
                f"Windows could not register {self.hotkey} (error {code}). "
                "Another application may already use it; choose a different hotkey."
            )
            self._ready.set()
            return
        self._ready.set()
        message = wintypes.MSG()
        try:
            while user32.GetMessageW(ctypes.byref(message), None, 0, 0) > 0:
                if message.message == WM_HOTKEY and int(message.wParam) == HOTKEY_ID:
                    self.callback()
        finally:
            user32.UnregisterHotKey(None, HOTKEY_ID)
