"""Native, dependency-light cleanup for the portable Windows release."""
from __future__ import annotations

import base64
import json
import os
from pathlib import Path
import stat
import subprocess
import sys
import tempfile


PRODUCT = "Language Lens"
MARKER = Path("_internal/portable-release.json")
MB_OK = 0x0
MB_OKCANCEL = 0x1
MB_YESNO = 0x4
MB_ICONWARNING = 0x30
IDOK = 1
IDYES = 6


def _message(text: str, flags: int = MB_OK) -> int:
    import ctypes
    return ctypes.windll.user32.MessageBoxW(None, text, f"Uninstall {PRODUCT}", flags)


def app_data_roots(environ=None) -> list[Path]:
    env = os.environ if environ is None else environ
    local = Path(env.get("LOCALAPPDATA", Path.home()))
    return [local / "LanguageLens", local / "GameLanguageLens"]


def shared_argos_roots(environ=None, home: Path | None = None) -> list[Path]:
    env = os.environ if environ is None else environ
    home = home or Path.home()
    data = Path(env.get("XDG_DATA_HOME", home / ".local" / "share"))
    cache = Path(env.get("XDG_CACHE_HOME", home / ".local" / "cache"))
    config = Path(env.get("XDG_CONFIG_HOME", home / ".config"))
    return [data / "argos-translate", cache / "argos-translate", config / "argos-translate"]


def validate_install_root(executable: Path) -> Path:
    root = executable.absolute().parent
    attributes = root.lstat()
    is_reparse = bool(getattr(attributes, "st_file_attributes", 0) & stat.FILE_ATTRIBUTE_REPARSE_POINT)
    if root == Path(root.anchor) or root == Path.home().absolute() or root.is_symlink() or is_reparse:
        raise ValueError("The application folder is not safe to remove.")
    try:
        marker = json.loads((root / MARKER).read_text(encoding="utf-8"))
    except (OSError, ValueError, UnicodeError) as exc:
        raise ValueError("This folder is not a complete Language Lens portable release.") from exc
    if marker != {"product": PRODUCT, "layout": 1}:
        raise ValueError("The Language Lens release marker is invalid.")
    required = ("LanguageLens.exe", "LanguageLensWorker.exe", "LanguageLensUninstall.exe", "_internal")
    if not all((root / name).exists() for name in required):
        raise ValueError("This folder is not a complete Language Lens portable release.")
    return root


def application_running(_root: Path) -> bool:
    from filelock import FileLock, Timeout
    lock_root = app_data_roots()[0]
    lock_root.mkdir(parents=True, exist_ok=True)
    lock = FileLock(str(lock_root / "instance.lock"))
    try:
        lock.acquire(timeout=0)
    except Timeout:
        return True
    else:
        lock.release()
        return False


def cleanup_command(paths: list[Path], pid: int) -> tuple[Path, list[str]]:
    # Paths cross the process boundary only as base64-encoded JSON. PowerShell
    # parses no user-controlled path as source code.
    payload = base64.b64encode(json.dumps([str(path) for path in paths]).encode("utf-8")).decode("ascii")
    script = (
        "$ErrorActionPreference='SilentlyContinue';"
        f"while(Get-Process -Id {pid} -ErrorAction SilentlyContinue){{Start-Sleep -Milliseconds 200}};"
        f"$p=[Text.Encoding]::UTF8.GetString([Convert]::FromBase64String('{payload}'))|ConvertFrom-Json;"
        "foreach($x in $p){if(Test-Path -LiteralPath $x){"
        "$a=[IO.File]::GetAttributes($x);if($a-band[IO.FileAttributes]::ReparsePoint){"
        "Remove-Item -LiteralPath $x -Force}else{Remove-Item -LiteralPath $x -Recurse -Force}}}"
    )
    encoded = base64.b64encode(script.encode("utf-16le")).decode("ascii")
    powershell = Path(os.environ["SystemRoot"]) / "System32/WindowsPowerShell/v1.0/powershell.exe"
    return powershell, ["-NoLogo", "-NoProfile", "-NonInteractive", "-WindowStyle", "Hidden",
                        "-EncodedCommand", encoded]


def schedule_cleanup(paths: list[Path], pid: int | None = None) -> None:
    powershell, arguments = cleanup_command(paths, pid or os.getpid())
    if not powershell.is_file():
        raise OSError("Windows PowerShell is unavailable.")
    subprocess.Popen([str(powershell), *arguments], cwd=tempfile.gettempdir(),
                     stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                     creationflags=subprocess.CREATE_NO_WINDOW | subprocess.DETACHED_PROCESS
                     | subprocess.CREATE_NEW_PROCESS_GROUP, close_fds=True)


def main() -> int:
    if sys.platform != "win32" or not getattr(sys, "frozen", False):
        return 2
    try:
        install_root = validate_install_root(Path(sys.executable))
        if sys.argv[1:] == ["--self-test"]:
            powershell, arguments = cleanup_command([install_root], os.getpid())
            if not powershell.is_file() or "-EncodedCommand" not in arguments:
                return 1
            return 0
        if application_running(install_root):
            _message("Close Language Lens from its tray icon before uninstalling it.", MB_OK | MB_ICONWARNING)
            return 1
        answer = _message(
            "Remove Language Lens, its application folder, downloaded OCR and sentence models, "
            "voices, language packs, caches, logs and settings?\n\nThis cannot be undone.",
            MB_OKCANCEL | MB_ICONWARNING,
        )
        if answer != IDOK:
            return 0
        paths = [*app_data_roots()]
        if any(path.exists() for path in shared_argos_roots()):
            answer = _message(
                "Also remove the shared Argos translation models and configuration?\n\n"
                "Other Argos-based applications may use these files. Choose No to keep them.",
                MB_YESNO | MB_ICONWARNING,
            )
            if answer == IDYES:
                paths.extend(shared_argos_roots())
        paths.append(install_root)
        schedule_cleanup(paths)
        _message("Language Lens will now remove its files. This window may close before deletion finishes.")
        return 0
    except Exception:
        _message("Language Lens could not start the uninstaller. The application files were not removed.",
                 MB_OK | MB_ICONWARNING)
        return 1
