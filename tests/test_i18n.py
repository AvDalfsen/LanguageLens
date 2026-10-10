"""UI localization is offline and independent of the text-processing pair."""
import ast
from collections import Counter
from dataclasses import asdict
from html import escape
from pathlib import Path
from string import Formatter

import pytest
from PySide6.QtCore import Qt
from PySide6.QtGui import QKeySequence
from PySide6.QtWidgets import QMenu, QWidget

from language_lens.config import LANGUAGES, Settings, load_settings, save_settings, validate_settings
from language_lens.i18n import UI_LANGUAGES, catalogs, language, set_language, tr, translate_ui
from language_lens.ui.setup import SetupWindow


@pytest.fixture(autouse=True)
def english_ui():
    set_language("en")
    yield
    set_language("en")


def fields(text):
    return {name for _, name, _, _ in Formatter().parse(text) if name is not None}


def test_all_text_languages_have_complete_bundled_ui_catalogs():
    data = catalogs()
    codes = {code for _, code in LANGUAGES}
    assert codes == {code for _, code in UI_LANGUAGES} == set(data["languages"])
    for code, catalog in data["languages"].items():
        assert set(catalog) == set(data["english"]), code
        for key, value in catalog.items():
            assert value.strip(), (code, key)
            assert fields(value) == fields(data["english"][key]), (code, key)
    assert set(data["sources"].values()) <= set(data["english"])


@pytest.mark.parametrize("raw", [None, [], "xx", "pt-BR", 12])
def test_invalid_ui_language_defaults_to_english(raw):
    settings = validate_settings({"ui_language": raw, "source_language": "ja", "target_language": "nl"})
    assert settings.ui_language == "en"
    assert settings.source_language == "ja" and settings.target_language == "nl"


def test_legacy_settings_and_language_preference_round_trip(tmp_path):
    assert validate_settings({"source_language": "ja"}).ui_language == "en"
    path = tmp_path / "settings.json"
    settings = Settings(ui_language="pb", source_language="ja", target_language="nl")
    save_settings(settings, path)
    assert load_settings(path) == settings


@pytest.fixture
def window(qapp, monkeypatch):
    from language_lens.ui import setup, pronunciation
    monkeypatch.setattr(setup.ServiceJob, "start", lambda *args, **kwargs: pytest.fail("UI switching started a service job"))
    monkeypatch.setattr(pronunciation, "runtime_ready", lambda: True)
    monkeypatch.setattr(pronunciation, "voice_present", lambda *args: False)
    w = SetupWindow(Settings(source_language="ja", target_language="nl", speech_speed=.8))
    w._status_timer.stop()
    w._apply_model_status({"ready": True, "prepared": True, "route": ["ja", "en", "nl"]})
    yield w
    w.shutdown()


@pytest.mark.parametrize("code", [code for _, code in UI_LANGUAGES])
def test_live_switch_keeps_pair_voice_hotkey_readiness_and_job_objects(window, code):
    before = asdict(window.current_settings())
    jobs = (window.model_job, window._status_job, window.pronunciation.download)
    changes = []
    window.source.currentIndexChanged.connect(lambda *_: changes.append("source"))
    window.target.currentIndexChanged.connect(lambda *_: changes.append("target"))
    window.pronunciation.voices.currentIndexChanged.connect(lambda *_: changes.append("voice"))
    window.ui_language.setCurrentIndex(window.ui_language.findData(code))
    after = asdict(window.current_settings())
    assert after == {**before, "ui_language": code}
    assert not changes
    assert jobs == (window.model_job, window._status_job, window.pronunciation.download)
    assert window.capture_ready
    for widget in window.findChildren(QWidget):
        if hasattr(widget, "_lens_help_source"):
            source = widget._lens_help_source
            assert source in catalogs()["sources"]
            assert widget.toolTip() == '<div style="max-width: 420px">' + escape(tr(source)) + '</div>'
    assert window.start_button.text() == tr("Start listening")
    assert window.model_status.text() == tr("Ready to capture — required local files verified")
    assert window.ui_language.accessibleName() == tr("UI language")
    assert [window.ui_language.itemText(i) for i in range(6)] == [
        "Čeština", "Dansk", "Deutsch", "English", "Español", "Français",
    ]
    assert window.ui_language.findData("pb") < window.ui_language.findData("pt")
    assert window.ui_language.currentData() == code
    assert window.layoutDirection() == (Qt.LayoutDirection.RightToLeft if code == "ar" else Qt.LayoutDirection.LeftToRight)
    assert window.ui_language.parentWidget().layoutDirection() == Qt.LayoutDirection.LeftToRight
    window.ui_language.setCurrentIndex(window.ui_language.findData("en"))
    assert window.source.currentText() == "Japanese"
    assert window.hotkey.keySequence().toString(QKeySequence.SequenceFormat.PortableText) == "F8"


