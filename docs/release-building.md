# Windows portable release preview

The first release milestone provides `LanguageLens.exe` and a separate console
protocol helper, `LanguageLensWorker.exe`, sharing `_internal`. Users extract the
whole folder and open the main executable. `LanguageLensUninstall.exe` removes
the portable folder and downloaded data. Python and Git are not required on
their machine. The source batch launcher remains supported for development.

## Build

Run from the repository on Windows x64 with Python 3.10 installed:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/build-release.ps1
```

Or pass a specific interpreter with `-Python C:\path\to\python.exe`. The script
creates a fresh environment under `artifacts/releases/<run-id>/build-env`, installs
the runtime using `constraints/windows-python310.txt`, and pins the build tools
using `packaging/requirements-build.txt`. It does not install the application's
development extra. Building needs an internet connection or populated pip cache.
It records the Python patch version; this is a version-pinned build recipe, not a
claim of byte-for-byte reproducibility across machines.

Each run has its own directory; existing release folders are never deleted or
overwritten. Outputs include:

- `dist/LanguageLens/`: executable and complete supporting runtime.
- `LanguageLensUninstall.exe`: confirmed cleanup of the bundle and downloaded data.
- `LanguageLens-<version>-windows-x64-preview.zip` and `.sha256`.
- `verification.json`: checks run against the actual executables.
- `size-report.md` and `size-report.json`: installed size, ZIP size, components and
  full file inventory. Downloaded model/voice assets are reported separately.
- `build.log` and `work/LanguageLens/bundle-inputs.json`: build diagnostics.

The build and pip environments are **not** part of the ZIP. Developers can reuse
a prepared environment with `-Python <build-env>\Scripts\python.exe
-UseExistingEnvironment`; the freeze step rejects mismatched installed snapshot
versions. Reuse refreshes the application package and catalogs without reinstalling
third-party dependencies. The default remains a fresh environment.

## Packaging decisions

The PyInstaller spec creates a windowed GUI and a console helper. The helper
retains stdin/stdout for the existing JSON protocol, while QProcess launches it
without opening a console. Source mode still uses `python -m`. Worker crashes,
cancellation, timeouts and scratch cleanup retain their existing supervision.

The windowed uninstaller validates a fixed release marker and expected executable
layout, refuses to run while the app owns its instance lock, and schedules
deletion from Windows PowerShell after its own process exits. Paths cross that
process boundary as base64-encoded JSON rather than executable text. Application
data is removed by default. Shared Argos translation data has a separate warning
and choice because another Argos-based application may use it.

The spec collects only the imported Qt modules and required native dependencies.
It excludes development tooling, spaCy, Stanza and Torch. Lens uses a small
version-checked Argos adapter with local MiniSBD ONNX sentence models. See
[sentence splitting](sentence-splitting.md) for compatibility and quality checks.
Japanese/Chinese tokenizers and
Japanese pronunciation dictionaries are excluded and installed as
[optional language packs](language-packs.md). Shared Pydantic support stays in
the base runtime for the external native Japanese frontend.

RapidOCR's bundled ONNX defaults are omitted: Lens already prepares and verifies
its selected OCR models through Settings. Translation and voice model weights
also remain separate downloads. Required distribution metadata and shared speech
data are retained. Optional pack code, dictionaries and notices live in user data.

DLL discovery uses a restricted PATH. A build fails if collected native libraries
come from outside its Python environments and Windows, preventing unrelated
applications' ICU/Qt/OpenSSL DLLs from entering the release.

## Verification

The default build checks the base runtime with no optional packs, English
pronunciation, actual QProcess task/speech exchanges, GUI startup and second-launch
IPC. It uses isolated temporary app data, an unrelated working directory, and a
PATH without Python or repository entries. It does not capture the desktop or
download test assets. This is not a substitute for a clean Windows VM test.

Use existing development fixtures for real offline inference:

```powershell
.\.venv\Scripts\python.exe scripts/verify-release.py `
  --bundle artifacts/releases/<run-id>/dist/LanguageLens `
  --output artifacts/releases/<run-id>/verification-full.json `
  --fixtures artifacts/offline-validation `
  --voices artifacts/voice-validation `
  --language-packs artifacts/pack-validation/LanguageLens/language-packs `
  --sentence-models artifacts/sentence-validation/LanguageLens/offline/sentences `
  --sentence-cases tests/data/sentence-boundaries.json
```

The fixture root must contain the prepared Portuguese/English/Dutch Argos
packages and Latin OCR assets produced by `scripts/verify-offline.py`. It is
copied into the isolated test directory. Prepare all sentence-model fixtures
with `scripts/verify-sentences.py --download` as described in the sentence guide.
The
voice root must contain the pinned English US and Japanese catalogue voices;
these are read without modification. Create the language pack fixtures using
`scripts/prepare-release-pack-fixtures.py` as described in the language pack guide.
These checks refresh readiness through the maintenance worker, then run OCR,
direct and pivot translation, normal and expanded candidates, and English/Japanese
synthesis through the bundled processes. They also exercise all 38 sentence
fixtures with networking disabled. Fixed synthetic samples are used throughout.

## Remaining release work

