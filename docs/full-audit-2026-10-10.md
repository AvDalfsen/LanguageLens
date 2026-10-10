# Language Lens full audit — 10 October 2026

Repairs and follow-up validation are recorded in [audit repairs](audit-repairs-2026-10-10.md). This report preserves the findings at the audited revision.

Audited revision: 2c4912d5df096f609df232d082b5acb28e7bd3fe.

The application has a substantial regression suite and sound foundations for local processing, Unicode offsets, asset integrity, and process isolation. The largest remaining gaps are incorrect success reporting, retained task objects, readiness checks that can outlive their translation route, and limited measurement of linguistic quality. Passing the suite does not currently establish that translations are useful in context or that repeated operations release their resources.

No P0/P1 defect was reproduced. The findings below use P2 for defects or quality gaps worth addressing in the next maintenance cycle, and P3 for lower-impact architectural or process improvements. Priorities reflect the demonstrated conditions.

## Scope and validation

Reviewed the application, services, UI, catalogs, tests, build/setup scripts, CI, documentation, and pronunciation prototype. The Python inventory is 49 application files / 8,962 lines, 32 test files / 6,936 lines, 16 script files / 1,282 lines, and seven pronunciation prototype files / 874 lines. The main suite contains 363 test functions, expanded by parametrization to 959 cases.

| Check | Result |
| --- | --- |
| .venv\Scripts\python.exe -m pytest -q -ra | 959 passed in 172.50 seconds; no skips on this host |
| .venv\Scripts\python.exe -m pytest prototypes\pronunciation\tests -q -ra | 32 passed in 6.17 seconds |
| pip check | No broken requirements |
| git diff --check before the audit report | Clean |
| UI catalog structure | 331 messages, 25 locales; catalog/placeholder tests passed |
| UI previews | Generated 100 views: 50 Settings views at two sizes, 25 Help views, 25 Review views; inspected the contact sheet and representative Arabic/German views |
| Real MiniSBD fixtures | 38 cases across 25 languages matched recorded baselines; 35 matched intended sentence boundaries |
| Real Argos samples | 16 cases across nl → en, pt → en, en → nl, and the pt → en → nl pivot |
| Focused behavior probes | Reproduced F1–F6 and F9 using synthetic data or existing isolated fixtures |

The real voice integration tests ran on this host because local fixtures were present. This included audio generation, phoneme playback data, and the muted Qt playback test. It was not a fluent-speaker listening assessment. Real translation sampling covered four routes and was not a certification of every supported language. Catalog review combined structural checks with selected linguistic examples, not native-speaker signoff for all 25 locales. No coverage percentage, clean-machine release validation, live-game performance benchmark, physical multi-monitor/DPI exercise, or dependency vulnerability scan was performed.

Application code was not changed. Synthetic probes and their results are retained under the ignored directory [artifacts/audit-2026-10-10](../artifacts/audit-2026-10-10/). They use isolated application-data paths and do not capture the desktop or download models. Visual previews are under the ignored [artifacts/localization-audit/previews](../artifacts/localization-audit/previews/).

## Prioritized findings

| ID | Priority | Finding | Evidence |
| --- | --- | --- | --- |
| F1 | P2 | Offline readiness does not track the route Argos currently selects | Real route selection with synthetic package metadata and readiness marker |
| F2 | P2 | Retries retain completed Qt jobs, signals, and task data | Real Qt/QProcess lifecycle with a synthetic worker |
| F3 | P2 | Empty backend output is returned as a successful copy of the source | Synthetic backend returning whitespace |
| F4 | P2 | Known failures and some speech recovery states remain English | Dutch UI and categorized failure probes |
| F5 | P2 | CJK segmentation repeatedly scans an already-activated pack manifest | Warm managed-pack timings and call counts |
| F6 | P2 | Recoverable translation exceptions bypass diagnostic logging | Worker execution with failing sentence and word translators |
| F7 | P2 | Translation tests establish availability more strongly than semantic quality | Test/script inspection and real model samples |
| F8 | P2 | Technical UI translations still contain meaning and terminology problems | Selected catalog entries |
| F9 | P3 | Language switching infers message identity from ambiguous translated text | French Cancel/Undo collision |
| F10 | P3 | Repository CI runs after merge and covers one Python version | Workflow and source setup configuration |

