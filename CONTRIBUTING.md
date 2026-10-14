# Contributing to Language Lens

Documentation, reproducible bug reports, language testing, and code improvements are welcome.

[User documentation](docs/README.md) · [Report a problem](https://github.com/AvDalfsen/LanguageLens/issues/new/choose)

## Source setup

Use **Python 3.10–3.12 on Windows x64**. Clone/download this repository, open its folder, and double-click **Start Language Lens.bat**. The launcher checks the environment, sets up/repairs it when needed, and starts the app.

To run the scripts directly from PowerShell in the checkout:

    .\scripts\setup.ps1
    .\scripts\run.ps1

The app's **Download required files** button manages OCR/translation readiness; voices are separate downloads. Source dependencies are larger than the portable runtime because upstream Argos declares dependencies omitted from the shipped bundle.

The source launcher and portable releases omit word-model weights. **Download required files** fetches the pinned, already-converted CTranslate2 int8 model only when the selected pair needs it. Models are shared across supported pairs and existing verified downloads are reused. Normal startup and app builds do not download publisher weights or run conversion. Model-release maintainers use the separate workflow described in [release building](docs/release-building.md); conversion tools never run in capture workers. See [translation integration](docs/translation-production-integration.md) and [third-party notices](THIRD_PARTY_TRANSLATION.md).

Source setup uses the pinned Windows Python 3.10 constraints on that runtime; Python 3.11/3.12 use the declared dependency ranges. Pull requests run tests on all three versions. See [release building](docs/release-building.md) for the snapshot and packaging decisions.

## Tests and previews

Install developer and optional language dependencies for the complete suite:

    .\.venv\Scripts\python.exe -m pip install -e ".[dev,language-packs]"
    .\.venv\Scripts\python.exe -m pytest

The normal launcher installs the core, not all optional test dependencies. Fixture-dependent speech and translation tests skip absent assets instead of downloading them. CI reports those skips; synthetic tests do not establish model quality.

For synthetic layout checks:

    .\.venv\Scripts\python.exe scripts/preview-ui.py

For the README's illustrated workflow and product icon:

    .\.venv\Scripts\python.exe scripts/render-presentation.py

Both render offscreen examples without capturing the desktop. Presentation images use supplied example translations, not live model output. Review generated assets visually after UI changes.

For offline translation meaning checks against existing fixtures:

    .\.venv\Scripts\python.exe scripts/verify-translations.py --models <argos-packages-directory> --sentences <minisbd-model-directory> --output artifacts/translation-quality.json

The curated corpus accepts selected paraphrases and reports isolated-word sense mismatches separately. It covers four routes and is an initial regression sample, not a fluent-speaker assessment. Set `LANGUAGE_LENS_TEST_TRANSLATIONS` and `LANGUAGE_LENS_TEST_SENTENCES` to include those fixtures in pytest.

Use opt-in verification scripts for real local inference and existing development fixtures. [Release verification](docs/release-building.md), [sentence splitting](docs/sentence-splitting.md), and [historical validation](docs/archive/README.md) record results and their limits. Do not use selected private text/images as committed fixtures.

[OCR model selection](docs/ocr-model-selection.md) records the per-language
recognizer comparison and reproducible commands. `scripts/verify-ocr-models.py`
compares identical line crops, including a public challenge corpus with small
print, blur, compression and mixed text. `scripts/report-ocr-models.py` balances
rendering scenarios and excludes the original reported heading from ranking.

[Upright screen OCR adoption](docs/ocr-upright-selection.md) records the current
accuracy-first production policy and its real-screen evidence. With the retained
benchmark corpus, `scripts/audit-ocr-upright.py` checks every adopted policy
through production inference without downloads or changes to user assets.

[OCR settings selection](docs/ocr-settings-selection.md) records fixed-model
pipeline tuning against disjoint development and validation passages, multiple
layouts, negative controls and additional colored text. Run
`scripts/verify-ocr-settings.py`, `scripts/finalize-ocr-settings.py` and
`scripts/report-ocr-settings.py` to reproduce the comparison; use
`scripts/audit-ocr-settings.py` to check the real adapter and word geometry.
`scripts/audit-ocr-workers.py` verifies the offline subprocess protocol with
workspace-local assets and public text.

[Joint OCR validation](docs/ocr-joint-selection.md) follows those phases by
comparing every compatible recognizer with baseline and tuned settings, tuning
strong challengers, and freezing the proposal before fresh passages. Run
`scripts/verify-ocr-joint.py`, `scripts/verify-ocr-joint-english.py` (the expanded
English catalogue comparison) and `scripts/report-ocr-joint.py`; use
`scripts/audit-ocr-joint.py` for uncached adapter and worker verification.
[Candidate tables](docs/ocr-joint-candidates.md) expose each model's scores.

## Interface translations

`src/language_lens/data/ui-translations.json` contains the bundled UI catalog. `english` defines messages, `sources` maps original text to message keys, and `languages` supplies every supported locale (the app uses `pb` for Brazilian Portuguese). Keep each locale complete and preserve named placeholders such as `{count}` and `{error}`. Each distinct English message must have its own key. Translate the complete meaning of tooltips, including conditions, keyboard limits, and recovery steps. Quoted control names must match their localized captions. Never map detailed help to a generic summary. The full English guides remain bundled.

Use natural UI wording and a consistent form of address within each locale. Review terms in their application context: local playback runs on the user's computer, voice previews are heard, and recognition means detecting text. Keep previously reviewed wording when updating other catalog entries. The UI language dropdown sorts its native labels with a fixed Unicode collation order, so changing the interface language does not rearrange it.

Native-speaker corrections are welcome. Run `tests/test_i18n.py` and relevant UI tests after edits; they check coverage, placeholders, saved preferences and live switching without changing the text-processing pair. Run `scripts/preview-ui.py` to inspect layout. Add new static captions to the catalog and use `tr()` for dynamic UI text. Bind text through `ui_text()`, constructors/actions through `ui_widget()`, and combo captions through `ui_item()` so language changes retain the original message identity. Mark content labels with `_lens_untranslated_text` (or use `make_copyable()`) and leave recognized text and model results untouched.

## Send a change

Explain the concrete behavior changed, why it helps, and relevant validation. Keep user instructions in task-based guides and technical evidence in developer references.

For bugs, include the version, Windows version, language pair, and reproduction steps. Sanitized logs help; temporary image jobs are not diagnostic attachments.

Language-testing contributions should identify the source/target pair, sample text, expected interpretation, and whether the issue comes from OCR, translation, segmentation, or pronunciation. Selectable language support does not imply equal quality.

## Licences

Application code is MIT licensed. Runtime libraries and downloaded models have separate terms. Read [speech and voice notices](THIRD_PARTY_SPEECH.md) and existing packaging documentation when changing distribution or voice catalogues.