The ZIP is an unsigned local preview. Before public distribution, test on clean
supported Windows systems, complete runtime/native dependency redistribution
review (including the GPL speech stack), and prepare the required source/notices.
The bundle includes notices available from installed distributions and Python.
Installer creation, executable signing and automated publishing are later work.

Optional Japanese/Chinese runtime packs now use pinned upstream artifacts,
transactional installation and capability-specific readiness checks. The
MiniSBD adapter replaces the Stanza/Torch sentence-processing path. Upstream
Argos still declares Stanza as a pip dependency, so source and build environments
remain larger than the shipped runtime. The source batch launcher is still a
developer installation; use the portable ZIP for the smaller end-user install.

## Original bundled-dictionary baseline on 2026-10-07

The Windows x64/Python 3.10.6 preview measured 1,309.1 MiB installed and 472.3 MiB
as a ZIP, compared with 2,282.7 MiB of installed runtime dependency files in the
clean build environment (about 43% less installed space). Qt's bundled portion
was 112.9 MiB, compared with 632.2 MiB in the development installation. Model and
voice downloads are additional. This is the baseline before optional packs.

The existing full source suite passed 710 tests; subsequent focused checks passed
84 tests including three additional bootstrap-dispatch regressions. The final
executables passed the isolated packaged checks and real offline inference using
existing Portuguese/English/Dutch model fixtures and English/Japanese voice
fixtures. GUI startup and second-launch IPC passed with Qt's offscreen platform.
No clean Windows VM, physical display/game capture or audio-device playback test
was performed for this preview.

The sandbox prevented the test harness from terminating its GUI process tree;
the successful final packaged verification ran outside that sandbox with isolated
fixture data. This limitation concerns the local test harness, not a requirement
for administrator access to run the portable application.

## Optional-pack validation on 2026-10-07

The updated preview is **863.4 MiB installed** and **336.6 MiB as a ZIP**, excluding
optional packs and model/voice downloads. Compared with the bundled-dictionary
baseline above, the installed folder is 34.0% smaller and the ZIP is 28.7% smaller.
The actual bundle inventory contains none of the five optional package directories.
Torch remains the largest core component at 365.1 MiB.

The full source suite passed 728 tests. After three additional pack regression
tests and final UI adjustments, the focused pack/speech/workflow suite passed
105 tests. Pack tests cover interrupted replacement, size/checksum failures,
same-size corruption, archive traversal and symlinks, selective readiness,
removal preserving unrelated assets, and Japanese notation without an audio model.

Official pinned packs were installed through the executable into isolated test
storage. The final packaged checks passed external Japanese/Chinese segmentation,
Japanese phonetic notation, English/Japanese synthesis, OCR, direct/pivot translation,
word candidates, GUI startup and second-launch IPC. The verifier then removed all
three copied packs through the worker protocol and successfully repeated core OCR,
translation and English speech with no packs installed. Original fixtures were kept.

Artifacts: `artifacts/releases/20261007-optional-packs-final/`, including
`verification-full.json`, `size-report.json`, `size-report.md`, the ZIP and its
SHA-256 file. The build reused the version-checked Python 3.10.6 build environment
after reinstalling the updated application metadata. Tests still do not replace
clean-machine Windows validation or physical screen/audio testing.

## MiniSBD validation on 2026-10-08

The step-5 preview is **453.1 MiB installed** and **195.7 MiB as a ZIP**
(475,144,613 and 205,225,187 bytes). Compared with step 4, the installed folder is
47.5% smaller and the ZIP is 41.9% smaller. Language models, voices and optional
packs remain additional downloads. The largest components are now Qt and OpenCV
at 112.9 and 111.8 MiB. Torch/Stanza/spaCy code is absent; dependency metadata and
notices for excluded upstream dependencies are still retained.

All **741 source tests passed**. The executable passed empty-install startup,
QProcess dispatch, GUI startup and second-launch IPC; 38 offline sentence cases
across 25 language choices; refreshed preparation, native OCR, direct/pivot
translation, normal/expanded word candidates; and English/Japanese synthesis.
All three copied optional packs were removed through the worker protocol, after
which the core checks passed again. A separate run omitted sentence fixtures
and successfully downloaded the required Portuguese/English models through the
executable's preparation worker before running offline inference. ZIP CRC checks
and the bundled catalog/module inventory passed.

The source comparison produced identical output in all 15 direct/pivot
translation cases. Three of 38 ideal sentence boundaries were merged by both
MiniSBD and default Stanza tokenizers; see [the corpus and limitations](sentence-splitting.md).
This does not establish translation equivalence across every language or input.

Artifacts: `artifacts/releases/20261008-minisbd-preview/`, including the ZIP,
`verification-base.json`, `verification-full.json`, `verification-downloads.json`,
size reports and checksum. ZIP SHA-256:
`352c37d7a34ed53867492ae4caa71f93e41893927bc16facb6ae0da8bcd1a294`.
The build reused the pinned Python 3.10.6 environment after refreshing the app.
Existing users must check required files once per language pair to migrate
readiness; settings, translation models and voices are preserved.

This is still an unsigned local preview. Clean Windows validation, physical
screen/audio testing, installer/signing and public distribution remain later
release work. A source clone/pip environment still pulls upstream heavy build
and development dependencies; use the portable ZIP for the measured small install.
