"""Qt supervision and playback for the local speech worker."""
from __future__ import annotations

from pathlib import Path
import sys

from PySide6.QtCore import QByteArray, QBuffer, QIODevice, QObject, QTimer, QUrl, Signal
from PySide6.QtMultimedia import QAudioOutput, QMediaDevices, QMediaPlayer

from language_lens.services.process_job import ProcessJob
from language_lens.services.voices import Voice, runtime_ready, voice_runtime_ready, voice_present, voices_root


class SpeechJob(ProcessJob):
    progress = Signal(int, int)
    stage_changed = Signal(str)
    succeeded = Signal(object)

    start_failure = "Could not start local speech. Restart using 'Start Language Lens.bat'."
    scratch_failure = "Could not create speech files. Check disk space and directory permissions."
    overflow_failure = "The speech task returned too much data. Try a shorter selection."
    stopped_failure = "The local speech process stopped unexpectedly. Please retry."

    def __init__(self, parent=None, *, root: Path | None = None) -> None:
        super().__init__(parent)
        self.root = root or voices_root()

    def start(self, command: str, voice: Voice, text: str = "", **data) -> None:
        self._start("language_lens.services.speech_worker", command, {"text": text, **data},
                    self.root, 60000 if command in ("download", "pronunciation") else 180000,
                    ["--voice", voice.id, "--root", str(self.root)])

    def _handle_message(self, message, process):
        stage = message.get("stage")
        if isinstance(stage, str) and stage in {"checking", "downloading", "verifying"}:
            self._touch(60000)
            self.stage_changed.emit(stage)
            if self._process is not process or self._cancelled:
                return
        if "done" in message and "total" in message:
            self._touch(60000)
            self.progress.emit(message["done"], message["total"])

    def _timeout_message(self):
        return ("The voice download stopped making progress. Check your connection and retry."
                if self._command == "download" else
                "Local speech timed out. Try again, or select a shorter passage.")

    def _succeeded(self, scratch):
        # Audio is consumed synchronously, before the base class cleans scratch.
        self.succeeded.emit(Path(scratch.path()))


class SpeechPlayer(QObject):
    changed = Signal(str, str)  # state, user-facing detail

    def __init__(self, parent=None, *, root: Path | None = None) -> None:
        super().__init__(parent)
        self.job = SpeechJob(self, root=root)
        self.job.succeeded.connect(self._generated)
        self.job.failed.connect(self._failed)
        self.job.cancelled.connect(lambda: self._set_state("idle", ""))
        self.state = "idle"
        self.speed = 1.0
        self._media: QMediaPlayer | None = None
        self._output: QAudioOutput | None = None
        self._buffer = QBuffer(self)
        self._cache_key: tuple | None = None
        self._pending_key: tuple | None = None
        self._audio = b""
        self._load_timer = QTimer(self)
        self._load_timer.setSingleShot(True)
        self._load_timer.timeout.connect(lambda: self._failed("Audio playback did not start. Check your output device and retry."))

    @property
    def busy(self) -> bool:
        return self.state in ("generating", "loading", "playing", "stopping")

    def _set_state(self, state: str, message: str) -> None:
        self.state = state
        self.changed.emit(state, message)

    def speak(self, text: str, voice: Voice) -> None:
        self._request(text, voice)

    def speak_phonemes(self, phonemes: tuple[str, ...], voice: Voice,
                       context_key: tuple = ()) -> None:
        """Use the exact prepared sequence, never parse the display IPA as text."""
        self._request("", voice, tuple(phonemes), context_key)

    def _request(self, text: str, voice: Voice, phonemes: tuple[str, ...] | None = None,
                 context_key: tuple = ()) -> None:
        if self.busy or self.job.active:
            return
        if not runtime_ready() or not voice_runtime_ready(voice):
            self._failed("Restart using 'Start Language Lens.bat' to install the speech components.")
            return
        if not voice_present(voice, self.job.root):
            self._failed("Use 'Download voice' in 'Settings' first.")
            return
        # Accent, exact text, engine version and voice revision are part of identity.
        from language_lens.services.voices import PIPER_VERSION, REVISION
        self._pending_key = (text, phonemes, context_key, voice.id, voice.espeak, PIPER_VERSION, REVISION, self.speed)
        if self._pending_key == self._cache_key and self._audio:
            self._play()
            return
        self._set_state("generating", "Preparing local audio…")
        if phonemes is None:
            self.job.start("synthesize", voice, text, speed=self.speed)
        else:
            self.job.start("phonemes", voice, phonemes=list(phonemes), speed=self.speed)

    def _generated(self, directory: Path) -> None:
        try:
            self._audio = (directory / "selection.wav").read_bytes()
            self._cache_key = self._pending_key
            self._play()
        except Exception as exc:
            self._failed(f"Could not play the generated audio: {exc}")

    def _play(self) -> None:
        device = QMediaDevices.defaultAudioOutput()
        if device.isNull():
            self._failed("No audio output device was found. Connect speakers or headphones, then retry.")
            return
        if self._media is None:
            self._media = QMediaPlayer(self)
            self._output = QAudioOutput(self)
            self._media.setAudioOutput(self._output)
            self._media.errorOccurred.connect(lambda _error, text: self._failed(f"Audio playback failed: {text}"))
            self._media.mediaStatusChanged.connect(self._media_status)
            self._media.playbackStateChanged.connect(self._playback_state)
        self._output.setDevice(device)
        self._media.stop()
        self._media.setSource(QUrl())
        self._buffer.close()
        self._buffer.setData(QByteArray(self._audio))
        self._buffer.open(QIODevice.OpenModeFlag.ReadOnly)
        self._set_state("loading", "Opening audio…")
        self._load_timer.start(15000)
        self._media.setSourceDevice(self._buffer, QUrl("file:///selection.wav"))
        self._media.play()

    def _playback_state(self, state) -> None:
        if state == QMediaPlayer.PlaybackState.PlayingState:
            self._load_timer.stop()
            self._set_state("playing", "Reading the original selection…")

    def _media_status(self, status) -> None:
        if status == QMediaPlayer.MediaStatus.EndOfMedia:
            self._load_timer.stop()
            self._set_state("idle", "")

    def _failed(self, message: str) -> None:
        self.stop()
        self._set_state("error", message)

    def stop(self) -> None:
        self._load_timer.stop()
        if self._media is not None:
            self._media.stop()
            self._media.setSource(QUrl())
        self._buffer.close()
        if self.job.active:
            self._set_state("stopping", "Stopping…")
            self.job.cancel()
        else:
            self._set_state("idle", "")

    def shutdown(self) -> None:
        self.stop()
        self.job.shutdown()
        self._buffer.setData(QByteArray())
        self._audio = b""
        self._cache_key = None
