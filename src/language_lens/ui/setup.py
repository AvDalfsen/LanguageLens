from __future__ import annotations

from collections import deque
from time import monotonic

from PySide6.QtCore import QObject, QRunnable, Qt, QThreadPool, QTimer, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from language_lens.config import LANGUAGES, Settings
from language_lens.services.translation import ArgosTranslator
from language_lens.services.model_download import DownloadProgress
from language_lens.ui.pronunciation import PronunciationSettings


HOTKEYS = (
    ("Ctrl + Shift + T", "<ctrl>+<shift>+t"),
    ("Ctrl + Shift + Space", "<ctrl>+<shift>+<space>"),
    ("Alt + Shift + T", "<alt>+<shift>+t"),
    ("F8", "<f8>"),
)


class InstallSignals(QObject):
    progress = Signal(str)
    download_progress = Signal(object)
    finished = Signal()
    error = Signal(str)


class InstallTask(QRunnable):
    def __init__(self, source: str, target: str) -> None:
        super().__init__()
        self.source = source
        self.target = target
        self.signals = InstallSignals()

    def run(self) -> None:
        try:
            ArgosTranslator().install_pair(
                self.source, self.target, self.signals.progress.emit,
                self.signals.download_progress.emit,
            )
            self.signals.finished.emit()
        except Exception as exc:
            self.signals.error.emit(str(exc))


