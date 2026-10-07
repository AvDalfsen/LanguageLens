"""Regressions for failures reproduced by the technical audit."""
import io
import json
from pathlib import Path
import shutil
from types import SimpleNamespace
import zipfile
import time

import pytest

from language_lens.services import model_download, model_management, offline


def wait_for(qapp, condition, timeout=10):
    from PySide6.QtTest import QTest
    deadline = time.monotonic() + timeout
    while not condition() and time.monotonic() < deadline:
        QTest.qWait(10)
    qapp.processEvents()
    assert condition(), "Asynchronous job did not finish"


def model_archive(path, name="translate-en_nl-1_1"):
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr(f"{name}/metadata.json", '{"from_code":"en","to_code":"nl"}')
        archive.writestr(f"{name}/model/model.bin", "new weights")
    return path


def installed_model(root, name, source="en", target="nl"):
    path = root / name
    path.mkdir(parents=True)
    (path / "metadata.json").write_text(json.dumps({"from_code": source, "to_code": target}))
    (path / "weights").write_bytes(b"working model")
    return path


def test_metadata_only_archive_cannot_replace_working_model(tmp_path):
    root = tmp_path / "packages"
    current = installed_model(root, "translate-en_nl-1_0")
    archive = tmp_path / "broken.argosmodel"
    with zipfile.ZipFile(archive, "w") as handle:
        handle.writestr(f"{current.name}/metadata.json", '{"from_code":"en","to_code":"nl"}')
        handle.writestr(f"{current.name}/model/", "")
    package = SimpleNamespace(settings=SimpleNamespace(package_data_dir=root),
        Package=lambda _path: SimpleNamespace(from_code="en", to_code="nl"))
    with pytest.raises(model_management.InvalidModelArchive, match="weights or tokenizer"):
        model_management.install_archive(archive, package)
    assert (current / "weights").read_bytes() == b"working model"
    assert not (tmp_path / "language-lens-removed-models").exists()


def test_preflight_loads_weights_and_tokenizer_and_checks_identity(monkeypatch, tmp_path):
    path = tmp_path / "model"
    (path / "model").mkdir(parents=True)
    (path / "model" / "model.bin").write_bytes(b"weights")
    requests = []
    class Runtime:
        def __init__(self, location, **kwargs):
            requests.append((location, kwargs))
        def translate_batch(self, tokens, **kwargs):
            requests.append((tokens, kwargs))
            return [SimpleNamespace(hypotheses=[["goed"]])]
    import sys
    monkeypatch.setitem(sys.modules, "ctranslate2", SimpleNamespace(Translator=Runtime))
    model = SimpleNamespace(from_code="en", to_code="nl", target_prefix="<nl>",
        tokenizer=SimpleNamespace(encode=lambda text: [text], decode=lambda tokens: " ".join(tokens)))
    package = SimpleNamespace(Package=lambda _path: model)
    with pytest.raises(ValueError, match="requested"):
        model_management.validate_staged_model(path, package, ("nl", "en"))
    assert not requests
    assert model_management.validate_staged_model(path, package, ("en", "nl")) is model
    assert requests[0][0] == str(path / "model")
    assert requests[1][1]["target_prefix"] == [["<nl>"]]


@pytest.mark.parametrize("fail_publish", [False, True])
def test_replacement_retires_every_old_version_or_restores_them_all(monkeypatch, tmp_path, fail_publish):
    root = tmp_path / "packages"
    old = [installed_model(root, name) for name in ("translate-en_nl-1_0", "duplicate-en_nl")]
    other = installed_model(root, "translate-nl_en", "nl", "en")
    # Malformed unrelated metadata must not prevent replacement.
    (installed_model(root, "damaged") / "metadata.json").write_text('{"from_code":[],"to_code":"nl"}')
    monkeypatch.setattr(model_management, "validate_staged_model",
                        lambda *_args: SimpleNamespace(from_code="en", to_code="nl"))
    package = SimpleNamespace(settings=SimpleNamespace(package_data_dir=root))
    archive = model_archive(tmp_path / "new.argosmodel")
    original = Path.replace
    if fail_publish:
        def replace(path, destination):
            if path.parent.name.startswith("install-"):
                raise OSError("publish interrupted")
            return original(path, destination)
        monkeypatch.setattr(Path, "replace", replace)
        with pytest.raises(OSError, match="interrupted"):
            model_management.install_archive(archive, package)
        assert all((path / "weights").read_bytes() == b"working model" for path in old)
        assert not (root / "translate-en_nl-1_1").exists()
    else:
        model_management.install_archive(archive, package)
        assert not any(path.exists() for path in old)
        assert (root / "translate-en_nl-1_1" / "model" / "model.bin").is_file()
        backups = list((tmp_path / "language-lens-removed-models").iterdir())
        assert len(backups) == 2 and all((path / "weights").exists() for path in backups)
    assert other.is_dir()
    assert not list((tmp_path / "language-lens-model-transactions").iterdir())


