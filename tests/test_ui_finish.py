"""Audit 10–12: no downloads, real desktop captures or saved preferences."""
from types import SimpleNamespace

import pytest
from PySide6.QtCore import QObject, QRect, Qt, Signal
from PySide6.QtGui import QPixmap
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from language_lens.config import Settings
from language_lens.domain import OcrLine, WordTranslation
from language_lens.services.speech import SpeechJob
from language_lens.ui import pronunciation, review, setup
from language_lens.ui.progress import TransferMetrics
from language_lens.ui.sections import copy_menu


class VoiceJob(QObject):
    activity_changed = Signal(bool)
    stage_changed = Signal(str)
    progress = Signal(int, int)
    succeeded = Signal(object)
    failed = Signal(str)
    cancelled = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.active = False

    def start(self, *_args):
        self.active = True
        self.activity_changed.emit(True)

    def cancel(self):
        self.active = False
        self.activity_changed.emit(False)
        self.cancelled.emit()

    shutdown = cancel


@pytest.fixture
def voice_progress(qapp, monkeypatch):
    clock = [100.0]
    monkeypatch.setattr(pronunciation, "monotonic", lambda: clock[0])
    monkeypatch.setattr(pronunciation, "SpeechJob", VoiceJob)
    monkeypatch.setattr(pronunciation, "voice_present", lambda _voice: False)
    monkeypatch.setattr(pronunciation, "runtime_ready", lambda: True)
    monkeypatch.setattr(pronunciation, "voice_runtime_ready", lambda _voice: True)
    widget = pronunciation.PronunciationSettings(Settings(show_ipa=True))
    widget.show()
    widget.install.click()
    yield widget, clock
    widget.shutdown()
    widget.close()


def test_voice_speed_stall_verification_and_cancellation(voice_progress):
    widget, clock = voice_progress
    assert "Checking voice files" in widget.status.text()
    assert widget.progress.maximum() == 0 and widget._progress_timer.isActive()
    widget.download.stage_changed.emit("downloading")
    widget.download.progress.emit(0, 10_000_000)
    clock[0] = 102
    widget.download.progress.emit(4_000_000, 10_000_000)
    assert widget.progress.value() == 400
    assert "40.0%" in widget.download_details.text()
    assert "2.0 MB/s" in widget.download_details.text()
    for timestamp in (103, 104, 105, 106):
        clock[0] = timestamp
        widget._update_download_metrics()
    assert "0 B/s" in widget.download_details.text()
    assert "Waiting for data (4 s)" in widget.download_details.text()
    widget.download.progress.emit(10_000_000, 10_000_000)
    assert widget.progress.value() == 1000
    widget.download.stage_changed.emit("verifying")
    assert widget.progress.maximum() == 0
    assert "Verifying voice files" in widget.status.text()
    assert "/s" not in widget.download_details.text()
    assert "installed" not in widget.status.text().lower()
    assert widget.install.text() == "Cancel download"
    assert not widget.ipa_accent_note.isHidden()
    widget.install.click()
    assert not widget._progress_timer.isActive() and widget.progress.isHidden()
    assert widget.install.isEnabled() and widget.install.text().startswith("Download voice")


def test_cached_voice_files_do_not_inflate_transfer_rate(voice_progress):
    widget, clock = voice_progress
    widget.download.stage_changed.emit("checking")
    widget.download.progress.emit(8_000_000, 10_000_000)  # validated, not transferred
    assert "/s" not in widget.download_details.text()
    widget.download.stage_changed.emit("downloading")
    widget.download.progress.emit(8_000_000, 10_000_000)
    clock[0] = 102
    widget.download.progress.emit(9_000_000, 10_000_000)
    assert "500.0 KB/s" in widget.download_details.text()


def test_transfer_metrics_unknown_size_and_restart():
    metrics = TransferMetrics(100)
    metrics.update(0, None, 100)
    metrics.text(100)
    metrics.update(100_000, None, 101)
    assert "100.0 KB/s" in metrics.text(101)
    assert "%" not in metrics.text(101)
    metrics.update(0, 200_000, 102)
    assert "0.0%" in metrics.text(102) and "0 B/s" in metrics.text(102)
    metrics.reset(103)
    assert metrics.text(105) == "2 s elapsed"


def test_speech_worker_phase_protocol_reaches_ui_and_ignores_cancelled_events(qapp, tmp_path):
    job = SpeechJob(root=tmp_path)
    stages, amounts = [], []
    job.stage_changed.connect(stages.append)
    job.progress.connect(lambda done, total: amounts.append((done, total)))
    output = [b'{"stage":"verifying","done":5,"total":5}\n']
    job._process = SimpleNamespace(readAllStandardOutput=lambda: output.pop(0))
    job._read()
    assert stages == ["verifying"] and amounts == [(5, 5)]
    job._cancelled = True
    job._timer.stop()
    output.append(b'{"stage":"downloading","done":1,"total":5}\n')
    job._read()
    assert stages == ["verifying"] and amounts == [(5, 5)]
    assert not job._timer.isActive()
    job._timer.stop()
    job._process = None


