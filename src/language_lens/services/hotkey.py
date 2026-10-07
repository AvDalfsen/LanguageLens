from __future__ import annotations

import ctypes
from ctypes import wintypes
import sys
import re
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

NAMED_KEYS = {
    "space": 0x20, "tab": 0x09, "backspace": 0x08, "enter": 0x0D,
    "escape": 0x1B, "insert": 0x2D, "delete": 0x2E, "home": 0x24,
    "end": 0x23, "pageup": 0x21, "pagedown": 0x22, "left": 0x25,
    "up": 0x26, "right": 0x27, "down": 0x28, "pause": 0x13,
}
MODIFIERS = {"ctrl": MOD_CONTROL, "alt": MOD_ALT, "shift": MOD_SHIFT}
ALIASES = {"control": "ctrl", "return": "enter", "esc": "escape", "pgup": "pageup", "pgdown": "pagedown"}


def normalize_hotkey(value: str) -> str:
    """Validate one chord, accepting both saved legacy tokens and Qt portable text."""
    if not isinstance(value, str) or not value.strip() or len(value) > 128:
        raise ValueError("Press a key or a key combination to choose a capture shortcut.")
    tokens = value.split("+")
    modifiers, keys = set(), []
    for raw in tokens:
        token = raw.strip().lower()
        if token.startswith("<") and token.endswith(">"):
            token = token[1:-1]
        token = ALIASES.get(token, token)
        if token in {"win", "meta", "cmd"}:
            raise ValueError("Windows-key shortcuts are reserved by Windows. Choose Ctrl, Alt or Shift instead.")
        if token in MODIFIERS:
            if token in modifiers:
                raise ValueError("Use each modifier only once.")
            modifiers.add(token)
        elif re.fullmatch(r"[a-z0-9]", token) or token in NAMED_KEYS:
            keys.append(token)
        elif re.fullmatch(r"f(?:[1-9]|1[0-9]|2[0-4])", token):
            if token == "f12":
                raise ValueError("F12 is reserved by Windows for debuggers. Choose another key.")
            keys.append(token)
        else:
            raise ValueError("Use a letter (A–Z), number (0–9), F1–F24 except F12, or a navigation key, with optional Ctrl, Alt or Shift.")
    if len(keys) != 1:
        raise ValueError("Choose exactly one key, optionally combined with Ctrl, Alt or Shift; not a sequence of shortcuts.")
    key = keys[0]
    if (key == "tab" and "alt" in modifiers) or (key == "delete" and {"ctrl", "alt"} <= modifiers):
        raise ValueError("That combination is reserved by Windows. Choose another shortcut.")
    return "+".join([f"<{name}>" for name in MODIFIERS if name in modifiers]
                    + [key if len(key) == 1 else f"<{key}>"])


def display_hotkey(value: str) -> str:
    names = {"ctrl": "Ctrl", "alt": "Alt", "shift": "Shift", "pageup": "PgUp", "pagedown": "PgDown"}
    return "+".join(names.get(token.strip("<>"), token.strip("<>").capitalize())
                    for token in normalize_hotkey(value).split("+"))


def parse_hotkey(value: str) -> tuple[int, int]:
    tokens = normalize_hotkey(value).split("+")
    modifiers = MOD_NOREPEAT
    for token in tokens[:-1]:
        modifiers |= MODIFIERS[token.strip("<>")]
    key_token = tokens[-1].strip("<>")
    if len(key_token) == 1:
        virtual_key = ord(key_token.upper())
    elif key_token in NAMED_KEYS:
        virtual_key = NAMED_KEYS[key_token]
    else:
        virtual_key = 0x70 + int(key_token[1:]) - 1  # validated function key
    return modifiers, virtual_key


class WindowsHotkeyListener:
    """Register a true Windows global hotkey on a dedicated message-loop thread."""

    def __init__(self, hotkey: str, callback: Callable[[], None]) -> None:
        if sys.platform != "win32":
            raise RuntimeError("Global hotkeys are currently implemented for Windows only.")
        self.hotkey = normalize_hotkey(hotkey)
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
        # Ensure PostThreadMessage can stop us even immediately after start().
        # RegisterHotKey does not guarantee this thread already has a queue.
        message = wintypes.MSG()
        user32.PeekMessageW(ctypes.byref(message), None, 0, 0, 0)
        if not user32.RegisterHotKey(None, HOTKEY_ID, modifiers, virtual_key):
            code = ctypes.get_last_error()
            self._error = (
                f"Windows could not register {display_hotkey(self.hotkey)} (error {code}). "
                "Another application or Windows may already use it; choose a different 'Capture hotkey'."
            )
            self._ready.set()
            return
        self._ready.set()
        try:
            while user32.GetMessageW(ctypes.byref(message), None, 0, 0) > 0:
                if message.message == WM_HOTKEY and int(message.wParam) == HOTKEY_ID:
                    self.callback()
        finally:
            user32.UnregisterHotKey(None, HOTKEY_ID)