@pytest.mark.parametrize("phase", ["retiring", "publishing", "committed"])
def test_crash_recovery_handles_partial_retirement_and_publication(tmp_path, phase):
    root = tmp_path / "packages"
    first, second = [installed_model(root, name) for name in ("v1", "v2")]
    removed = tmp_path / "language-lens-removed-models"
    removed.mkdir()
    first.replace(removed / "v1-backup")
    if phase != "retiring":
        second.replace(removed / "v2-backup")
        installed_model(root, "v3")
    journals = tmp_path / "language-lens-model-transactions"
    journals.mkdir()
    (journals / "test.json").write_text(json.dumps({"version": 2, "phase": phase, "destination": "v3",
        "backups": [{"original": name, "backup": name + "-backup"} for name in ("v1", "v2")]}))
    model_management.recover_transactions(root)
    assert not list(journals.iterdir())
    if phase == "committed":
        assert (root / "v3").is_dir() and not first.exists() and not second.exists()
    else:
        assert first.is_dir() and second.is_dir() and not (root / "v3").exists()


@pytest.mark.parametrize("runtime", ["ctranslate2", "sentencepiece", "sacremoses"])
def test_readiness_tracks_translation_runtime_versions(monkeypatch, tmp_path, runtime):
    monkeypatch.setattr(offline, "assets_root", lambda: tmp_path)
    model = tmp_path / "weights"
    model.write_bytes(b"weights")
    info = model.stat()
    versions = offline.runtime_identity()
    assert runtime in versions
    offline.marker_path("en", "nl").write_text(json.dumps({"version": 2, "runtime": versions,
        "files": [[str(model), info.st_size, info.st_mtime_ns]]}))
    assert offline.offline_ready("en", "nl")
    monkeypatch.setattr(offline, "runtime_identity", lambda: {**versions, runtime: "changed"})
    assert not offline.offline_ready("en", "nl")


def test_completed_download_survives_job_cleanup_and_version_change_redownloads(monkeypatch, tmp_path):
    monkeypatch.setattr(model_download, "settings_path", lambda: tmp_path / "app" / "settings.json")
    package = SimpleNamespace(settings=SimpleNamespace(), argospm_package_name=lambda _: "translate-en_nl")
    model = SimpleNamespace(from_code="en", to_code="nl", package_version="1", links=["https://example.test/model"])
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w") as archive:
        archive.writestr("model/metadata.json", "{}")
    requests = []
    class Response(io.BytesIO):
        headers = {}
    def fetch(*args, **kwargs):
        requests.append(True)
        return Response(output.getvalue())
    monkeypatch.setattr(model_download, "urlopen", fetch)
    first_job = tmp_path / "first-job"
    model_download.configure_cache(package, first_job)
    cached = model_download.download_model(model, package, "test", lambda _: None)
    assert not list(first_job.rglob("*.part"))
    shutil.rmtree(first_job)
    model_download.configure_cache(package, tmp_path / "second-job")
    assert model_download.download_model(model, package, "test", lambda _: None) == cached
    assert len(requests) == 1 and cached.is_file()
    model.package_version = "2"
    assert model_download.download_model(model, package, "test", lambda _: None) != cached
    assert len(requests) == 2


def test_progressive_translation_sends_each_unique_word_once():
    from language_lens.domain import WordTranslation
    from language_lens.services.translation import selection_results
    translator = SimpleNamespace(translate=lambda *_: "sentence",
        word_candidates=lambda word, *_: WordTranslation((word,)))
    words = [str(index) for index in range(500)]
    results = list(selection_results(translator, "source", words + words, "en", "nl", lambda _: None))
    assert results[0] == ("sentence", {})
    assert len(results) == 501 and sum(len(update) for _, update in results) == 500
    assert all(sentence is None and len(update) == 1 for sentence, update in results[1:])


