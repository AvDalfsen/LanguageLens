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
import time


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


_CLEANUP_SCRIPT = r"""
$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
$job = [Text.Encoding]::UTF8.GetString([Convert]::FromBase64String('__PAYLOAD__')) | ConvertFrom-Json
if ($job.status) {
    [IO.File]::WriteAllText((Join-Path $job.status 'started'), 'ready')
}
while (Get-Process -Id $job.pid -ErrorAction SilentlyContinue) {
    Start-Sleep -Milliseconds 200
}
$failures = @()
foreach ($path in $job.paths) {
    for ($attempt = 0; $attempt -lt 20; $attempt++) {
        try {
            if (Test-Path -LiteralPath $path) {
                $attributes = [IO.File]::GetAttributes($path)
                if ($attributes -band [IO.FileAttributes]::ReparsePoint) {
                    Remove-Item -LiteralPath $path -Force
                } else {
                    Remove-Item -LiteralPath $path -Recurse -Force
                }
            }
            if (Test-Path -LiteralPath $path) {
                throw 'The path still exists after removal.'
            }
            break
        } catch {
            if ($attempt -eq 19) {
                $failures += @{path = $path; error = $_.Exception.Message}
            } else {
                Start-Sleep -Milliseconds 250
            }
        }
    }
}
if ($job.status) {
    $result = @{ok = ($failures.Count -eq 0); failures = @($failures)} | ConvertTo-Json -Depth 4
    [IO.File]::WriteAllText((Join-Path $job.status 'result.tmp'), $result)
    [IO.File]::Move((Join-Path $job.status 'result.tmp'), (Join-Path $job.status 'result.json'))
}
if ($failures.Count) {
    if ($job.show_errors) {
        Add-Type -AssemblyName System.Windows.Forms
        $message = "Some Language Lens files could not be removed. The diagnostic record lists the remaining folders and errors."
        $message += [Environment]::NewLine + [Environment]::NewLine + "Details: $($job.status)\result.json"
        [void][Windows.Forms.MessageBox]::Show($message, 'Uninstall Language Lens')
    }
    Write-Error ($failures | ConvertTo-Json -Depth 4)
    exit 1
}
exit 0
"""


def cleanup_command(paths: list[Path], pid: int, *, status_dir: Path | None = None,
                    show_errors: bool = False) -> tuple[Path, list[str]]:
    if not isinstance(pid, int) or pid <= 0:
        raise ValueError("The uninstaller process ID is invalid.")
    paths = [path.absolute() for path in paths]
    if any(path == Path(path.anchor) or path == Path.home().absolute() for path in paths):
        raise ValueError("The cleanup target is not safe to remove.")
    # Paths cross the process boundary only as base64-encoded JSON. PowerShell
    # parses no user-controlled path as source code.
    job = {"paths": [str(path) for path in paths], "pid": pid,
           "status": str(status_dir) if status_dir else None, "show_errors": show_errors}
    payload = base64.b64encode(json.dumps(job).encode("utf-8")).decode("ascii")
    script = _CLEANUP_SCRIPT.replace("__PAYLOAD__", payload)
    encoded = base64.b64encode(script.encode("utf-16le")).decode("ascii")
    powershell = Path(os.environ["SystemRoot"]) / "System32/WindowsPowerShell/v1.0/powershell.exe"
    return powershell, ["-NoLogo", "-NoProfile", "-NonInteractive", "-WindowStyle", "Hidden",
                        "-EncodedCommand", encoded]


def schedule_cleanup(paths: list[Path], pid: int | None = None, *,
                     show_errors: bool = False) -> Path:
    status = Path(tempfile.mkdtemp(prefix="LanguageLens-uninstall-"))
    powershell, arguments = cleanup_command(
        paths, os.getpid() if pid is None else pid, status_dir=status, show_errors=show_errors)
    if not powershell.is_file():
        raise OSError("Windows PowerShell is unavailable.")
    env = dict(os.environ)
    bundle = getattr(sys, "_MEIPASS", None)
    if bundle:
        bundle = Path(bundle).resolve()
        env["PATH"] = os.pathsep.join(
            entry for entry in env.get("PATH", "").split(os.pathsep)
            if entry and not Path(entry).resolve().is_relative_to(bundle))
    # Windows PowerShell silently exits without running the command when it is
    # launched with DETACHED_PROCESS. A hidden console process survives our exit.
    # Frozen DLL search paths must not leak into the system-installed helper.
    kernel = None
    previous_directory = None
    if sys.platform == "win32" and getattr(sys, "frozen", False):
        import ctypes
        kernel = ctypes.windll.kernel32
        size = kernel.GetDllDirectoryW(0, None)
        directory = ctypes.create_unicode_buffer(size + 1)
        kernel.GetDllDirectoryW(len(directory), directory)
        previous_directory = directory.value or None
        if not kernel.SetDllDirectoryW(None):
            raise ctypes.WinError()
    try:
        with (status / "helper.log").open("wb") as log:
            process = subprocess.Popen(
                [str(powershell), *arguments], cwd=tempfile.gettempdir(), env=env,
                stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT,
                creationflags=subprocess.CREATE_NO_WINDOW | subprocess.CREATE_NEW_PROCESS_GROUP,
                close_fds=True)
    finally:
        if kernel is not None:
            kernel.SetDllDirectoryW(previous_directory)
    deadline = time.monotonic() + 10
    while not (status / "started").is_file():
        if process.poll() is not None:
            raise OSError(f"The cleanup helper exited before starting. Details: {status / 'helper.log'}")
        if time.monotonic() >= deadline:
            process.terminate()
            process.wait(timeout=5)
            raise OSError(f"The cleanup helper did not start. Details: {status / 'helper.log'}")
        time.sleep(.05)
    return status


def verify_cleanup() -> None:
    """Exercise the actual hidden launcher against newly created disposable data."""
    with tempfile.TemporaryDirectory(prefix="LanguageLens-uninstall-test-") as temporary:
        root = Path(temporary)
        targets = [root / "portable", root / "LanguageLens", root / "argos-translate"]
        for target in targets:
            target.mkdir()
            (target / "fixture.dat").write_bytes(b"Uninstaller verification fixture")
        # This cannot be a live Windows process ID; don't wait for our own exit.
        status = schedule_cleanup(targets, pid=2147483647)
        result = status / "result.json"
        deadline = time.monotonic() + 15
        while not result.is_file() and time.monotonic() < deadline:
            time.sleep(.05)
        if not result.is_file() or not json.loads(result.read_text("utf-8"))["ok"]:
            raise OSError(f"Cleanup verification failed. Details: {status}")
        if any(target.exists() for target in targets):
            raise OSError("Cleanup verification left test files behind.")


def main() -> int:
    if sys.platform != "win32" or not getattr(sys, "frozen", False):
        return 2
    self_test = sys.argv[1:] == ["--self-test"]
    try:
        install_root = validate_install_root(Path(sys.executable))
        if self_test:
            verify_cleanup()
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
        schedule_cleanup(paths, show_errors=True)
        _message("Close this message to finish uninstalling Language Lens.\n\n"
                 "File removal starts after the uninstaller exits.")
        return 0
    except Exception as exc:
        if not self_test:
            _message(f"Language Lens could not start the uninstaller. The application files were not removed.\n\n{exc}",
                     MB_OK | MB_ICONWARNING)
        return 1