def test_switch_preserves_listening_and_running_model_task(window):
    window.set_listening("<ctrl>+<alt>+q")
    window._installing = True
    window.ui_language.setCurrentIndex(window.ui_language.findData("ar"))
    assert window._installing
    assert window.start_button.text() == tr("Pause listening")
    assert window.current_settings().hotkey == "<ctrl>+<alt>+q"
    assert not window.hotkey.isEnabled()
    window._installing = False


def test_language_change_does_not_apply_status_from_previous_pair(window):
    window.source.setCurrentIndex(window.source.findData("fr"))
    window._status_timer.stop()
    window.ui_language.setCurrentIndex(window.ui_language.findData("nl"))
    assert not window.capture_ready
    assert window.source.currentData() == "fr"


def test_tooltips_and_tray_round_trip(window):
    original = window.source.toolTip()
    menu = QMenu()
    action = menu.addAction("Settings")
    for code in ("nl", "ja", "ar", "en"):
        previous = language()
        window.ui_language.setCurrentIndex(window.ui_language.findData(code))
        translate_ui(menu, previous)
        assert action.text() == tr("Settings")
    assert window.source.toolTip() == original


def test_template_arguments_and_unknown_diagnostics_are_preserved():
    set_language("nl")
    message = tr("Could not check models: {error}", error="model/path {untrusted}")
    assert message == "De vertaalmodellen konden niet worden gecontroleerd: model/path {untrusted}"
    assert tr("Unknown low-level diagnostic {text}") == "Unknown low-level diagnostic {text}"
    assert "3" in tr("Found {count} words. Hover for details; click to pin. Use the left and right arrow keys to browse words.", count=3)


def test_localized_review_leaves_recognized_text_and_model_translations_untouched(review_factory):
    from language_lens.domain import OcrLine, WordTranslation
    set_language("ar")
    review, _ = review_factory()
    source = "Installed Missing"
    review._ocr_finished([OcrLine(source, .99, ((0, 0), (180, 0), (180, 25), (0, 25)))])
    review._translation_finished(("Settings", {"Installed": WordTranslation(("Missing",))}))
    assert review.recognized_text.text() == source
    assert review._translated_text == "Settings"
    assert "Settings" in review.translation.text()
    assert review.read_button.text() == tr("Read selection")
    review.shutdown_speech()

def test_distinct_english_messages_never_share_a_translation_key():
    data = catalogs()
    assert data["languages"]["en"] == data["english"]
    assert len(set(data["sources"].values())) == len(data["sources"])
    for source, key in data["sources"].items():
        assert data["english"][key] == source, (key, source)