def test_word_deltas_update_all_occurrences_without_recreating_other_hits(review_factory):
    from language_lens.domain import OcrLine, WordTranslation
    window, _ = review_factory()
    window._ocr_finished([OcrLine("word other word", .99, ((0, 0), (300, 0), (300, 30), (0, 30)))])
    original = list(window.canvas._hits)
    window._translation_finished(("sentence", {}))
    window._translation_finished((None, {"word": WordTranslation(("woord",))}))
    assert window._translated_text == "sentence" and "sentence" in window.translation.text()
    assert "1 of 2 completed" in window.status.text()
    assert window.canvas._hits[1] is original[1]
    assert all(window.canvas._hits[index].translation.candidates == ("woord",) for index in (0, 2))
    assert window._hits == original
    window._translation_finished((None, {"other": WordTranslation((), "failed")}))
    assert "pending" not in window.status.text() and "1 word lookup unavailable" in window.status.text()
    window._translation_finished((None, {"other": WordTranslation(("ander",))}))
    assert "unavailable" not in window.status.text()


def test_worker_and_domain_ocr_preserve_custom_retry_scale(monkeypatch, tmp_path, qapp):
    from PySide6.QtCore import QPoint, QSize
    from PySide6.QtGui import QImage
    from language_lens.config import Settings
    from language_lens.domain import OcrLine
    from language_lens.services import task_worker, tasks
    from language_lens.services.jobs import decode_line
    class Engine:
        def __init__(self):
            self.calls = 0
        def recognize(self, image, _confidence):
            self.calls += 1
            if self.calls == 1:
                return []
            assert image.shape == (210, 420, 3)
            return [OcrLine("word", .99, ((60, 60), (120, 60), (120, 90), (60, 90)))]
    monkeypatch.setattr(tasks, "create_ocr_engine", lambda _settings: Engine())
    task = tasks.OcrTask(QImage(100, 30, QImage.Format.Format_RGB888), Settings(),
        retry_image=QImage(140, 70, QImage.Format.Format_RGB888), retry_scale=3,
        retry_offset=QPoint(-10, -10), selection_size=QSize(100, 30))
    results = []
    task.signals.result.connect(results.append)
    task.run()
    command, payload, images = tasks.encode_task(task)
    for name, image in images.items():
        assert image.save(str(tmp_path / name), "PNG")
    events = []
    task_worker.execute(command, payload, tmp_path, events.append)
    actual = [decode_line(item) for item in events[-1]["result"]]
    assert actual == results[0] and actual[0].bounds.x == 10


def test_empty_worker_ocr_does_not_load_models(monkeypatch, tmp_path):
    from dataclasses import asdict
    from language_lens.config import Settings
    from language_lens.services import task_worker, tasks
    def unexpected(_settings):
        raise AssertionError("No engine is needed for an empty selection")
    monkeypatch.setattr(tasks, "create_ocr_engine", unexpected)
    events = []
    task_worker.execute("ocr", {"settings": asdict(Settings()), "regions": []}, tmp_path, events.append)
    assert events == [{"result": []}]


def test_domain_ocr_factory_uses_verified_local_models(monkeypatch):
    from language_lens.config import Settings
    from language_lens.services import tasks
    parameters = {"Rec.model_path": "verified-model", "intra_threads": 2}
    monkeypatch.setattr(tasks, "local_ocr_parameters", lambda _: parameters)
    calls = []
    tasks.create_ocr_engine(Settings(source_language="en"), engine_factory=lambda language, **kwargs: calls.append((language, kwargs)))
    assert calls == [("en", {"params": parameters})]


def test_native_capture_selection_and_review_do_not_allocate_composite(monkeypatch, qapp):
    from PySide6.QtCore import QRect
    from PySide6.QtGui import QColor, QPixmap
    from language_lens.config import Settings
    from language_lens.services.capture import DesktopCapture, ScreenCapture
    from language_lens.ui import review
    from language_lens.ui.selection import SelectionOverlay
    shot = QPixmap(1600, 1200)
    shot.fill(QColor("red"))
    capture = DesktopCapture(None, QRect(-800, 0, 800, 600), (ScreenCapture(shot, QRect(-800, 0, 800, 600)),))
    monkeypatch.setattr(review, "QThreadPool", SimpleNamespace(globalInstance=lambda: SimpleNamespace(start=lambda _: None)))
    selection = SelectionOverlay(capture)
    selection.show()
    window = review.ReviewWindow(capture, QRect(100, 100, 300, 40), Settings(speech_enabled=False))
    window.show()
    qapp.processEvents()
    assert capture._pixmap is None
    assert window.canvas._display_to_source(window.canvas.selection_display_rect().center()).x() == 250
    assert capture.pixmap.size() == capture.size
    assert capture.pixmap.toImage().pixelColor(50, 50) == QColor("red")