### F1 — Offline readiness can validate a different route from the one used for inference

Locations: [offline.py](../src/language_lens/services/offline.py), lines 100–122 and 182–186; [task_worker.py](../src/language_lens/services/task_worker.py), lines 32–39.

Preparation records runtime identity, sentence-model identities, and file sizes/timestamps. The offline_ready() function checks those recorded files, but does not compare the installed package set or selected ordered translation route with the route that was prepared. The status worker resolves the current route separately and can report that new route as prepared using the old marker.

A probe started with metadata-only pt → en and en → nl packages plus a synthetic valid readiness marker. Adding an unverified metadata-only pt → nl package changed Argos's selected route to the direct package; both offline_ready() and status prepared remained true. The new package had no usable tokenizer/weights. This demonstrates the gate error, not successful inference or a real preparation of those synthetic packages. It is relevant because Argos packages can also be modified by other tools sharing the installation.

**Recommended change:** bind preparation to selected ordered package identities, paths/versions, and required sentence languages. Invalidate preparation when the selected route changes. Keep background inspection responsible for expensive model work; avoid importing/loading native translation models on the GUI capture path.

**Regression check:** prepare a pivot, add a direct package while leaving every recorded file unchanged, and assert readiness becomes false. Also cover removal/replacement and a harmless unrelated-package addition.

Evidence: [route_probe.py](../artifacts/audit-2026-10-10/route_probe.py), [route-results.json](../artifacts/audit-2026-10-10/route-results.json).

### F2 — Completed review tasks accumulate until the window is destroyed

Locations: [review.py](../src/language_lens/ui/review.py), lines 786–839, 934–953, and 1005–1010; [jobs.py](../src/language_lens/services/jobs.py), lines 62–87; [process_job.py](../src/language_lens/services/process_job.py), lines 196–219.

Review tasks parent their TaskSignals to the window. Each ServiceJob is then parented to those signals, and its event callback captures the whole task. Process completion deletes the QProcess, but neither the job nor its signals. Clearing the _jobs list therefore does not release the parent-owned objects. Translation retries additionally append to the list without removing completed entries.

With a real Qt event loop and QProcess, but a tiny synthetic worker:

| State | Retained TaskSignals | Retained ServiceJobs | _jobs entries |
| --- | ---: | ---: | ---: |
| Initial OCR and translation | 2 | 2 | 2 |
| After 10 translation retries | 12 | 12 | 12 |
| After another 10 OCR retries | 32 | 32 | 2 |

The OCR tasks retain their original and padded image fields through the captured task reference. Memory growth depends on crop sizes and retry count; this is retained state within a live review window, not a demonstrated process-global leak after window destruction.

**Recommended change:** give disposable review tasks an explicit terminal lifecycle. After success, failure, or cancellation, disconnect/release task callbacks and delete task signals/jobs safely after result delivery. Clear large image fields when staging no longer needs them. Preserve cancellation and staging-thread teardown guarantees. Persistent Setup/Speech jobs have a different lifecycle and should remain reusable.

**Regression check:** repeat successful, failing, and cancelled OCR/translation/wider-search operations; assert QObject descendants and retained image/task references return to a bounded baseline, not merely that the _jobs list is cleared.

Evidence: [audit_probe.py](../artifacts/audit-2026-10-10/audit_probe.py), [probe-results.json](../artifacts/audit-2026-10-10/probe-results.json).

### F3 — An empty translation is silently converted into untranslated source text

Location: [translation.py](../src/language_lens/services/translation.py), line 251 and the word fallback at lines 236–237.

