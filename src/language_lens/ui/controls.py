"""Controls that do not mistake page scrolling for a preference edit."""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QComboBox


class ChoiceBox(QComboBox):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

    def wheelEvent(self, event):  # noqa: N802
        # The open list handles wheel navigation. A closed field passes wheel
        # input to its scroll-area parent, including when the field has focus.
        event.ignore()
