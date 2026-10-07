import json
import pytest

from language_lens.config import Settings, load_settings, save_settings


@pytest.mark.parametrize("scope", ["all", "current"])
def test_settings_round_trip(tmp_path, scope):
    path = tmp_path / "settings.json"
    expected = Settings(source_language="de", target_language="nl", capture_scope=scope)
    save_settings(expected, path)
    assert load_settings(path) == expected


def test_settings_without_capture_scope_keep_all_monitor_default(tmp_path):
    path = tmp_path / "settings.json"
    path.write_text(json.dumps({"source_language": "de"}), encoding="utf-8")
    assert load_settings(path).capture_scope == "all"


def test_invalid_settings_fall_back_to_defaults(tmp_path):
    path = tmp_path / "settings.json"
    path.write_text("not json", encoding="utf-8")
    assert load_settings(path) == Settings()


def test_removed_pause_settings_are_ignored_and_dropped_on_save(tmp_path):
    path = tmp_path / "settings.json"
    path.write_text(json.dumps({
        "pause_game": True, "send_escape": True, "source_language": "nl",
    }), encoding="utf-8")

    settings = load_settings(path)
    assert settings.source_language == "nl"
    assert not hasattr(settings, "send_escape")
    save_settings(settings, path)
    raw = json.loads(path.read_text(encoding="utf-8"))
    assert "send_escape" not in raw
    assert "pause_game" not in raw


def test_window_preferences_round_trip(tmp_path):
    path = tmp_path / "settings.json"
    settings = Settings(settings_window_size=[920, 650], settings_window_maximized=True)
    save_settings(settings, path)
    assert load_settings(path) == settings


@pytest.mark.parametrize("size", [None, "820x650", [], [800], [800, 600, 1], [True, 600], [-1, 600], [800, 0]])
def test_invalid_window_size_falls_back_to_content_fitting(tmp_path, size):
    path = tmp_path / "settings.json"
    path.write_text(json.dumps({"settings_window_size": size, "settings_window_maximized": "false"}), encoding="utf-8")
    settings = load_settings(path)
    assert settings.settings_window_size is None
    assert settings.settings_window_maximized is False
