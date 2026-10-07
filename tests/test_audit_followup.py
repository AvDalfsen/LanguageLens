from dataclasses import asdict
import json
import socket
from types import SimpleNamespace
from uuid import uuid4
import zipfile

import pytest
from PySide6.QtCore import QRect
from PySide6.QtGui import QPixmap, QKeySequence

from language_lens.config import LANGUAGES, Settings, validate_settings, save_settings, load_settings
from language_lens.domain import OcrLine, WordTranslation
from language_lens.services import offline, task_worker
from language_lens.services.jobs import decode_line, ServiceJob
from language_lens.services.model_management import install_archive, retire
from language_lens.services.voices import VOICES, voices_for
from language_lens.ui import review, setup


@pytest.mark.parametrize("raw", [None, [], False, 42, "bad", {"source_language": []},
    {"speech_enabled": "false"}, {"speech_voices": []}, {"speech_voices": {"bad": "voice", "en": []}},
    {"min_ocr_confidence": float("nan")}, {"speech_speed": float("inf")},
    {"speech_speed": True}, {"speech_speed": 10 ** 1000}, {"hotkey": {}},
    {"settings_window_size": [10 ** 100, 600]}])
def test_malformed_config_recovers_without_startup_failure(raw):
    assert validate_settings(raw) == Settings()


def test_settings_write_failure_preserves_previous_file(monkeypatch, tmp_path):
    path = tmp_path / "settings.json"
    save_settings(Settings(), path)
    from pathlib import Path
    monkeypatch.setattr(Path, "replace", lambda *_: (_ for _ in ()).throw(OSError("disk full")))
    with pytest.raises(OSError):
        save_settings(Settings(source_language="ja"), path)
    assert load_settings(path) == Settings()
    assert list(tmp_path.iterdir()) == [path]


def test_every_language_has_a_pinned_voice_and_explicit_format():
    assert {code for _name, code in LANGUAGES} == {voice.language for voice in VOICES}
    assert len({voice.id for voice in VOICES}) == len(VOICES)
    for voice in VOICES:
        assert voice.phoneme_type in {"japanese", "espeak"}
        assert voice.license_note and voice.sample
        assert all(size > 0 and len(digest) == 64 for _file, size, digest in voice.files)
    assert voices_for("ja")[0].phoneme_type == "japanese"


def test_offline_network_guard_restores_functions_and_blocks_outbound():
    original = socket.create_connection
    with offline.no_network():
        with pytest.raises(RuntimeError, match="'Download required files'"):
            socket.create_connection(("example.invalid", 443))
        with socket.socket() as connection:
            with pytest.raises(RuntimeError):
                connection.connect(("127.0.0.1", 12345))
    assert socket.create_connection is original


def test_offline_readiness_invalidates_changed_or_missing_assets(monkeypatch, tmp_path):
    monkeypatch.setattr(offline, "assets_root", lambda: tmp_path)
    model = tmp_path / "model.onnx"
    model.write_bytes(b"verified model")
    stat = model.stat()
    marker = offline.marker_path("ja", "es")
    marker.write_text(json.dumps({"version": 2, "runtime": offline.runtime_identity(), "files": [[str(model), stat.st_size, stat.st_mtime_ns]]}))
    assert offline.offline_ready("ja", "es")
    model.write_bytes(b"changed")
    assert not offline.offline_ready("ja", "es")
    model.unlink()
    assert not offline.offline_ready("ja", "es")
    with pytest.raises(ValueError):
        offline.marker_path("../secret", "en")


def test_ocr_wire_format_preserves_offsets_and_geometry():
    line = OcrLine("cafe\u0301 漢字", .98, ((1, 2), (9, 2), (9, 8), (1, 8)), token_spans=((0, 5), (6, 8)))
    assert decode_line(json.loads(json.dumps(asdict(line)))) == line


def test_sentence_failure_does_not_block_individual_words(monkeypatch, tmp_path):
    class Translator:
        def translate(self, *_):
            raise RuntimeError("private selected text")
        def word_candidates(self, word, *_):
            if word == "bad":
                raise RuntimeError("private selected text")
            return WordTranslation(("goed",))
    from language_lens.services import translation
    monkeypatch.setattr(translation, "ArgosTranslator", Translator)
    events = []
    task_worker.execute("translate", {"settings": asdict(Settings()), "text": "bad good", "words": ["bad", "good"]}, tmp_path, events.append)
    results = [item["result"] for item in events if "result" in item]
    words = {word: value for result in results for word, value in result["words"].items()}
    assert words["good"]["candidates"] == ("goed",)
    assert words["bad"]["candidates"] == ()
    assert "private selected text" not in str(events)


