"""Bounded, cancellable native tasks, isolated from the Qt GUI process."""
from __future__ import annotations


from PySide6.QtCore import Signal
from language_lens.services.process_job import ProcessJob

from language_lens.config import settings_path
from language_lens.domain import OcrLine, OcrSpanBox, WordTranslation


def decode_line(item) -> OcrLine:
    return OcrLine(item["text"], item["confidence"], tuple(map(tuple, item["polygon"])),
                   tuple(OcrSpanBox(box["start"], box["end"], tuple(map(tuple, box["polygon"])))
                         for box in item.get("span_boxes", ())),
                   tuple(map(tuple, item["token_spans"])) if item.get("token_spans") is not None else None)


class ServiceJob(ProcessJob):
    event = Signal(object)
    finished = Signal()

    # Preserve the public service-job process/scratch accessors.
    @property
    def process(self):
        return self._process

    @process.setter
    def process(self, value):
        self._process = value

    @property
    def scratch(self):
        return self._scratch

    @scratch.setter
    def scratch(self, value):
        self._scratch = value

    def start(self, command: str, payload: dict, images: dict | None = None) -> None:
        timeout = 300000 if command in ("install", "prepare", "repair", "remove", "pack-install", "pack-remove") else 120000
        if command == "status":
            timeout = 30000
        self._start("language_lens.services.task_worker", command, payload,
                    settings_path().parent / "jobs", timeout, images=images)

    def _handle_message(self, message, process):
        self.event.emit(message)
        if self._process is process and (message.get("progress") or message.get("download") or "result" in message):
            self._touch()

    def _succeeded(self, scratch):
        self.finished.emit()


class TaskPool:
    """Small compatibility dispatcher for the existing domain task signals."""
    @classmethod
    def globalInstance(cls):  # noqa: N802
        return cls()

    def start(self, task):
        from language_lens.services.tasks import encode_task
        command, payload, images = encode_task(task)
        job = ServiceJob(task.signals)
        def event(message):
            if "progress" in message:
                task.signals.progress.emit(message["progress"])
            if "result" not in message:
                return
            result = message["result"]
            if command == "ocr":
                value = [decode_line(item) for item in result]
            elif command == "translate":
                value = (result["sentence"], {word: WordTranslation(tuple(item["candidates"]), item["note"])
                                              for word, item in result["words"].items()})
            else:
                value = (task.word, WordTranslation(tuple(result["candidates"]), result["note"]), "")
            task.signals.result.emit(value)
        job.event.connect(event)
        job.failed.connect(task.signals.error)
        if command == "more":
            job.failed.connect(lambda message: task.signals.result.emit((task.word, None, message)))
            job.cancelled.connect(lambda: task.signals.result.emit((task.word, None, "Search cancelled. Choose 'Retry wider search'.")))
        job.start(command, payload, images)
        return job