@pytest.mark.parametrize("cancel", [False, True])
def test_image_staging_keeps_gui_responsive_and_cleans_scratch(monkeypatch, tmp_path, qapp, cancel):
    from dataclasses import asdict
    from threading import Event, get_ident
    from PySide6.QtCore import QProcess, QTimer
    from PySide6.QtGui import QImage
    from language_lens.config import Settings
    from language_lens.services.jobs import ServiceJob
    from language_lens.services import process_job
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    entered, release = Event(), Event()
    thread_ids = []
    original = QImage.save
    def delayed_save(image, *args):
        thread_ids.append(get_ident())
        entered.set()
        assert release.wait(5)
        return original(image, *args)
    monkeypatch.setattr(QImage, "save", delayed_save)
    job = ServiceJob()
    completed, cancelled, failures = [], [], []
    job.finished.connect(lambda: completed.append(True))
    job.cancelled.connect(lambda: cancelled.append(True))
    job.failed.connect(failures.append)
    try:
        job.start("ocr", {"settings": asdict(Settings()), "regions": []},
                  {"crop.png": QImage(100, 30, QImage.Format.Format_RGB888)})
        assert entered.wait(1) and job.active
        assert job.process.state() == QProcess.ProcessState.NotRunning
        assert len(thread_ids) == 1 and thread_ids[0] != get_ident()
        ticks = []
        QTimer.singleShot(0, lambda: ticks.append(True))
        qapp.processEvents()
        assert ticks
        if cancel:
            job.cancel()
        release.set()
        wait_for(qapp, lambda: not job.active and not process_job._STAGERS)
        assert not failures
        assert bool(cancelled) == cancel and bool(completed) != cancel
        assert not list((tmp_path / "LanguageLens" / "jobs").iterdir())
    finally:
        release.set()
        job.shutdown()


def test_window_destruction_during_staging_keeps_thread_alive_until_cleanup(monkeypatch, tmp_path, qapp):
    from dataclasses import asdict
    from threading import Event
    from PySide6.QtCore import QCoreApplication, QEvent, QObject
    from PySide6.QtGui import QImage
    from language_lens.config import Settings
    from language_lens.services.jobs import ServiceJob
    from language_lens.services import process_job
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    entered, release = Event(), Event()
    original = QImage.save
    def delayed_save(image, *args):
        entered.set()
        assert release.wait(5)
        return original(image, *args)
    monkeypatch.setattr(QImage, "save", delayed_save)
    owner = QObject()
    job = ServiceJob(owner)
    try:
        job.start("ocr", {"settings": asdict(Settings()), "regions": []},
                  {"crop.png": QImage(100, 30, QImage.Format.Format_RGB888)})
        assert entered.wait(1)
        owner.deleteLater()
        QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        release.set()
        wait_for(qapp, lambda: not process_job._STAGERS)
        assert not list((tmp_path / "LanguageLens" / "jobs").iterdir())
    finally:
        release.set()
        for stage in tuple(process_job._STAGERS):
            stage.cancel()
            stage.wait(5000)
        qapp.processEvents()


def test_speech_final_progress_cannot_rearm_timer_or_change_old_completion(tmp_path, qapp):
    from PySide6.QtCore import QProcess, QTemporaryDir
    from language_lens.services.speech import SpeechJob
    job = SpeechJob(root=tmp_path)
    scratch = QTemporaryDir(str(tmp_path / "old-XXXXXX"))
    scratch_path = Path(scratch.path())
    job._scratch = scratch
    job._process = SimpleNamespace(readAllStandardOutput=lambda: b'{"stage":"verifying","done":5,"total":5,"ok":true}\n', deleteLater=lambda: None)
    succeeded = []
    job.succeeded.connect(succeeded.append)
    # The activity callback can reset the state for a subsequent operation.
    job.activity_changed.connect(lambda active: setattr(job, "_ok", False) if not active else None)
    job._finished(0, QProcess.ExitStatus.NormalExit)
    assert succeeded == [scratch_path] and not scratch_path.exists()
    assert not job._timer.isActive()


