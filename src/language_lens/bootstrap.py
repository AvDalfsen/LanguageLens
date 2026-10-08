"""Dispatch before importing Qt: windowed app and console protocol helper share a bundle."""
import multiprocessing
import os
import sys


def main() -> int:
    multiprocessing.freeze_support()
    if sys.platform == "win32":
        import ctypes
        ctypes.windll.kernel32.SetErrorMode(3)
    if sys.executable.lower().endswith("languagelensuninstall.exe"):
        from language_lens.uninstall import main as uninstall
        return uninstall()
    if sys.argv[1:2] == ["--worker"]:
        kind = sys.argv[2:3]
        if kind == ["task"]:
            from language_lens.services.task_worker import main as run
        elif kind == ["speech"]:
            from language_lens.services.speech_worker import main as run
        else:
            return 2
        del sys.argv[1:3]
        return run()
    if sys.argv[1:2] == ["--self-test"]:
        del sys.argv[1]
        from language_lens.release_check import main as check
        return check()
    # A helper opened accidentally must not start a second GUI.
    if sys.executable.lower().endswith("languagelensworker.exe"):
        return 2
    from language_lens.services.startup import report_startup, record_startup_failure
    from language_lens.runtime import frozen, recovery_instruction
    try:
        from language_lens.app import main as run
        return run()
    except Exception as exc:
        record_startup_failure(exc)
        message = ("A local component failed during startup. Check the diagnostic files in "
                   "'%LOCALAPPDATA%/LanguageLens/logs'. " + recovery_instruction())
        report_startup("error", message)
        if frozen() and sys.platform == "win32" and not os.environ.get("LANGUAGE_LENS_STARTUP_FILE"):
            import ctypes
            ctypes.windll.user32.MessageBoxW(None, message, "Language Lens could not start", 0x10)
        return 1
