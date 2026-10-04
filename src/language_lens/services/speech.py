"""Qt supervision and playback for the local speech worker."""
from __future__ import annotations

import json
from pathlib import Path
import sys

from PySide6.QtCore import QByteArray, QBuffer, QIODevice, QObject, QProcess, QTemporaryDir, QTimer, QUrl, Signal
from PySide6.QtMultimedia import QAudioOutput, QMediaDevices, QMediaPlayer

from language_lens.services.voices import Voice, runtime_ready, voice_present, voices_root


class SpeechJob(QObject):
    progress = Signal(int, int)
    succeeded = Signal(object)
    failed = Signal(str)
    cancelled = Signal()

    def __init__(self, parent=None, *, root: Path | None = None) -> None:
        super().__init__(parent)
        self.root = root or voices_root()
        self._process: QProcess | None = None
        self._scratch: QTemporaryDir | None = None
        self._buffer = b""
        self._error = ""
        self._ok = False
        self._cancelled = False
        self._command = ""
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self._timeout)

    @property
    def active(self) -> bool:
        return self._process is not None

    def start(self, command: str, voice: Voice, text: str = "", **data) -> None:
        if self.active:
            return
        try:
            self.root.mkdir(parents=True, exist_ok=True)
            # QTemporaryDir fails promptly for a read-only Windows directory.
            # Python 3.10's tempfile can repeatedly retry PermissionError there.
            self._scratch = QTemporaryDir(str(self.root / ".job-XXXXXX"))
            if not self._scratch.isValid():
                raise OSError(self._scratch.errorString())
        except OSError as exc:
            self.failed.emit(f"Could not create speech files: {exc}")
            return
        self._buffer, self._error, self._ok, self._cancelled = b"", "", False, False
        self._command = command
        process = QProcess(self)
        self._process = process
        python = Path(sys.executable)
        if python.name.lower() == "pythonw.exe":
            python = python.with_name("python.exe")
        process.setProgram(str(python))
        process.setArguments(["-m", "language_lens.services.speech_worker", command,
                              "--voice", voice.id, "--root", str(self.root),
                              "--scratch", self._scratch.path()])
        # Qt uses CREATE_NO_WINDOW when the parent (our pythonw launcher) has no console.
        process.readyReadStandardOutput.connect(self._read)
        process.readyReadStandardError.connect(lambda: process.readAllStandardError())
        process.errorOccurred.connect(self._process_error)
        process.finished.connect(self._finished)
        payload = json.dumps({"text": text, **data}, ensure_ascii=False).encode("utf-8")

        def send_request():
            process.write(payload)
            process.closeWriteChannel()

        process.started.connect(send_request)
        self._timer.start(60000 if command in ("download", "pronunciation") else 180000)
        process.start()

    def _read(self) -> None:
        if self._process is None:
            return
        self._buffer += bytes(self._process.readAllStandardOutput())
        while b"\n" in self._buffer:
            raw, self._buffer = self._buffer.split(b"\n", 1)
            try:
                message = json.loads(raw)
            except (ValueError, UnicodeError):
                continue
            if "done" in message and "total" in message:
                self._timer.start(60000)  # download inactivity timeout
                if not self._cancelled:
                    self.progress.emit(message["done"], message["total"])
            if message.get("error"):
                self._error = str(message["error"])
            self._ok |= message.get("ok") is True

    def _process_error(self, error) -> None:
        if error == QProcess.ProcessError.FailedToStart:
            self._error = "Could not start local speech. Restart using Start Language Lens.bat."
            self._finished(-1, QProcess.ExitStatus.CrashExit)

    def _timeout(self) -> None:
        self._error = (
            "The voice download stopped making progress. Check your connection and retry."
            if self._command == "download" else
            "Local speech timed out. Try again, or select a shorter passage."
        )
        if self._process is not None:
            self._process.kill()

    def _finished(self, code: int, status) -> None:
        process = self._process
        if process is None:
            return
        self._timer.stop()
        self._read()
        self._process = None
        try:
            if self._cancelled:
                self.cancelled.emit()
            elif code or status == QProcess.ExitStatus.CrashExit or not self._ok or self._error:
                self.failed.emit(self._error or "The local speech process stopped unexpectedly. Please retry.")
            else:
                # Slots read the completed audio synchronously, before scratch cleanup.
                self.succeeded.emit(Path(self._scratch.path()))
        finally:
            if self._scratch is not None:
                self._scratch.remove()
                self._scratch = None
            process.deleteLater()

    def cancel(self) -> None:
        self._cancelled = True
        self._timer.stop()
        if self._process is not None:
            self._process.kill()

    def shutdown(self) -> None:
        self.cancel()
        if self._process is not None:
            self._process.waitForFinished(1500)


class SpeechPlayer(QObject):
    changed = Signal(str, str)  # state, user-facing detail

    def __init__(self, parent=None, *, root: Path | None = None) -> None:
        super().__init__(parent)
        self.job = SpeechJob(self, root=root)
        self.job.succeeded.connect(self._generated)
        self.job.failed.connect(self._failed)
        self.job.cancelled.connect(lambda: self._set_state("idle", ""))
        self.state = "idle"
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
        if not runtime_ready():
            self._failed("Restart using Start Language Lens.bat to install the speech components.")
            return
        if not voice_present(voice, self.job.root):
            self._failed("Download this voice in Settings first.")
            return
        # Accent, exact text, engine version and voice revision are part of identity.
        from language_lens.services.voices import PIPER_VERSION, REVISION
        self._pending_key = (text, phonemes, context_key, voice.id, voice.espeak, PIPER_VERSION, REVISION)
        if self._pending_key == self._cache_key and self._audio:
            self._play()
            return
        self._set_state("generating", "Preparing local audio…")
        if phonemes is None:
            self.job.start("synthesize", voice, text)
        else:
            self.job.start("phonemes", voice, phonemes=list(phonemes))

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
