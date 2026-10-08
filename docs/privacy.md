# Privacy and local files

[Documentation](README.md) · [Troubleshooting](troubleshooting.md)

## What stays on your computer

Screenshots, OCR, translations, pronunciation preparation, and speech run locally. Capture and speech do not send selected text or images to a translation/speech service.

The app requires explicit preparation/download actions for OCR/translation models, sentence files, optional language packs, and voices. Changing a language choice alone does not download files. Capture does not silently fetch assets.

During capture and speech, workers disable Python outbound socket connections and automatic Stanza downloads; Argos uses its local provider. This guards against implicit library requests. It is not an operating-system firewall or security sandbox.

## When a connection is used

Requested file preparation/download/repair operations contact model/package hosts. They verify local inference using fixed sample text rather than screenshots.

External documentation, bug-report, and **Voice details and licence** links open in your browser. Opening these pages does not attach your selected screenshot or recognized text; their hosts receive an ordinary browser request.

## Stored and temporary data

| Data | Location or lifetime |
| --- | --- |
| Settings | Per-user Language Lens data, outside the portable folder |
| Diagnostics | %LOCALAPPDATA%/LanguageLens/logs |
| Temporary OCR crops | %LOCALAPPDATA%/LanguageLens/jobs |
| Download cache | %LOCALAPPDATA%/LanguageLens/model-cache |
| Voices | %LOCALAPPDATA%/LanguageLens/voices |
| Optional language packs | %LOCALAPPDATA%/LanguageLens/language-packs |
| Translation models/backups | Argos's per-user packages directory; models can be shared with other Argos apps |
| Replay audio | In memory for the current review; cleared when it closes |

OCR workers briefly save selected/padded image regions to local jobs folders and remove them after completion/cancellation. A hard crash or power loss can leave those images behind. Interrupted voice or model downloads can also leave temporary job folders. Do not share these folders as diagnostics.

There is no permanent screenshot/audio history. Rotating logs record stages, exception types, and stack locations; they omit selected text, screenshot contents, and exception messages.

## Updates and removal

Extracting a new portable release leaves per-user preferences and downloads in place. Deleting the portable folder does not remove them.

To remove the app and Language Lens data, quit and run **LanguageLensUninstall.exe**. Shared Argos models have a separate confirmation because another app may use them. Recoverable model backups and caches are distinct; removing a translation route keeps backups and does not automatically reclaim their space.

Downloaded models and native packs execute local processing code. Use official releases and the app's pinned, verified downloads. See [pack management](language-packs.md) for integrity/version behavior and [third-party notices](../THIRD_PARTY_SPEECH.md) for runtime and voice provenance.
