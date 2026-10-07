# Voice coverage and audit points 7–13 — 6 October 2026

Implementation follow-up to the original audit. Points 1–6 and the earlier
settings sizing/help changes remain in the working tree. No commit, public
release or binary distribution was created. Ignored environments, downloaded
models and generated development artifacts are not application source.

## Voices: feasibility and implementation

- All 25 source-language choices now have a downloadable local voice; English
  has US and UK choices, for 26 voices total. Existing English/Portuguese
  defaults remain unchanged. The additional catalogue is metadata-only JSON
  with exact file lengths, SHA-256 digests and pinned model-card links.
- The existing pinned Piper runtime remains suitable for the local, CPU-only,
  no-account workflow. Japanese needs the pinned pyopenjtalk-plus frontend and
  its dictionaries, rather than an unsupported eSpeak Japanese substitution.
  The tested Windows wheel avoids asking users to build OpenJTalk from source.
  Initial setup becomes larger; audio models remain individual opt-in downloads.
- Settings exposes the appropriate voice, size, sample, per-language preference,
  licence note and pronunciation speed. Samples, sentence audio and word audio
  use the same speed setting; phonetic strings are not rewritten for speed.
- English/Portuguese retain the audited IPA formatting profiles. Other language
  engines are labelled honestly as engine notation, with no English cluster or
  stress heuristics applied. Japanese word readings are explicitly isolated.
- Every voice passed actual normal and slower synthesis with verified model,
  configuration and card files. This establishes basic technical compatibility,
  not fluent-speaker quality, contextual disambiguation or suitability for every
  dialect/loanword/name. Some voices have noncommercial or unclear licence
  declarations; redistribution needs review. See the full source-card table in
  [speech notices](../THIRD_PARTY_SPEECH.md).

## 7. Genuine offline preparation

'Download required files' installs a missing direct/pivot translation route,
obtains the source writing system's OCR detector/classifier/recognizer, warms
the actual auxiliary sentence model and verifies a fixed sample with networking
disabled. Successful preparation records asset identities and relevant runtime
versions; changes invalidate readiness. OCR assets are hashed again before use.
An installed Argos route is no longer presented as complete offline readiness.

Argos always selects its local provider, even when the environment requests a
cloud provider. Capture workers disable Python outbound sockets, and Stanza
loads without automatic downloads. Speech/pronunciation also runs without
Python networking. Preparation uses a catalogue sample, never captured text.
This is an accidental-download guard, not an OS security sandbox. Translation
marker size/mtime checks are not cryptographic verification of all Argos files.

## 8. Failure recovery, bounded work and diagnostics

OCR, translation, wider search and settings capability checks use disposable
QProcess workers. Native engine crashes/hangs are isolated from normal Qt UI
work and produce retryable failures. Timers bound inactivity: 120 seconds for
OCR/translation/search, 30 seconds for status and five minutes for model tasks.
Speech retains separate preparation/download/playback limits. Close/cancel
kills the corresponding jobs, and completion callbacks cannot delete a new
job's scratch directory. Result streams have a size limit.

Sentence and individual-word failures are independent and share one domain
implementation. Pending word results receive terminal failure states. Configuration
types are validated, writes are atomic, and persistence/startup failures are
reported. Diagnostics omit exception messages and source text, retaining stage,
exception type and stack locations, including causes. Fixed per-command log
channels avoid competing GUI/worker log rotation handles on Windows.

Normal job cleanup removes OCR crop/audio scratch files. Power loss or a hard
application crash can leave sensitive temporary files; no claim of secure
erasure or an automatic screenshot history is made. GUI/native Qt faults remain
possible. The previously reported test crash was addressed by installing styles
before widgets in an isolated startup test and disposing test widgets; later
suites completed without that fault.

## 9. Separate capability indicators

Settings distinguishes installed translation route (including pivot languages),
OCR/translation offline preparation, dictionary/Unicode word segmentation,
phonetic notation limitations, and voice readiness. Model inspection runs in a
background process rather than importing neural runtimes on the GUI thread.
Debouncing and pair matching reject stale status results; failed maintenance
triggers a fresh check instead of trusting pre-operation readiness.

## 10. Recover without another screenshot

Review provides 'Retry OCR', 'Select another area', 'Retry translation' and
'Copy source text'. OCR retries clear old boxes, phones and keyboard state. Reselection
reuses the frozen capture and session/focus target, not a recaptured screen.
In-place OCR text editing has not been added: changing text would also require
reconciling hover geometry, offsets, segmentation and pronunciation alignment.

## 11. Long-selection layout

Whole-selection content scrolls and can be collapsed independently of controls.
Recovery, read and close buttons remain outside the scrolling area. Late
translation results respect the collapsed state. Popup lists scroll and are
bounded to the active monitor. Settings retains content-fit sizing unless the
desktop limits or a remembered manual size require scrolling.

## 12. Candidate controls and truthful counts

The default remains one best model match plus the candidate count. Revealing or
hiding already-found alternatives is immediate and separate from requesting
a wider search. Hiding during a search is respected when results arrive; failed
searches retain previous results and offer retry. Wider results are cached only
for the current screenshot and can change the top-ranked suggestion.

The compact search requests five hypotheses and keeps up to four distinct
results; a wider search requests twelve. Counts mean distinct model suggestions,
not dictionary senses or probabilities. No language-specific morphological
filters conceal alternate forms, numbers or low-ranked model rubbish.

## 13. Everyday operation and maintenance

- The main button toggles between 'Start listening' and 'Pause listening'.
  'Capture hotkey' shows the registered shortcut and is locked until paused;
  there is no duplicate status/pause row. Pausing unregisters the hotkey without
  quitting. Lens never injects Escape or pauses another app.
