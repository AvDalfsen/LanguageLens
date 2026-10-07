import pytest
import sys
from language_lens.services.hotkey import (
    normalize_hotkey, display_hotkey, parse_hotkey, WindowsHotkeyListener,
    MOD_NOREPEAT, MOD_CONTROL, MOD_ALT, MOD_SHIFT,
)
from language_lens.config import Settings, validate_settings, save_settings, load_settings


@pytest.mark.parametrize("text,canonical,modifiers,key", [
    ("F8", "<f8>", 0, 0x77),
    ("F24", "<f24>", 0, 0x87),
    ("Ctrl+Alt+Q", "<ctrl>+<alt>+q", MOD_CONTROL | MOD_ALT, ord("Q")),
    ("<shift>+<ctrl>+t", "<ctrl>+<shift>+t", MOD_CONTROL | MOD_SHIFT, ord("T")),
    ("Alt+Shift+9", "<alt>+<shift>+9", MOD_ALT | MOD_SHIFT, ord("9")),
    ("Control+Space", "<ctrl>+<space>", MOD_CONTROL, 0x20),
    ("Ctrl+PgDown", "<ctrl>+<pagedown>", MOD_CONTROL, 0x22),
    ("Shift+Left", "<shift>+<left>", MOD_SHIFT, 0x25),
    ("Ctrl+Return", "<ctrl>+<enter>", MOD_CONTROL, 0x0D),
    ("Esc", "<escape>", 0, 0x1B),
])
def test_custom_shortcuts_round_trip_and_map_to_windows_keys(text, canonical, modifiers, key):
    assert normalize_hotkey(text) == canonical
    assert normalize_hotkey(display_hotkey(canonical)) == canonical
    assert parse_hotkey(text) == (MOD_NOREPEAT | modifiers, key)


@pytest.mark.parametrize("value", [None, {}, 42, "", "Ctrl", "Ctrl+Ctrl+Q", "Ctrl+A+B",
    "Ctrl+", "Ctrl++Q", "Ctrl+K, Ctrl+C", "F0", "F25", "F12", "Ctrl+F12", "Win+Q",
    "Meta+Q", "Alt+Tab", "Ctrl+Alt+Delete", "é", "Ctrl+;", "a" * 129])
def test_invalid_or_reserved_shortcuts_are_rejected_synchronously(value):
    with pytest.raises(ValueError):
        normalize_hotkey(value)
    with pytest.raises(ValueError):
        WindowsHotkeyListener(value, lambda: None)
    assert validate_settings({"hotkey": value}).hotkey == "<f8>"


def test_f8_default_and_existing_shortcuts_are_preserved(tmp_path):
    assert Settings().hotkey == "<f8>"
    assert load_settings(tmp_path / "missing.json").hotkey == "<f8>"
    for value in ("<ctrl>+<shift>+t", "<ctrl>+<alt>+q", "<f9>"):
        path = tmp_path / "settings.json"
        save_settings(Settings(hotkey=value), path)
        assert load_settings(path).hotkey == value


@pytest.mark.skipif(sys.platform != "win32", reason="Windows hotkey API")
def test_native_listener_can_suspend_and_resume_without_leaving_threads():
    # No key injection or desktop capture. Use an uncommon chord and release
    # it immediately; skip if another application already owns it.
    listener = WindowsHotkeyListener("<ctrl>+<shift>+<f23>", lambda: None)
    try:
        try:
            listener.start()
        except RuntimeError as error:
            pytest.skip(str(error))
        thread = listener._thread
        listener.stop()
        assert not thread.is_alive()
        for _ in range(10):
            listener.start()
            thread = listener._thread
            listener.stop()
            assert not thread.is_alive()
    finally:
        listener.stop()
