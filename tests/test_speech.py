from dataclasses import replace
import hashlib
import io
from pathlib import Path
import time
import wave

import pytest
from PySide6.QtCore import QRect
from PySide6.QtGui import QPixmap

from language_lens.config import Settings, load_settings, save_settings
from language_lens.domain import OcrLine
from language_lens.services import speech_worker, voices
from language_lens.services.speech import SpeechJob, SpeechPlayer
from language_lens.ui import pronunciation, review


def wait_until(qapp, condition, timeout=10):
    deadline = time.monotonic() + timeout
    while not condition() and time.monotonic() < deadline:
        qapp.processEvents()
        time.sleep(0.01)
    assert condition(), "Timed out waiting for Qt operation"


def test_preferences_keep_accents_and_never_use_another_language(tmp_path):
    preferences = {"en": "en_GB-alan-medium", "pt": "en_US-lessac-medium"}
    assert voices.selected_voice("en", preferences).locale == "en-GB"
    assert voices.selected_voice("pt", preferences).locale == "pt-PT"
    assert voices.selected_voice("pb", preferences).locale == "pt-BR"
    assert voices.selected_voice("de", preferences).language == "de"
    path = tmp_path / "settings.json"
    settings = Settings(speech_voices=preferences, speech_enabled=False, speech_speed=.65)
    save_settings(settings, path)
    assert load_settings(path) == settings


def test_remembered_review_speed_applies_to_settings_voice_sample(qapp, monkeypatch):
    widget = pronunciation.PronunciationSettings(Settings(speech_speed=.65))
    assert not hasattr(widget, "speed")  # speed is controlled in the screenshot, not Settings
    assert widget.speech_speed == widget.player.speed == .65
    widget.set_speech_speed(.8)
    requests = []
    monkeypatch.setattr(widget.player, "speak", lambda *_args: requests.append(widget.player.speed))
    widget._preview()
    assert requests == [.8]
    widget.shutdown()
    widget.close()


@pytest.mark.parametrize("audio", [False, True])
@pytest.mark.parametrize("installed", [False, True])
@pytest.mark.parametrize("runtime", [False, True])
def test_ipa_accent_explanation_is_independent_of_audio_and_voice_readiness(qapp, monkeypatch, audio, installed, runtime):
    monkeypatch.setattr(pronunciation, "runtime_ready", lambda: runtime)
    monkeypatch.setattr(pronunciation, "voice_runtime_ready", lambda _voice: runtime)
    monkeypatch.setattr(pronunciation, "voice_present", lambda _voice: installed)
    widget = pronunciation.PronunciationSettings(Settings(source_language="en", show_ipa=True, speech_enabled=audio))
    assert widget.ipa_accent_note.text() == "IPA uses this accent."
    assert not widget.ipa_accent_note.isHidden()
    widget.enabled.setChecked(not audio)
    assert not widget.ipa_accent_note.isHidden()
    widget.voices.setCurrentIndex((widget.voices.currentIndex() + 1) % widget.voices.count())
    assert not widget.ipa_accent_note.isHidden()
    widget.show_ipa.setChecked(False)
    assert widget.ipa_accent_note.isHidden()
    widget.show_ipa.setChecked(True)
    assert not widget.ipa_accent_note.isHidden()
    widget.shutdown()
    widget.close()


def test_ipa_accent_explanation_survives_download_and_playback_status_updates(qapp, monkeypatch):
    from types import SimpleNamespace
    monkeypatch.setattr(pronunciation, "runtime_ready", lambda: True)
    monkeypatch.setattr(pronunciation, "voice_runtime_ready", lambda _voice: True)
    monkeypatch.setattr(pronunciation, "voice_present", lambda _voice: True)
    widget = pronunciation.PronunciationSettings(Settings(source_language="en", show_ipa=True))
    widget.download = SimpleNamespace(active=True, shutdown=lambda: None)
    widget.refresh()
    assert not widget.ipa_accent_note.isHidden()
    widget._download_progress(50, 100)
    assert "50.0%" in widget.download_details.text() and not widget.ipa_accent_note.isHidden()
    widget._download_failed("Test failure")
    assert "Test failure" in widget.status.text() and not widget.ipa_accent_note.isHidden()
    widget._playback_changed("playing", "Playing")
    assert not widget.ipa_accent_note.isHidden()
    widget.shutdown()
    widget.close()