The translate() function returns result.strip() or text. For a nonempty cross-language request whose backend returns whitespace, the caller receives the original text as a successful translation. The word fallback similarly produces a successful candidate containing that source text.

The synthetic backend returned whitespace for Bonjour, fr → en. The sentence result was Bonjour; the word result was a single Bonjour candidate with the note “Alternatives unavailable; showing a single translation.” Nothing identified the empty inference result.

**Recommended change:** raise a categorized TranslationUnavailable for an empty backend result on nonempty cross-language input. Keep explicit empty-input and same-language passthrough behavior. Do not reject a nonempty unchanged result indiscriminately: names and loanwords can legitimately remain unchanged.

**Regression check:** whitespace-only sentence output, an empty n-best list followed by empty fallback, a valid unchanged proper name, and same-language/empty input. Preserve independent recovery for sentence and word failures.

Evidence: [probe-results.json](../artifacts/audit-2026-10-10/probe-results.json).

### F4 — Error and recovery localization has gaps outside explicit translation calls

Locations: [errors.py](../src/language_lens/services/errors.py), lines 24–40 and 68–71; [i18n.py](../src/language_lens/i18n.py), lines 106–122; [review.py](../src/language_lens/ui/review.py), lines 1025–1040 and the pronunciation runtime recovery branch.

The catalog is structurally complete for its registered messages, but many categorized failures are assembled from English stage prefixes and recovery text that is absent from the catalog. The tr_message() function supports a failure_prefixes catalog field, yet the JSON has no such field. Dutch UI probes left permission, missing-pack, runtime, and OCR execution failures entirely English. These are known user-facing recovery messages, not arbitrary technical diagnostics.

Two speech states have additional gaps:

- Missing voice: “Use 'Download voice' in 'Settings' to read this text aloud.” is assigned directly and this source variant is not catalogued.
- Overlong selection: “Select a shorter passage to read aloud (up to 2,000 characters).” is catalogued, but assigned without tr(). The Dutch translation exists and was not used.

The AST catalog audit checks existing literal tr() calls. It cannot detect a missing call, an uncatalogued assembled message, or a branch the UI previews never enter.

**Recommended change:** render known failure codes/stages through explicit catalog templates in the GUI, and catalogue every actionable recovery state. Use existing structured Failure fields rather than reconstructing identity from English prose. Localize speech and pronunciation recovery branches when they are displayed.

**Regression check:** render every known failure code and stage in representative non-English locales; exercise missing voice, runtime unavailable, overlong selection, and language switching while these states are visible. Assert actual widget text, not only that tr() can translate an unrelated template.

Evidence: [failure-results.json](../artifacts/audit-2026-10-10/failure-results.json), [probe-results.json](../artifacts/audit-2026-10-10/probe-results.json).

### F5 — Managed CJK segmentation repeatedly scans all pack files

Locations: [text.py](../src/language_lens/text.py), lines 48–73; [language_packs.py](../src/language_lens/services/language_packs.py), lines 85–103 and 124–137.

The word_spans() function calls activate() inside its regex-match loop. The activate() function calls _installed() before checking whether the same pack is already activated. The _installed() function parses the pointer and manifest and resolves/stats every listed file each time. A sentence with spaces or punctuation can contain many matching runs.

Timings used already-activated managed fixtures with warm tokenizers, no download, and networking disabled. These are total segmentation timings, including the repeated checks:

| Managed pack | Matching runs | Manifest checks | Time |
| --- | ---: | ---: | ---: |
| Japanese | 1 / 10 / 100 | 1 / 10 / 100 | 26.6 / 258.1 / 2,549.9 ms |
| Chinese | 1 / 10 / 100 | 1 / 10 / 100 | 21.2 / 212.1 / 2,112.1 ms |

The Japanese fixture yielded 200 tokens at 100 runs, and the Chinese fixture 300. Unbroken CJK text can produce one regex run; source-installed packs can have different costs. The defect is redundant validation per run, not a claim that every short Japanese/Chinese selection takes seconds.

