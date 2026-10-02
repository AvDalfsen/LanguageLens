from __future__ import annotations

from PySide6.QtCore import QObject, QRunnable, QThreadPool, Signal
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
    QVBoxLayout,
    QWidget,
)

from language_lens.config import LANGUAGES, Settings
from language_lens.services.translation import ArgosTranslator


HOTKEYS = (
    ("Ctrl + Shift + T", "<ctrl>+<shift>+t"),
    ("Ctrl + Shift + Space", "<ctrl>+<shift>+<space>"),
    ("Alt + Shift + T", "<alt>+<shift>+t"),
    ("F8", "<f8>"),
)


class InstallSignals(QObject):
    progress = Signal(str)
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
                self.source, self.target, self.signals.progress.emit
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
        self.resize(680, 570)

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
            "Send Escape after capture, then again on return (attempt to pause the active app)"
        )
        self.escape_helper.setChecked(settings.send_escape)

        form.addRow("Text language", self.source)
        form.addRow("Translate into", self.target)
        form.addRow("Capture hotkey", self.hotkey)
        form.addRow("Escape helper", self.escape_helper)

        self.model_status = QLabel()
        self.model_status.setWordWrap(True)
        self.model_progress = QProgressBar()
        self.model_progress.setRange(0, 0)
        self.model_progress.setTextVisible(False)
        self.model_progress.hide()
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
        layout.addWidget(card)
        layout.addLayout(model_row)
        layout.addWidget(self.model_progress)
        layout.addWidget(note)
        layout.addStretch()
        layout.addLayout(button_row)
        self.setCentralWidget(container)

        self.source.currentIndexChanged.connect(self.refresh_model_status)
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
        )

    def refresh_model_status(self) -> None:
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
        self.source.setEnabled(False)
        self.target.setEnabled(False)
        self.start_button.setEnabled(False)
        self.install_button.setEnabled(False)
        self.install_button.setText("Downloading…")
        self.model_progress.show()
        self.model_status.setText("Preparing download…")
        task = InstallTask(self.source.currentData(), self.target.currentData())
        task.signals.progress.connect(self.model_status.setText)
        task.signals.finished.connect(self._install_finished)
        task.signals.error.connect(self._install_failed)
        QThreadPool.globalInstance().start(task)

    def _install_finished(self) -> None:
        self.source.setEnabled(True)
        self.target.setEnabled(True)
        self.install_button.setEnabled(True)
        self.install_button.setText("Download local translation model")
        self.model_progress.hide()
        self.refresh_model_status()

    def _install_failed(self, message: str) -> None:
        self.source.setEnabled(True)
        self.target.setEnabled(True)
        self.install_button.setEnabled(True)
        self.install_button.setText("Retry model download")
        self.model_progress.hide()
        self.model_status.setText(f"Model download failed: {message}")

    def _start(self) -> None:
        self.listen_requested.emit(self.current_settings())