@pytest.mark.parametrize("member", ["../escape/metadata.json", "/absolute", "model\\escape"])
def test_staged_installer_rejects_unsafe_archives(tmp_path, member):
    archive = tmp_path / "bad.argosmodel"
    with zipfile.ZipFile(archive, "w") as handle:
        handle.writestr(member, "{}")
    package = SimpleNamespace(settings=SimpleNamespace(package_data_dir=tmp_path / "packages"))
    with pytest.raises(ValueError):
        install_archive(archive, package)
    assert not list((tmp_path / "packages").iterdir())


def test_model_removal_is_recoverable_and_target_is_validated(tmp_path):
    root = tmp_path / "packages"
    model = root / "model"
    model.mkdir(parents=True)
    (model / "data").write_bytes(b"model")
    removed = retire(model, root)
    assert not model.exists() and (removed / "data").read_bytes() == b"model"
    assert removed.parent != root
    with pytest.raises(ValueError):
        retire(tmp_path, root)


@pytest.fixture
def review_window(review_factory):
    return review_factory()


def test_review_retry_reuses_frozen_capture_and_clears_old_results(review_window, qapp):
    window, tasks = review_window
    capture = window.canvas.capture
    line = OcrLine("old text", .99, ((0, 0), (100, 0), (100, 30), (0, 30)))
    window._ocr_finished([line])
    window._translation_finished(("translation", {"old": WordTranslation(("oud",))}))
    window._copy_source()
    assert qapp.clipboard().text() == "old text"
    window._retry_ocr()
    assert window.canvas.capture is capture and not window.canvas._hits
    assert window.translation.isHidden() and not window.copy_button.isEnabled()
    assert not window.collapse_translation.isEnabled()
    assert isinstance(tasks[-1], review.OcrTask)


def test_long_translation_scrolls_but_controls_stay_visible(review_window, qapp):
    window, _tasks = review_window
    window._translation_finished(("long translated sentence " * 300, {}))
    qapp.processEvents()
    assert window._footer_scroll.verticalScrollBar().maximum() > 0
    for button in (window.retry_ocr, window.reselect, window.read_button):
        assert window._footer.rect().contains(button.geometry())
    window._toggle_translation()
    assert window.translation.isHidden()
    window._translation_finished(("late update", {}))
    assert window.translation.isHidden()
    window._toggle_translation()
    assert window.translation.isVisible()


def test_keyboard_navigation_uses_source_occurrences(review_window):
    window, _tasks = review_window
    window._ocr_finished([OcrLine("word word", .99, ((0, 0), (300, 0), (300, 30), (0, 30)))])
    window._navigate_word(1)
    first = window.canvas._hovered.source_start
    window._navigate_word(1)
    assert window.canvas._hovered.source_start > first and window.canvas._pinned


def test_unmodified_arrow_keys_browse_words_including_focused_popup(review_window, qapp):
    from PySide6.QtTest import QTest
    from PySide6.QtCore import Qt
    window, _tasks = review_window
    window._ocr_finished([OcrLine("first second", .99, ((0, 0), (300, 0), (300, 30), (0, 30)))])
    window.show()
    window.activateWindow()
    qapp.processEvents()
    QTest.keyClick(window, Qt.Key.Key_Right)
    assert window.canvas._hovered.text == "first"
    QTest.keyClick(window.canvas._bubble, Qt.Key.Key_Right)
    assert window.canvas._hovered.text == "second"
    QTest.keyClick(window.canvas._bubble, Qt.Key.Key_Left)
    assert window.canvas._hovered.text == "first"
    assert "Use the left and right arrow keys" in window.status.text()


@pytest.mark.parametrize("clicked,key,expected", [
    (2, "Right", "a"), (2, "Left", "and"),
    (4, "Right", "Read"), (0, "Left", "language"),
])
def test_click_synchronizes_arrow_navigation_and_wrapping(review_window, qapp, clicked, key, expected):
    from PySide6.QtTest import QTest
    from PySide6.QtCore import Qt
    window, _tasks = review_window
    window._ocr_finished([OcrLine("Read and learn a language", .99,
        ((0, 0), (300, 0), (300, 30), (0, 30)))])
    window.activateWindow()
    qapp.processEvents()
    window._navigate_word(1)  # a later click must replace an existing keyboard position
    window.speed_slider.setEnabled(True)
    window.speed_slider.setFocus()
    assert window.speed_slider.hasFocus()
    hit = window.canvas._hits[clicked]
    point = window.canvas._source_to_display(hit.bounds).center().toPoint()
    QTest.mouseClick(window.canvas, Qt.MouseButton.LeftButton, pos=point)
    assert window._current_word_index == clicked and window.canvas._pinned
    assert window.canvas._bubble.hasFocus()
    speed = window.speed_slider.value()
    QTest.keyClick(qapp.focusWidget(), getattr(Qt.Key, "Key_" + key))
    assert window.canvas._hovered.text == expected
    assert window.speed_slider.value() == speed