**Recommended change:** activate once per segmentation operation or worker. Retain full integrity verification on first activation, and a cheap change/identity check at the appropriate operation boundary to preserve the pack-restart contract.

**Regression check:** tokenize a punctuation/space-separated passage with 100 CJK runs and assert manifest validation is bounded per operation. Separately retain tests for changed, removed, and corrupt packs.

Evidence: [quality_probe.py](../artifacts/audit-2026-10-10/quality_probe.py), [quality-results.json](../artifacts/audit-2026-10-10/quality-results.json).

### F6 — Recoverable translation failures leave no diagnostic trace

Locations: [translation.py](../src/language_lens/services/translation.py), lines 36–48; [task_worker.py](../src/language_lens/services/task_worker.py), lines 80–82 and 107–117.

The selection_results() function catches sentence and word exceptions to keep partial results available. That behavior is useful, but it neither records a sanitized failure nor returns structured failure information. The outer worker sees normal completion and emits ok: true; its exception logger never receives those errors.

A failing synthetic translator produced an empty sentence and an unavailable word result. The execute() function returned normally, emitted no structured failure event, and called record_failure() zero times. The user sees generic retry guidance, while the component/stack information needed to investigate recurring failures is lost. This is a diagnostic gap, not a claim that the UI displays a valid translated sentence after an exception.

**Recommended change:** retain partial-result streaming and log caught failures using the existing privacy-safe logger, which records exception types and stack locations rather than captured text. Include structured per-sentence/per-word failure state where it helps recovery. Distinguish a supported “no n-best available” fallback from a runtime failure so routine fallbacks do not flood logs.

**Regression check:** a failing sentence with successful words, a successful sentence with one failing word, and both failing. Assert useful partial results and sanitized diagnostic records, and assert private text is absent from logs/events.

Evidence: [failure_probe.py](../artifacts/audit-2026-10-10/failure_probe.py), [failure-results.json](../artifacts/audit-2026-10-10/failure-results.json).

### F7 — Semantic translation quality is not adequately tested

Locations: [test_translation.py](../tests/test_translation.py); [verify-offline.py](../scripts/verify-offline.py), around line 64; [verify-sentences.py](../scripts/verify-sentences.py), lines 67–72 and 87–92; [translation.py](../src/language_lens/services/translation.py), lines 189–226.

The unit tests thoroughly check ranking, normalization, capitalization, deduplication, caching, and failure handling with fake backends. Real offline checks largely assert nonempty output/candidates. The sentence comparison script checks stability against an older backend, which can preserve an incorrect result. There is no committed, reviewed source/expected-meaning corpus establishing translation quality across the main routes.

The 16 real-model samples generally produced sensible sentences, including negation and number distinctions. One awkward sentence was “Take the turn right.” Isolated word results often did not express the meaning used in the sentence:

| Input / lookup | Sentence output | Compact word candidates |
| --- | --- | --- |
| Hij zat op de bank. / bank, Dutch → English | He was sitting on the couch. | bank, Bank, bench, sofa |
| Ik heb er geen zin in. / zin, Dutch → English | I don't feel like it. | sentence, phrase, clause, sentences |
| Kun je het licht uitdoen? / uitdoen, Dutch → English | Can you turn off the lights? | take off, take it off, off, Take it off |
| A manga da camisa está rasgada. / manga, Portuguese → English | The sleeve of the shirt is torn. | mango, manga, sleeve, Mango |
| Same Portuguese sentence → Dutch through English | De mouw van het shirt is gescheurd. | mango, manga, Mango, Manga |
| Eu não quero que vás embora. / embora, Portuguese → English | I don't want you to leave. | although, Although, though, However |

This is largely an acknowledged consequence of translating individual words without sentence context, rather than a new algorithm regression. The isolation warning is useful, but “Best word translation” and the leading candidate can still imply the right sense for the selected sentence. Capitalization variants also consume compact candidate slots; blanket case-fold deduplication would be unsafe because distinctions such as US/us and Polish/polish are meaningful.

