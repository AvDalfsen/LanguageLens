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
INVENTORY = Path("_internal/uninstall-files.json")
EXECUTABLES = ("LanguageLens.exe", "LanguageLensWorker.exe", "LanguageLensUninstall.exe")
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
    if not all((root / name).is_file() for name in EXECUTABLES) or not (root / "_internal").is_dir():
        raise ValueError("This folder is not a complete Language Lens portable release.")
    release_cleanup_plan(root)
    return root


def _release_entry(root: Path, value: str) -> Path:
    if (not isinstance(value, str) or not value or any(c in value for c in "\\:")
            or any(part in ("", ".", "..") or part.rstrip(" .") != part for part in value.split("/"))):
        raise ValueError("The release file inventory contains an unsafe path.")
    path = root.joinpath(*value.split("/"))
    if not path.is_relative_to(root):
        raise ValueError("The release file inventory contains an unsafe path.")
    checked = path
    while checked.is_relative_to(root):
        try:
            attributes = checked.lstat()
        except FileNotFoundError:
            attributes = None
        if attributes and (checked.is_symlink() or getattr(attributes, "st_file_attributes", 0) & stat.FILE_ATTRIBUTE_REPARSE_POINT):
            raise ValueError("Release cleanup paths must not be links or junctions.")
        if checked == root:
            break
        checked = checked.parent
    return path


def write_install_inventory(root: Path) -> None:
    """Called by packaging only, after collecting all shipped files."""
    root = root.resolve()
    files = {INVENTORY.as_posix()}
    for path in root.rglob("*"):
        relative = path.relative_to(root).as_posix()
        _release_entry(root, relative)
        if path.is_file():
            files.add(relative)
    (root / INVENTORY).write_text(json.dumps({"product": PRODUCT, "version": 1,
                                            "files": sorted(files)}, indent=2), encoding="utf-8")


def release_cleanup_plan(root: Path) -> dict:
    """Only inventoried files may be removed; directories are removed if empty."""
    root = root.absolute()
    if root == Path(root.anchor) or root == Path.home().absolute():
        raise ValueError("The application folder is not safe to remove.")
    _release_entry(root, INVENTORY.as_posix())
    try:
        if (root / INVENTORY).stat().st_size > 4 * 1024 * 1024:
            raise ValueError("Release file inventory is too large.")
        record = json.loads((root / INVENTORY).read_text(encoding="utf-8"))
    except (OSError, ValueError, UnicodeError) as exc:
        raise ValueError("The release file inventory is missing or invalid. Extract a fresh complete release.") from exc
    if not isinstance(record, dict) or record.get("product") != PRODUCT or record.get("version") != 1:
        raise ValueError("The release file inventory is invalid.")
    names = record.get("files")
    if not isinstance(names, list) or not names or len(names) > 50000:
        raise ValueError("The release file inventory is invalid.")
    files = [_release_entry(root, name) for name in names]
    if len({str(path).casefold() for path in files}) != len(files):
        raise ValueError("The release file inventory contains duplicate paths.")
    required = {*EXECUTABLES, MARKER.as_posix(), INVENTORY.as_posix()}
    if not required.issubset(names):
        raise ValueError("The release file inventory is incomplete.")
    directories = {root}
    for path in files:
        directories.update(parent for parent in path.parents if parent.is_relative_to(root))
    return {"root": str(root), "files": [str(path) for path in files],
            "directories": [str(path) for path in sorted(directories, key=lambda path: len(path.parts), reverse=True)]}


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
if ($job.manifest) {
    $job = [IO.File]::ReadAllText($job.manifest) | ConvertFrom-Json
}
if ($job.status) {
    [IO.File]::WriteAllText((Join-Path $job.status 'started'), 'ready')
}
while (Get-Process -Id $job.pid -ErrorAction SilentlyContinue) {
    Start-Sleep -Milliseconds 200
}
$failures = @()
function Assert-ReleasePath([string]$path) {
    $root = [IO.Path]::GetFullPath($job.release.root)
    $current = [IO.Path]::GetFullPath($path)
    if ($current -ne $root -and -not $current.StartsWith($root + [IO.Path]::DirectorySeparatorChar, [StringComparison]::OrdinalIgnoreCase)) {
        throw 'Release cleanup path is outside the application folder.'
    }
    while ($current) {
        if (Test-Path -LiteralPath $current) {
            if ([IO.File]::GetAttributes($current) -band [IO.FileAttributes]::ReparsePoint) {
                throw 'Release cleanup paths must not be links or junctions.'
            }
        }
        if ($current -eq $root) { break }
        $current = [IO.Path]::GetDirectoryName($current)
    }
}
if ($job.release) {
    foreach ($path in $job.release.files) {
        for ($attempt = 0; $attempt -lt 20; $attempt++) {
            try {
                Assert-ReleasePath $path
                if (Test-Path -LiteralPath $path) {
                    if ([IO.File]::GetAttributes($path) -band [IO.FileAttributes]::Directory) {
                        throw 'A shipped file has been replaced by a directory; it was preserved.'
                    }
                    [IO.File]::Delete($path)
                }
                break
            } catch {
                if ($attempt -eq 19) { $failures += @{path = $path; error = $_.Exception.Message} }
                else { Start-Sleep -Milliseconds 250 }
            }
        }
    }
    foreach ($path in $job.release.directories) {
        try {
            Assert-ReleasePath $path
            if ([IO.Directory]::Exists($path) -and -not (Get-ChildItem -LiteralPath $path -Force | Select-Object -First 1)) {
                # Never recurse here: files added after planning must survive too.
                [IO.Directory]::Delete($path, $false)
            }
        } catch {
            $failures += @{path = $path; error = $_.Exception.Message}
        }
    }
}
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
                    show_errors: bool = False, release_root: Path | None = None) -> tuple[Path, list[str]]:
    if not isinstance(pid, int) or pid <= 0:
        raise ValueError("The uninstaller process ID is invalid.")
    paths = [path.absolute() for path in paths]
    if any(path == Path(path.anchor) or path == Path.home().absolute() for path in paths):
        raise ValueError("The cleanup target is not safe to remove.")
    release = release_cleanup_plan(release_root) if release_root is not None else None
    if release and any(Path(release["root"]).is_relative_to(path) for path in paths):
        raise ValueError("Recursive data cleanup must not contain the application folder.")
    # Paths cross the process boundary only as base64-encoded JSON. PowerShell
    # parses no user-controlled path as source code.
    job = {"paths": [str(path) for path in paths], "pid": pid,
           "status": str(status_dir) if status_dir else None, "show_errors": show_errors, "release": release}
    # A full portable inventory exceeds Windows's process command-line limit.
    # Hand off JSON in our private diagnostics directory; paths remain data.
    if status_dir is not None:
        manifest = status_dir.absolute() / "cleanup.json"
        with manifest.open("x", encoding="utf-8") as handle:
            json.dump(job, handle)
        job = {"manifest": str(manifest)}
    payload = base64.b64encode(json.dumps(job).encode("utf-8")).decode("ascii")
    script = _CLEANUP_SCRIPT.replace("__PAYLOAD__", payload)
    encoded = base64.b64encode(script.encode("utf-16le")).decode("ascii")
    if len(encoded) > 30000:
        raise ValueError("A status directory is required for a large cleanup plan.")
    powershell = Path(os.environ["SystemRoot"]) / "System32/WindowsPowerShell/v1.0/powershell.exe"
    return powershell, ["-NoLogo", "-NoProfile", "-NonInteractive", "-WindowStyle", "Hidden",
                        "-EncodedCommand", encoded]


