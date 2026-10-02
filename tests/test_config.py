import json

from language_lens.config import Settings, load_settings, save_settings


def test_settings_round_trip(tmp_path):
    path = tmp_path / "settings.json"
    expected = Settings(source_language="de", target_language="nl", send_escape=False)
    save_settings(expected, path)
    assert load_settings(path) == expected


def test_invalid_settings_fall_back_to_defaults(tmp_path):
    path = tmp_path / "settings.json"
    path.write_text("not json", encoding="utf-8")
    assert load_settings(path) == Settings()


def test_legacy_pause_game_setting_is_migrated(tmp_path):
    path = tmp_path / "settings.json"
    path.write_text(json.dumps({"pause_game": False}), encoding="utf-8")

    assert not load_settings(path).send_escape
