"""Regressions from the independent UI translation audit."""
import ast
from pathlib import Path
import pytest
from PySide6.QtWidgets import QMenu, QMessageBox
from language_lens.config import Settings
from language_lens.i18n import UI_LANGUAGES, catalogs, language, set_language, tr, translate_ui
from language_lens.ui.help import HelpDialog

@pytest.fixture(autouse=True)
def english_ui():
    set_language("en")
    yield
    set_language("en")

@pytest.mark.parametrize("code", [code for _, code in UI_LANGUAGES])
def test_controls_created_in_saved_language_round_trip(qapp, code):
    set_language(code)
    menu = QMenu()
    action = menu.addAction(tr("Settings"))
    translate_ui(menu)
    help_dialog = HelpDialog()
    page = help_dialog.browser.toPlainText()
    set_language("en")
    translate_ui(menu, code)
    translate_ui(help_dialog, code)
    assert action.text() == "Settings"
    assert help_dialog.windowTitle() == "Help and about — Language Lens"
    assert help_dialog.topics.itemText(0) == "Getting started"
    assert help_dialog.browser.toPlainText() == page
    help_dialog.close()


def test_every_literal_translation_call_is_in_the_catalog():
    sources = catalogs()["sources"]
    for path in (Path(__file__).parents[1] / "src/language_lens").rglob("*.py"):
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if (isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
                    and node.func.id == "tr" and node.args
                    and isinstance(node.args[0], ast.Constant)):
                assert node.args[0].value in sources, (path.name, node.lineno, node.args[0].value)


@pytest.mark.parametrize("code", [code for _, code in UI_LANGUAGES])
def test_worker_progress_and_retry_values_are_localized(qapp, code):
    from language_lens.i18n import tr_message
    set_language(code)
    assert tr_message("Downloading model.zip (attempt 2/4)…") == tr(
        "Downloading {item} (attempt {attempt}/{attempts})…", item="model.zip", attempt="2", attempts="4")
    assert tr_message("Downloading Japanese pronunciation…") == tr(
        "Downloading {item}…", item="Japanese pronunciation")
    assert tr_message("Checking ja sentence model…") == tr("Checking {code} sentence model…", code="ja")
    assert tr_message("Unexpected diagnostic {path}") == "Unexpected diagnostic {path}"


def test_switch_preserves_original_template_arguments(qapp):
    from PySide6.QtWidgets import QLabel
    from language_lens.i18n import tr_message
    set_language("nl")
    label = QLabel(tr_message("Downloading Japanese pronunciation…"))
    translate_ui(label)
    set_language("ja")
    translate_ui(label, "nl")
    assert label.text() == tr("Downloading {item}…", item="Japanese pronunciation")
    set_language("en")
    translate_ui(label, "ja")
    assert label.text() == "Downloading Japanese pronunciation…"


@pytest.mark.parametrize("code", [code for _, code in UI_LANGUAGES if code != "en"])
def test_standard_message_box_button_uses_ui_language(qapp, monkeypatch, code):
    from language_lens.i18n import MessageBox
    set_language(code)
    seen = []
    def inspect(dialog):
        seen.append(dialog.button(QMessageBox.StandardButton.Ok).text())
        return QMessageBox.StandardButton.Ok
    monkeypatch.setattr(QMessageBox, "exec", inspect)
    result = MessageBox.warning(None, tr("Error"), tr("Translation unavailable"))
    assert seen == [tr("OK")]
    assert result == QMessageBox.StandardButton.Ok


@pytest.mark.parametrize("code", [code for _, code in UI_LANGUAGES])
def test_hotkey_rejection_is_localized_without_changing_shortcut(qapp, code):
    from language_lens.i18n import tr_message
    from language_lens.services.hotkey import normalize_hotkey
    set_language(code)
    with pytest.raises(ValueError) as exc:
        normalize_hotkey("F12")
    source = str(exc.value)
    assert source in catalogs()["sources"]
    assert tr_message(source) == tr(source)
    assert normalize_hotkey("Ctrl+Alt+Q") == "<ctrl>+<alt>+q"


def test_model_management_confirmations_have_no_english_fragments(qapp, monkeypatch):
    from language_lens.ui import setup
    monkeypatch.setattr(setup.ServiceJob, "start", lambda *args: None)
    window = setup.SetupWindow(Settings(ui_language="nl"))
    window._status_timer.stop()
    window._apply_model_status({"ready": True, "prepared": True, "route": ["en", "nl"]})
    messages = []
    monkeypatch.setattr(setup, "question", lambda parent, title, text, buttons: messages.append(text))
    window._manage_model("remove")
    window._manage_model("repair")
    assert len(messages) == 2
    assert all("Backups are kept" not in text and "Removing shared packages" not in text for text in messages)
    assert tr("Backups are kept beside the Argos packages directory. Continue?") in messages[0]
    window.shutdown()



def test_dynamic_status_switches_after_render_cache_eviction(qapp):
    from PySide6.QtWidgets import QLabel
    from language_lens.i18n import tr_message
    set_language("nl")
    label = QLabel(tr("Preparing download…"))
    translate_ui(label)
    label.setText(tr_message("Downloading Japanese pronunciation…"))
    for count in range(700):
        tr("Found {count} words. Hover for details; click to pin. Use the left and right arrow keys to browse words.", count=count)
    set_language("ja")
    translate_ui(label, "nl")
    assert label.text() == tr("Downloading {item}…", item="Japanese pronunciation")



@pytest.mark.parametrize("code", [code for _, code in UI_LANGUAGES])
def test_builtin_text_menus_follow_ui_language_and_keep_shortcuts(qapp, code):
    from PySide6.QtWidgets import QLineEdit, QTextBrowser
    set_language(code)
    line = QLineEdit("F8")
    menu = line.createStandardContextMenu()
    captions = [action.text() for action in menu.actions()]
    if code == "en":
        assert "&Copy\tCtrl+C" in captions
    else:
        assert tr("Copy selection") + "\tCtrl+C" in captions
        assert tr("Select all") + "\tCtrl+A" in captions
    assert any("Ctrl+Z" in caption for caption in captions)
    browser = QTextBrowser()
    menu = browser.createStandardContextMenu()
    if code != "en":
        assert tr("Copy link address") in [action.text() for action in menu.actions()]
    assert line.text() == "F8"
