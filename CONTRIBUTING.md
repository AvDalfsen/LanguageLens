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

## Interface translations

`src/language_lens/data/ui-translations.json` contains the bundled UI catalog. `english` defines messages, `sources` maps original text to message keys, and `languages` supplies every supported locale (the app uses `pb` for Brazilian Portuguese). Keep each locale complete and preserve named placeholders such as `{count}` and `{error}`. Each distinct English message must have its own key. Translate the complete meaning of tooltips, including conditions, keyboard limits, and recovery steps. Quoted control names must match their localized captions. Never map detailed help to a generic summary. The full English guides remain bundled.

Use natural UI wording and a consistent form of address within each locale. Review terms in their application context: local playback runs on the user's computer, voice previews are heard, and recognition means detecting text. Keep previously reviewed wording when updating other catalog entries. The UI language dropdown sorts its native labels with a fixed Unicode collation order, so changing the interface language does not rearrange it.

Native-speaker corrections are welcome. Run `tests/test_i18n.py` and relevant UI tests after edits; they check coverage, placeholders, saved preferences and live switching without changing the text-processing pair. Run `scripts/preview-ui.py` to inspect layout. Add new static captions to the catalog and use `tr()` for dynamic UI text; leave recognized text and model results untouched.

## Send a change

Explain the concrete behavior changed, why it helps, and relevant validation. Keep user instructions in task-based guides and technical evidence in developer references.

For bugs, include the version, Windows version, language pair, and reproduction steps. Sanitized logs help; temporary image jobs are not diagnostic attachments.

Language-testing contributions should identify the source/target pair, sample text, expected interpretation, and whether the issue comes from OCR, translation, segmentation, or pronunciation. Selectable language support does not imply equal quality.

## Licences

Application code is MIT licensed. Runtime libraries and downloaded models have separate terms. Read [speech and voice notices](THIRD_PARTY_SPEECH.md) and existing packaging documentation when changing distribution or voice catalogues.