def test_static_tooltips_have_complete_dedicated_translations():
    data = catalogs()
    sources = set()
    root = Path(__file__).parents[1] / "src" / "language_lens"
    for path in root.rglob("*.py"):
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if not isinstance(node, ast.Call):
                continue
            if isinstance(node.func, ast.Name) and node.func.id == "set_help" and len(node.args) > 1:
                # set_help owns translation and must retain the original English.
                assert not any(isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
                               and n.func.id == "tr" for n in ast.walk(node.args[1])), path
                sources.update(n.value for n in ast.walk(node.args[1])
                               if isinstance(n, ast.Constant) and isinstance(n.value, str))
            elif isinstance(node.func, ast.Attribute) and node.func.attr == "setToolTip" and node.args:
                argument = node.args[0]
                if isinstance(argument, ast.Constant) and argument.value != "Language Lens":
                    sources.add(argument.value)
                sources.update(n.args[0].value for n in ast.walk(argument)
                               if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
                               and n.func.id == "tr" and n.args
                               and isinstance(n.args[0], ast.Constant))
    assert len(sources) >= 30
    for source in sources:
        key = data["sources"][source]
        assert key in data["tooltips"]
        for code, locale in data["languages"].items():
            assert code == "en" or locale[key] != source, (code, key)


def test_tooltip_control_references_match_the_actual_localized_labels():
    data = catalogs()
    for code, locale in data["languages"].items():
        for key, references in data["references"].items():
            for reference, count in Counter(references).items():
                assert locale[key].count(locale[reference]) >= count, (code, key, reference)
        for token in ("A–Z", "0–9", "F1–F24", "F12", "F8", "Ctrl", "Alt", "Shift", "Windows"):
            assert token in locale["hotkey_recording_tip"], (code, token)
        for token in ("0.5×", "1.5×", "IPA"):
            assert token in locale["speech_speed_tip"], (code, token)


def test_capture_area_gold_standard_excludes_both_removed_sentences(window):
    source = window.capture_scope._lens_help_source
    assert source.endswith("memory, and reduces screenshot/rendering work.")
    assert "It does not improve" not in source
    assert "Try a capture now" not in source
    key = catalogs()["sources"][source]
    assert key == "capture_area_tip"
    assert catalogs()["references"][key] == ["all", "current"]


@pytest.mark.parametrize("code", [code for _, code in UI_LANGUAGES])
def test_start_and_pause_help_keep_english_sources_across_language_switches(window, code):
    start = window.start_button._lens_help_source
    window.set_listening("F8")
    pause = window.start_button._lens_help_source
    window.ui_language.setCurrentIndex(window.ui_language.findData(code))
    assert window.start_button._lens_help_source == pause
    assert escape(tr(pause)) in window.start_button.toolTip()
    window.set_listening(None)
    assert window.start_button._lens_help_source == start
    assert escape(tr(start)) in window.start_button.toolTip()
    window.ui_language.setCurrentIndex(window.ui_language.findData("en"))
    assert escape(start) in window.start_button.toolTip()


def test_pronunciation_tooltips_translate_explanations_without_changing_phonemes(review_factory):
    from language_lens.domain import OcrLine
    set_language("fr")
    review, _ = review_factory()
    review._ocr_finished([OcrLine("Word", .99, ((0, 0), (180, 0), (180, 25), (0, 25)))])
    hit = review.canvas._hits[0]
    phones = "wˈɜːd"
    note = "No IPA display profile exists for this accent."
    reason = "Native source alignment unavailable."
    item = dict(start=hit.source_start, end=hit.source_end, text=hit.text,
                ipa=phones, phonemes=phones, mode="isolated", reason=reason,
                ipa_notation="engine", ipa_notes=(note,))
    review.canvas.set_pronunciations([item])
    review.canvas._hovered = hit
    review.canvas._refresh_bubble()
    popup = review.canvas._bubble
    assert tr(note) in popup.ipa.toolTip()
    assert tr(reason) in popup.detail.toolTip()
    assert tr("Original synthesis phonemes: [{phonemes}]", phonemes=phones) in popup.ipa.toolTip()
    assert popup.ipa.text() == "[" + phones + "]"
    assert item["phonemes"] == phones
    review.shutdown_speech()