def test_required_action_stays_prominent_and_maintenance_is_optional(qapp, monkeypatch):
    monkeypatch.setattr(setup.ServiceJob, "start", lambda *_args, **_kw: None)
    window = setup.SetupWindow(Settings(speech_enabled=False))
    window.show()
    window._status_timer.stop()
    window._apply_model_status({"ready": False, "prepared": False, "route": []})
    qapp.processEvents()
    assert window.prepare_button.isVisible()
    assert window.maintenance.content.isHidden() and window.technical_details.content.isHidden()
    assert not window.repair_button.isVisible()
    window._apply_model_status({"ready": True, "prepared": True, "route": ["pt", "en"]})
    assert "Ready to capture" in window.model_status.text()
    assert not window.prepare_button.isVisible()  # optional check is inside the disclosure
    window.maintenance.toggle.setFocus()
    QTest.keyClick(window.maintenance.toggle, Qt.Key.Key_Space)
    assert window.prepare_button.isVisible() and window.repair_button.isVisible()
    window.maintenance.toggle.click()
    window._start_model_job("prepare")
    assert window.cancel_button.isVisible() and window.model_progress.isVisible()
    window._install_failed("test error")
    assert window.prepare_button.isVisible()  # readiness invalidated; next action reappears
    window.shutdown()
    window.close()


@pytest.fixture
def reader(review_factory):
    window, _tasks = review_factory(size=(1000, 800), selection=QRect(200, 100, 400, 40))
    return window


def scan(window, text="word word other"):
    window._ocr_finished([OcrLine(text, .99, ((0, 0), (400, 0), (400, 30), (0, 30)))])


def test_translation_progress_counts_unique_lookups_and_failures(reader):
    scan(reader)
    reader._translation_finished(("translated", {}))
    assert "0 of 2 completed (2 pending)" in reader.status.text()
    reader._translation_finished(("translated", {"word": WordTranslation(("woord",))}))
    assert "1 of 2 completed (1 pending)" in reader.status.text()
    reader._translation_finished(("translated", {"word": WordTranslation(("woord",)),
                                               "other": WordTranslation((), "failed")}))
    assert "pending" not in reader.status.text()
    assert "1 word lookup unavailable" in reader.status.text()
    assert "Use the left and right arrow keys" in reader.status.text()


def test_source_and_translation_copy_exact_text_without_changing_alignment(reader, qapp):
    text = "cafe\u0301 <b> & العربية"
    scan(reader, text)
    original = list(reader._hits)
    reader._translation_finished(("coffee & <tea>", {}))
    assert reader.recognized_text.text() == text
    assert reader.recognized_section.content.isHidden()
    reader.recognized_section.toggle.click()
    assert reader.recognized_text.isVisible()
    for label, expected, source in ((reader.recognized_text, text, lambda: reader._speech_text),
                                     (reader.translation, "coffee & <tea>", lambda: reader._translated_text)):
        menu = copy_menu(label, source)
        assert not menu.actions()[0].isEnabled()
        menu.actions()[1].trigger()
        assert qapp.clipboard().text() == expected
        menu.deleteLater()
        assert label.textInteractionFlags() & Qt.TextInteractionFlag.TextSelectableByKeyboard
        assert label.accessibleName()
    assert reader._hits == original
    reader._retry_ocr()
    assert not reader.recognized_text.text() and not reader._translated_text
    assert not reader.recognized_section.toggle.isEnabled()
    scan(reader, "new text")
    assert reader.recognized_text.text() == "new text" and reader.recognized_section.toggle.isEnabled()


def test_readonly_text_focus_order_and_selection_copy(reader, qapp):
    scan(reader)
    reader._translation_finished(("translated", {}))
    reader.recognized_section.toggle.click()
    reader.activateWindow()
    qapp.processEvents()
    reader.recognized_section.toggle.setFocus()
    QTest.keyClick(qapp.focusWidget(), Qt.Key.Key_Tab)
    assert reader.recognized_text.hasFocus()
    reader.recognized_text.setSelection(0, 4)
    QTest.keyClick(reader.recognized_text, Qt.Key.Key_C, Qt.KeyboardModifier.ControlModifier)
    assert QApplication.clipboard().text() == "word"
    menu = copy_menu(reader.recognized_text, lambda: reader._speech_text)
    assert menu.actions()[0].isEnabled()
    menu.actions()[0].trigger()
    assert QApplication.clipboard().text() == "word"
    menu.deleteLater()
    QTest.keyClick(qapp.focusWidget(), Qt.Key.Key_Tab)
    assert reader.translation.hasFocus()
