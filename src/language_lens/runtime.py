"""Entry points and recovery advice shared by source and portable installations."""
from pathlib import Path
import sys


WORKERS = {
    "language_lens.services.task_worker": "task",
    "language_lens.services.speech_worker": "speech",
}


def frozen() -> bool:
    return bool(getattr(sys, "frozen", False))


def worker_command(module: str) -> tuple[str, list[str]]:
    # Only our protocol workers may be dispatched through the release helper.
    kind = WORKERS[module]
    executable = Path(sys.executable)
    if frozen():
        return str(executable.with_name("LanguageLensWorker.exe")), ["--worker", kind]
    if executable.name.lower() == "pythonw.exe":
        executable = executable.with_name("python.exe")
    return str(executable), ["-m", module]


def recovery_instruction() -> str:
    if frozen():
        return "Close Language Lens and extract a fresh copy of the complete release folder, then reopen LanguageLens.exe."
    return "Restart using 'Start Language Lens.bat' to check or repair the installation."
