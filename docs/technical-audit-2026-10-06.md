# LanguageLens technical audit — 6 October 2026

This records the working tree **before repairs**. The ten findings have since been addressed; see [technical repairs and validation](technical-repairs-2026-10-06.md). The original measurements and line references below describe the audited snapshot.

The highest priority is model replacement correctness. The current installer accepts unusable model archives, and versioned replacements can leave the previous model selected. The largest demonstrated performance costs are cumulative translation-result snapshots and synchronous image compression on the interface thread.

This audit covers the current working tree, including its existing uncommitted and untracked changes. Application code and existing tests were left unchanged. The findings below distinguish reproduced defects, measured costs, and maintainability opportunities.

## Scope and validation

Reviewed the application/controller, configuration, OCR and geometry, translation, model preparation/download/replacement, supervised processes, speech/pronunciation, UI lifecycle, launch/setup scripts, and test architecture. Inspected the installed Argos implementation where the application's assumptions depended on it.

| Check | Result |
| --- | --- |
| Application Python inventory | 37 files; 7,036 lines |
| Main test inventory | 23 files; 5,388 lines |
| Pronunciation prototype inventory | 7 Python files; 874 lines |
| Main suite: `.venv/Scripts/python.exe -m pytest -q` | **655 passed, 22 skipped**, 129.04 seconds |
| Installed dependency compatibility: `pip check` | No broken requirements found |
| Existing tracked diff: `git diff --check` | Passed; ordinary CRLF conversion notices |
| Model-publication and route-selection probes | Reproduced findings 1 and 2 using temporary package roots |
| Readiness-version probe | Reproduced finding 5 using a synthetic marker |
| Translation protocol scaling | Counted actual helper output and serialized worker-shaped messages |
| Image staging | Timed Qt PNG encoding of synthetic images; no desktop capture |

The audit probe is saved at [language_lens_audit_probe.py](<C:/Users/Fillask/.codex/visualizations/2026/10/06/01a1126c-2d2b-78d0-acaf-6edf5341f54e/language_lens_audit_probe.py>). Run it with the project's Python environment. It uses temporary model/configuration roots and blocks networking during Argos route inspection. Its models are deliberately synthetic; it tests publication and selection, without claiming to validate actual translation quality.

P1 means high priority because an operation can replace a working installation with an unusable one. P2 covers functional gaps and demonstrated performance problems. P3 covers cleanup and optimization opportunities.

## Findings

### 1. P1 — Replacement preflight does not validate a usable model

**Location:** [model_management.py:87](<C:/Users/Fillask/Desktop/GitHub repos/LanguageLens/src/language_lens/services/model_management.py:87>), especially the `package.Package(...)` call at line 90.

`install_archive()` requires a `model/` directory and `metadata.json`, constructs an Argos `Package`, then publishes the directory. The installed Argos constructor reads metadata and creates a tokenizer wrapper only if a tokenizer file exists. It does not require a tokenizer or load model weights; SentencePiece loading is also lazy. Consequently this is insufficient preflight for a replacement.

**Reproduction:** a ZIP containing metadata and an empty `model/` directory was accepted. The previous active directory was moved to backup, and the active replacement contained no model files and no tokenizer. A backup remained, but the working model was no longer active. `repair` ends after publication without the offline smoke check performed by `prepare`.

**Fix:** validate expected route identity, required tokenizer and model files, and load/run a fixed sample in an isolated process against the staged directory before retiring the active model. Keep rollback available until that validation succeeds.

**Test gap:** [test_audit_followup.py:403](<C:/Users/Fillask/Desktop/GitHub repos/LanguageLens/tests/test_audit_followup.py:403>) substitutes `Package=lambda _path: None`. It verifies rename rollback, but cannot detect a failed model preflight. Add a separate regression for syntactically valid, unusable packages and verify the active model remains untouched.

### 2. P2 — Versioned replacement and removal can leave another active package

**Locations:** [model_management.py:91](<C:/Users/Fillask/Desktop/GitHub repos/LanguageLens/src/language_lens/services/model_management.py:91>) and [model_management.py:129](<C:/Users/Fillask/Desktop/GitHub repos/LanguageLens/src/language_lens/services/model_management.py:129>).

