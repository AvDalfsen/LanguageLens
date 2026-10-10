
from language_lens.i18n import tr, ui_text, ui_widget
"""Small keyboard-operable disclosures and read-only text inspection helpers."""
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QApplication, QLabel, QMenu, QToolButton, QVBoxLayout, QWidget


class ExpandableSection(QWidget):
    expanded = Signal(bool)

    def __init__(self, title: str, parent=None) -> None:
        super().__init__(parent)
        self.toggle = QToolButton()
        ui_text(self.toggle, title)
        ui_text(self.toggle, title, property="accessibleName")
        self.toggle.setCheckable(True)
        self.toggle.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.toggle.setArrowType(Qt.ArrowType.RightArrow)
        self.content = QWidget()
        ui_text(self.content, title, property="accessibleName")
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
    selection = ui_widget(menu.addAction, tr("Copy selection"))
    selection.setEnabled(bool(label.selectedText()))
    selection.triggered.connect(lambda: ui_text(QApplication.clipboard(), label.selectedText()))
    whole = ui_widget(menu.addAction, tr("Copy all"))
    whole.setEnabled(bool(text()))
    whole.triggered.connect(lambda: ui_text(QApplication.clipboard(), text()))
    return menu


def make_copyable(label: QLabel, name: str, text) -> None:
    label._lens_untranslated_text = True
    ui_text(label, name, property="accessibleName")
    label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse |
                                  Qt.TextInteractionFlag.TextSelectableByKeyboard)
    label.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
    label.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
    ui_text(label, tr("Read-only text. Select and copy with the keyboard or use the context menu to copy all."), property="accessibleDescription")

    def show_menu(point):
        menu = copy_menu(label, text)
        menu.exec(label.mapToGlobal(point))
        menu.deleteLater()

    label.customContextMenuRequested.connect(show_menu)
