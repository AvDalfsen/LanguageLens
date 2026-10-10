"""Shared Qt process supervision and asynchronous, owned image staging."""
from __future__ import annotations

import json
from pathlib import Path
from threading import Event

from PySide6.QtCore import QCoreApplication, QObject, QProcess, QTemporaryDir, QThread, QTimer, Signal, Slot
from PySide6.QtGui import QImage
from language_lens.runtime import worker_command
from language_lens.services.diagnostics import record_failure
from language_lens.services.errors import MESSAGES, describe_failure, failure_from_code


# A window can disappear while PNG encoding is finishing. Keep the unparented
# thread alive independently until its finished signal releases it.
_STAGERS: set = set()


class _ImageStage(QThread):
    def __init__(self, scratch, images):
        super().__init__()
        self.scratch = scratch
        self.images = {name: QImage(image) for name, image in images.items()}
        self.stopped = Event()
        self.error = ""
        self.claimed = False

    @Slot()
    def cancel(self):
        self.stopped.set()

    def run(self):
        try:
            for name, image in self.images.items():
                if self.stopped.is_set():
                    break
                if (Path(name).name != name or any(char in name for char in "\\/:")
                        or not image.save(str(Path(self.scratch.path()) / name), "PNG")):
                    raise OSError("Could not prepare the OCR crop.")
        except Exception as exc:
            record_failure("ocr-image-staging", exc)
            self.error = describe_failure(exc, "ocr").message
        finally:
            self.images.clear()

    @Slot()
    def release(self):
        if not self.claimed and self.scratch:
            self.scratch.remove()
        self.scratch = None
        _STAGERS.discard(self)
        self.deleteLater()

    @Slot()
    def on_quit(self):
        self.cancel()
        self.wait(30000)
        if not self.claimed and self.scratch and self.isFinished():
            self.scratch.remove()


class ProcessJob(QObject):
    failed = Signal(str)
    cancelled = Signal()
    activity_changed = Signal(bool)
    settled = Signal()  # Emitted after terminal callbacks and scratch cleanup.

    def __init__(self, parent=None):
        super().__init__(parent)
        self._process = self._scratch = self._stager = None
        self._buffer, self._error = b"", ""
        self._cancelled = self._ok = False
        self._command = ""
        self._timeout_ms = 120000
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self._timeout)

    @property
    def active(self):
        return self._process is not None

    def _start(self, module, command, payload, root, timeout, arguments=(), images=None):
        if self.active:
            return
        self._buffer, self._error, self._cancelled, self._ok = b"", "", False, False
        self._command, self._timeout_ms = command, timeout
        try:
            root.mkdir(parents=True, exist_ok=True)
            self._scratch = QTemporaryDir(str(root / ".job-XXXXXX"))
            if not self._scratch.isValid():
                raise OSError("Task directory is not writable.")
        except OSError as exc:
            record_failure("task-scratch", exc)
            if self._scratch:
                self._scratch.remove()
                self._scratch = None
            self.failed.emit(describe_failure(exc, command).message)
            self.settled.emit()
            return
        process = QProcess(self)
        self._process = process
        program, prefix = worker_command(module)
        process.setProgram(program)
        process.setArguments([*prefix, command, *arguments, "--scratch", self._scratch.path()])
        process.readyReadStandardOutput.connect(self._read)
        process.readyReadStandardError.connect(lambda: process.readAllStandardError())
        process.errorOccurred.connect(self._process_error)
        process.finished.connect(self._finished)
        request = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        def send():
            process.write(request)
            process.closeWriteChannel()
        process.started.connect(send)
        self._timer.start(timeout)
        if images:
            stage = _ImageStage(self._scratch, images)
            self._stager = stage
            _STAGERS.add(stage)
            stage.finished.connect(self._staged)
            stage.finished.connect(stage.release)
            self.destroyed.connect(stage.cancel)
            app = QCoreApplication.instance()
            if app:
                app.aboutToQuit.connect(stage.on_quit)
            stage.start()
        else:
            process.start()
        self.activity_changed.emit(True)

    @Slot()
    def _staged(self):
        self._finish_staging(self.sender())

    def _finish_staging(self, stage):
        if stage is not self._stager:
            return
        self._stager = None
        if self._cancelled or self._error or stage.error:
            self._error = self._error or stage.error
            # The staging thread owns cleanup until encoding has stopped.
            self._scratch = None
            self._finished(-1, QProcess.ExitStatus.CrashExit)
        else:
            stage.claimed = True
            self._timer.start(self._timeout_ms)
            self._process.start()

    def _read(self):
        process = self._process
        if process is None:
            return
        self._buffer += bytes(process.readAllStandardOutput())
        if len(self._buffer) > 16 * 1024 * 1024:
            self._error = failure_from_code("execution", self._command).message
            process.kill()
            return
        while b"\n" in self._buffer:
            line, self._buffer = self._buffer.split(b"\n", 1)
            try:
                message = json.loads(line)
            except (ValueError, UnicodeError):
                continue
            if not isinstance(message, dict):
                continue
            self._ok |= message.get("ok") is True
            if message.get("error"):
                failure = message.get("failure")
                self._error = (failure_from_code(failure["code"], self._command).message
                               if isinstance(failure, dict) and failure.get("code") in MESSAGES
                               else str(message["error"]))
            if not self._cancelled:
                self._handle_message(message, process)
            if self._process is not process:
                return

    def _touch(self, timeout=None):
        if not self._cancelled:
            self._timer.start(timeout or self._timeout_ms)

    def _handle_message(self, message, process):
        raise NotImplementedError

    def _process_error(self, error):
        if error == QProcess.ProcessError.FailedToStart:
            self._error = failure_from_code("runtime", self._command).message
            self._finished(-1, QProcess.ExitStatus.CrashExit)

    def _timeout_message(self):
        return failure_from_code("timeout", self._command).message

    def _timeout(self):
        self._error = self._timeout_message()
        if self._stager:
            self._stager.cancel()
        elif self._process:
            self._process.kill()

    def _finished(self, code, status):
        process = self._process
        if process is None:
            return
        self._read()
        if self._process is not process:
            return
        # Final buffered progress must not leave an inactivity timer running.
        self._timer.stop()
        cancelled, error, ok = self._cancelled, self._error, self._ok
        self._process = None
        scratch, self._scratch = self._scratch, None
        try:
            self.activity_changed.emit(False)
            if cancelled:
                self.cancelled.emit()
            elif code or status == QProcess.ExitStatus.CrashExit or error or not ok:
                self.failed.emit(error or failure_from_code("execution", self._command).message)
            else:
                self._succeeded(scratch)
        finally:
            if scratch:
                scratch.remove()
            process.deleteLater()
            self.settled.emit()

    def _succeeded(self, scratch):
        raise NotImplementedError

    def cancel(self):
        self._cancelled = True
        self._timer.stop()
        if self._stager:
            self._stager.cancel()
        elif self._process:
            self._process.kill()

    def shutdown(self):
        self.cancel()
        stage = self._stager
        if stage:
            if stage.wait(1500):
                self._finish_staging(stage)
        elif self._process:
            self._process.waitForFinished(1500)