- A per-user OS-owned file lock and local IPC enforce a single app instance and
  let a second launch request reopening Settings. No PID-killing liveness probe.
- Model tasks can be cancelled. ZIP paths/links are validated and installation
  is staged before publication. Repair retains working packages until validated
  replacements are ready. Journals restore backups after an interrupted rename
  on the next model operation. Management rejects links/junctions; cleanup is
  restricted to owned staging folders. Broken journals remain for diagnosis.
- Removal moves route packages into recoverable sibling backups. Shared pivot
  effects are confirmed before repair/removal. Backups are not auto-deleted;
  removing a model does not reclaim backup disk space.
- Capture and model/voice maintenance cannot overlap; unavailable capture has
  visible feedback. Maintenance buttons recover after cancellation/failure.
- The review's speed slider applies to samples, words and sentences. Left/right arrow keys browse
  source occurrences (including repeated words) and pins their popup; Tab reaches
  buttons. Existing Escape/focus restoration behavior remains best-effort.
- New maintenance/listening controls have near-instant, detailed help.

## Verification and support matrix

Tested host: Windows 10 Pro 22H2 x64 (10.0.19045), Python 3.10.6. Installed test
runtimes: PySide6 6.11.2, RapidOCR 3.9.2, ONNX Runtime 1.23.2, Argos 1.11.0,
Stanza 1.10.1, MiniSBD 0.9.5, CTranslate2 4.8.2, Piper 1.8.0,
pyopenjtalk-plus 0.4.1.post9 and filelock 4.0.9.

- Full regression result after the UI wording/listening-control follow-up:
  **519 passed, 22 skipped in 54.81 seconds**, exit 0.
  Skips are optional audio fixtures unavailable in the older prototype fixture
  location; the separate 26-voice real synthesis check passed. A final English,
  Japanese and Mandarin worker rerun also passed after diagnostic changes.
- Source/script compilation passed, and `git diff --check` reported no
  whitespace errors. No commit was made.
- Voice smoke check: 26/26 passed verified normal + 0.75× synthesis, without
  downloading test voices into the user's application voice directory.
- Offline integration: Portuguese→English, Dutch→English, Portuguese→Dutch
  through English all passed preparation followed by fresh-process OCR,
  sentence/word translation and wider search with networking disabled. An
  inherited cloud-provider setting was deliberately supplied and overridden.
- Actual Qt review/supervisor integration passed OCR → translation → retry the
  same screenshot → wider search, using isolated test configuration/model copies.
- Synthetic offscreen previews checked settings at 1920×1080 and 640×480 and
  review at 1280×720 and 640×480, including long text/popups. These are not a
  live multi-monitor/game or audio-device listening validation.
- Focused tests cover malformed settings, atomic-write failure, worker timeout/
  cancellation/reentrant completion, independent word recovery, stale status,
  interrupted/failed model replacement, journal/path validation, recoverable
  removal, reselect/session preservation, long layout, and candidate controls.

Windows 11 is intended but untested here; Python 3.11/3.12 are allowed but not
exercised on this host. Windows 7/8/Vista, native ARM64 and non-Windows desktop
operation remain unsupported. Do not mistake 26 successful voice samples for
all possible translation pairs or comprehensive cross-language OCR/phonetic
accuracy testing. Upstream runtime changes still require regression checks.

To use the update, close the old tray instance and reopen **Start Language
Lens.bat**. Choose the pair and run 'Download required files'; download a voice
only if audio is wanted. Ignored development model copies are not user installs.

## Remaining intentional limitations

UI wording follow-up: the setup/check control is now 'Download required files'
or 'Check required files', optional replacement is 'Reinstall translation model',
and an installed voice offers 'Check voice files'. These controls do not imply
online translation or a detected fault. Named controls in help/status/error prose
are single-quoted; their own button labels remain unquoted.

The duplicate listening-status/pause row has also been removed. The main button
switches to 'Pause listening' while registered, remains usable during model work,
and returns to 'Start listening' after pausing. Pause first to edit 'Capture hotkey'
so that the row cannot display a shortcut different from the one actually active.

The duplicate translation-only download button has been removed. 'Download required
files' is the single setup action for a selected pair, covering missing translation,
OCR and sentence-boundary assets and the fixed-sample check. Voice downloads remain
separate and optional; replacement/removal controls remain optional maintenance.

Capture readiness follow-up: both OCR/supporting files and the translation route
must be verified before capture or hotkey registration. Settings and tray capture
are disabled until then, and every capture entry rechecks the preparation marker.
Changing pairs or starting model work unregisters an active hotkey; readiness does
not silently re-enable listening. Completing an unchanged screenshot does not
invalidate readiness or interrupt the registered listener. Pronunciation speed
has moved from Settings to a remembered slider below the review buttons. Plain
left/right arrow keys browse words except while the slider has focus.

Capture shortcut follow-up: new settings default to F8, existing valid shortcuts
are preserved, and the preset list is replaced by a single-chord recorder with
'Reset to F8'. Valid edits are persisted immediately without applying other
pending settings. Validation is shared by Settings and the Windows listener;
unsupported/reserved input disables listening with an explanation. Invalid
input never overwrites the last valid saved shortcut. Pause before editing.

No new cloud service, calibrated sense probabilities, complete dictionary,
source-text editor, game pause mechanism, packaged executable, full native-speaker
pronunciation review or distribution-licence approval was introduced. The current
stack remains appropriate for this local screenshot-learning workflow; these
changes improve reliability and coverage without changing it to an online or
LLM-based system. Word-in-isolation ambiguity and imperfect OCR/contextual
pronunciation remain visible limitations, not silently “corrected” output.
