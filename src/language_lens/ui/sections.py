
from language_lens.i18n import tr
"""Small keyboard-operable disclosures and read-only text inspection helpers."""
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QApplication, QLabel, QMenu, QToolButton, QVBoxLayout, QWidget


class ExpandableSection(QWidget):
    expanded = Signal(bool)

    def __init__(self, title: str, parent=None) -> None:
        super().__init__(parent)
        self.toggle = QToolButton()
        self.toggle.setText(title)
        self.toggle.setAccessibleName(title)
        self.toggle.setCheckable(True)
        self.toggle.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.toggle.setArrowType(Qt.ArrowType.RightArrow)
        self.content = QWidget()
        self.content.setAccessibleName(title)
        self.content.hide()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.toggle)
        layout.addWidget(self.content)
        self.toggle.toggled.connect(self._toggle)

    def _toggle(self, expanded: bool) -> None:
        self.content.setVisible(expanded)
        self.toggle.setArrowType(Qt.ArrowType.DownArrow if expanded else Qt.ArrowType.RightArrow)
        self.expanded.emit(expanded)


def copy_menu(label: QLabel, text) -> QMenu:
    menu = QMenu(label)
    selection = menu.addAction(tr("Copy selection"))
    selection.setEnabled(bool(label.selectedText()))
    selection.triggered.connect(lambda: QApplication.clipboard().setText(label.selectedText()))
    whole = menu.addAction(tr("Copy all"))
    whole.setEnabled(bool(text()))
    whole.triggered.connect(lambda: QApplication.clipboard().setText(text()))
    return menu


def make_copyable(label: QLabel, name: str, text) -> None:
    label.setAccessibleName(name)
    label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse |
                                  Qt.TextInteractionFlag.TextSelectableByKeyboard)
    label.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
    label.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
    label.setAccessibleDescription(tr("Read-only text. Select and copy with the keyboard or use the context menu to copy all."))

    def show_menu(point):
        menu = copy_menu(label, text)
        menu.exec(label.mapToGlobal(point))
        menu.deleteLater()

    label.customContextMenuRequested.connect(show_menu)