**Recommended change:** create a small reviewed semantic corpus covering homographs, idioms, phrasal verbs, negation, numbers, names, and formality, with acceptable paraphrases and direct/pivot routes. Measure sentence meaning and useful word senses separately. Consider a clearer “Top suggestion for the isolated word” label, and context-aware/phrase lookup as a separately scoped product improvement.

The sentence-boundary fixtures also deliberately accept three known merges: Arabic “افتح الباب. المفتاح على الطاولة.”, Chinese “请打开门。钥匙在桌子上。”, and Japanese “鍵はどこですか？ここにあります！”. All 38 cases matched their recorded baseline, but only 35 matched intended boundaries. Track these as quality debt rather than treating baseline agreement as accuracy.

**Regression check:** optional real-model integration tests using deterministic local fixtures and semantic expectations reviewed by speakers. Do not reduce all translation quality tests to exact output snapshots or nonempty assertions.

Evidence: [quality-results.json](../artifacts/audit-2026-10-10/quality-results.json), [sentence-results.json](../artifacts/audit-2026-10-10/sentence-results.json), [sentence-boundaries.json](../tests/data/sentence-boundaries.json).

### F8 — Pronunciation warning translations need a terminology review

Location: [ui-translations.json](../src/language_lens/data/ui-translations.json), especially lines 2362, 2586, 2695, 2919, 6589, and 6612.

Structural completeness is strong; linguistic consistency is weaker in technical pronunciation explanations. Selected examples:

| Entry | Concern | Intended meaning / direction for revision |
| --- | --- | --- |
| Arabic maximal-onset tooltip, line 6612 | Uses أقصى عدد من المقاطع, meaning a maximum number of syllables; the source refers to maximal syllable onsets, not counting syllables | Explain the longest permissible consonant sequence at the start of a syllable, estimated for the chosen accent |
| Portuguese ipa_accent, lines 2362 / 2695 | acento is ambiguous alongside stress-mark terminology; the setting refers to the selected voice's speaking accent. Other related strings use sotaque | Prefer consistent sotaque, e.g. “O IPA segue este sotaque.” |
| Portuguese isolated-fallback warning, lines 2586 / 2919 | substituto isolado is unnatural and does not explain what replaces the failed mapping | State that word pronunciation is generated for the word alone, without sentence context |
| Arabic “Generated for this word in isolation”, line 6589 | ولدت لهذه الكلمة في عزلة. is ambiguous and awkward; it does not clearly describe generated pronunciation without sentence context | Use an explicit generated-pronunciation formulation with “without sentence context” |

The Arabic onset mistranslation changes the technical meaning. The other examples are terminology/clarity concerns and should be reviewed by native speakers before replacing production wording. French and Japanese fallback strings also read literally and merit the same focused review; this audit does not claim fluency signoff for them.

**Recommended change:** establish a short glossary for speaking accent, stress, syllable onset, isolated word, contextual pronunciation, and mapping failure. Simplify English technical warnings where possible, then commission targeted native review across locales. Completeness/reference metadata does not substitute for linguistic review.

**Regression check:** record reviewed terminology decisions and use targeted checks for those terms. Automated catalog tests can preserve approved wording and placeholders; they cannot independently establish naturalness or accuracy.

### F9 — Retranslation can confuse two messages with the same localized text

Location: [i18n.py](../src/language_lens/i18n.py), lines 55–58 and 87–103.

The render cache identifies a message by locale and rendered text. The fallback reverse dictionary likewise maps localized text to one English source. Natural translations are not unique: French “Cancel” and “Undo” both produce Annuler.

A menu action created as tr("Cancel") in French changed to Undo on switching to English after an intervening tr("Undo") overwrote the render-cache entry. Once translate_ui() has captured a control's original source it often avoids this, so the reproduced scope is first discovery or newly changed captions; this is not proof that every existing Cancel button switches incorrectly.