Replacement identifies the existing model by the incoming archive directory name. Argos directories include version identifiers, so a newer version with a different name is published beside the old version. Argos's installed backend selects the first translation for a source/target pair rather than choosing the newest version. `remove_route()` retires only packages returned by the selected route.

**Reproduction:** publishing `translate-en_nl-1_0` followed by `translate-en_nl-1_1` left both directories active. After clearing both Argos caches, the selected route still used `1_0`. Running removal and clearing both caches again left the pair installed through the remaining package.

**Fix:** plan replacements by source/target route identity, retire superseded versions transactionally, and make removal account for duplicate installations. Preserve the shared-pivot confirmation. Add upgrade and duplicate-removal regressions with different directory names.

### 3. P2 — Progressive translation results create quadratic protocol and UI work

**Locations:** [translation.py:27](<C:/Users/Fillask/Desktop/GitHub repos/LanguageLens/src/language_lens/services/translation.py:27>), [task_worker.py:73](<C:/Users/Fillask/Desktop/GitHub repos/LanguageLens/src/language_lens/services/task_worker.py:73>), and [review.py:1095](<C:/Users/Fillask/Desktop/GitHub repos/LanguageLens/src/language_lens/ui/review.py:1095>).

After each unique word, `selection_results()` copies the entire accumulated dictionary. The worker serializes it again, the GUI decodes it again, and every canvas recreates its full hit list. The unchanged sentence is rendered and the control layout is recalculated on each update as well.

| Unique words | Word entries resent | Serialized bytes with short dummy candidates |
| --- | --- | --- |
| 10 | 55 | 3,896 |
| 100 | 5,050 | 308,006 |
| 500 | 125,250 | 7,619,806 |

These figures measure protocol work, excluding neural inference. Real candidate strings can increase the byte count. The entry count follows `n(n+1)/2`.

**Fix:** emit the sentence once and send word-result deltas or small batches. Merge results into GUI state, update affected occurrences, and coalesce layout/repaint work. Keep terminal failure results and repeated-word reuse. Add a scaling assertion on transmitted entries so this remains linear.

### 4. P2 — OCR image staging blocks the interface before the worker starts

**Location:** [jobs.py:54](<C:/Users/Fillask/Desktop/GitHub repos/LanguageLens/src/language_lens/services/jobs.py:54>).

`ServiceJob.start()` synchronously saves every original and padded retry image as PNG before launching `QProcess`. This happens on the GUI thread. The retry images are encoded even when the first scan ultimately succeeds. During encoding, the event loop cannot process normal input or cancellation.

**Measured:** two saves of deterministic random RGB images took **0.357 seconds at 1920×1080** and **1.395 seconds at 3840×2160**, producing approximately 12.5 MB and 49.9 MB respectively. These are synthetic high-entropy examples; ordinary text crops can compress faster. The blocking location is independent of content.

**Fix:** move owned `QImage` serialization to a bounded background staging step, or use an uncompressed/shared-memory transport. Preserve cancellation, scratch ownership and native pixel coordinates. Defer retry-specific work where practical. Verify that GUI events continue during large-image staging.

### 5. P2 — Readiness ignores changes to the translation inference runtime

**Location:** [offline.py:101](<C:/Users/Fillask/Desktop/GitHub repos/LanguageLens/src/language_lens/services/offline.py:101>).

The readiness marker records several dependency versions but omits `ctranslate2`, the runtime Argos uses to load and execute translation models. A CTranslate2 update can therefore leave a previous offline-verification marker valid, even though the model/runtime combination has changed.

**Reproduction:** changing the reported CTranslate2 version while keeping the listed versions and files constant left `offline_ready()` returning `True`. The package name was never queried by `runtime_identity()`.

**Fix:** include CTranslate2 and other directly relevant tokenizer/runtime dependencies in a documented verification identity. Bump the marker schema if appropriate. Parameterize version-invalidation tests over the actual dependency names; the existing test replaces the entire identity dictionary and misses omissions.

### 6. P2 — Production model downloads discard the cache tested by the helper

