# UI translation audit — 9 October 2026

The existing localization was independently reviewed against the English UI and exercised in Qt. The review found both misleading translations and functional gaps; those have been corrected. The existing English catalog entries and source mappings are unchanged.

## Scope and results

All 25 UI choices have complete catalogs of 331 messages: Arabic, Chinese, Czech, Danish, Dutch, English, Finnish, French, German, Greek, Hindi, Hungarian, Italian, Japanese, Korean, Norwegian Bokmål, Polish, Portuguese (Portugal), Portuguese (Brazil), Romanian, Russian, Spanish, Swedish, Turkish and Ukrainian.

The audit updated 791 existing non-English entries, including wording, terminology and Unicode normalization, and added 45 messages to every catalog. These counts compare against the saved localization before this audit, rather than against Git HEAD, which also includes the preceding localization work.

The wording review covered action labels, status messages, counts, detailed control tooltips and pronunciation explanations. Corrections preserve the action, relevant conditions and limits, and references to the actual translated control captions. Count messages use noun-label constructions where that avoids incorrect singular/plural forms at zero, one and multiple results.

## Meaning and wording corrected

| Issue | Result |
| --- | --- |
| “Stop word” read as a linguistic stopword | Labels now describe stopping playback. |
| “Accent” became a diacritic, stress or emphasis | Voice-selection explanations now refer to a speaking accent. |
| Keyboard shortcuts became desktop shortcuts | Hotkey instructions use keyboard terminology. |
| Translation “candidates” became people, and “returned” became came back | Messages now describe translation suggestions being found. |
| “Help and about” became help and around/about something | Window titles use the same natural wording as the help button. |
| A voice model's “speaker” became a loudspeaker | The licence tooltip describes the person behind the voice. |
| Speech “runtime” became speaking duration | Sample tooltips explain the installed speech components. |
| Pronunciation “off” became incorrect pronunciation | Status messages now describe a disabled feature. |
| Word-isolation ranking sounded like a word being pronounced alone | Labels and tooltips describe translation-model ranking independently of sentence context. |
| Japanese close action implied returning to Esc | Closing/returning and the Esc shortcut are distinct. |
| Detailed recognition and IPA help sounded literal or changed technical meaning | Rewritten explanations distinguish local OCR, estimated notation, engine output and contextual limitations. |

## Functional corrections and verification

- Fixed menus/help created in an already selected non-English language: they now retain their English sources when switching again. A new regression reproduced the original failure in all 24 translated locales.
- Localized known worker progress, audio states, hotkey validation, tray status, model-management confirmations and pack/download information. Unknown technical exception details, filenames and language codes remain intact.
- Preserved original template arguments across language switches, including after the rendering cache has evicted a dynamic status. Active downloads regenerate their stage from the original worker message.
- Added localized standard message-box OK buttons and Qt's built-in editing/copy menus while preserving shortcut notation such as Ctrl+C and F8.
- Verified catalog completeness, placeholder equality, quoted control references, language preference persistence, live switching, Arabic right-to-left layout and unchanged text/voice preferences and service jobs.

The full test suite passed **959 tests**. After the final wording edits, the localization suites passed **195 tests** again. `git diff --check` passed.

The preview script rendered **100 views** using synthetic content and no downloads: settings at two window sizes for every locale, 25 help dialogs and 25 review overlays with word details. The button-width check reported no clipped visible settings buttons. The full contact sheet and representative German, Japanese, Arabic and Hindi views were visually inspected. These offscreen checks are not a manual test of every physical display/DPI configuration.

## Content boundaries and confidence

The bundled help article bodies remain English, as documented by the existing localization design; their navigation and controls are localized. External voice model/licence pages and unrecognized technical diagnostics may also remain English. Captured text and translation-model results are content, so changing the UI language does not rewrite them.

This is an independent model-assisted linguistic review and automated/visual UI verification. It is **not native-speaker sign-off** for all translated locales. Native reviewers can still refine regional usage and specialized phonetic terminology.

## Reproduce

Run from the repository root with the project environment:

```powershell
.venv\Scripts\python.exe -m pytest -q --tb=short
.venv\Scripts\python.exe -m pytest tests/test_i18n.py tests/test_i18n_audit.py -q --tb=short
.venv\Scripts\python.exe scripts/preview-translations.py
```

Generated screenshots and the contact sheet are in the ignored `artifacts/localization-audit/previews/` directory. The preview script explicitly loads installed Windows fonts for the offscreen renderer.