**Recommended change:** attach the explicit source/message ID and formatting values to controls when assigning translated text. Avoid reverse-inference as the authoritative identity mechanism. Keep it only as a limited compatibility fallback if needed.

**Regression check:** French Cancel/Undo, other duplicate localized captions, cache eviction, and dynamic text changes before a language switch.

Evidence: [probe-results.json](../artifacts/audit-2026-10-10/probe-results.json).

### F10 — Tests are not automatically run on pull requests, and source support exceeds the CI matrix

Locations: [windows-release.yml](../.github/workflows/windows-release.yml), lines 3–7 and 23–32; [pyproject.toml](../pyproject.toml), line 10; [environment.ps1](../scripts/environment.ps1), lines 18–31; [setup.ps1](../scripts/setup.ps1), lines 18–20.

The workflow runs on pushes to main and manual dispatch, not pull_request. It runs the source suite and builds with pinned Python 3.10.6 dependencies after changes reach main. Source setup advertises Python 3.10, 3.11, and 3.12, but the repository's CI only exercises 3.10. Source setup also resolves broader dependency ranges without release constraints. These are reproducibility and change-detection gaps, not evidence that 3.11/3.12 currently fail.

Real voice tests skip on hosts without external fixtures, and default release verification does not pass model/voice/pack fixture arguments. Therefore a green clean-host workflow does not establish the same real inference coverage exercised by this audit. The README already honestly identifies Windows 11 clean-machine validation as pending.

**Recommended change:** add a lightweight pull-request test workflow, use a supported-interpreter matrix or narrow advertised source support, and document tested source dependency constraints for each supported interpreter. Keep portable packaging on its intentional Python 3.10 baseline. Add a separate periodic/manual integration job using explicit immutable fixtures, and make its expected skips/results visible. Repository workflow changes alone do not establish an enforced branch-protection rule.

## Code quality, duplication, and test organization

These are maintainability observations rather than additional demonstrated user-facing defects.

### Keep the repaired foundations

- Model installation stages packages, validates usable model/tokenizer content, retires duplicate versions of the route, and preserves rollback/recovery. Earlier concerns about treating ZIP validity as model validity have been addressed.
- Translation progress sends word deltas rather than repeatedly serializing the whole accumulated result. The earlier quadratic IPC concern has been addressed.
- Shared process supervision implements inactivity timeouts, cancellation, worker isolation, scratch cleanup, and off-thread image staging. Fix disposable job lifecycle without duplicating supervision again.
- Unicode normalization and grapheme/source offsets are explicit, with meaningful regression tests for combining marks, repeated words, punctuation, and CJK segmentation.
- Asset catalogs, checksums, managed archive paths, settings validation/atomic writes, and privacy-safe diagnostic formatting are materially stronger than a minimal prototype implementation.
- Help article bodies remain English by documented design; translated navigation with English articles is not counted as an accidental missing catalog entry.

### Separate review session state from widget construction

[SetupWindow.__init__](../src/language_lens/ui/setup.py) is 329 lines; [ReviewWindow.__init__](../src/language_lens/ui/review.py) is 202; [PronunciationSettings.__init__](../src/language_lens/ui/pronunciation.py) is 120. Construction, sizing, translation, asynchronous state, maintenance actions, and result application sit close together. That makes missing-state branches and lifecycle ownership hard to assess.

Prefer small, targeted extractions: review session/result state, task ownership, model maintenance state, and localized status rendering. Leave basic widget construction straightforward. There is no evidence supporting a wholesale UI rewrite. The format_ipa() function is also 130 lines and deserves small language-rule helpers when its rules next change, rather than unrelated restructuring during a lifecycle fix.

### Give the worker protocol explicit types and ownership

Commands and dictionary payload shapes are repeated across task encoding, dispatcher decoding, worker execution, CLI choices, timeout selection, and online/offline policy. The “TaskPool as QThreadPool” alias in Review preserves compatibility but implies threading semantics that production no longer uses. Old QRunnable.run() paths coexist with process dispatch; injected test translators/cancellation callbacks do not necessarily exercise the serialized production path.