class SetupWindow(QMainWindow):
    listen_requested = Signal(object)
    capture_requested = Signal()

    def __init__(self, settings: Settings) -> None:
        super().__init__()
        self.setWindowTitle("Language Lens")
        self.setMinimumSize(610, 520)
        self.resize(740, 800)
        self._min_ocr_confidence = settings.min_ocr_confidence
        self._installing = False
        self._download_snapshot: DownloadProgress | None = None
        self._transfer_samples: deque[tuple[float, int]] = deque()
        self._stage_started = monotonic()
        self._last_byte_time = self._stage_started
        self._progress_timer = QTimer(self)
        self._progress_timer.setInterval(250)
        self._progress_timer.timeout.connect(self._update_download_metrics)

        title = QLabel("Language Lens")
        title.setObjectName("title")
        intro = QLabel(
            "Take a screenshot, read it with local OCR, and hover over words to see "
            "their translations. No screenshot or text is sent to a server."
        )
        intro.setWordWrap(True)
        intro.setObjectName("intro")

        card = QFrame()
        card.setObjectName("card")
        form = QFormLayout(card)
        form.setContentsMargins(24, 22, 24, 22)
        form.setVerticalSpacing(16)
        form.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapLongRows)

        self.source = QComboBox()
        self.target = QComboBox()
        for name, code in LANGUAGES:
            self.source.addItem(name, code)
            self.target.addItem(name, code)
        self._select_data(self.source, settings.source_language)
        self._select_data(self.target, settings.target_language)

        self.hotkey = QComboBox()
        for label, value in HOTKEYS:
            self.hotkey.addItem(label, value)
        self._select_data(self.hotkey, settings.hotkey)

        self.escape_helper = QCheckBox(
            "Send Escape after capture and on return"
        )
        self.escape_helper.setToolTip("Attempts to pause and resume the active application.")
        self.escape_helper.setChecked(settings.send_escape)

        form.addRow("Text language", self.source)
        form.addRow("Translate into", self.target)
        form.addRow("Capture hotkey", self.hotkey)
        form.addRow("Escape helper", self.escape_helper)

        self.model_status = QLabel()
        self.model_status.setTextFormat(Qt.TextFormat.PlainText)
        self.model_status.setWordWrap(True)
        self.model_progress = QProgressBar()
        self.model_progress.setRange(0, 0)
        self.model_progress.setTextVisible(False)
        self.model_progress.hide()
        self.model_details = QLabel()
        self.model_details.setObjectName("note")
        self.model_details.setTextFormat(Qt.TextFormat.PlainText)
        self.model_details.setWordWrap(True)
        self.model_details.hide()
        self.install_button = QPushButton("Download local translation model")
        self.install_button.clicked.connect(self.install_model)
        model_row = QHBoxLayout()
        model_row.addWidget(self.model_status, 1)
        model_row.addWidget(self.install_button)

        self.start_button = QPushButton("Start listening")
        self.start_button.setObjectName("primaryButton")
        self.start_button.clicked.connect(self._start)
        self.try_button = QPushButton("Try a capture now")
        self.try_button.clicked.connect(self.capture_requested)

        button_row = QHBoxLayout()
        button_row.addWidget(self.try_button)
        button_row.addStretch()
        button_row.addWidget(self.start_button)

        note = QLabel(
            "First use downloads OCR and translation models. After that, capture, OCR, "
            "and translation work offline. Borderless-windowed games are the most reliable."
        )
        note.setWordWrap(True)
        note.setObjectName("note")

        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(32, 30, 32, 30)
        layout.setSpacing(18)
        layout.addWidget(title)
        layout.addWidget(intro)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        content = QWidget()
        body = QVBoxLayout(content)
        body.setContentsMargins(0, 0, 8, 0)
        body.setSpacing(16)
        body.addWidget(card)
        body.addLayout(model_row)
        body.addWidget(self.model_progress)
        body.addWidget(self.model_details)
        self.pronunciation = PronunciationSettings(settings)
        body.addWidget(self.pronunciation)
        body.addWidget(note)
        body.addStretch()
        scroll.setWidget(content)
        layout.addWidget(scroll, 1)
        layout.addLayout(button_row)
        self.setCentralWidget(container)

        self.source.currentIndexChanged.connect(self.refresh_model_status)
        self.source.currentIndexChanged.connect(
            lambda: self.pronunciation.set_language(self.source.currentData())
        )
        self.target.currentIndexChanged.connect(self.refresh_model_status)
        self.refresh_model_status()

    @staticmethod
    def _select_data(combo: QComboBox, value: str) -> None:
        index = combo.findData(value)
        if index >= 0:
            combo.setCurrentIndex(index)

    def current_settings(self) -> Settings:
        return Settings(
            source_language=self.source.currentData(),
            target_language=self.target.currentData(),
            hotkey=self.hotkey.currentData(),
            send_escape=self.escape_helper.isChecked(),
            min_ocr_confidence=self._min_ocr_confidence,
            speech_enabled=self.pronunciation.enabled.isChecked(),
            show_ipa=self.pronunciation.show_ipa.isChecked(),
            speech_voices=dict(self.pronunciation.preferences),
        )

    def hideEvent(self, event) -> None:  # noqa: N802
        self.pronunciation.player.stop()
        super().hideEvent(event)

    def refresh_model_status(self) -> None:
        if self._installing:
            return
        try:
            ready = ArgosTranslator().is_pair_installed(
                self.source.currentData(), self.target.currentData()
            )
        except Exception:
            ready = False
        if ready:
            self.model_status.setText("✓ Local translation model is ready")
            self.model_status.setObjectName("modelReady")
            self.install_button.hide()
            self.start_button.setEnabled(True)
        else:
            self.model_status.setText("Local translation model is not installed yet")
            self.model_status.setObjectName("modelMissing")
            self.install_button.show()
            self.start_button.setEnabled(False)
        self.style().unpolish(self.model_status)
        self.style().polish(self.model_status)

    def install_model(self) -> None:
        if self._installing:
            return
        self._installing = True
        self.source.setEnabled(False)
        self.target.setEnabled(False)
        self.start_button.setEnabled(False)
        self.install_button.setEnabled(False)
        self.install_button.setText("Downloading…")
        self.model_progress.show()
        self.model_details.show()
        self._model_stage_changed("Preparing download…")
        self._progress_timer.start()
        task = InstallTask(self.source.currentData(), self.target.currentData())
        task.signals.progress.connect(self._model_stage_changed)
        task.signals.download_progress.connect(self._download_progress_changed)
        task.signals.finished.connect(self._install_finished)
        task.signals.error.connect(self._install_failed)
        QThreadPool.globalInstance().start(task)

    def _model_stage_changed(self, message: str) -> None:
        self.model_status.setText(message)
        self._stage_started = monotonic()
        self._download_snapshot = None
        self._transfer_samples.clear()
        self.model_progress.setRange(0, 0)
        self._update_download_metrics()

    def _download_progress_changed(self, progress: DownloadProgress) -> None:
        if not self._installing:
            return
        previous = self._download_snapshot
        if previous is None:
            self._transfer_samples.clear()
            self._transfer_samples.append((progress.timestamp, 0))
            self._last_byte_time = progress.timestamp
        if previous is None or progress.received > previous.received:
            self._last_byte_time = progress.timestamp
        self._download_snapshot = progress
        if progress.total:
            # Use a small fixed range to support archives larger than Qt's int range.
            self.model_progress.setRange(0, 1000)
            self.model_progress.setValue(min(1000, progress.received * 1000 // progress.total))
        else:
            self.model_progress.setRange(0, 0)
        self._update_download_metrics()

    @staticmethod
    def _size_label(size: float) -> str:
        for unit in ("B", "KB", "MB", "GB"):
            if size < 1000 or unit == "GB":
                return f"{size:.0f} {unit}" if unit == "B" else f"{size:.1f} {unit}"
            size /= 1000
        return ""

    @staticmethod
    def _duration_label(seconds: float) -> str:
        seconds = max(0, int(seconds))
        if seconds < 60:
            return f"{seconds} s"
        return f"{seconds // 60} min {seconds % 60:02} s"

    def _update_download_metrics(self) -> None:
        if not self._installing:
            return
        now = monotonic()
        current = self._download_snapshot
        if current is None:
            self.model_details.setText(f"{self._duration_label(now - self._stage_started)} elapsed")
            return
        samples = self._transfer_samples
        samples.append((now, current.received))
        while len(samples) > 2 and samples[1][0] <= now - 3:
            samples.popleft()
        # Smooth over the last three seconds, including timer ticks with no new data.
        elapsed = now - samples[0][0]
        rate = max(0, current.received - samples[0][1]) / elapsed if elapsed > .1 else 0
        received = self._size_label(current.received)
        if current.total:
            percent = min(100, current.received * 100 / current.total)
            amount = f"{percent:.1f}% · {received} / {self._size_label(current.total)}"
        else:
            amount = f"{received} downloaded · total size unavailable"
        details = f"{amount} · {self._size_label(rate)}/s"
        idle = now - self._last_byte_time
        if idle >= 3:
            details += f" · Waiting for data ({self._duration_label(idle)})"
        elif current.total and rate > 0 and current.received < current.total:
            remaining = (current.total - current.received) / rate
            details += f" · ~{self._duration_label(remaining)} remaining"
        self.model_details.setText(details)

    def _stop_model_progress(self) -> None:
        self._installing = False
        self._progress_timer.stop()
        self._download_snapshot = None
        self._transfer_samples.clear()
        self.model_progress.hide()
        self.model_details.hide()

    def _install_finished(self) -> None:
        self._stop_model_progress()
        self.source.setEnabled(True)
        self.target.setEnabled(True)
        self.install_button.setEnabled(True)
        self.install_button.setText("Download local translation model")
        self.refresh_model_status()

    def _install_failed(self, message: str) -> None:
        self._stop_model_progress()
        self.source.setEnabled(True)
        self.target.setEnabled(True)
        self.install_button.setEnabled(True)
        self.install_button.setText("Retry model download")
        self.model_status.setText(f"Model download failed: {message}")

    def _start(self) -> None:
        self.listen_requested.emit(self.current_settings())