def test_installed_voice_offers_optional_file_check_not_repair(qapp, monkeypatch):
    from html import unescape
    monkeypatch.setattr(pronunciation, "runtime_ready", lambda: True)
    monkeypatch.setattr(pronunciation, "voice_runtime_ready", lambda _voice: True)
    monkeypatch.setattr(pronunciation, "voice_present", lambda _voice: True)
    calls = []
    monkeypatch.setattr(SpeechJob, "start", lambda _job, command, voice: calls.append((command, voice.id)))
    widget = pronunciation.PronunciationSettings(Settings(source_language="en"))
    try:
        assert widget.install.text() == "Check voice files"
        assert "Voice installed" in widget.status.text() and "'Hear sample'" in widget.status.text()
        assert "optional integrity check" in unescape(widget.install.toolTip())
        widget.install.click()
        assert calls == [("download", widget.voice.id)]  # same checksum/download recovery, neutral label
        monkeypatch.setattr(pronunciation, "voice_present", lambda _voice: False)
        widget.refresh()
        assert widget.install.text().startswith("Download voice")
    finally:
        widget.shutdown()
        widget.close()
        widget.deleteLater()


def small_voice(payload=b"model"):
    return replace(voices.VOICES[0], files=(("model.onnx", len(payload), hashlib.sha256(payload).hexdigest()),))


def test_download_progress_verification_and_offline_reuse(tmp_path, monkeypatch):
    voice = small_voice()
    scratch = tmp_path / "scratch"
    scratch.mkdir()
    requests, progress = [], []

    def fetch(url, **kwargs):
        requests.append(url)
        return io.BytesIO(b"model")

    monkeypatch.setattr(speech_worker, "urlopen", fetch)
    speech_worker.download(voice, tmp_path, scratch, lambda **event: progress.append(event))
    speech_worker.download(voice, tmp_path, scratch)
    assert len(requests) == 1
    assert voices.REVISION in requests[0]
    assert progress[-1] == {"done": 5, "total": 5}
    assert [event["stage"] for event in progress if "stage" in event] == ["checking", "downloading", "verifying"]
    assert (tmp_path / voice.id / "model.onnx").read_bytes() == b"model"
    assert not list(scratch.iterdir())


def test_corrupt_download_is_never_published(tmp_path, monkeypatch):
    voice = small_voice()
    directory = tmp_path / voice.id
    directory.mkdir()
    target = directory / "model.onnx"
    target.write_bytes(b"older")
    scratch = tmp_path / "scratch"
    scratch.mkdir()
    monkeypatch.setattr(speech_worker, "urlopen", lambda *a, **kw: io.BytesIO(b"wrong"))
    with pytest.raises(ValueError, match="verification"):
        speech_worker.download(voice, tmp_path, scratch)
    assert target.read_bytes() == b"older"
    assert not list(scratch.iterdir())


@pytest.mark.parametrize("text", ["", " ", "x" * 2001, "hello\0world"])
def test_invalid_speech_requests_are_rejected(text):
    with pytest.raises(ValueError):
        speech_worker.validate_text(text)


def test_worker_failure_and_cancel_do_not_prevent_next_request(qapp, tmp_path):
    job = SpeechJob(root=tmp_path)
    failures, successes, cancellations = [], [], []
    job.failed.connect(failures.append)
    job.succeeded.connect(successes.append)
    job.cancelled.connect(lambda: cancellations.append(True))
    job.start("synthesize", voices.VOICES[0], "Hello")
    wait_until(qapp, lambda: not job.active)
    assert failures and not successes
    job.start("synthesize", voices.VOICES[0], "Hello again")
    job.cancel()
    wait_until(qapp, lambda: not job.active)
    assert cancellations == [True]
    assert not successes
    job.start("synthesize", voices.VOICES[0], "Try again")
    wait_until(qapp, lambda: not job.active)
    assert len(failures) == 2
    assert not list(tmp_path.glob(".job-*"))


