"""User interaction regressions from the Translator UI audit."""
import pytest
from PySide6.QtCore import QEvent, QPoint, QPointF, QRect, Qt
from PySide6.QtGui import QWheelEvent
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication
from language_lens.app import STYLESHEET
from language_lens.config import Settings
from language_lens.domain import OcrLine, WordTranslation
from language_lens.i18n import language_name, set_language, tr
from language_lens.ui import setup, pronunciation


@pytest.fixture
def settings_window(qapp, monkeypatch):
    monkeypatch.setattr(setup.ServiceJob, "start", lambda *a, **k: None)
    monkeypatch.setattr(pronunciation, "runtime_ready", lambda: True)
    monkeypatch.setattr(pronunciation, "voice_runtime_ready", lambda *a: True)
    monkeypatch.setattr(pronunciation, "voice_present", lambda *a: False)
    w = setup.SetupWindow(Settings(source_language="en", target_language="nl", tray_close_notice_shown=True))
    w.setStyleSheet(STYLESHEET)
    w._available_geometry = lambda: QRect(0, 0, 1600, 1400)
    w._status_timer.stop()
    w._apply_model_status({"ready": True, "prepared": True, "route": ["en", "nl"]})
    w.show()
    QTest.qWait(120)
    yield w
    w.shutdown()
    w.close()
    set_language("en")


@pytest.mark.parametrize("control", ["source", "target", "capture_scope", "ui_language"])
def test_page_scroll_cannot_edit_a_closed_choice(settings_window, control, qapp):
    w = settings_window
    field = getattr(w, control)
    for focused in (False, True):
        (field if focused else w.maintenance.toggle).setFocus()
        before = w.current_settings()
        event = QWheelEvent(QPointF(25, 15), QPointF(field.mapToGlobal(QPoint(25, 15))),
            QPoint(), QPoint(0, -120), Qt.MouseButton.NoButton, Qt.KeyboardModifier.NoModifier,
            Qt.ScrollPhase.NoScrollPhase, False)
        QApplication.sendEvent(field, event)
        assert w.current_settings() == before
        assert not event.isAccepted()


def test_disclosures_and_language_changes_keep_the_window_stable(settings_window):
    w = settings_window
    initial = w.size()
    events = []
    class Watcher(setup.QWidget):
        def eventFilter(self, watched, event):
            if event.type() in (QEvent.Type.Show, QEvent.Type.Hide):
                events.append(event.type())
            return False
    watcher = Watcher()
    w.scroll.verticalScrollBar().installEventFilter(watcher)
    w.maintenance.toggle.click()
    w.technical_details.toggle.click()
    w.performance.toggle.click()
    QTest.qWait(150)
    assert w.size() == initial and w.width() <= 820
    assert not (QEvent.Type.Show in events and QEvent.Type.Hide in events)
    assert w.current_settings().settings_window_size is None
    for code in ("de", "ar", "ja", "en"):
        w.ui_language.setCurrentIndex(w.ui_language.findData(code))
        QTest.qWait(100)
        assert w.size() == initial
        assert w.source.currentData() == "en" and w.target.currentData() == "nl"


def test_short_window_preserves_a_useful_settings_view(settings_window):
    w = settings_window
    w.resize(610, 350)
    QTest.qWait(120)
    assert w._intro.isHidden()
    assert w.scroll.viewport().height() >= 120
    assert w.try_button.isVisible() and w.start_button.isVisible()


def test_check_failure_replaces_ready_appearance_and_exposes_retry(settings_window):
    w = settings_window
    w.refresh_model_status()
    w._status_timer.stop()
    w._status_failed("Cannot read files")
    assert w.model_status.palette().color(w.model_status.foregroundRole()).name() == "#f7c96b"
    assert w.prepare_button.isVisible() and w.prepare_button.text() == "Retry file check"
    assert not w.capture_ready


def test_voice_error_survives_ui_translation_and_speed_is_a_saved_preference(settings_window):
    w = settings_window
    w.pronunciation._download_failed("Connection interrupted")
    w.ui_language.setCurrentIndex(w.ui_language.findData("fr"))
    assert w.pronunciation.status.text() == tr("Voice download failed: {error}", error="Connection interrupted")
    edits = []
    w.preferences_changed.connect(lambda: edits.append(w.current_settings().speech_speed))
    w.pronunciation.speed_slider.setValue(75)
    assert edits[-1] == .75
    assert w.pronunciation.player.speed == .75
    assert not w.maintenance.isAncestorOf(w.keep_translation_models_loaded)
    assert w.performance.isAncestorOf(w.keep_translation_models_loaded)