def schedule_cleanup(paths: list[Path], pid: int | None = None, *,
                     show_errors: bool = False, release_root: Path | None = None) -> Path:
    status = Path(tempfile.mkdtemp(prefix="LanguageLens-uninstall-"))
    powershell, arguments = cleanup_command(
        paths, os.getpid() if pid is None else pid, status_dir=status, show_errors=show_errors,
        release_root=release_root)
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
        portable = targets[0]
        (portable / MARKER).parent.mkdir()
        (portable / MARKER).write_text(json.dumps({"product": PRODUCT, "layout": 1}), encoding="utf-8")
        for name in EXECUTABLES:
            (portable / name).write_bytes(b"Uninstaller verification executable")
        write_install_inventory(portable)
        keep = portable / "unrelated-document.txt"
        keep.write_bytes(b"Preserve unrelated files")
        status = schedule_cleanup(targets[1:], pid=2147483647, release_root=portable)
        result = status / "result.json"
        deadline = time.monotonic() + 15
        while not result.is_file() and time.monotonic() < deadline:
            time.sleep(.05)
        if not result.is_file() or not json.loads(result.read_text("utf-8"))["ok"]:
            raise OSError(f"Cleanup verification failed. Details: {status}")
        if any(target.exists() for target in targets[1:]) or sorted(portable.iterdir()) != [keep]:
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
            "Remove Language Lens's shipped files, downloaded OCR and sentence models, "
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
        schedule_cleanup(paths, show_errors=True, release_root=install_root)
        _message("Close this message to finish uninstalling Language Lens.\n\n"
                 "File removal starts after the uninstaller exits. Unrelated files in the release folder are kept.")
        return 0
    except Exception as exc:
        if not self_test:
            _message(f"Language Lens could not start the uninstaller. The application files were not removed.\n\n{exc}",
                     MB_OK | MB_ICONWARNING)
        return 1
