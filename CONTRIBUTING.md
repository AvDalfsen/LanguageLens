# Contributing to Language Lens

Documentation, reproducible bug reports, language testing, and code improvements are welcome.

[User documentation](docs/README.md) · [Report a problem](https://github.com/AvDalfsen/LanguageLens/issues/new/choose)

## Source setup

Use **Python 3.10–3.12 on Windows x64**. Clone/download this repository, open its folder, and double-click **Start Language Lens.bat**. The launcher checks the environment, sets up/repairs it when needed, and starts the app.

To run the scripts directly from PowerShell in the checkout:

    .\scripts\setup.ps1
    .\scripts\run.ps1

The app's **Download required files** button manages OCR/translation readiness; voices are separate downloads. Source dependencies are larger than the portable runtime because upstream Argos declares dependencies omitted from the shipped bundle.

See [release building](docs/release-building.md) for the pinned Windows Python 3.10 snapshot and packaging decisions.

## Tests and previews

Install developer and optional language dependencies for the complete suite:

    .\.venv\Scripts\python.exe -m pip install -e ".[dev,language-packs]"
    .\.venv\Scripts\python.exe -m pytest

The normal launcher installs the core, not all optional test dependencies. Fixture-dependent speech tests skip absent assets instead of downloading them.

For synthetic layout checks:

    .\.venv\Scripts\python.exe scripts/preview-ui.py

For the README's illustrated workflow and product icon:

    .\.venv\Scripts\python.exe scripts/render-presentation.py

Both render offscreen examples without capturing the desktop. Presentation images use supplied example translations, not live model output. Review generated assets visually after UI changes.

Use opt-in verification scripts for real local inference and existing development fixtures. [Release verification](docs/release-building.md), [sentence splitting](docs/sentence-splitting.md), and [historical validation](docs/archive/README.md) record results and their limits. Do not use selected private text/images as committed fixtures.

## Send a change

Explain the concrete behavior changed, why it helps, and relevant validation. Keep user instructions in task-based guides and technical evidence in developer references.

For bugs, include the version, Windows version, language pair, and reproduction steps. Sanitized logs help; temporary image jobs are not diagnostic attachments.

Language-testing contributions should identify the source/target pair, sample text, expected interpretation, and whether the issue comes from OCR, translation, segmentation, or pronunciation. Selectable language support does not imply equal quality.

## Licences

Application code is MIT licensed. Runtime libraries and downloaded models have separate terms. Read [speech and voice notices](THIRD_PARTY_SPEECH.md) and existing packaging documentation when changing distribution or voice catalogues.
