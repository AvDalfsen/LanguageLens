import ctypes
from ctypes import wintypes
from types import SimpleNamespace

import pytest

from language_lens.services import windows


class NativeFunction:
    def __init__(self, result):
        self.result = result
        self.calls = []

    def __call__(self, *args):
        self.calls.append(tuple(getattr(arg, "value", arg) for arg in args))
        return self.result


@pytest.fixture
def user32(monkeypatch):
    api = SimpleNamespace(
        GetForegroundWindow=NativeFunction(0x123456789),
        IsWindow=NativeFunction(True),
        IsIconic=NativeFunction(False),
        ShowWindow=NativeFunction(True),
        SetForegroundWindow=NativeFunction(True),
    )
    monkeypatch.setattr(windows.sys, "platform", "win32")
    monkeypatch.setattr(windows.ctypes, "windll", SimpleNamespace(user32=api), raising=False)
    return api


def test_foreground_handle_uses_pointer_sized_result(user32):
    assert windows.foreground_window() == 0x123456789
    assert user32.GetForegroundWindow.restype is wintypes.HWND
    assert user32.GetForegroundWindow.argtypes == []
    assert user32.SetForegroundWindow.argtypes == [wintypes.HWND]
    assert user32.SetForegroundWindow.restype is wintypes.BOOL
    assert user32.ShowWindow.argtypes == [wintypes.HWND, ctypes.c_int]


def test_visible_window_focus_does_not_change_placement(user32):
    assert windows.restore_foreground(0x123456789)
    assert not user32.ShowWindow.calls
    assert user32.SetForegroundWindow.calls == [(0x123456789,)]


def test_minimized_window_is_restored_before_focusing(user32):
    user32.IsIconic.result = True
    assert windows.restore_foreground(42)
    assert user32.ShowWindow.calls == [(42, windows.SW_RESTORE)]
    assert user32.SetForegroundWindow.calls == [(42,)]


def test_closed_window_is_not_focused(user32):
    user32.IsWindow.result = False
    assert not windows.restore_foreground(42)
    assert not user32.ShowWindow.calls
    assert not user32.SetForegroundWindow.calls


def test_windows_can_refuse_focus_without_forced_input(user32):
    user32.SetForegroundWindow.result = False
    assert not windows.restore_foreground(42)
    assert not user32.ShowWindow.calls


@pytest.mark.parametrize("handle", [None, 0])
def test_missing_window_does_not_call_windows(user32, handle):
    assert not windows.restore_foreground(handle)
    assert not user32.IsWindow.calls


def test_non_windows_does_not_load_user32(monkeypatch):
    monkeypatch.setattr(windows.sys, "platform", "linux")
    assert windows.foreground_window() is None
    assert not windows.restore_foreground(42)
