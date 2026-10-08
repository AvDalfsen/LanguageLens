from pathlib import Path
import sys

import pytest

from language_lens import runtime


def test_source_worker_uses_console_python(monkeypatch):
    monkeypatch.setattr(sys, "frozen", False, raising=False)
    monkeypatch.setattr(sys, "executable", str(Path("C:/Lens folder/pythonw.exe")))
    program, args = runtime.worker_command("language_lens.services.task_worker")
    assert Path(program).name == "python.exe"
    assert args == ["-m", "language_lens.services.task_worker"]


@pytest.mark.parametrize("module,kind", runtime.WORKERS.items())
def test_frozen_worker_uses_adjacent_helper(monkeypatch, module, kind):
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    executable = Path("C:/Lens folder/LanguageLens.exe")
    monkeypatch.setattr(sys, "executable", str(executable))
    program, args = runtime.worker_command(module)
    assert Path(program) == executable.with_name("LanguageLensWorker.exe")
    assert args == ["--worker", kind]


def test_worker_dispatch_rejects_unknown_module():
    with pytest.raises(KeyError):
        runtime.worker_command("untrusted.module")


def test_release_recovery_does_not_require_source_checkout(monkeypatch):
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    assert "release folder" in runtime.recovery_instruction()
    assert ".bat" not in runtime.recovery_instruction()


@pytest.mark.parametrize("kind,module", [(kind, module) for module, kind in runtime.WORKERS.items()])
def test_bootstrap_dispatches_before_gui_and_preserves_worker_arguments(monkeypatch, kind, module):
    from types import SimpleNamespace
    from language_lens import bootstrap
    seen = []
    monkeypatch.setitem(sys.modules, module, SimpleNamespace(main=lambda: seen.append(sys.argv[:]) or 7))
    monkeypatch.setattr(sys, "argv", ["LanguageLensWorker.exe", "--worker", kind, "status", "--scratch", "folder with spaces"])
    monkeypatch.setattr(bootstrap.multiprocessing, "freeze_support", lambda: None)
    assert bootstrap.main() == 7
    assert seen == [["LanguageLensWorker.exe", "status", "--scratch", "folder with spaces"]]


def test_bootstrap_rejects_unknown_worker_before_importing_gui(monkeypatch):
    from language_lens import bootstrap
    monkeypatch.setattr(sys, "argv", ["LanguageLensWorker.exe", "--worker", "unknown"])
    monkeypatch.setattr(bootstrap.multiprocessing, "freeze_support", lambda: None)
    assert bootstrap.main() == 2