Use a small explicit command/payload/event schema, rename the dispatcher to communicate process-based behavior, and keep shared domain execution functions. Add a few protocol/lifecycle integration checks at the serialization boundary. Avoid replacing useful backend unit tests with slower integration tests everywhere.

### Organize regression tests by subsystem

The files test_audit_followup.py, test_workflow_fixes.py, test_technical_repairs.py, and test_i18n_audit.py contain about 1,600 lines organized around past repair rounds. Alongside subsystem tests, they repeat some fake dispatchers, window construction, and waiting helpers. Shared factories already exist in conftest.py, so consolidation has begun.

Move historical regressions into relevant subsystem modules and reuse narrowly scoped helpers. Preserve assertions and meaningful edge cases; do not delete tests just because two fixtures look alike. In particular, use an occasional real TaskPool/QProcess test to detect ownership failures that a fake start() cannot expose. Prioritize concrete regression checks under F1–F6 and F9 over adding more tests that only restate catalog or ranking implementation details.

### Make prototype duplication deliberate

AST comparison found identical tokenize(), align_units(), _events(), and nested collect() bodies in [production pronunciation.py](../src/language_lens/services/pronunciation.py) and [prototype engine.py](../prototypes/pronunciation/engine.py). An independent frozen prototype can be a useful baseline, so sharing all code would remove that independence.

Document whether the prototype is a frozen reference or maintained tool. If frozen, label independent copies and historical claims clearly. If maintained, share deliberately selected stable helpers and keep distinct behavioral baseline tests. Its 32 tests are outside default testpaths and require a separate command.

### Add modest static checks

The repository has pytest configuration but no configured linter/type-checker workflow. There are small unused-import candidates, but test-facing re-exports and compatibility aliases should be checked before removal. A modest lint pass for undefined names and unused imports, plus type checking of protocol/domain boundaries, would be more valuable than a large style-only diff. New tooling should use explicit versions and fit the supported Windows/Python matrix.

## Recommended order of work

1. Fix F1–F3 together with targeted readiness, lifecycle, and empty-output regression tests. These affect whether the tool is actually ready, reports a valid result, and releases task data.
2. Fix F4 and F6 using structured failure rendering plus sanitized diagnostic recording. Add state-based UI localization tests.
3. Fix F5 by moving repeated activation checks to an operation boundary; retain integrity/change tests and repeat the warm managed-pack benchmark.
4. Add the semantic corpus from F7 and review terminology in F8. Treat contextual word/phrase support as an explicit product decision informed by those results.
5. Address F9/F10 and incremental subsystem/test/protocol cleanup. Preserve existing transaction, privacy, Unicode, cancellation, and release-pinning protections.

## Reproduction artifacts

The following files remain local and ignored, so the report is usable independently of them while detailed evidence remains available in this checkout:

- [audit_probe.py](../artifacts/audit-2026-10-10/audit_probe.py) / [probe-results.json](../artifacts/audit-2026-10-10/probe-results.json): empty output, speech status localization, caption collision, Qt job retention, and duplicate-body inventory.
- [route_probe.py](../artifacts/audit-2026-10-10/route_probe.py) / [route-results.json](../artifacts/audit-2026-10-10/route-results.json): selected route changing without readiness invalidation.
- [failure_probe.py](../artifacts/audit-2026-10-10/failure_probe.py) / [failure-results.json](../artifacts/audit-2026-10-10/failure-results.json): categorized failure localization and swallowed diagnostic records.
- [quality_probe.py](../artifacts/audit-2026-10-10/quality_probe.py) / [quality-results.json](../artifacts/audit-2026-10-10/quality-results.json): managed-pack timings and 16 real-model translation samples.
- [sentence-results.json](../artifacts/audit-2026-10-10/sentence-results.json): real MiniSBD results against intended and recorded boundaries.
