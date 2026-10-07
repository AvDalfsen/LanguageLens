import sys
from language_lens.services.startup import report_startup, record_startup_failure

try:
    if sys.platform == "win32":
        import ctypes
        ctypes.windll.kernel32.SetErrorMode(3)
    from language_lens.app import main
    code = main()
except Exception as exc:
    record_startup_failure(exc)
    report_startup("error", "A local component failed during startup. Check the diagnostic files in "
                   "'%LOCALAPPDATA%/LanguageLens/logs', then run 'Start Language Lens.bat' again.")
    code = 1
raise SystemExit(code)