def test_worker_timeout_is_reported_and_scratch_removed(qapp, tmp_path):
    job = SpeechJob(root=tmp_path)
    failures = []
    job.failed.connect(failures.append)
    job.start("synthesize", voices.VOICES[0], "Hello")
    job._timer.start(1)
    wait_until(qapp, lambda: not job.active)
    assert failures and "timed out" in failures[0]
    assert not list(tmp_path.glob(".job-*"))


def test_worker_failed_launch_cleans_up(qapp, tmp_path, monkeypatch):
    from language_lens import runtime
    monkeypatch.setattr(runtime.sys, "executable", str(tmp_path / "missing-python.exe"))
    job = SpeechJob(root=tmp_path)
    errors = []
    job.failed.connect(errors.append)
    job.start("synthesize", voices.VOICES[0], "Hello")
    wait_until(qapp, lambda: not job.active)
    assert errors and "A required local component could not be loaded." in errors[0]
    assert not list(tmp_path.glob(".job-*"))


def test_replay_cache_uses_exact_text_and_voice_and_is_cleared(qapp, tmp_path, monkeypatch):
    import language_lens.services.speech as speech
    monkeypatch.setattr(speech, "runtime_ready", lambda: True)
    monkeypatch.setattr(speech, "voice_present", lambda *args: True)
    player = SpeechPlayer(root=tmp_path)
    calls, played = [], []
    monkeypatch.setattr(player.job, "start", lambda *args, **kwargs: calls.append(args))
    monkeypatch.setattr(player, "_play", lambda: played.append(True))
    (tmp_path / "selection.wav").write_bytes(b"generated-audio")
    player.speak("Hello", voices.VOICES[0])
    player._generated(tmp_path)
    player.stop()
    player.speak("Hello", voices.VOICES[0])
    assert len(calls) == 1 and len(played) == 2
    player.stop()
    player.speak("Hello", voices.VOICES[1])
    assert len(calls) == 2
    player.stop()
    player.speak("hello", voices.VOICES[0])
    assert len(calls) == 3
    player.shutdown()
    assert not player._audio and not player._buffer.data()


def test_settings_remember_voice_and_update_download_status(qapp, monkeypatch):
    monkeypatch.setattr(pronunciation, "runtime_ready", lambda: True)
    monkeypatch.setattr(pronunciation, "voice_present", lambda v: v.locale == "en-GB")
    widget = pronunciation.PronunciationSettings(Settings(source_language="en"))
    assert not widget.preview.isEnabled()
    widget.voices.setCurrentIndex(1)
    assert widget.preview.isEnabled()
    widget.set_language("pb")
    assert widget.voice.locale == "pt-BR"
    widget.set_language("en")
    assert widget.voice.locale == "en-GB"
    widget._download_progress(32_000_000, 64_000_000)
    assert "50.0%" in widget.download_details.text()
    widget.set_language("de")
    assert not widget.preview.isEnabled()
    assert widget.install.isEnabled()
    widget.shutdown()


def test_review_reads_original_before_translation_and_ignores_late_results(qapp, monkeypatch, tmp_path):
    class IdlePool:
        @staticmethod
        def globalInstance():
            return IdlePool()

        def start(self, task):
            pass

    monkeypatch.setattr(review, "TaskPool", IdlePool)
    monkeypatch.setattr(review, "runtime_ready", lambda: True)
    monkeypatch.setattr(review, "voice_present", lambda v: True)
    window = review.ReviewWindow(QPixmap(1000, 800), QRect(100, 100, 300, 60), Settings())
    window.pronunciation_job.root = tmp_path
    calls, stopped = [], []
    monkeypatch.setattr(window.speech, "speak", lambda text, voice: calls.append((text, voice.locale)))
    monkeypatch.setattr(window.speech, "shutdown", lambda: stopped.append(True))
    lines = [OcrLine("Olá mundo.", .99, ((0, 0), (100, 0), (100, 20), (0, 20)))]
    window._ocr_finished(lines)
    assert window.read_button.isEnabled()
    assert window.translation.isHidden()
    window.read_button.click()
    assert calls == [("Olá mundo.", "pt-PT")]
    window._failed("Translation failed")
    assert window.read_button.isEnabled()
    window.close()
    window._ocr_finished([])
    assert stopped == [True]
    assert window._speech_text == "Olá mundo."