def scan(w):
    w._ocr_finished([OcrLine("Read and learn a language", .99, ((0, 0), (470, 0), (470, 35), (0, 35)))])
    w._translation_finished(("Lees en leer een taal.", {"Read": WordTranslation(("Lees", "gelezen"))}))
    QApplication.processEvents()


def test_selecting_text_owns_arrows_and_copy_has_no_caption(review_factory, qapp):
    w, _ = review_factory()
    scan(w)
    w.recognized_section.toggle.click()
    w.activateWindow()
    w.recognized_text.setFocus()
    w.recognized_text.setSelection(0, 4)
    QTest.keyClick(w.recognized_text, Qt.Key.Key_Right)
    assert w.recognized_text.hasFocus()
    assert w._current_word_index == -1
    w.copy_translation.click()
    assert qapp.clipboard().text() == "Lees en leer een taal."
    assert w.translation.text() == qapp.clipboard().text()
    w.canvas._hovered = w.canvas._hits[0]
    w.canvas._pinned = True
    w.canvas._refresh_bubble()
    label = w.canvas._bubble.translation
    label.setFocus()
    QTest.keyClick(label, Qt.Key.Key_A, Qt.KeyboardModifier.ControlModifier)
    QTest.keyClick(label, Qt.Key.Key_C, Qt.KeyboardModifier.ControlModifier)
    assert qapp.clipboard().text() == "Lees"
    assert w.canvas._bubble.pin.isVisible()
    w.canvas._bubble.pin.click()
    assert w.canvas._bubble.isHidden() and not w.canvas._pinned


@pytest.mark.parametrize("size", [(800, 600), (640, 480), (640, 360)])
def test_small_reviews_preserve_source_and_bound_word_details(review_factory, size, qapp):
    w, _ = review_factory(size=size, selection=QRect(75, 70, 480, 40))
    w.setStyleSheet(STYLESHEET)
    scan(w)
    QTest.qWait(120)
    selection = w.canvas.selection_display_rect().toRect().translated(w.canvas.pos())
    assert not selection.intersects(w._footer.geometry())
    w.canvas._hovered = w.canvas._hits[0]
    w.canvas._pinned = True
    w.canvas._refresh_bubble()
    QTest.qWait(80)
    popup = w.canvas._bubble.geometry()
    assert w.rect().contains(popup)
    assert not popup.intersects(w.canvas._source_to_display(w.canvas._hits[0].bounds).toRect().translated(w.canvas.pos()))
    assert w._footer.isHidden() or not popup.intersects(w._footer.geometry())
    w.canvas.dismiss_word()
    assert w._footer.isVisible()


def test_corrected_text_retranslates_without_false_word_coordinates(review_factory):
    w, tasks = review_factory()
    scan(w)
    assert w.canvas._hits
    w._apply_corrected_source("Read a corrected sentence.")
    assert w.recognized_text.text() == "Read a corrected sentence."
    assert not w.canvas._hits and not w._hits and not w._translated_text
    assert w.words.isHidden() and w.word_label.isHidden()
    assert tasks[-1].lines[0].text == w._speech_text
    assert not tasks[-1].words
    assert "Edited text" in w._word_instructions()
    assert "Edited text" in w.status.toolTip()
    w._translation_finished(("Lees een verbeterde zin.", {}))
    assert w.translation.text() == "Lees een verbeterde zin."
    assert w.copy_translation.isEnabled()
    w._retry_ocr()
    assert not w._corrected_source


def test_localized_language_names_and_rtl_disclosures(settings_window):
    w = settings_window
    w.ui_language.setCurrentIndex(w.ui_language.findData("de"))
    assert language_name("ja") == "Japanisch"
    assert w.source.itemText(w.source.findData("ja")) == "Japanisch"
    w.ui_language.setCurrentIndex(w.ui_language.findData("ar"))
    assert w.performance.toggle.arrowType() == Qt.ArrowType.LeftArrow
    w.performance.toggle.click()
    assert w.performance.toggle.arrowType() == Qt.ArrowType.DownArrow


def test_open_review_language_change_preserves_results_and_requests(review_factory):
    w, tasks = review_factory()
    scan(w)
    before = list(tasks)
    text, hits = w.translation.text(), list(w._hits)
    w.canvas._hovered = w.canvas._hits[0]
    w.canvas._pinned = True
    w.canvas._refresh_bubble()
    set_language("ar")
    w.refresh_language("en")
    assert tasks == before and w._hits == hits
    assert w.translation.text() == text
    assert w.copy_translation.text() == tr("Copy translation")
    assert w.words.itemText(0) == "1. Read"
    assert w.canvas._bubble.translation.text() == "Lees"
    assert w.layoutDirection() == Qt.LayoutDirection.RightToLeft
    set_language("en")
    w.refresh_language("ar")
    assert w.translation.text() == text and w.copy_translation.text() == "Copy translation"
