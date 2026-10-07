"""Standard-library startup reporting, usable before Qt or native imports load."""
import json
import os
from pathlib import Path
import re
import traceback


def startup_root() -> Path:
    return Path(os.environ.get("LOCALAPPDATA", Path.home())) / "LanguageLens"


def report_startup(status: str, message: str = "") -> None:
    name = os.environ.get("LANGUAGE_LENS_STARTUP_FILE", "")
    if not name:
        return
    path = Path(name)
    if path.parent.resolve() != startup_root().resolve() or not re.fullmatch(r"startup-[a-f0-9]{32}\.json", path.name):
        return
    try:
        temporary = path.with_suffix(".tmp")
        temporary.write_text(json.dumps({"status": status, "message": message}), encoding="utf-8")
        temporary.replace(path)
    except OSError:
        pass


def record_startup_failure(exception: BaseException) -> None:
    try:
        root = startup_root() / "logs"
        root.mkdir(parents=True, exist_ok=True)
        lines = [f"Startup failure: {type(exception).__name__}"]
        lines.extend(f"{frame.filename}:{frame.lineno} in {frame.name}"
                     for frame in traceback.extract_tb(exception.__traceback__))
        (root / "startup.log").write_text("\n".join(lines), encoding="utf-8")
    except OSError:
        pass
