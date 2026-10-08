from pathlib import Path
import subprocess
import sys

import pytest


SCRIPT = Path(__file__).resolve().parents[1] / "scripts/set-release-version.py"


@pytest.fixture
def release_project(tmp_path):
    project = tmp_path / "pyproject.toml"
    project.write_bytes(
        b'[project]\r\nname = "language-lens"\r\nversion = "0.1.0"\r\n'
        b'\r\n[tool.example]\r\nversion = "9.8.7"\r\n')
    module = tmp_path / "src/language_lens/__init__.py"
    module.parent.mkdir(parents=True)
    module.write_bytes(b'"""Language Lens."""\r\n\r\n__version__ = "0.1.0"\r\n')
    return tmp_path, project, module


def run_version(project, *arguments):
    return subprocess.run(
        [sys.executable, str(SCRIPT), "--project", str(project), *arguments],
        cwd=project, capture_output=True, text=True, timeout=10)


@pytest.mark.parametrize("version", ["0.1.1", "0.1.1rc1"])
def test_requested_version_updates_both_declarations_and_preserves_other_settings(
        release_project, version):
    root, project, module = release_project
    result = run_version(root, "--version", version)
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == version
    assert project.read_bytes() == (
        f'[project]\r\nname = "language-lens"\r\nversion = "{version}"\r\n'
        '\r\n[tool.example]\r\nversion = "9.8.7"\r\n').encode()
    assert module.read_bytes() == (
        f'"""Language Lens."""\r\n\r\n__version__ = "{version}"\r\n').encode()


def test_push_build_uses_project_version_and_synchronizes_module(release_project):
    root, project, module = release_project
    project.write_bytes(project.read_bytes().replace(b'0.1.0', b'0.2.0'))
    original_project = project.read_bytes()
    result = run_version(root)
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "0.2.0"
    assert project.read_bytes() == original_project
    assert b'__version__ = "0.2.0"' in module.read_bytes()


@pytest.mark.parametrize("version", ["invalid", ""])
def test_invalid_input_fails_before_modifying_version_files(release_project, version):
    root, project, module = release_project
    original_project, original_module = project.read_bytes(), module.read_bytes()
    result = run_version(root, "--version", version)
    assert result.returncode != 0
    assert "Invalid version" in result.stderr
    assert project.read_bytes() == original_project
    assert module.read_bytes() == original_module


def test_missing_module_declaration_cannot_partially_stamp_project(release_project):
    root, project, module = release_project
    module.write_bytes(b'"""Language Lens."""\r\n')
    original_project, original_module = project.read_bytes(), module.read_bytes()
    result = run_version(root, "--version", "0.1.1")
    assert result.returncode != 0
    assert "Expected one __version__ declaration" in result.stderr
    assert project.read_bytes() == original_project
    assert module.read_bytes() == original_module
