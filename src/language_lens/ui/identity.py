"""Shared identity for the application and portable release."""
from pathlib import Path

from PySide6.QtGui import QIcon


def app_icon() -> QIcon:
    return QIcon(str(Path(__file__).resolve().parents[1] / "assets" / "language-lens.ico"))