def test_remove_route_retires_all_versions_of_each_pivot_leg(monkeypatch, tmp_path):
    from functools import lru_cache
    from language_lens.services.translation import ArgosTranslator
    root = tmp_path / "packages"
    paths = [installed_model(root, name, source, target) for name, source, target in
             (("nl-en-v1", "nl", "en"), ("nl-en-v2", "nl", "en"), ("en-pt", "en", "pt"))]
    keep = installed_model(root, "pt-en", "pt", "en")
    backend = SimpleNamespace(get_installed_languages=lru_cache()(lambda: []), installed_translates=["stale"])
    package = SimpleNamespace(settings=SimpleNamespace(package_data_dir=root))
    monkeypatch.setattr(ArgosTranslator, "_modules", staticmethod(lambda: (package, backend)))
    monkeypatch.setattr(ArgosTranslator, "route", lambda *_: [
        SimpleNamespace(from_code="nl", to_code="en", package_path=paths[0]),
        SimpleNamespace(from_code="en", to_code="pt", package_path=paths[2])])
    monkeypatch.setattr(offline, "assets_root", lambda: tmp_path / "offline")
    model_management.remove_route("nl", "pt", lambda _: None)
    assert not any(path.exists() for path in paths) and keep.is_dir()
    assert len(list((tmp_path / "language-lens-removed-models").iterdir())) == 3
    assert not backend.installed_translates


@pytest.mark.parametrize("error,discard", [(ValueError("bad weights"), True),
    (PermissionError("runtime file denied"), False), (ImportError("missing runtime"), False)])
def test_unusable_cached_weights_are_discarded_but_runtime_failures_keep_download(monkeypatch, tmp_path, error, discard):
    from language_lens.services import translation
    root = tmp_path / "packages"
    current = installed_model(root, "old")
    cache = tmp_path / "cache"
    cache.mkdir()
    archive = model_archive(cache / "cached.argosmodel")
    model = SimpleNamespace(from_code="en", to_code="nl", from_name="English", to_name="Dutch")
    package = SimpleNamespace(settings=SimpleNamespace(package_data_dir=root, downloads_dir=cache,
        language_lens_download_scratch=tmp_path / "job"), update_package_index=lambda: None,
        get_available_packages=lambda: [model])
    monkeypatch.setattr(translation.ArgosTranslator, "_modules", staticmethod(lambda: (package, None)))
    monkeypatch.setattr(translation, "download_model", lambda *_: archive)
    def reject(*_):
        raise error
    monkeypatch.setattr(model_management, "validate_staged_model", reject)
    with pytest.raises(model_management.InvalidModelArchive if discard else type(error)):
        translation.ArgosTranslator().install_pair("en", "nl", staged=True, force=True)
    assert archive.exists() != discard
    assert (current / "weights").read_bytes() == b"working model"


def test_managed_cache_prunes_old_archives_without_removing_current_download(tmp_path):
    import os
    paths = [tmp_path / f"{index}.argosmodel" for index in range(3)]
    for index, path in enumerate(paths):
        path.write_bytes(b"12345")
        os.utime(path, (index + 1, index + 1))
    model_download._prune_cache(tmp_path, paths[-1], limit=10)
    assert not paths[0].exists() and all(path.exists() for path in paths[1:])
    model_download._prune_cache(tmp_path, paths[-1], limit=1)
    assert paths[-1].exists() and not paths[1].exists()


def test_archive_folder_collision_cannot_retire_a_different_language_pair(monkeypatch, tmp_path):
    root = tmp_path / "packages"
    other = installed_model(root, "translate-en_nl-1_1", "pt", "en")
    current = installed_model(root, "en-nl-old")
    monkeypatch.setattr(model_management, "validate_staged_model",
                        lambda *_args: SimpleNamespace(from_code="en", to_code="nl"))
    package = SimpleNamespace(settings=SimpleNamespace(package_data_dir=root))
    with pytest.raises(model_management.InvalidModelArchive, match="collides"):
        model_management.install_archive(model_archive(tmp_path / "model.argosmodel"), package)
    assert other.is_dir() and current.is_dir()
    assert not (tmp_path / "language-lens-removed-models").exists()


def test_cache_retention_failure_does_not_discard_completed_download(monkeypatch, tmp_path):
    old, current = tmp_path / "old.argosmodel", tmp_path / "current.argosmodel"
    old.write_bytes(b"old")
    current.write_bytes(b"complete")
    original = Path.unlink
    def locked(path, *args, **kwargs):
        if path == old:
            raise PermissionError("archive is locked")
        return original(path, *args, **kwargs)
    monkeypatch.setattr(Path, "unlink", locked)
    model_download._prune_cache(tmp_path, current, limit=1)
    assert old.exists() and current.read_bytes() == b"complete"
