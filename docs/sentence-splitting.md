# ONNX sentence splitting

Language Lens uses MiniSBD 0.9.5 for sentence boundaries and CTranslate2 for
translation. The portable runtime excludes PyTorch, Stanza and spaCy. Both the
source application and executable use the same sentence adapter; the upstream
Argos pip dependency declaration still installs Stanza/PyTorch in development
and build environments. This change reduces the distributed executable folder,
not the size of a normal source installation.

## Models and updates

`src/language_lens/data/sentence-models.json` pins official MiniSBD release asset
URLs, byte sizes and published SHA-256 digests. All 25 text-language choices map
to explicit models (24 files; European/Brazilian Portuguese share one). Chinese
uses `zh-hans`. There is no silent English fallback for unsupported languages.
The complete catalogue is about 5.5 MB; normal use downloads only the source
languages on the selected route. Portuguese to Dutch through English needs the
Portuguese and English sentence models, not the Dutch model.

Settings' required-files action downloads and verifies models under
`%LOCALAPPDATA%\LanguageLens\offline\sentences`. Installs use a lock, temporary
file, exact byte count, checksum and atomic replacement. Inference accepts only
a verified local model path, disables network access and rejects outputs that
lose or change non-whitespace characters. It cannot trigger MiniSBD's implicit
downloader. Translation model weights and decoding settings are unchanged.

An upgrade from the Stanza runtime invalidates old readiness markers. Use
**Check required files** (or **Download required files**, when offered) once for
each pair. Existing OCR/translation models and voices are reused. Old Stanza
assets inside Argos packages are preserved but no longer loaded or required by
readiness checks; user files are not automatically pruned.

Catalog updates are deliberate, like optional language-pack updates. Run
`scripts/update-sentence-catalog.py` to regenerate the catalog from official
release metadata, then review and validate the changes. Model filenames include
a digest, so a replacement does not overwrite another version. Readiness records
track models used by that route; changing an unrelated model does not invalidate
it. The adapter explicitly requires Argos 1.11.0 and MiniSBD 0.9.5. Updating those
pins requires reviewing Argos's SBD interface and repeating these checks.

## Validation on 2026-10-08

The fixed corpus in `tests/data/sentence-boundaries.json` has 38 cases across all
25 text-language choices: ordinary game-like sentences, abbreviations, decimals,
a URL/version number, quotes and punctuation without spaces. All cases preserved
non-whitespace text. Thirty-five matched the hand-written ideal boundaries.
Three merged two sentences: one Arabic, one Chinese and one Japanese sample.
Stanza 1.10.1's default tokenizer models made exactly the same three merges.
The corpus retains both ideal boundaries and observed upstream baselines rather
than introducing punctuation rules tailored to these examples.

Fifteen real translations using the existing English/Dutch/Portuguese Argos
packages were identical before and after the change: English to Dutch, Dutch to
English, Portuguese to English and Portuguese to Dutch through English. The old
comparison uses each package's original Stanza tokenizer in a separate process.
The Arabic/Chinese/Japanese comparison uses separately downloaded default Stanza
tokenizers, not Argos translation packages for those languages.

These are reproducible regression samples, not a broad human evaluation of
translation quality. Full translation comparisons for the other languages,
long documents and more punctuation/abbreviation cases remain useful follow-up
coverage. The three known boundary merges remain model limitations.

The final portable build measured 453.1 MiB extracted and 195.7 MiB zipped.
All 741 source tests passed. Bundled checks covered the same 38 sentence samples,
first-time sentence downloads, readiness migration, real offline OCR/translation,
English/Japanese synthesis, startup and optional-pack removal. The full record
and remaining platform-test limits are in [release building](release-building.md).

## Repeat the comparison

With a development environment and existing Portuguese/English/Dutch packages:

```powershell
.\.venv\Scripts\python.exe scripts/verify-sentences.py `
  --output artifacts/sentence-validation `
  --fixtures artifacts/offline-validation --download
.\.venv\Scripts\python.exe scripts/compare-sentence-baselines.py `
  --output artifacts/sentence-validation --download
```

The first command explicitly prepares all 24 small models, then compares
boundaries and translation offline in isolated app storage. Omit `--download`
to require existing fixtures. It writes `minisbd.json`, `legacy.json` and
`comparison.json`. Unexpected boundary changes or different translations fail
the check. The second command prepares the three default Stanza tokenizers and
writes `stanza-comparison.json`. These larger legacy fixtures are development
assets only. Neither command changes users' installed models.

Run `scripts/verify-release.py` with the sentence fixtures and case file to check
the same inputs in the actual executable; see the release-building guide. The
base check also asserts that Torch/Stanza/spaCy modules are unavailable.

## Upstream provenance

[MiniSBD](https://github.com/LibreTranslate/MiniSBD) supplies quantized ONNX
versions of Stanza tokenizers. Its code is AGPL-3.0; this change does not alter
upstream licensing. The catalog records assets from its
[v0.0.1 model release](https://github.com/LibreTranslate/MiniSBD/releases/tag/v0.0.1).
The release retains installed dependency notices; public redistribution/source
preparation remains part of the release checklist.
