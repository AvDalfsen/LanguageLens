Language Lens - Windows x64 portable preview

Extract the complete LanguageLens folder, then open LanguageLens.exe.
Keep LanguageLensWorker.exe and _internal beside it. No Python installation,
Git checkout, administrator access or batch launcher is required.

Choose your text/translation languages in Settings and select Download required
files. OCR and translation models need a one-time download for the selected
languages. Voices are separate optional downloads. Capture and speech then work
offline. Japanese and Chinese word lookup dictionaries download with required
files only when those text languages are selected. Japanese pronunciation is an
additional optional pack, downloaded with its voice or separately for phonetic
notation with audio turned off. Settings > Manage local files lets you check or
remove each pack. Sizes are shown before downloading.

Packs live in %LOCALAPPDATA%\LanguageLens\language-packs and are shared across
language pairs. Versions and checksums are pinned to the app's catalog. An app
update can require an updated pack; interrupted downloads retain the previous
installation. Pack removal keeps translation models and audio voice files.

Settings, downloaded models and voices are stored outside this folder. Existing
Language Lens installations use the same per-user data. Close the app before
updating; extract a new complete release folder and launch it. Do not mix files
from different releases. Removing this folder does not remove downloaded assets.
When upgrading from a Stanza-based release, use Check required files (or Download
required files if offered) once for each language pair. This prepares small ONNX
sentence models and rechecks existing translation/OCR files. Existing translation
models, voices and settings are retained.

If the runtime is incomplete, extract a fresh copy of the complete ZIP.
Diagnostic files: %LOCALAPPDATA%\LanguageLens\logs

To remove Language Lens, close it from the tray icon and open
LanguageLensUninstall.exe. It removes this complete portable folder and Language
Lens settings, logs, caches, OCR/sentence models, voices and optional packs. A
second confirmation controls removal of the shared Argos translation directory;
choose No if another Argos-based application uses those models. Cancellation
does not remove anything. The uninstaller validates the release folder before
scheduling deletion and does not need administrator access.

This is an unsigned local preview, not a published installer. See LICENSE,
THIRD_PARTY_SPEECH.md and notices for dependency provenance and notices.
