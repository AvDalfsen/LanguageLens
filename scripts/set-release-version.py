"""Stamp the application version in a release checkout before package installation."""
import argparse
from pathlib import Path
import re

from packaging.version import Version


def version_field(text: str, name: str):
    pattern = rf"""(?m)^{re.escape(name)}[ \t]*=[ \t]*(?P<quote>["'])(?P<version>[^"'\r\n]+)(?P=quote)"""
    matches = list(re.finditer(pattern, text))
    if len(matches) != 1:
        raise ValueError(f"Expected one {name} declaration.")
    return matches[0]


def stamp_version(project: Path, requested: str | None = None) -> str:
    project_file = project / "pyproject.toml"
    module_file = project / "src/language_lens/__init__.py"
    project_text = project_file.read_bytes().decode("utf-8")
    module_text = module_file.read_bytes().decode("utf-8")
    section = re.search(r"(?ms)^\[project\][ \t]*\r?\n(?P<body>.*?)(?=^\[|\Z)", project_text)
    if section is None:
        raise ValueError("pyproject.toml has no [project] section.")
    declaration = version_field(section["body"], "version")
    version = str(Version((requested if requested is not None else declaration["version"]).strip()))
    module_declaration = version_field(module_text, "__version__")

    # Validate both declarations before changing either file, and preserve newlines.
    start = section.start("body") + declaration.start("version")
    end = section.start("body") + declaration.end("version")
    updated_project = project_text[:start] + version + project_text[end:]
    start, end = module_declaration.span("version")
    updated_module = module_text[:start] + version + module_text[end:]
    if updated_project != project_text:
        project_file.write_bytes(updated_project.encode("utf-8"))
    if updated_module != module_text:
        module_file.write_bytes(updated_module.encode("utf-8"))
    return version


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--version", help="Requested release version; defaults to [project].version.")
    args = parser.parse_args()
    try:
        version = stamp_version(args.project, args.version)
    except (OSError, ValueError) as error:
        parser.error(str(error))
    print(version)


if __name__ == "__main__":
    main()
