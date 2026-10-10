# Audit repairs — 10 October 2026

This follows the [full audit](full-audit-2026-10-10.md) of revision `2c4912d5df096f609df232d082b5acb28e7bd3fe`. Changes are local and have not been committed or published.

## Changes and remaining scope

| Finding | Repair | Limits |
| --- | --- | --- |
| F1: stale offline readiness | Readiness version 3 records the selected ordered route, package metadata catalog, package roots, Argos configuration, and relevant environment. The GUI checks this without importing native translation engines; the status worker also checks its actual route. Preparation rejects catalog changes during warmup. | Any catalog change conservatively requires rechecking, including unrelated additions. Existing version 2 markers require one **Check required files** operation; intact assets are reused. |
| F2: retained task objects | A `settled` signal runs after terminal callbacks and cleanup. The one-shot task dispatcher releases signal ownership and callbacks; Review keeps only active jobs and explicit translation/search references. | Setup and speech jobs remain reusable. Large UI constructors and the broader task protocol are unchanged. |
| F3: false success for empty output | Cross-language translations returning empty or whitespace-only output raise a recoverable failure. Same-language passthrough and valid unchanged names still work. | Unchanged output can be valid, so equality with the source is not treated as failure. |
| F4: untranslated recovery states | Known failure codes, supervisor failures, runtime recovery instructions, missing-voice advice, long-passage warnings, and wider-search recovery now use translated UI messages. | Unknown diagnostics are preserved. New wording needs fluent-speaker review. |
| F5: repeated CJK manifest scans | Each segmentation operation validates/activates its managed pack once. The next operation rechecks; Latin-only input does not activate a pack. | This remains an integrity check at operation boundaries, rather than a permanent cache. |
| F6: missing diagnostics | Partial sentence/word/hypothesis failures and image/scratch failures log exception types and stack locations. Recoverable results keep streaming; Review exposes diagnostics when lookups or the sentence fail. | Captured text, exception messages, and images are not logged. |
| F7: insufficient meaning checks | Added 12 curated sentence cases for four routes, accepted paraphrase constraints, an offline verifier, and an optional fresh-process integration test. Word labels now say “Top suggestion · isolated word” and “model order”. | The backend still translates words independently. Only 6/12 sample word lists contain the selected contextual sense. Corpus constraints are an initial regression gate, not a complete semantic assessment. |
| F8: technical translation errors | Corrected selected Arabic syllable-onset/pronunciation wording, Portuguese accent terminology and isolated-word warnings, and French/Japanese isolated-pronunciation explanations. Added recovery wording for all 25 locales. | Full native-speaker review of all locales remains pending. |
| F9: ambiguous reverse translation | `tr()` carries message identity to bound widget properties, actions, and combo items. Caption updates use `ui_text`, `ui_widget`, and `ui_item`. Opaque OCR/model content is protected during live switching. | Reverse lookup remains a compatibility fallback for raw/unbound Qt strings; preserve provenance for new controls. |
| F10: missing PR/runtime CI | Added a read-only pull-request/main/manual Windows test workflow for Python 3.10, 3.11, and 3.12, including separate prototype tests. Source setup pins pip and applies the tested constraints on Python 3.10. | This host validates Python 3.10 only. The new remote matrix has not run. Python 3.11/3.12 dependencies still resolve from declared ranges. |

Removed the misleading `QThreadPool` alias, unused imports, and redundant supervisor error definitions. Updated rendering/integration scripts for the new dispatcher and job lifecycle. Documented the pronunciation prototype as an intentionally frozen independent baseline; its duplicated helpers were not merged into application code.

## Verification

| Check | Result |
| --- | --- |
| Full application suite | 1,040 passed in 171.19 seconds; no skips on this host (81 additional cases since the audit) |
| Independent pronunciation prototype | 32 passed in 6.43 seconds |
| Dependency compatibility | `pip check`: no broken requirements |
| Offline inference | Fresh-process OCR, sentence translation, word lookups, and wider search passed for pt→en, nl→en, and pt→nl. Preparation verifies inference with networking disabled. |
| Real Qt integration | OCR→translation, retry of the same screenshot, and wider search passed with real model workers. |
| Resource ownership | New tests exercise actual QProcess success, failure, cancellation, scratch errors, retries, and image staging; they check deleted signals/jobs, released task references, and removed scratch directories. |
| Meaning corpus | 12/12 sentence constraints passed across nl→en, pt→en, en→nl, and pt→nl; 6/12 contextual word-sense observations matched. No fixture downloads in the semantic verifier. |
| UI catalog/layout | 361 messages across 25 locales; rendered 100 views with no clipped buttons detected. Inspected the Arabic review overlay. Catalog, placeholders, control references, recovery states, live switching, and French Cancel/Undo collision tests pass. |
| Setup/CI structure | PowerShell setup parser passed; YAML parsed with PR/main/manual events and all three runtime entries. Installer and remote CI were not executed. |
| Patch whitespace | `git diff --check`: clean |

Managed-pack warm measurements on this host:

| Sample | Before | After | Manifest checks |
| --- | ---: | ---: | ---: |
| Japanese, 100 runs / 200 tokens | 2,549.944 ms | 34.855 ms | 100→1 |
| Chinese, 100 runs / 300 tokens | 2,112.062 ms | 23.824 ms | 100→1 |

These are single-host warm samples (approximately 73× and 89× faster), not a live-game end-to-end benchmark. Before/after results and semantic output are retained under ignored `artifacts/audit-2026-10-10/`. UI previews are under ignored `artifacts/localization-audit/previews/`.

## Remaining work that needs broader evidence

- Fluent-speaker review of UI wording and translation/pronunciation quality across supported languages and routes.
- Context-sensitive word translation or disambiguation, with a larger independently reviewed corpus. New labels describe the current backend honestly.
- MiniSBD's known Arabic, Chinese, and Japanese boundary misses. The model baselines preserve these limitations; punctuation-only repairs would need broader abbreviation/quote/offset validation.
- Python 3.11/3.12 matrix results, clean-machine Windows 11/portable-release validation, and live-game/multi-monitor/DPI checks.
- Larger architectural refactors: splitting Settings/Review responsibilities, typed task payloads, and reorganizing historical test modules. These were left for focused changes with their own behavior checks.