def test_click_tracks_repeated_occurrences_after_translation_and_not_passive_hover(review_window, qapp):
    from PySide6.QtTest import QTest
    from PySide6.QtCore import Qt
    window, _tasks = review_window
    window._ocr_finished([OcrLine("Read word word end", .99,
        ((0, 0), (300, 0), (300, 30), (0, 30)))])
    window._translation_finished(("Lees woord woord einde", {"word": WordTranslation(("woord",))}))
    second = window.canvas._hits[2]
    assert second != window._hits[2]  # translated copy, same source occurrence
    point = window.canvas._source_to_display(second.bounds).center().toPoint()
    QTest.mouseClick(window.canvas, Qt.MouseButton.LeftButton, pos=point)
    assert window._current_word_index == 2
    window.canvas.dismiss_word()
    QTest.mouseMove(window.canvas, window.canvas._source_to_display(window._hits[3].bounds).center().toPoint())
    assert window._current_word_index == 2  # hovering is not an explicit selection
    window._navigate_word(-1)
    assert window.canvas._hovered.source_start == window._hits[1].source_start
    assert window.canvas._hovered.translation.candidates == ("woord",)


def test_translation_toggle_is_unavailable_until_content_exists(review_window):
    window, _tasks = review_window
    assert not window.collapse_translation.isEnabled()
    window._toggle_translation()
    assert not window._translation_hidden
    window._translation_finished(("Translated", {}))
    assert window.collapse_translation.isEnabled()
    window.collapse_translation.click()
    assert window._translation_hidden
    window._retry_ocr()
    assert not window.collapse_translation.isEnabled()
    window._translation_finished(("New translation", {}))
    assert window.collapse_translation.isEnabled() and window.translation.isHidden()
    assert window.collapse_translation.text() == "Show translation"


def test_review_speed_slider_sits_below_buttons_and_owns_focused_arrows(review_window, qapp, monkeypatch):
    from PySide6.QtTest import QTest
    from PySide6.QtCore import Qt
    window, _tasks = review_window
    stopped, changes = [], []
    monkeypatch.setattr(window.speech, "stop", lambda: stopped.append(True))
    window.speech_speed_changed.connect(changes.append)
    window.speed_slider.setValue(65)
    assert window.speech.speed == .65 and window.settings.speech_speed == .65
    assert changes == [.65] and stopped == [True]
    assert "0.65×" in window.speed_label.text()
    assert (window.speed_slider.minimum(), window.speed_slider.maximum()) == (50, 150)
    window._ocr_finished([OcrLine("first second", .99, ((0, 0), (300, 0), (300, 30), (0, 30)))])
    window.speed_slider.setEnabled(True)
    window.show()
    window.activateWindow()
    window.speed_slider.setFocus()
    qapp.processEvents()
    assert window.speed_slider.geometry().top() > window.read_button.geometry().bottom()
    assert window._footer.rect().contains(window.speed_slider.geometry())
    QTest.keyClick(window.speed_slider, Qt.Key.Key_Right)
    assert window.speed_slider.value() == 70 and window.speech.speed == .7
    assert window._current_word_index == -1  # focused slider does not select words
    QTest.keyClick(window.speed_slider, Qt.Key.Key_Left)
    assert window.speed_slider.value() == 65


@pytest.mark.parametrize("width,height", [(1000, 800), (640, 480)])
def test_speed_changes_do_not_move_or_resize_slider(review_window, qapp, width, height):
    window, _tasks = review_window
    window.resize(width, height)
    window.show()
    qapp.processEvents()
    track = window.speed_slider.geometry()
    label_width = window.speed_label.width()
    for value in (99, 100, 101, 50, 75, 125, 150, *range(50, 151)):
        window.speed_slider.setValue(value)
        qapp.processEvents()
        assert window.speed_slider.geometry() == track
        assert window.speed_label.width() == label_width
        assert window.speed_label.fontMetrics().horizontalAdvance(window.speed_label.text()) <= label_width
    assert window._footer.rect().contains(track)


