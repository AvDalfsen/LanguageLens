# LanguageLens technical repairs — 6 October 2026

The ten findings in the [technical audit](technical-audit-2026-10-06.md) have been addressed in the existing working tree. These changes preserve the capture/review controls, local translation, sentence and word pronunciation, optional IPA, cancellation, recoverable model backups and worker crash isolation. Existing unrelated work was retained; no commit was created.

## Changes

| Audit finding | Repair |
| --- | --- |
| 1. Unusable model can replace a working installation | Staged preflight verifies the requested language pair, loads the tokenizer and CTranslate2 weights and translates a fixed sample with networking disabled. Validation finishes before installed directories move. Invalid managed downloads are discarded so retry can fetch a fresh archive; runtime/permission failures retain the download. |
| 2. Versioned replacements/removals leave old packages active | Replacement identifies every installed version by language pair and retires them together. A durable, versioned journal supports rollback during partial retirement/publication and recovery after a crash. Earlier journals remain readable. Removal retires all versions of each route leg. Archive names cannot overwrite another language pair. |
| 3. Quadratic translation updates | The sentence is sent once, followed by one-word deltas. Review merges deltas, tracks completed/failed words, updates only matching word occurrences and coalesces layout work. Repeated words, pinned popups, wider candidates and independent sentence/word recovery remain covered. |
| 4. PNG staging freezes the GUI | Owned QImages are encoded by a background thread before starting the worker. Staging participates in timeout/cancellation and retains ownership until encoding stops, including when the review window is destroyed. |
| 5. Readiness misses translation-runtime changes | Runtime identity now includes CTranslate2, SentencePiece and Sacremoses alongside the existing components. |
| 6. Completed archives disappear with each job | Completed archives use a persistent application cache keyed by route/version/download links and verified before reuse. Old archives are pruned toward 2 GiB while retaining the current download. Interrupted transfers stay in disposable scratch directories. A locked old cache file cannot turn a completed download into a failed installation. |
| 7. UI tasks and production worker implement different behavior | Shared domain tasks now own image conversion, OCR retry/mapping, request serialization and engine creation from verified local parameters. The worker no longer imports the review UI. Custom retry scale survives serialization; empty OCR requests skip engine startup. Existing public UI task names remain available through thin adapters. |
| 8. Unnecessary desktop composite | Geometry supplies coordinate bounds independently of pixels. Selection/review draw native monitor tiles without creating a composite. The existing pixmap interface creates a preview lazily when requested. |
| 9. Duplicated process supervision | Speech and service jobs share process launch, JSON buffering, limits, scratch ownership, startup failure, timers, cancellation and completion cleanup. Protocol-specific signals and timeout policies remain separate. Completion snapshots its outcome before callbacks can start/reset another job; final buffered progress cannot leave an old timeout running. |
| 10. Duplicated test factories/cleanup and missing voice fixtures | Review fixtures share a factory and use the existing global widget cleanup owner. The redundant module cleanup was removed. Voice integrations discover expanded catalogue assets, retain the older locale fallback, support `LANGUAGE_LENS_TEST_VOICES` and check the voice's configured sample rate. Distinct existing behavioral tests were retained. |

The installed Windows x64/Python 3.10 runtime/dev versions are recorded in `constraints/windows-python310.txt` (96 dependency distributions). This is an optional reproducibility snapshot, not a cross-platform lockfile or evidence for untested Python combinations.

## Verification

| Check | Result |
| --- | --- |
| Full suite with all available voice fixtures | **699 passed, zero skips**, 320.49 seconds. This includes all 26 catalogue voices with real sentence audio, prepared pronunciation and phoneme-based word audio. |
| Subsequent suite after additional model/cache guard regressions, excluding only the already-passed 26 voice fixture cases | **678 passed, 26 deselected**, 110.29 seconds. |
| Final focused run after the cache-retention guard and final cleanup | **71 passed**, 1.97 seconds, including all **28 new repair regressions** and existing download/review/UI regressions. |
| Real offline integration | Portuguese → English, Dutch → English and Portuguese → Dutch passed preparation, fresh-process OCR, sentence/word translation and wider search. The actual Qt review flow passed OCR → translation → retry the same screenshot → wider search. |
| Real model replacement integration | A copied Portuguese → English model passed staged inference. A broken replacement left it active. A valid renamed replacement became the selected Argos directory. Removal left no active route and retained both recoverable models. |
| Installed dependency compatibility | `pip check`: no broken requirements found. |
| Whitespace and syntax | `git diff --check` passed; Python compilation passed. |

The suite now contains **705 cases**: the full run covered the original cases and first repair regressions; subsequent runs covered the additional guards without repeating expensive, unchanged voice inference. No regression was removed to obtain a passing result.

For 500 unique words, protocol word entries decrease from **125,250 to 500**. This is a deterministic payload-count improvement, not a claim that inference is 250 times faster. Native screenshot previews remain absent through selection/review in the lazy-composite regression. A deliberately blocked PNG writer proves that the GUI event loop keeps processing events during staging; cancellation and destruction tests verify scratch cleanup.

The real integration scripts use isolated copies/test roots. They do not modify the user's installed Argos packages. The offline harness needed an unsandboxed run to access required runtime resources; its model and application-data roots remained isolated. Physical mixed-DPI monitors and live game capture were not repeated. Their existing geometry, gap, focus and lifecycle regressions passed.

## Readiness migration and retained design choices

Previously prepared language pairs need **Check required files** once to refresh their readiness record with the additional runtime versions. Installed translation models and voice files remain available; this is verification, not removal.

Workers still run as separate, bounded native processes. Retaining a warm worker or adding a larger audio cache would require further profiling and lifecycle design; no speculative change to crash isolation was introduced. The pronunciation research prototype remains an independent baseline, as documented by the project. No CI run or broader platform validation is claimed.

Reproduction commands (from the repository root):

```powershell
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe scripts/verify-offline.py --models "PATH_TO_EXISTING_ARGOS_PACKAGES"
.\.venv\Scripts\python.exe scripts/verify-model-replacement.py --model "PATH_TO_ONE_EXISTING_ARGOS_PACKAGE"
.\.venv\Scripts\python.exe -m pip check
git diff --check
```