**Locations:** [task_worker.py:35](<C:/Users/Fillask/Desktop/GitHub repos/LanguageLens/src/language_lens/services/task_worker.py:35>), [model_download.py:43](<C:/Users/Fillask/Desktop/GitHub repos/LanguageLens/src/language_lens/services/model_download.py:43>), and [jobs.py:125](<C:/Users/Fillask/Desktop/GitHub repos/LanguageLens/src/language_lens/services/jobs.py:125>).

`download_model()` can reuse a complete archive in `package.settings.downloads_dir`. Production explicitly redirects that directory to the current job's scratch folder, which is removed at completion, failure or cancellation. Each subsequent job gets a new scratch directory and cannot see the previous archive or the normal Argos download cache.

This matters when a download finishes but installation fails, or when the user repeats repair: the completed archive must be downloaded again. Already-published translation packages still survive; this finding concerns archive reuse. The README's description of normal-cache reuse does not match the production wiring.

**Fix:** use a dedicated persistent archive cache with validated identities, atomic publication and a bounded retention policy. Keep incomplete job files disposable. Test reuse across two real supervisor jobs, including download-success/install-failure. [test_model_download.py:42](<C:/Users/Fillask/Desktop/GitHub repos/LanguageLens/tests/test_model_download.py:42>) currently invokes the helper twice against the same directory, bypassing the production override and cleanup.

### 7. P3 — Legacy task execution duplicates the production path and weakens test fidelity

**Locations:** [review.py:214](<C:/Users/Fillask/Desktop/GitHub repos/LanguageLens/src/language_lens/ui/review.py:214>), [review.py:250](<C:/Users/Fillask/Desktop/GitHub repos/LanguageLens/src/language_lens/ui/review.py:250>), [jobs.py:155](<C:/Users/Fillask/Desktop/GitHub repos/LanguageLens/src/language_lens/services/jobs.py:155>), and [task_worker.py:51](<C:/Users/Fillask/Desktop/GitHub repos/LanguageLens/src/language_lens/services/task_worker.py:51>).

The UI retains four `QRunnable.run()` implementations, while its imported `QThreadPool` is actually a compatibility dispatcher that serializes tasks into processes. Native OCR mapping/selection filtering exists in both `NativeOcrTask.run()` and `task_worker.execute()`. Several tests call `.run()` directly, so they exercise the legacy mapping path. The production path supplies verified offline OCR parameters and sanitized worker failures; the legacy path initializes defaults and exposes exception strings.

The split already creates differences: the legacy native task returns immediately for empty regions, whereas the worker initializes OCR before iterating regions. The dispatcher also does not serialize the task's configurable `retry_scale`, so a helper test with a custom scale would not prove production behavior.

**Fix:** extract image conversion, retry recognition and native mapping into service/domain functions used by the worker and tests. Replace compatibility runnables with explicit request objects. Retain small process-boundary tests for serialization, offline parameters, cancellation, stale results and terminal UI states. The opt-in integration script provides useful coverage, but is separate from the default suite.

This also removes the worker's dependency on importing the large review widget module and its Qt multimedia/UI dependencies just to access OCR task logic.

### 8. P3 — Every native capture builds a redundant full-desktop bitmap

**Location:** [capture.py:105](<C:/Users/Fillask/Desktop/GitHub repos/LanguageLens/src/language_lens/services/capture.py:105>).

The app retains native monitor pixmaps and also allocates, fills and renders a logical desktop composite. The native selection/review branches draw the monitor pixmaps directly and crop them directly for OCR. They primarily use the composite for dimensions and coordinate bounds.

At 100% scaling, two adjacent 3840×2160 monitors require approximately **63.3 MiB** for the composite alone at four bytes per pixel, in addition to the native buffers. Desktop gaps increase the composite's bounding area. These are calculated buffer costs, excluding Qt/platform overhead.

**Fix:** represent desktop bounds independently of pixels and use the existing per-monitor tiles. Retain or lazily create a composite only for callers that actually need it. Keep negative-origin, fractional-DPI and desktop-gap regressions while changing the representation.

### 9. P3 — Two process supervisors duplicate lifecycle machinery

**Locations:** [jobs.py:26](<C:/Users/Fillask/Desktop/GitHub repos/LanguageLens/src/language_lens/services/jobs.py:26>) and [speech.py:14](<C:/Users/Fillask/Desktop/GitHub repos/LanguageLens/src/language_lens/services/speech.py:14>).

