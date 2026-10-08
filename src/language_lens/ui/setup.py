from __future__ import annotations

from dataclasses import asdict
from time import monotonic

from PySide6.QtCore import QEvent, QSize, Qt, QTimer, Signal
from PySide6.QtGui import QCursor, QGuiApplication, QKeySequence
from PySide6.QtWidgets import (
    QComboBox,
    QBoxLayout,
    QFormLayout,
    QGridLayout,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLayout,
    QMainWindow,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QStyle,
    QVBoxLayout,
    QWidget,
)

from language_lens.config import LANGUAGES, Settings
from language_lens.services.hotkey import normalize_hotkey, display_hotkey
from language_lens.services.model_download import DownloadProgress
from language_lens.services.jobs import ServiceJob
from language_lens.services.availability import Availability
from language_lens.services.diagnostics import open_folder
from language_lens.ui.pronunciation import PronunciationSettings
from language_lens.ui.style import set_help
from language_lens.ui.help import HelpDialog
from language_lens.ui.identity import app_icon
from language_lens.ui.hotkey import CaptureHotkeyEdit
from language_lens.ui.progress import TransferMetrics
from language_lens.ui.sections import ExpandableSection


class SetupWindow(QMainWindow):
    listen_requested = Signal(object)
    capture_requested = Signal()
    window_preferences_changed = Signal()
    pause_requested = Signal()
    readiness_changed = Signal(bool)
    hotkey_changed = Signal(str)
    preferences_changed = Signal()
    availability_changed = Signal()
    visibility_changed = Signal()
    closed_to_tray = Signal()

    def __init__(self, settings: Settings) -> None:
        super().__init__()
        self.setWindowTitle("Language Lens")
        self.setWindowIcon(app_icon())
        self._help_dialog = None
        self._size_initialized = False
        self._auto_sizing = False
        size = settings.settings_window_size
        self._remembered_size = list(size) if (
            isinstance(size, list) and len(size) == 2
            and all(type(value) is int and value > 0 for value in size)
        ) else None
        self._remembered_maximized = settings.settings_window_maximized is True
        self._auto_width: int | None = None
        self._sizing_timer = QTimer(self)
        self._sizing_timer.setSingleShot(True)
        self._sizing_timer.timeout.connect(self._fit_or_restore_size)
        self._preference_timer = QTimer(self)
        self._preference_timer.setSingleShot(True)
        self._preference_timer.setInterval(300)
        self._preference_timer.timeout.connect(self.window_preferences_changed)
        self._min_ocr_confidence = settings.min_ocr_confidence
        self._installing = False
        self._capture_busy = False
        self._shutting_down = False
        self._last_availability = None
        self._close_notified = settings.tray_close_notice_shown
        self._translation_ready = False
        self._files_ready = False
        self._model_task_error = None
        self._status_check_failed = False
        self._status_job = ServiceJob(self)
        self._status_job.event.connect(self._status_event)
        self._status_job.failed.connect(self._status_failed)
        self._status_timer = QTimer(self)
        self._status_timer.setSingleShot(True)
        self._status_timer.timeout.connect(self._start_status_check)
        self.model_job = ServiceJob(self)
        self.model_job.event.connect(self._model_event)
        self.model_job.finished.connect(self._install_finished)
        self.model_job.failed.connect(self._install_failed)
        self.model_job.cancelled.connect(self._install_finished)
        self._active_hotkey = None
        self._download_snapshot: DownloadProgress | None = None
        self._transfer_metrics = TransferMetrics(monotonic())
        self._progress_timer = QTimer(self)
        self._progress_timer.setInterval(250)
        self._progress_timer.timeout.connect(self._update_download_metrics)

        title = QLabel("Language Lens")
        title.setObjectName("title")
        intro = QLabel(
            "Explore the text on your screen, one word or a whole sentence at a time. "
            "Everything is processed on your computer."
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

        self._hotkey_value = normalize_hotkey(settings.hotkey)
        self.hotkey_valid = True
        self.hotkey = CaptureHotkeyEdit(QKeySequence(display_hotkey(self._hotkey_value)))
        self.hotkey.setMaximumSequenceLength(1)
        self.hotkey.setAccessibleName("Capture hotkey")
        self.reset_hotkey = QPushButton("Reset to F8")
        self.reset_hotkey.clicked.connect(lambda: self.hotkey.setKeySequence(QKeySequence("F8")))
        set_help(self.reset_hotkey, "Restore 'Capture hotkey' to F8, the default for new settings. "
            "The shortcut is remembered immediately for future sessions. Click 'Pause listening' before changing it; "
            "then click 'Start listening' to register it. Resetting does not start listening or capture a screenshot.")
        hotkey_field = QWidget()
        hotkey_layout = QVBoxLayout(hotkey_field)
        hotkey_layout.setContentsMargins(0, 0, 0, 0)
        hotkey_row = QHBoxLayout()
        hotkey_row.addWidget(self.hotkey, 1)
        hotkey_row.addWidget(self.reset_hotkey)
        hotkey_layout.addLayout(hotkey_row)
        self.hotkey_note = QLabel("Click the shortcut field and press your preferred key combination.")
        self.hotkey_note.setObjectName("note")
        self.hotkey_note.setWordWrap(True)
        hotkey_layout.addWidget(self.hotkey_note)

        self.capture_scope = QComboBox()
        self.capture_scope.addItem("All monitors", "all")
        self.capture_scope.addItem("Monitor under the pointer", "current")
        self._select_data(self.capture_scope, settings.capture_scope)
        set_help(self.source,
            "Choose the language written in the screenshot. This controls OCR, word segmentation, "
            "and the original-language pronunciation and IPA. It is independent of the language "
            "you translate into. Recognition and pronunciation support vary by language."
        )
        set_help(self.target,
            "Choose the language you want to read the translations in, usually a language you "
            "already know. Translation models are directional: a model for English to Dutch "
            "does not also provide Dutch to English. Some pairs use two local models via English."
        )
        set_help(self.hotkey,
            "Click this field and press a key or combination to set the global screenshot shortcut. "
            "It shows 'Listening for new hotkey...' while waiting; leaving without entering a shortcut "
            "restores the previous value. "
            "F8 is the default; 'Reset to F8' restores it. Letters A–Z, digits 0–9, function keys F1–F24 "
            "except F12, and navigation keys are supported, optionally with Ctrl, Alt or Shift. "
            "Prefer a function key or modifiers: bare letters and numbers can interfere with typing while listening. "
            "One combination is recorded, not a sequence. Windows-key shortcuts and reserved combinations are excluded. "
            "Valid choices are remembered immediately. Click 'Start listening' to register this shortcut. While listening, this row "
            "shows the active shortcut and cannot be changed; click 'Pause listening' first to choose another. "
            "If another application already uses it, choose a different shortcut. Lens does not "
            "pause the application; pause manually before capturing if needed."
        )
        set_help(self.capture_scope,
            "'All monitors' freezes a screenshot on every connected monitor so you can select text "
            "anywhere on the desktop. 'Monitor under the pointer' captures only the screen your mouse "
            "is on when capture starts. This leaves other monitors uncovered and usable, uses less "
            "memory, and reduces screenshot/rendering work. It does not improve translation accuracy: "
            "OCR already reads only the area you select. With 'Try a capture now', the monitor is "
            "chosen before 'Settings' is hidden."
        )

        form.addRow("Text language", self.source)
        form.addRow("Translate into", self.target)
        form.addRow("Capture hotkey", hotkey_field)
        form.addRow("Capture area", self.capture_scope)
        for field, name in ((self.source, "Text language"), (self.target, "Translate into"),
                            (self.capture_scope, "Capture area")):
            field.setAccessibleName(name)
        self.hotkey.keySequenceChanged.connect(self._hotkey_edited)

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
        self.capabilities = QLabel()
        self.capabilities.setWordWrap(True)
        self.capabilities.setTextFormat(Qt.TextFormat.PlainText)
        self.capabilities.setObjectName("note")
        self.prepare_button = QPushButton("Download required files")
        self.prepare_button.clicked.connect(self._prepare_files)
        set_help(self.prepare_button, "Lens always runs OCR and translation locally; there is no online translation mode. "
            "Download any missing OCR, translation, and sentence-boundary files, then check a fixed sample without networking. "
            "Translation between some languages needs two models via English; both are handled automatically. "
            "Only missing or changed files need downloading. Once checked, this button becomes 'Check required files' "
            "to repeat the check. Voices are separate downloads. Use 'Cancel model task' to stop the operation.")
        self.repair_button = QPushButton("Reinstall translation model")
        self.remove_button = QPushButton("Remove translation")
        self.cancel_button = QPushButton("Cancel model task")
        self.cancel_button.hide()
        self.diagnostics_button = QPushButton("Open diagnostics folder")
        self.diagnostics_button.clicked.connect(open_folder)
        self.diagnostics_button.hide()
        set_help(self.repair_button, "Optional troubleshooting: download and validate replacement translation packages "
            "for this direction if translation keeps failing. This button does not mean a problem has been detected. "
            "Existing packages stay usable until replacements are ready; replaced packages are kept as recoverable backups. "
            "A route via English may share models with other pairs. Use 'Check required files' afterwards.")
        set_help(self.remove_button, "Move every translation package used by this direction to a recoverable backup "
            "beside the Argos packages directory. Shared pivot packages may also be needed by other language pairs. "
            "OCR assets and voices are not removed. This does not reclaim the backup's disk space.")
        set_help(self.cancel_button, "Stop the current model operation, including a stalled download or preparation. "
            "Previously installed models are retained. A completed package stays installed; an interrupted replacement "
            "is recovered on the next model operation. You can retry without restarting Lens.")
        self.cancel_button.clicked.connect(self.model_job.shutdown)
        self.repair_button.clicked.connect(lambda: self._manage_model("repair"))
        self.remove_button.clicked.connect(lambda: self._manage_model("remove"))
        self.maintenance = ExpandableSection("Manage local files")
        set_help(self.maintenance.toggle, "Show optional checks and troubleshooting actions for the selected language pair. "
            "These are not required for routine captures and do not mean that files are broken. "
            "'Reinstall translation model' replaces translation packages; 'Remove translation' keeps recoverable backups.")
        self._maintenance_layout = QGridLayout(self.maintenance.content)
        self._maintenance_layout.setContentsMargins(0, 0, 0, 0)
        self._maintenance_layout.addWidget(self.repair_button, 1, 0)
        self._maintenance_layout.addWidget(self.remove_button, 1, 1)
        from language_lens.services import language_packs as packs
        self.pack_choice = QComboBox()
        self.pack_choice.setAccessibleName("Optional language pack")
        for key, item in packs.catalog()["packs"].items():
            self.pack_choice.addItem(item["name"], key)
        self.pack_status = QLabel()
        self.pack_status.setWordWrap(True)
        self.pack_install = QPushButton("Download pack")
        self.pack_remove = QPushButton("Remove pack")
        self._pack_inventory = []
        self._maintenance_layout.addWidget(self.pack_choice, 2, 0, 1, 2)
        self._maintenance_layout.addWidget(self.pack_status, 3, 0, 1, 2)
        self._maintenance_layout.addWidget(self.pack_install, 4, 0)
        self._maintenance_layout.addWidget(self.pack_remove, 4, 1)
        self.pack_choice.currentIndexChanged.connect(self._refresh_packs)
        self.pack_install.clicked.connect(lambda: self._start_model_job("pack-install", pack=self.pack_choice.currentData()))
        self.pack_remove.clicked.connect(self._remove_pack)
        self._required_actions = QHBoxLayout()
        self._required_actions.addWidget(self.prepare_button)
        self._required_actions.addWidget(self.cancel_button)
        self._required_actions.addStretch()
        self.technical_details = ExpandableSection("Technical details")
        details_layout = QVBoxLayout(self.technical_details.content)
        details_layout.setContentsMargins(0, 0, 0, 0)
        details_layout.addWidget(self.capabilities)

        self.start_button = QPushButton("Start listening")
        self.start_button.setObjectName("primaryButton")
        self.start_button.clicked.connect(self._toggle_listening)
        self.try_button = QPushButton("Try a capture now")
        self.try_button.clicked.connect(self.capture_requested)
        set_help(self.try_button,
            "Hide 'Settings' briefly, capture the selected monitor(s), and let you drag around text. "
            "This tests capture, OCR, translation, and pronunciation without registering a global "
            "hotkey. First use 'Download required files' or 'Check required files' to verify the local OCR "
            "and translation files; this button stays disabled until they are ready. "
            "Closing or cancelling the screenshot returns to 'Settings'."
        )

        self.help_button = QPushButton("Help and about")
        self.help_button.clicked.connect(self.show_help)
        button_row = QHBoxLayout()
        button_row.addWidget(self.help_button)
        button_row.addWidget(self.try_button)
        button_row.addStretch()
        button_row.addWidget(self.start_button)
        self._button_row = button_row
        buttons = QWidget()
        buttons.setLayout(button_row)

        note = QLabel(
            "Pause games manually before capturing. Borderless-windowed apps work best. "
            "Closing 'Settings' keeps Lens running in the tray."
        )
        note.setWordWrap(True)
        note.setObjectName("note")

        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(32, 30, 32, 30)
        layout.setSpacing(18)
        layout.setSizeConstraint(QLayout.SizeConstraint.SetNoConstraint)
        layout.addWidget(title)
        layout.addWidget(intro)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.scroll = scroll
        content = QWidget()
        body = QVBoxLayout(content)
        body.setContentsMargins(0, 0, 8, 0)
        body.setSpacing(16)
        body.addWidget(card)
        body.addWidget(self.model_status)
        body.addWidget(self.model_progress)
        body.addWidget(self.model_details)
        body.addLayout(self._required_actions)
        body.addWidget(self.diagnostics_button)
        body.addWidget(self.maintenance)
        body.addWidget(self.technical_details)
        self.pronunciation = PronunciationSettings(settings)
        self.pronunciation.activity_changed.connect(self._refresh_availability)
        self.pronunciation.download.succeeded.connect(lambda _path: self.refresh_model_status())
        self.pronunciation.preferences_changed.connect(self.preferences_changed)
        body.addWidget(self.pronunciation)
        body.addWidget(note)
        body.addStretch()
        content.installEventFilter(self)
        scroll.setWidget(content)
        layout.addWidget(scroll, 1)
        layout.addWidget(buttons)
        self.setCentralWidget(container)

        self.source.currentIndexChanged.connect(self.refresh_model_status)
        self.source.currentIndexChanged.connect(
            lambda: self.pronunciation.set_language(self.source.currentData())
        )
        self.target.currentIndexChanged.connect(self.refresh_model_status)
        for combo in (self.source, self.target, self.capture_scope):
            combo.currentIndexChanged.connect(self.preferences_changed)
        self.refresh_model_status()

    def _place_file_check(self, optional: bool) -> None:
        """Only a needed next action belongs outside optional maintenance."""
        self.prepare_button.setObjectName("" if optional else "primaryButton")
        self.start_button.setObjectName("primaryButton" if optional else "")
        for button in (self.prepare_button, self.start_button):
            button.style().unpolish(button)
            button.style().polish(button)
            button.update()
        self._required_actions.removeWidget(self.prepare_button)
        self._maintenance_layout.removeWidget(self.prepare_button)
        if optional:
            self._maintenance_layout.addWidget(self.prepare_button, 0, 0, 1, 2)
        else:
            self._required_actions.insertWidget(0, self.prepare_button)
        self.prepare_button.show()
        # Reparenting the optional check changes Qt's default focus chain.
        # Keep Tab in visual order in both ready and not-ready layouts.
        order = [self.source, self.target, self.hotkey, self.reset_hotkey, self.capture_scope]
        if not optional:
            order.append(self.prepare_button)
        order.extend((self.cancel_button, self.diagnostics_button, self.maintenance.toggle))
        if optional:
            order.append(self.prepare_button)
        order.extend((self.repair_button, self.remove_button, self.pack_choice, self.pack_install, self.pack_remove, self.technical_details.toggle,
                      self.pronunciation.enabled, self.pronunciation.show_ipa, self.pronunciation.voices,
                      self.pronunciation.install, self.pronunciation.preview, self.pronunciation.details,
                      self.help_button, self.try_button, self.start_button))
        for before, after in zip(order, order[1:]):
            QWidget.setTabOrder(before, after)

    def show_help(self) -> None:
        if self._help_dialog is None:
            self._help_dialog = HelpDialog(self)
        self._help_dialog.open()
        self._help_dialog.raise_()

    @staticmethod
    def _select_data(combo: QComboBox, value: str) -> None:
        index = combo.findData(value)
        if index >= 0:
            combo.setCurrentIndex(index)

    def current_settings(self) -> Settings:
        return Settings(
            source_language=self.source.currentData(),
            target_language=self.target.currentData(),
            hotkey=self._hotkey_value,
            capture_scope=self.capture_scope.currentData(),
            min_ocr_confidence=self._min_ocr_confidence,
            speech_enabled=self.pronunciation.enabled.isChecked(),
            show_ipa=self.pronunciation.show_ipa.isChecked(),
            speech_voices=dict(self.pronunciation.preferences),
            speech_speed=self.pronunciation.speech_speed,
            settings_window_size=list(self._remembered_size) if self._remembered_size else None,
            settings_window_maximized=self._remembered_maximized,
            tray_close_notice_shown=self._close_notified,
        )

    def _available_geometry(self):
        screen = self.screen() if self._size_initialized else (
            QGuiApplication.screenAt(QCursor.pos()) or self.screen()
        )
        return screen.availableGeometry()

    def _preferred_size(self, maximum: QSize) -> QSize:
        """Measure wrapped content, bypassing QScrollArea's limited size hint."""
        layout = self.centralWidget().layout()
        content_layout = self.scroll.widget().layout()
        margins = layout.contentsMargins()
        frame = self.scroll.frameWidth() * 2
        if self._auto_width is None:
            self._auto_width = max(
                layout.minimumSize().width(),
                content_layout.sizeHint().width() + margins.left() + margins.right() + frame,
            )
        width = min(maximum.width(), max(
            self._auto_width,
            self.minimumWidth(),
            content_layout.minimumSize().width() + margins.left() + margins.right() + frame
            + self.style().pixelMetric(QStyle.PixelMetric.PM_ScrollBarExtent),
        ))
        height = self._height_at_width(width)
        if height > maximum.height():
            # Find the narrowest wider layout that fits. Qt forms can change
            # row wrapping at discrete widths, so measure actual candidate widths.
            while width < maximum.width() and height > maximum.height():
                width = min(maximum.width(), width + 24)
                height = self._height_at_width(width)
        self._adapt_footer(width)
        return QSize(width, min(maximum.height(), height))

    def _height_at_width(self, width: int) -> int:
        layout = self.centralWidget().layout()
        content_layout = self.scroll.widget().layout()
        margins = layout.contentsMargins()
        frame = self.scroll.frameWidth() * 2
        inner_width = max(1, width - margins.left() - margins.right())
        self._adapt_footer(width)
        viewport_width = max(1, inner_width - frame)
        # Reserve a scrollbar-width worth of wrapping room. Otherwise Qt can
        # latch onto the narrower, already-scrollable viewport during first
        # layout and retain a scrollbar even at the exact no-scroll height.
        wrapping_width = max(1, viewport_width - self.style().pixelMetric(QStyle.PixelMetric.PM_ScrollBarExtent))
        content_width = max(wrapping_width, content_layout.minimumSize().width())
        content_height = content_layout.totalHeightForWidth(content_width)
        if content_height < 0:
            content_height = content_layout.totalSizeHint().height()
        height = margins.top() + margins.bottom() + content_height + frame
        if content_width > viewport_width:
            height += self.style().pixelMetric(QStyle.PixelMetric.PM_ScrollBarExtent)
        visible = 1  # the scroll area
        for index in range(layout.count()):
            widget = layout.itemAt(index).widget()
            if widget is None or widget is self.scroll or widget.isHidden():
                continue
            widget_height = widget.heightForWidth(inner_width)
            height += widget_height if widget_height >= 0 else widget.sizeHint().height()
            visible += 1
        height += layout.spacing() * (visible - 1)
        return height + 8  # allow Qt's final scroll-area layout a little rounding room

    def _adapt_footer(self, width: int) -> None:
        # Apply this to saved/manual sizes too, especially on a smaller monitor.
        margins = self.centralWidget().layout().contentsMargins()
        inner_width = max(1, width - margins.left() - margins.right())
        row_margins = self._button_row.contentsMargins()
        horizontal_minimum = (
            sum(max(button.minimumWidth(), button.minimumSizeHint().width())
                for button in (self.help_button, self.try_button, self.start_button))
            + row_margins.left() + row_margins.right()
            + max(0, self._button_row.spacing()) * 3
        )
        self._button_row.setDirection(
            QBoxLayout.Direction.TopToBottom if inner_width < horizontal_minimum
            else QBoxLayout.Direction.LeftToRight
        )

    def _fit_or_restore_size(self, *, center: bool = False) -> None:
        if self.isMinimized() or (self._size_initialized and self.isMaximized()):
            return
        self._auto_sizing = True
        try:
            area = self._available_geometry()
            extra = self.frameGeometry().size() - self.size()
            maximum = QSize(max(1, area.width() - max(0, extra.width())),
                            max(1, area.height() - max(0, extra.height())))
            self.setMinimumSize(min(610, maximum.width()), min(350, maximum.height()))
            if self._remembered_size:
                target = QSize(*self._remembered_size).expandedTo(self.minimumSize()).boundedTo(maximum)
            else:
                target = self._preferred_size(maximum).expandedTo(self.minimumSize()).boundedTo(maximum)
            self._adapt_footer(target.width())
            if self.size() != target:
                self.resize(target)
            frame = self.frameGeometry()
            if center:
                frame.moveCenter(area.center())
            else:
                frame.moveLeft(max(area.left(), min(frame.left(), area.right() - frame.width() + 1)))
                frame.moveTop(max(area.top(), min(frame.top(), area.bottom() - frame.height() + 1)))
            self.move(frame.topLeft())
        finally:
            self._auto_sizing = False

    def showEvent(self, event) -> None:  # noqa: N802
        super().showEvent(event)
        if not self._size_initialized:
            self.ensurePolished()
            for widget in self.findChildren(QWidget):
                widget.ensurePolished()
            self._fit_or_restore_size(center=True)
            self._size_initialized = True
            if self._remembered_maximized:
                self._auto_sizing = True
                self.showMaximized()
                self._auto_sizing = False
        self._sizing_timer.start(0)
        self.visibility_changed.emit()

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        self._adapt_footer(event.size().width())
        if (self._size_initialized and self.isVisible() and not self._auto_sizing
                and not self.isMaximized() and not self.isMinimized()):
            self._remembered_size = [event.size().width(), event.size().height()]
            self._remembered_maximized = False
            self._preference_timer.start()

    def changeEvent(self, event) -> None:  # noqa: N802
        super().changeEvent(event)
        if (event.type() == QEvent.Type.WindowStateChange and self._size_initialized
                and not self._auto_sizing and not self.isMinimized()):
            self._remembered_maximized = self.isMaximized()
            if self._remembered_maximized and self._remembered_size is None:
                size = self.normalGeometry().size()
                self._remembered_size = [size.width(), size.height()]
            self._preference_timer.start()

    def eventFilter(self, watched, event) -> bool:  # noqa: N802
        if (event.type() == QEvent.Type.LayoutRequest and self._size_initialized
                and not self._auto_sizing and self._remembered_size is None and self.isVisible()):
            self._sizing_timer.start(0)
        return super().eventFilter(watched, event)

    def hideEvent(self, event) -> None:  # noqa: N802
        self.pronunciation.player.stop()
        if self._preference_timer.isActive():
            self._preference_timer.stop()
            self.window_preferences_changed.emit()
        super().hideEvent(event)
        self.preferences_changed.emit()
        self.visibility_changed.emit()

    def closeEvent(self, event) -> None:  # noqa: N802
        if not self._shutting_down and not self._close_notified:
            self._close_notified = True
            self.closed_to_tray.emit()
        self.preferences_changed.emit()
        super().closeEvent(event)

    def refresh_model_status(self) -> None:
        if self._installing or self._shutting_down:
            return
        self._translation_ready = False
        self._set_files_ready(False)
        self._refresh_listening()
        self.repair_button.setEnabled(False)
        self.remove_button.setEnabled(False)
        self.model_status.setText("Checking local capabilities…")
        self._place_file_check(False)
        self._status_check_failed = False
        self._show_model_task_error()
        self._status_timer.start(100)

    def _show_model_task_error(self) -> None:
        if self._model_task_error and self._model_task_error[:2] == (self.source.currentData(), self.target.currentData()):
            self.model_status.setText(self.model_status.text() + f"\nPrevious model task failed: {self._model_task_error[2]}")

    def _start_status_check(self) -> None:
        if self._installing or self._shutting_down:
            return
        self._status_job.shutdown()
        self._status_job.start("status", {"settings": asdict(self.current_settings())})

    def _status_event(self, message) -> None:
        if "result" in message and not self._installing:
            result = message["result"]
            if (result["source"], result["target"]) == (self.source.currentData(), self.target.currentData()):
                self._apply_model_status(result)

    def _status_failed(self, message: str) -> None:
        if not self._installing:
            self._translation_ready = False
            self._set_files_ready(False)
            self._status_check_failed = True
            self.model_status.setText(f"Could not check models: {message}")
            self.model_status.setObjectName("modelMissing")
            self.prepare_button.setText("Retry file check")
            self.capabilities.setText("Installation status is unknown because the check failed. No local files were removed.")
            self.diagnostics_button.show()
            self._refresh_availability()

    def _prepare_files(self) -> None:
        if self._status_check_failed:
            self.refresh_model_status()
        else:
            self._start_model_job("prepare")

    def _apply_model_status(self, result) -> None:
        self._pack_inventory = result.get("packs", [])
        self.pronunciation.refresh()
        self._status_check_failed = False
        self.diagnostics_button.setVisible(bool(self._model_task_error))
        ready = self._translation_ready = result["ready"]
        prepared = result["prepared"]
        if ready and prepared:
            self.model_status.setText("Ready to capture — required local files verified")
            self.model_status.setObjectName("modelReady")
        elif ready:
            self.model_status.setText("Translation model installed. Required files still need checking; use 'Download required files'.")
            self.model_status.setObjectName("modelMissing")
        else:
            self.model_status.setText("Translation model missing for this language pair; use 'Download required files'.")
            self.model_status.setObjectName("modelMissing")
        self._set_files_ready(ready and prepared)
        self.prepare_button.setText("Check required files" if ready and prepared else "Download required files")
        self._place_file_check(ready and prepared)
        self.repair_button.setEnabled(ready and self.source.currentData() != self.target.currentData())
        self.remove_button.setEnabled(self.repair_button.isEnabled())
        source = self.source.currentData()
        from language_lens.services import language_packs as packs
        required = packs.text_pack(source)
        if required and any(item["id"] == required and not item["ready"] for item in self._pack_inventory):
            self.model_status.setText(self.model_status.text() +
                f" {packs.definition(required)['name']} adds a {packs.download_bytes(required) / 1_000_000:.1f} MB download.")
        segmentation = "Offline dictionary segmentation" if source in {"ja", "zh"} else "Unicode word boundaries; not a morphological parser"
        route_text = " → ".join(result["route"]) if result["route"] else "Same language" if ready else "Missing"
        notation = "Audited estimated IPA" if source in {"en", "pt", "pb"} else "Engine phonetic notation (not conventionally formatted IPA)"
        self.capabilities.setText(f"Required OCR + translation files: {'checked and ready' if ready and prepared else 'not checked / files changed'}. "
            f"Translation route: {route_text}.\nWords: {segmentation}. Pronunciation display: {notation}. "
            "Voice readiness is shown below. Recognition, word boundaries and pronunciations may be approximate.")
        self.style().unpolish(self.model_status)
        self.style().polish(self.model_status)
        self._show_model_task_error()
        self.set_capture_busy(self._capture_busy)

    def _refresh_packs(self) -> None:
        from language_lens.services import language_packs as packs
        key = self.pack_choice.currentData()
        item = next((item for item in self._pack_inventory if item["id"] == key), {})
        installed = item.get("ready", False)
        self.pack_status.setText(("Installed" if installed else "Not installed or needs updating")
            + f" · Download: {packs.download_bytes(key) / 1_000_000:.1f} MB. Shared by all language pairs.")
        self.pack_install.setText("Check pack files" if installed else "Download pack")
        allowed = self.availability.maintenance_enabled
        self.pack_choice.setEnabled(allowed)
        self.pack_install.setEnabled(allowed)
        self.pack_remove.setEnabled(allowed and item.get("managed", False))

    def _remove_pack(self) -> None:
        if not self.availability.maintenance_enabled:
            return
        answer = QMessageBox.question(self, "Remove language pack",
            "Remove this optional pack for all language pairs? Its word lookup or pronunciation will need a new download. "
            "Translation models and voices are kept. Files currently in use may be freed after restarting and removing again.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        if answer == QMessageBox.StandardButton.Yes:
            self._start_model_job("pack-remove", pack=self.pack_choice.currentData())

    def _manage_model(self, command: str) -> None:
        if not self.availability.maintenance_enabled:
            return
        action = ("Validated replacements are installed only after downloading; previous versions are kept as backups. "
                  if command == "repair" else "Removing shared packages may stop other language pairs working. ")
        answer = QMessageBox.question(self, "Manage local translation models",
            "This affects every package in this pair's translation route, including shared English pivot models. "
            + action + "Backups are kept beside the Argos packages directory. Continue?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        if answer == QMessageBox.StandardButton.Yes:
            self._start_model_job(command)

    def _start_model_job(self, command: str, **extra) -> None:
        if not self.availability.maintenance_enabled:
            return
        self._installing = True
        self._refresh_availability()
        self._set_files_ready(False)
        self._model_task_error = None
        self._status_timer.stop()
        self._status_job.shutdown()
        self.source.setEnabled(False)
        self.target.setEnabled(False)
        self._refresh_listening()
        self.try_button.setEnabled(False)
        for button in (self.prepare_button, self.repair_button, self.remove_button):
            button.setEnabled(False)
        self.cancel_button.show()
        self.model_progress.show()
        self.model_details.show()
        self._model_stage_changed("Preparing download…")
        self._progress_timer.start()
        self.model_job.start(command, {"settings": asdict(self.current_settings()), **extra})

    def _model_event(self, message) -> None:
        if "progress" in message:
            self._model_stage_changed(message["progress"])
        if "download" in message:
            self._download_progress_changed(DownloadProgress(**message["download"]))

    def _model_stage_changed(self, message: str) -> None:
        self.model_status.setText(message)
        self._transfer_metrics.reset(monotonic())
        self._download_snapshot = None
        self.model_progress.setRange(0, 0)
        self._update_download_metrics()

    def _download_progress_changed(self, progress: DownloadProgress) -> None:
        if not self._installing:
            return
        self._transfer_metrics.update(progress.received, progress.total, progress.timestamp)
        self._download_snapshot = progress
        if progress.total:
            # Use a small fixed range to support archives larger than Qt's int range.
            self.model_progress.setRange(0, 1000)
            self.model_progress.setValue(min(1000, progress.received * 1000 // progress.total))
        else:
            self.model_progress.setRange(0, 0)
        self._update_download_metrics()

    def _update_download_metrics(self) -> None:
        if not self._installing:
            return
        self.model_details.setText(self._transfer_metrics.text(monotonic()))

    def _stop_model_progress(self) -> None:
        self._installing = False
        self._progress_timer.stop()
        self._download_snapshot = None
        self._transfer_metrics.reset(monotonic())
        self.model_progress.hide()
        self.model_details.hide()
        self.cancel_button.hide()
        self.try_button.setEnabled(False)  # wait for the fresh readiness check
        self.prepare_button.setEnabled(True)
        self._refresh_availability()

    def _install_finished(self) -> None:
        self._stop_model_progress()
        self.source.setEnabled(True)
        self.target.setEnabled(True)
        self.refresh_model_status()

    def _install_failed(self, message: str) -> None:
        self._stop_model_progress()
        self.source.setEnabled(True)
        self.target.setEnabled(True)
        self._model_task_error = (self.source.currentData(), self.target.currentData(), message)
        self.refresh_model_status()

    def set_listening(self, hotkey: str | None, *, suspended: bool = False) -> None:
        self._active_hotkey = hotkey
        self._listening_suspended = suspended
        self._refresh_listening()

    def _refresh_listening(self) -> None:
        active = self._active_hotkey
        listening = active is not None
        if listening:
            self._hotkey_value = normalize_hotkey(active)
            self.hotkey_valid = True
            blocked = self.hotkey.blockSignals(True)
            try:
                self.hotkey.setKeySequence(QKeySequence(display_hotkey(active)))
            finally:
                self.hotkey.blockSignals(blocked)
        self.hotkey.setEnabled(not listening)
        self.reset_hotkey.setEnabled(not listening)
        self.start_button.setText("Pause listening" if listening else "Start listening")
        # Stopping an existing listener must remain possible even when models
        # are missing, being checked or undergoing maintenance.
        self.start_button.setEnabled(listening or (
            self.availability.listening_enabled))
        set_help(self.start_button,
            "Unregister the global capture hotkey without closing Language Lens. 'Try a capture now' still works. "
            "The button becomes 'Start listening'; you can then change 'Capture hotkey' and resume listening. "
            "Pausing does not close an existing screenshot or stop model downloads. "
            "The global shortcut is temporarily suspended while 'Settings' or a screenshot is open, "
            "and while local files are being changed, so it cannot intercept Lens's own keyboard controls."
            if listening else
            "Register the selected 'Capture hotkey' and hide 'Settings' to the tray. Language Lens keeps "
            "running so the shortcut works from other applications. The button becomes 'Pause listening' "
            "while the shortcut is active. First use 'Download required files' or 'Check required files' "
            "to verify OCR and translation readiness. Reopen 'Settings' from the tray, or choose 'Quit' there to stop Lens completely."
        )

    def shutdown(self) -> None:
        self._shutting_down = True
        self._refresh_availability()
        self._status_timer.stop()
        self._status_job.shutdown()
        self.model_job.shutdown()
        self.pronunciation.shutdown()

    def set_capture_busy(self, busy: bool) -> None:
        self._capture_busy = busy
        self._refresh_availability()

    @property
    def availability(self) -> Availability:
        return Availability(self.capture_ready, self._capture_busy, self._installing,
                            self.pronunciation.download.active, self._shutting_down, self.hotkey_valid)

    def _refresh_availability(self) -> None:
        state = self.availability
        self.try_button.setEnabled(state.capture_enabled)
        managed = self._translation_ready and self.source.currentData() != self.target.currentData()
        self.prepare_button.setEnabled(state.maintenance_enabled)
        self.repair_button.setEnabled(state.maintenance_enabled and managed)
        self.remove_button.setEnabled(state.maintenance_enabled and managed)
        self.pronunciation.set_maintenance_blocked(state.capture_busy or state.model_busy or state.shutting_down)
        self._refresh_packs()
        self._refresh_listening()
        if state != self._last_availability:
            self._last_availability = state
            self.availability_changed.emit()

    def _toggle_listening(self) -> None:
        if self._active_hotkey is not None:
            self.pause_requested.emit()
        elif self.availability.listening_enabled:
            self.listen_requested.emit(self.current_settings())

    def _hotkey_edited(self, sequence: QKeySequence) -> None:
        if self._active_hotkey is not None:
            self._refresh_listening()
            return
        try:
            value = normalize_hotkey(sequence.toString(QKeySequence.SequenceFormat.PortableText))
        except ValueError as exc:
            self.hotkey_valid = False
            self.hotkey_note.setText(str(exc))
        else:
            self.hotkey_valid = True
            changed = value != self._hotkey_value
            self._hotkey_value = value
            self.hotkey_note.setText("Click the shortcut field and press your preferred key combination.")
            if changed:
                self.hotkey_changed.emit(value)
        self._refresh_listening()
        self._refresh_availability()

    @property
    def capture_ready(self) -> bool:
        return self._translation_ready and self._files_ready and not self._installing

    def _set_files_ready(self, ready: bool) -> None:
        changed = self._files_ready != ready
        self._files_ready = ready
        self._refresh_availability()
        if changed:
            self.readiness_changed.emit(self.capture_ready)

