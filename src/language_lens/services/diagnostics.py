"""Bounded diagnostics: stages, exception types and stack locations, never text."""
import faulthandler
import logging
from logging.handlers import RotatingFileHandler
import sys
import traceback
import re

from language_lens.config import settings_path

LOGGER = logging.getLogger("language_lens")
_crash_handle = None


def open_folder() -> bool:
    from PySide6.QtCore import QUrl
    from PySide6.QtGui import QDesktopServices
    try:
        directory = settings_path().parent / "logs"
        directory.mkdir(parents=True, exist_ok=True)
        return QDesktopServices.openUrl(QUrl.fromLocalFile(str(directory)))
    except OSError:
        return False


def record_failure(stage: str, exception: BaseException) -> None:
    seen = set()
    while exception is not None and id(exception) not in seen:
        seen.add(id(exception))
        LOGGER.error("%s: %s", stage, type(exception).__name__)
        for frame in traceback.extract_tb(exception.__traceback__):
            LOGGER.error("  %s:%s in %s", frame.filename, frame.lineno, frame.name)
        exception = exception.__cause__ or exception.__context__
        stage = "caused by"


def initialize(channel: str = "app") -> None:
    global _crash_handle
    if LOGGER.handlers:
        return
    if not re.fullmatch(r"[a-z-]{1,32}", channel):
        raise ValueError("Invalid diagnostic channel.")
    try:
        directory = settings_path().parent / "logs"
        directory.mkdir(parents=True, exist_ok=True)
        # Separate command channels avoid competing GUI/worker rename handles
        # during Windows log rotation. Names are from fixed worker commands.
        handler = RotatingFileHandler(directory / f"{channel}.log", maxBytes=512 * 1024,
                                      backupCount=2, encoding="utf-8")
        handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
        LOGGER.addHandler(handler)
        LOGGER.setLevel(logging.INFO)
        crash = directory / ("crash.log" if channel == "app" else f"{channel}-crash.log")
        if crash.exists() and crash.stat().st_size > 1024 * 1024:
            crash.replace(crash.with_suffix(".previous.log"))
        _crash_handle = crash.open("ab")
        faulthandler.enable(file=_crash_handle)
    except OSError:
        LOGGER.addHandler(logging.NullHandler())
    sys.excepthook = lambda _type, exception, _tb: record_failure("unhandled callback", exception)
    LOGGER.info("Application starting (captured text and images are never logged).")