@pytest.mark.parametrize("voice", voices.VOICES, ids=lambda v: v.locale)
def test_installed_fixture_generates_real_audio_with_pinned_catalogue(qapp, tmp_path, voice):
    """Optional integration test: uses available local fixtures, never downloads."""
    import os
    import shutil

    artifacts = Path(__file__).resolve().parents[1] / "artifacts"
    configured = os.environ.get("LANGUAGE_LENS_TEST_VOICES")
    candidates = ([Path(configured) / voice.id, Path(configured) / voice.locale] if configured else
                  [artifacts / "voice-validation" / voice.id,
                   artifacts / "pronunciation" / "voices" / voice.locale])
    fixture = next((path for path in candidates if path.is_dir()), candidates[0])
    if not fixture.is_dir() or not voices.runtime_ready():
        pytest.skip("Requires local pronunciation fixtures and pinned Piper runtime")
    directory = tmp_path / voice.id
    directory.mkdir()
    for name, size, checksum in voice.files:
        source = fixture / name
        assert voices.valid_file(source, size, checksum)
        try:
            os.link(source, directory / name)
        except OSError:
            shutil.copyfile(source, directory / name)
    job = SpeechJob(root=tmp_path)
    audio, errors = [], []
    job.succeeded.connect(lambda path: audio.append((path / "selection.wav").read_bytes()))
    job.failed.connect(errors.append)
    # Literal brackets must be treated as text, not as a raw-phoneme command.
    job.start("synthesize", voice, voice.sample + " [[hello]]")
    wait_until(qapp, lambda: not job.active, timeout=60)
    assert not errors
    assert len(audio) == 1
    with wave.open(io.BytesIO(audio[0]), "rb") as wav:
        assert wav.getnchannels() == 1
        assert wav.getsampwidth() == 2
        import json
        sample_rate = json.loads((directory / (voice.id + ".onnx.json")).read_text(encoding="utf-8"))["audio"]["sample_rate"]
        assert wav.getframerate() == sample_rate
        assert wav.getnframes() > sample_rate
    # Also synthesize a word from the exact sequence returned by the IPA worker.
    from language_lens.domain import build_word_hits
    import json
    hits = build_word_hits([OcrLine(voice.sample, .99, ((0, 0), (500, 0), (500, 40), (0, 40)))])
    preparation = SpeechJob(root=tmp_path)
    prepared = []
    preparation.failed.connect(errors.append)
    preparation.succeeded.connect(lambda path: prepared.append(json.loads(
        (path / "pronunciation.json").read_text(encoding="utf-8"))))
    preparation.start("pronunciation", voice, voice.sample,
                      spans=[[hit.source_start, hit.source_end] for hit in hits])
    wait_until(qapp, lambda: not preparation.active, timeout=30)
    assert not errors and prepared
    word = prepared[0]["words"][0]
    job.start("phonemes", voice, phonemes=[word["phonemes"]])
    wait_until(qapp, lambda: not job.active, timeout=60)
    assert not errors and len(audio) == 2
    with wave.open(io.BytesIO(audio[1]), "rb") as wav:
        assert wav.getnframes() > 1000
        assert wav.getsampwidth() == 2
    assert not list(tmp_path.glob(".job-*"))


def test_audio_device_playback_and_stop(qapp, monkeypatch, tmp_path):
    """Exercise Qt's real WAV backend while muted, including replay and stop."""
    from PySide6.QtMultimedia import QMediaDevices
    if QMediaDevices.defaultAudioOutput().isNull():
        pytest.skip("No audio output is exposed in this environment")
    data = io.BytesIO()
    with wave.open(data, "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(22050)
        wav.writeframes(b"\0\0" * 22050)
    player = SpeechPlayer(root=tmp_path)
    player._audio = data.getvalue()
    states = []
    player.changed.connect(lambda state, message: states.append((state, message)))
    player._play()
    if player._output:
        player._output.setMuted(True)
    wait_until(qapp, lambda: player.state in ("playing", "error"))
    assert player.state == "playing", states
    player.stop()
    assert player.state == "idle"
    player._play()
    wait_until(qapp, lambda: player.state == "playing")
    wait_until(qapp, lambda: player.state == "idle")
    player.shutdown()
