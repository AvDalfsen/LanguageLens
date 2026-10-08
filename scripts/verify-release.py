"""Run the actual executables with isolated data and no source/Python search paths."""
import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import time
import uuid


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--bundle", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--fixtures", type=Path, help="Existing offline-validation fixture root to copy; no downloads.")
    parser.add_argument("--voices", type=Path, help="Existing voice-validation root, read-only.")
    parser.add_argument("--language-packs", type=Path, help="Existing managed packs to copy into isolated storage.")
    parser.add_argument("--sentence-models", type=Path, help="Verified sentence models to copy into isolated storage.")
    parser.add_argument("--sentence-cases", type=Path, help="Fixed sentence cases to check offline in the bundle.")
    args = parser.parse_args()
    bundle = args.bundle.resolve()
    args.output = args.output.resolve()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    result = {"bundle": str(bundle), "ok": False}
    with tempfile.TemporaryDirectory(prefix="release-check-", dir=args.output.parent,
                                     ignore_cleanup_errors=True) as temporary:
        root = Path(temporary)
        (root / "tmp").mkdir()
        if args.language_packs:
            shutil.copytree(args.language_packs, root / "LanguageLens/language-packs")
        if args.fixtures:
            for name in ("data", "config", "cache", "LanguageLens/offline"):
                source = args.fixtures / name
                if source.exists():
                    shutil.copytree(source, root / name)
        if args.sentence_models:
            shutil.copytree(args.sentence_models, root / "LanguageLens/offline/sentences", dirs_exist_ok=True)
        env = {key: value for key, value in os.environ.items()
               if not key.startswith(("PYTHON", "QT_", "ARGOS_", "LANGUAGE_LENS_"))}
        env.update(LOCALAPPDATA=str(root), XDG_DATA_HOME=str(root / "data"),
                   XDG_CONFIG_HOME=str(root / "config"), XDG_CACHE_HOME=str(root / "cache"),
                   ARGOS_PACKAGES_DIR=str(root / "data/argos-translate/packages"),
                   QT_QPA_PLATFORM="offscreen", PATH=str(Path(os.environ["SystemRoot"]) / "System32"),
                   TEMP=str(root / "tmp"), TMP=str(root / "tmp"))
        command = [str(bundle / "LanguageLensWorker.exe"), "--self-test"]
        if args.language_packs:
            command.append("--with-packs")
        if args.fixtures:
            command.append("--with-models")
        if args.voices:
            command.extend(["--voices", str(args.voices.resolve())])
        if args.sentence_cases:
            command.extend(["--sentence-cases", str(args.sentence_cases.resolve())])
        try:
            probe = subprocess.run(command, cwd=root, env=env, capture_output=True, timeout=900,
                                   creationflags=subprocess.CREATE_NO_WINDOW)
            result["worker_exit_code"] = probe.returncode
            result["stdout"] = probe.stdout.decode("utf-8", errors="replace")
            result["stderr"] = probe.stderr.decode("utf-8", errors="replace")
            if probe.returncode:
                raise RuntimeError("Bundled runtime/worker check failed")
            events = [json.loads(line) for line in result["stdout"].splitlines() if line.startswith("{")]
            if not events or not events[-1].get("ok"):
                raise RuntimeError("Worker did not acknowledge successful checks")
            result["checks"] = events[-1]
            uninstaller = subprocess.run([str(bundle / "LanguageLensUninstall.exe"), "--self-test"],
                                         cwd=root, env=env, capture_output=True, timeout=45,
                                         creationflags=subprocess.CREATE_NO_WINDOW)
            result["uninstaller_exit_code"] = uninstaller.returncode
            if uninstaller.returncode:
                raise RuntimeError("Bundled uninstaller cleanup check failed")
            result["uninstaller"] = True
            result["uninstaller_cleanup"] = True
            if args.language_packs:
                # Delete only this verifier's private copies through the real
                # maintenance protocol; prove that the core still operates.
                scratch = root / "pack-removal-job"
                scratch.mkdir()
                from language_lens.config import Settings
                from dataclasses import asdict
                for pack in ("ja-text", "zh-text", "ja-speech"):
                    request = json.dumps({"settings": asdict(Settings()), "pack": pack}).encode()
                    removed = subprocess.run([str(bundle / "LanguageLensWorker.exe"), "--worker", "task",
                                              "pack-remove", "--scratch", str(scratch)],
                                             input=request, cwd=root, env=env, capture_output=True, timeout=120,
                                             creationflags=subprocess.CREATE_NO_WINDOW)
                    if removed.returncode or (root / "LanguageLens/language-packs" / f"{pack}.json").exists():
                        raise RuntimeError(f"Isolated pack removal failed: {pack}")
                core_command = [part for part in command if part != "--with-packs"]
                core = subprocess.run(core_command, cwd=root, env=env, capture_output=True, timeout=900,
                                      creationflags=subprocess.CREATE_NO_WINDOW)
                result["after_removal"] = {"exit_code": core.returncode,
                                           "stdout": core.stdout.decode("utf-8", errors="replace"),
                                           "stderr": core.stderr.decode("utf-8", errors="replace")}
                if core.returncode:
                    raise RuntimeError("Core inference failed after removing optional packs")
            # Exercise the windowed entry point and normal application startup.
            app_data = root / "LanguageLens"
            app_data.mkdir(exist_ok=True)
            startup = app_data / f"startup-{uuid.uuid4().hex}.json"
            env["LANGUAGE_LENS_STARTUP_FILE"] = str(startup)
            process = subprocess.Popen([str(bundle / "LanguageLens.exe")], cwd=root, env=env,
                                       creationflags=subprocess.CREATE_NO_WINDOW)
            result["gui_test_pid"] = process.pid
            try:
                deadline = time.monotonic() + 45
                while not startup.exists() and process.poll() is None and time.monotonic() < deadline:
                    time.sleep(.1)
                if not startup.exists():
                    raise RuntimeError(f"GUI did not acknowledge startup (exit {process.poll()})")
                result["gui"] = json.loads(startup.read_text(encoding="utf-8"))
                if result["gui"]["status"] != "ready":
                    raise RuntimeError("GUI reported startup failure")
                # Second launch must notify the existing app and exit successfully.
                second = subprocess.run([str(bundle / "LanguageLens.exe")], cwd=root, env=env,
                                        timeout=45, creationflags=subprocess.CREATE_NO_WINDOW)
                if second.returncode != 0:
                    raise RuntimeError("Second launch failed")
                result["single_instance"] = True
            finally:
                if process.poll() is None:
                    # The GUI can still own a status worker. Stop only this
                    # isolated test's process tree before removing its fixtures.
                    stopped = subprocess.run(
                        [str(Path(os.environ["SystemRoot"]) / "System32/taskkill.exe"),
                         "/PID", str(process.pid), "/T", "/F"],
                        capture_output=True, creationflags=subprocess.CREATE_NO_WINDOW, timeout=30)
                    if stopped.returncode and process.poll() is None:
                        raise RuntimeError("Could not stop the isolated GUI test process tree")
                process.wait(timeout=30)
            result["ok"] = True
        except Exception as exc:
            result["error"] = str(exc)
            result["test_directory"] = str(root)
        finally:
            # Only fixed test samples are processed; preserve diagnostics on failure.
            if not result["ok"]:
                logs = root / "LanguageLens/logs"
                result["diagnostics"] = {p.name: p.read_text(encoding="utf-8", errors="replace")
                                         for p in logs.glob("*.log")} if logs.exists() else {}
            args.output.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps({"ok": result["ok"], "report": str(args.output)}))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