def test_main_listening_button_toggles_and_hotkey_shows_registered_shortcut(monkeypatch, qapp):
    window = setup.SetupWindow(Settings())
    window.set_listening("<f8>")
    assert window.current_settings().hotkey == "<f8>" and not window.hotkey.isEnabled()
    assert window.start_button.text() == "Pause listening" and window.start_button.isEnabled()
    window.hotkey.setKeySequence(QKeySequence("F9"))
    assert window.current_settings().hotkey == "<f8>"  # never misrepresent the registered shortcut
    assert window.hotkey.keySequence().toString() == "F8"
    paused = []
    window.pause_requested.connect(lambda: paused.append(True))
    window.start_button.click()
    assert paused
    window.set_listening(None)
    assert window.start_button.text() == "Start listening" and window.hotkey.isEnabled()
    assert not hasattr(window, "listening_status") and not hasattr(window, "pause_button")
    window.set_capture_busy(True)
    window._start_model_job("prepare")
    assert not window.model_job.active and not window.prepare_button.isEnabled()
    window.shutdown()
    window.close()


def test_service_job_timeout_and_cancel_clean_scratch(monkeypatch, tmp_path, qapp):
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    job = ServiceJob()
    failed = []
    job.failed.connect(failed.append)
    job.start("ocr", {"settings": asdict(Settings()), "regions": []})
    assert job.active
    job._timeout()
    job.process.waitForFinished(5000)
    assert failed and "timed out" in failed[-1]
    assert not job.active and not list((tmp_path / "LanguageLens" / "jobs").iterdir())
    cancelled = []
    job.cancelled.connect(lambda: cancelled.append(True))
    job.start("ocr", {"settings": asdict(Settings()), "regions": []})
    job.shutdown()
    assert cancelled and not job.active
    assert not list((tmp_path / "LanguageLens" / "jobs").iterdir())


def test_second_instance_requests_reopening(qapp, tmp_path):
    from language_lens.services.instance import SingleInstance
    first, second = SingleInstance(root=tmp_path), SingleInstance(root=tmp_path)
    first.name = second.name = "Lens-test-" + uuid4().hex
    reopened = []
    first.reopen.connect(lambda: reopened.append(True))
    try:
        assert first.claim()
        assert not second.claim()
        for _ in range(10):
            qapp.processEvents()
        assert reopened
    finally:
        first.close()
        second.close()


def test_offline_readiness_invalidates_runtime_change(monkeypatch, tmp_path):
    monkeypatch.setattr(offline, "assets_root", lambda: tmp_path)
    marker = offline.marker_path("en", "nl")
    model = tmp_path / "model.onnx"
    model.write_bytes(b"model")
    details = model.stat()
    marker.write_text(json.dumps({"version": 2, "runtime": offline.runtime_identity(),
        "files": [[str(model), details.st_size, details.st_mtime_ns]]}))
    assert offline.offline_ready("en", "nl")
    monkeypatch.setattr(offline, "runtime_identity", lambda: {"rapidocr": "different"})
    assert not offline.offline_ready("en", "nl")


def test_interrupted_model_publish_restores_backup_and_cleans_owned_staging(tmp_path):
    from language_lens.services.model_management import recover_transactions
    root = tmp_path / "packages"
    root.mkdir()
    backup = tmp_path / "language-lens-removed-models" / "model-backup"
    backup.mkdir(parents=True)
    (backup / "data").write_bytes(b"working model")
    journals = tmp_path / "language-lens-model-transactions"
    journals.mkdir()
    (journals / "test.json").write_text(json.dumps({"destination": "model", "backup": backup.name}))
    stage = tmp_path / "language-lens-model-staging" / "install-interrupted"
    stage.mkdir(parents=True)
    (stage / "partial").write_bytes(b"partial")
    unrelated = stage.parent / "keep"
    unrelated.mkdir()
    recover_transactions(root)
    assert (root / "model" / "data").read_bytes() == b"working model"
    assert not list(journals.iterdir()) and not stage.exists() and unrelated.exists()


@pytest.mark.parametrize("destination", ["../escape", "", "model"])
def test_unrecoverable_or_invalid_journal_is_retained(tmp_path, destination):
    from language_lens.services.model_management import recover_transactions
    root = tmp_path / "packages"
    root.mkdir()
    journals = tmp_path / "language-lens-model-transactions"
    journals.mkdir()
    journal = journals / "test.json"
    journal.write_text(json.dumps({"destination": destination, "backup": "missing"}))
    with pytest.raises(ValueError):
        recover_transactions(root)
    assert journal.exists()


