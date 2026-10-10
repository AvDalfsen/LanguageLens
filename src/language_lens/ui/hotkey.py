"""Single-chord recorder with a non-destructive listening prompt."""
from PySide6.QtCore import QEvent
from PySide6.QtGui import QKeySequence
from PySide6.QtWidgets import QKeySequenceEdit, QLineEdit


class CaptureHotkeyEdit(QKeySequenceEdit):
    PROMPT = "Listening for new hotkey..."

    def __init__(self, sequence: QKeySequence, parent=None):
        super().__init__(sequence, parent)
        self._previous_sequence = QKeySequence(sequence)
        self._line_edit = self.findChild(QLineEdit)
        self._line_edit.installEventFilter(self)
        self.keySequenceChanged.connect(self._remember_sequence)
        self.editingFinished.connect(self._recording_finished)

    def _show_prompt(self) -> None:
        if self.isEnabled():
            sequence = self.keySequence()
            if not sequence.isEmpty():
                self._previous_sequence = QKeySequence(sequence)
            # Change display text only. The saved sequence remains intact until
            # Qt records an actual key; focusing must not clear user settings.
            from language_lens.i18n import tr
            self._line_edit.setText(tr(self.PROMPT))

    def _remember_sequence(self, sequence: QKeySequence) -> None:
        if not sequence.isEmpty():
            self._previous_sequence = QKeySequence(sequence)

    def _recording_finished(self) -> None:
        if self.hasFocus() and self.keySequence().isEmpty():
            self._show_prompt()

    def focusInEvent(self, event) -> None:  # noqa: N802
        super().focusInEvent(event)
        self._show_prompt()

    def focusOutEvent(self, event) -> None:  # noqa: N802
        # Pressing modifiers alone clears Qt's sequence but does not enter a
        # shortcut. Restore before Qt emits its editingFinished/change signals.
        if self.keySequence().isEmpty():
            self.setKeySequence(self._previous_sequence)
        super().focusOutEvent(event)
        # Qt deliberately skips finishing for popup focus changes, but the
        # display should still revert when the field loses focus to a menu.
        self._line_edit.setText(self.keySequence().toString(QKeySequence.SequenceFormat.NativeText))

    def eventFilter(self, watched, event) -> bool:  # noqa: N802
        if watched is getattr(self, "_line_edit", None) and event.type() == QEvent.Type.MouseButtonPress:
            self._show_prompt()  # also works on a second click while already focused
        return super().eventFilter(watched, event)