`ServiceJob` and `SpeechJob` separately implement process launch, Python executable selection, stdin requests, buffered JSON parsing, the 16 MiB buffer cap, startup failure, inactivity timers, cancellation, reentrant completion and temporary-directory cleanup. Their event/result protocols differ, but the lifecycle guarantees overlap substantially.

**Fix:** share a small lifecycle supervisor with command-specific protocol adapters and timeout policies. Keep the existing parameterized reentrant-completion regression and add transport-level failure cases there. Avoid an abstraction that merges unrelated speech/model domain behavior.

### 10. P3 — Test setup and cleanup are repeated across regression files

**Locations:** [conftest.py:24](<C:/Users/Fillask/Desktop/GitHub repos/LanguageLens/tests/conftest.py:24>), [test_review.py:18](<C:/Users/Fillask/Desktop/GitHub repos/LanguageLens/tests/test_review.py:18>), [test_audit_followup.py:125](<C:/Users/Fillask/Desktop/GitHub repos/LanguageLens/tests/test_audit_followup.py:125>), and [test_ui_finish.py:158](<C:/Users/Fillask/Desktop/GitHub repos/LanguageLens/tests/test_ui_finish.py:158>).

The global fixture already snapshots and disposes newly created widgets. A module fixture independently disposes all review/canvas windows, and individual factories repeat close/delete/worker shutdown. Review factories also repeat fake dispatchers and synthetic image construction. The cleanup paths use different ownership rules, which makes native object lifetime harder to reason about.

**Fix:** provide shared review/settings factories, a reusable fake dispatcher/job, and one explicit cleanup owner for each fixture-created object. Organize new regressions by subsystem as the historical audit files grow. Most behavioral assertions cover distinct regressions and should be retained.

The 22 skipped optional voice-fixture cases use the older prototype directory. The expanded catalogue has a separate all-voices script, so default-suite success alone does not establish all-voice synthesis coverage. Give opt-in integrations a shared asset-root configuration and clear markers, with fixture availability reported explicitly.

## Additional improvement opportunities

- **Repeated model startup:** every wider search and uncached speech synthesis starts a fresh process and reloads its runtime/model. GUI-side Argos caches do not cross that process boundary; speech retains only its latest audio entry. Profile a supervised worker retained for the current review and a bounded audio cache before changing the isolation design. Keep crash recovery, inactivity limits, cancellation and screenshot-data disposal. This audit did not benchmark real inference latency.
- **Reproducible environments:** the repository has broad ML/Qt dependency ranges and no committed lock/constraints file or CI workflow. It also uses private RapidOCR internals and Argos cache internals. Save the validated dependency set and run Windows/Python-version checks against it before expanding supported combinations. `pip check` establishes installed dependency consistency, not compatibility with every future version allowed by the ranges.
- **Prototype duplication:** AST comparison found identical `tokenize`, `align_units` and `_events` implementations in production and the research prototype. The README describes the prototype as an independent baseline. Preserve that independence deliberately by documenting/pinning its baseline; extract shared code only if the prototype should track production. The nested `collect` callback is part of the same duplicated `_events` implementation.
- **UI responsibilities:** `review.py` is 1,386 lines and `setup.py` is 803; their constructors span 195 and 272 lines. The service extraction in finding 7 is a useful first cut. Further separate view construction, review session state and result application where it reduces coupling.

## Suggested sequence

1. Fix and cover staged validation, versioned replacement and duplicate removal.
2. Restore persistent archive reuse and complete readiness-version identity.
3. Replace cumulative translation snapshots and move image staging off the GUI thread.
4. Consolidate task execution and test factories, then remove redundant bitmap work.
5. Consolidate process lifecycle code and profile bounded worker/audio reuse.

Existing strengths include atomic settings writes, supervised native tasks, explicit offline preparation, sanitized diagnostics, native-monitor geometry preservation, recoverable backups, and broad UI/Unicode regression coverage. Preserve those guarantees while reducing duplication.

The new probes used synthetic images and temporary package roots. This audit did not repeat live game capture, physical mixed-DPI display testing, all-voice listening/synthesis, or the opt-in real-model offline integration script. No application fixes or commits were made.