def test_failed_replacement_keeps_working_model(monkeypatch, tmp_path):
    from pathlib import Path
    from language_lens.services import model_management
    monkeypatch.setattr(model_management, "validate_staged_model",
                        lambda *_args: SimpleNamespace(from_code="en", to_code="nl"))
    root = tmp_path / "packages"
    current = root / "model"
    current.mkdir(parents=True)
    (current / "data").write_bytes(b"old model")
    archive = tmp_path / "model.argosmodel"
    with zipfile.ZipFile(archive, "w") as handle:
        handle.writestr("model/metadata.json", "{}")
        handle.writestr("model/model/weights", "new model")
    original = Path.replace
    def fail_publish(path, destination):
        if path.parent.name.startswith("install-") and path.name == "model":
            raise OSError("publish failed")
        return original(path, destination)
    monkeypatch.setattr(Path, "replace", fail_publish)
    package = SimpleNamespace(settings=SimpleNamespace(package_data_dir=root), Package=lambda _path: None)
    with pytest.raises(OSError):
        install_archive(archive, package)
    assert (current / "data").read_bytes() == b"old model"
    assert not list((tmp_path / "language-lens-model-transactions").iterdir())


@pytest.mark.parametrize("speech", [False, True])
def test_completion_callback_can_start_new_job_without_losing_scratch(tmp_path, qapp, speech):
    from PySide6.QtCore import QProcess, QTemporaryDir
    from language_lens.services.speech import SpeechJob
    job = SpeechJob(root=tmp_path) if speech else ServiceJob()
    process_key, scratch_key = ("_process", "_scratch") if speech else ("process", "scratch")
    old = QTemporaryDir(str(tmp_path / "old-XXXXXX"))
    old_path = old.path()
    setattr(job, process_key, QProcess(job))
    setattr(job, scratch_key, old)
    job._ok = True
    next_scratch = []
    def restart(*_args):
        scratch = QTemporaryDir(str(tmp_path / "next-XXXXXX"))
        next_scratch.append(scratch)
        setattr(job, process_key, QProcess(job))
        setattr(job, scratch_key, scratch)
    (job.succeeded if speech else job.finished).connect(restart)
    job._finished(0, QProcess.ExitStatus.NormalExit)
    from pathlib import Path
    assert not Path(old_path).exists() and Path(next_scratch[0].path()).is_dir()
    assert getattr(job, scratch_key) is next_scratch[0]
    process = getattr(job, process_key)
    setattr(job, process_key, None)
    setattr(job, scratch_key, None)
    process.deleteLater()
    next_scratch[0].remove()


def test_reverse_keyboard_navigation_starts_at_last_and_retry_resets(review_window):
    window, _tasks = review_window
    window._ocr_finished([OcrLine("first middle last", .99, ((0, 0), (300, 0), (300, 30), (0, 30)))])
    window._navigate_word(-1)
    assert window.canvas._hovered.text == "last"
    window.canvas.set_pronunciations([{"start": 0, "end": 5, "ipa": "old"}])
    window._retry_ocr()
    assert window._current_word_index == -1 and not window.canvas._pronunciations


def test_status_results_for_previous_pair_are_ignored(qapp):
    window = setup.SetupWindow(Settings(source_language="en", target_language="nl"))
    window._status_timer.stop()
    window._status_event({"result": {"source": "pt", "target": "en", "ready": True, "prepared": True, "route": ["pt", "en"]}})
    assert not window._translation_ready
    window._apply_model_status({"ready": True, "prepared": False, "route": ["en", "nl"]})
    window._start_model_job = lambda _command: None
    window.set_capture_busy(True)
    assert not window.repair_button.isEnabled()
    window.set_capture_busy(False)
    assert window.repair_button.isEnabled()
    window._installing = True
    window._install_failed("test failure")
    assert not window.repair_button.isEnabled()  # recheck instead of trusting pre-operation state
    window._status_timer.stop()
    window._apply_model_status({"ready": True, "prepared": False, "route": ["en", "nl"]})
    assert window.repair_button.isEnabled() and window.remove_button.isEnabled()
    assert "test failure" in window.model_status.text()
    window.shutdown()
    window.close()


def test_diagnostics_record_chains_without_sensitive_messages(caplog):
    from language_lens.services.diagnostics import record_failure
    try:
        try:
            raise ValueError("private screenshot words")
        except ValueError as exc:
            raise RuntimeError("more private content") from exc
    except RuntimeError as exc:
        record_failure("test-stage", exc)
    assert "RuntimeError" in caplog.text and "ValueError" in caplog.text
    assert "private" not in caplog.text
