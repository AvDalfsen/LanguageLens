import json
import pytest

from language_lens.config import Settings, load_settings, save_settings


@pytest.mark.parametrize("removed", ["ar", "ko"])
@pytest.mark.parametrize("field", ["source_language", "target_language", "ui_language"])
def test_retired_language_settings_fall_back_without_resetting_other_preferences(tmp_path, removed, field):
    path = tmp_path / "settings.json"
    raw = {"source_language": "ja", "target_language": "nl", "ui_language": "de",
           "speech_speed": .8, "speech_voices": {removed: "retired", "en": "en_US-lessac-medium"}}
    raw[field] = removed
    path.write_text(json.dumps(raw), encoding="utf-8")
    settings = load_settings(path)
    assert getattr(settings, field) == getattr(Settings(), field)
    for unchanged in {"source_language", "target_language", "ui_language"} - {field}:
        assert getattr(settings, unchanged) == raw[unchanged]
    assert settings.speech_speed == .8
    assert settings.speech_voices == {"en": "en_US-lessac-medium"}
    save_settings(settings, path)
    assert load_settings(path) == settings


def test_retired_languages_are_absent_from_application_catalogs():
    from language_lens.config import LANGUAGES
    from language_lens.i18n import UI_LANGUAGES, catalogs, _language_names
    from language_lens.services import sentence_models, translation_assets, voices
    from language_lens.services.ocr_profiles import PROFILES_BY_LANGUAGE
    from language_lens.services.ocr_settings import SETTINGS_BY_LANGUAGE

    removed = {"ar", "ko"}
    supported = {code for _, code in LANGUAGES}
    assert len(supported) == 23 and not supported & removed
    assert {code for _, code in UI_LANGUAGES} == supported
    assert set(catalogs()["languages"]) == supported
    assert set(_language_names()) == supported
    assert all(set(locale["languages"]) == supported for locale in _language_names().values())
    assert set(PROFILES_BY_LANGUAGE) == set(SETTINGS_BY_LANGUAGE) == supported
    assert set(sentence_models.catalog()["languages"]) == supported
    assert not set(sentence_models.catalog()["models"]) & removed
    assert {voice.language for voice in voices.VOICES} == supported
    catalog = translation_assets.catalog()
    for field in ("full_text", "words"):
        assert all(not set(pair.split("-")) & removed for pair in catalog[field])
    assert all(model.get("source") not in removed and model.get("target") not in removed
               for model in catalog["models"].values())


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


def test_language_feature_preferences_round_trip_and_keep_legacy_defaults(tmp_path):
    path = tmp_path / "settings.json"
    settings = Settings(source_language="ja", japanese_word_lookup=False,
                        chinese_word_lookup=False, show_ipa=True)
    save_settings(settings, path)
    restored = load_settings(path)
    assert restored == settings
    assert not restored.word_lookup_enabled
    assert restored.speech_enabled and restored.show_ipa
    restored.source_language = "en"
    assert restored.word_lookup_enabled and restored.speech_enabled and restored.show_ipa
    path.write_text('{"source_language": "ja", "japanese_word_lookup": "false"}', encoding="utf-8")
    legacy = load_settings(path)
    assert legacy.japanese_word_lookup and legacy.chinese_word_lookup
