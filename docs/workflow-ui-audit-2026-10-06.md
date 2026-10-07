# Workflow and UI/UX audit — 6 October 2026

## Outcome and scope

The core interaction remains appropriate: freeze a screenshot, select text, read
the whole-selection translation, inspect words, optionally listen, and return.
The findings below do not call for replacing that workflow or its frameworks.
The main weaknesses are inconsistent action availability, crowded layouts,
preference persistence, and recovery messages.

No application source, configuration, installed models, or voices were changed
for this audit. Existing working-tree changes were preserved. Files excluded by
`.gitignore` were not audited as application source. The existing environment
was used to execute checks; synthetic diagnostic scripts and rendered previews
were placed under ignored `artifacts/`.

Verification performed:

- Full existing test suite: **599 passed, 22 skipped**, in 48.65 seconds. The
  skipped checks are optional audio fixtures; this is not a fresh listening
  assessment of every voice.
- Source-path review from batch launch through setup, readiness checks, downloads,
  tray/hotkey actions, selection, OCR, translation, candidates, pronunciation,
  retries, return, persistence, and shutdown.
- Offscreen Qt interaction probes with service boundaries mocked: these exercise
  actual widget/controller logic without downloading files, changing user settings,
  registering global shortcuts, or capturing the user's desktop.
- Synthetic settings and review renders, including constrained logical desktop
  sizes. Windows Segoe UI fonts were explicitly loaded for layout checks.

Evidence labels below distinguish **reproduced** behavior, **code-confirmed**
paths, and **native verification needed**. Offscreen results do not certify
Windows focus behavior, screen readers, fullscreen games, or physical mixed-DPI
monitor behavior.

## Findings

### 1. Review controls can obstruct the selected words — P2, reproduced

When neither the above-selection nor below-selection position fits, the panel
is clamped into the screen and overlaps the selection. The panel cannot be
dragged or temporarily hidden as a whole. Raising word popups above it does not
help when the panel prevents the user from hovering over the underlying words.

In a synthetic 1280×720 review with a 900×280 selection, the panel covered
**51% of the selected rectangle**. On a 640×360 logical desktop, it covered the
entire 100-pixel-high selection in the tested layout. These are geometry results,
not claims about the percentage of words obscured in every screenshot.

Recommendation: keep the current preferred anchoring, but add a movable panel
and a compact/temporarily-hidden-controls mode with an obvious recovery handle
or shortcut. Ensure the close action remains reachable. Adapt the button grid
at narrow widths. Hiding only the translated sentence is not enough because
the remaining controls can still overlap text.

Evidence: `src/language_lens/ui/review.py:1085–1126`, especially the fallback
clamp at line 1113; fixed three-column action layout at lines 734–737.

### 2. Capture/download availability is not coordinated consistently — P2, reproduced

Three parts of the same state-management problem were reproduced:

- During a capture, the settings capture button is disabled, but tray
  'Capture now' stays enabled and clicking it silently returns.
- During a voice download, 'Try a capture now', 'Start listening', and tray
  'Capture now' can remain enabled. The actual capture path then rejects the
  operation with a modal message. An already-registered hotkey stays active.
- During review, 'Check voice files'/'Download voice' can still start a voice
  maintenance job if Settings is accessible, for example on another monitor.
  Only the reverse order—download first, capture second—is guarded.

The voice worker publishes files atomically, so this is not evidence of file
corruption. It nevertheless contradicts the app's stated mutual-exclusion
rule and presents actions as available when they cannot proceed.

Recommendation: derive availability from a single shared state covering
verification, capture, translation maintenance, voice maintenance, and shutdown.
Apply it to all buttons, tray actions, and hotkey dispatch. Explain temporary
unavailability without forcing the user to click a misleading enabled action.
Keep cancellation and 'Pause listening' available when appropriate.

Evidence: `src/language_lens/app.py:239–278,396–402`;
`src/language_lens/ui/setup.py:681–692,719–728`;
`src/language_lens/ui/pronunciation.py:161–216`.

### 3. Custom capture keys can conflict with Lens's own controls — P2, native verification needed

The validator explicitly accepts bare Escape, Left, Right, Enter, and Tab.
The global registration stays active during selection/review, where Escape
and arrows are supposed to perform local actions. The hotkey callback instead
enters `begin_capture`, which returns immediately while a capture is busy.

Acceptance and continued registration are code-confirmed. The resulting native
keyboard-routing conflict is a risk inferred from this code and Windows's
[RegisterHotKey behavior](https://learn.microsoft.com/en-in/windows/win32/api/winuser/nf-winuser-registerhotkey):
matching input is delivered as `WM_HOTKEY` to the registered thread. I did not
register or inject these keys on the user's desktop during this audit.

Recommendation: preserve the user's configured shortcut but temporarily suspend
its global registration while Lens owns selection/review input, restoring it
safely afterward. Account for registration conflicts on restoration and keep
the displayed listening state honest. Alternatively, explicitly disallow bare
keys required by the UI, with a clear explanation; suspension is less restrictive.

Evidence: `src/language_lens/services/hotkey.py:22–69,139–167`;
`src/language_lens/app.py:252–255,346–380`;
`src/language_lens/ui/selection.py:113–119`;
`src/language_lens/ui/review.py:777–782,1132–1136`.

### 4. Settings persistence depends on how the session ends — P2, reproduced

Hotkeys, review speed, and window dimensions have immediate/debounced save
paths. Languages, capture scope, voice choice, and the audio/IPA switches are
saved when the user starts listening, captures, or explicitly chooses tray
'Quit'. Closing/hiding Settings does not save those values, and the general
shutdown path does not save them either.

The probe changed IPA and capture scope, hid the window, then invoked shutdown:
**zero persistence calls** occurred, and the controller still held the old IPA
value. Hiding and reopening Settings in the same running process retains the
values; the problem is durability when that process ends without one of the
save-triggering actions, including shutdown or a forced exit.

Recommendation: debounce-save valid preference changes, while separating saved
preferences from the immutable settings used by a current capture. Flush pending
saves on close/shutdown. Briefly explain that closing Settings leaves Lens in
the tray, ideally on the first close only.

Evidence: `src/language_lens/app.py:190–201,205–207,265–266,382–394,416–430`;
`src/language_lens/ui/setup.py:442–447`.

### 5. Automatic sizing can scroll unnecessarily — P2, reproduced

The fitter chooses a preferred width and then caps the height. It does not
try a wider width when wrapping makes the content taller than the desktop.
Consequently it can add a scrollbar despite sufficient horizontal space.

On a synthetic 1920×1080 available area, fresh Japanese→English settings
opened at **610×1076**, with **29 pixels of vertical overflow** and no saved
manual size. Widening the same window to **850×1076** removed the overflow.
That contradicts the requested default behavior of fitting everything before
resorting to scrolling.

Recommendation: when content exceeds available height, search for a wider
fitting width within the desktop before enabling scrolling. Preserve explicitly
remembered manual sizes. An optional 'Fit to contents' action would help users
return from a previously saved small size.

Evidence: `src/language_lens/ui/setup.py:318–358,376–401`.

### 6. Some failures are indistinguishable from missing files — P2, reproduced/code-confirmed

Model inspection catches every exception and reports `ready=False` with an
empty route. The UI then says the translation model is not installed. A
synthetic access failure reproduced exactly that result, even though the check
had failed rather than established that a model was absent.

Other worker failures are reduced to an exception class plus advice to use
'Download required files'/'Check required files'. That does not distinguish
network failure, unavailable model route, insufficient disk space, denied access,
or a model execution failure. Repeating the suggested action can produce the
same failure without teaching the user what needs changing.

Recommendation: return structured, privacy-safe error categories and stages.
Distinguish 'not installed' from 'could not check'. Give a relevant next action,
and an 'Open diagnostics folder' option for unresolved errors. Preserve the
existing restriction against putting captured text in diagnostic messages/logs;
do not simply expose arbitrary exception strings.

Evidence: `src/language_lens/services/task_worker.py:23–35,107–112`;
`src/language_lens/ui/setup.py:477–505`;
`src/language_lens/services/diagnostics.py:15–23`.

### 7. Launcher recovery has gaps — P2, code-confirmed

The batch launcher detects missing environment executables and requests setup,
but `setup.ps1` only creates an environment when the **directory itself** is
absent. An incomplete `.venv` directory without its Python executable therefore
enters the setup path and fails again instead of being repaired.

Setup also selects whichever `python` is on PATH without first checking its
supported version/architecture. Finally, successful `Start-Process` means a
process was launched, not that the UI initialized; early failures before the
app's own startup handling can leave the user without a useful launcher error.

Recommendation: preflight a compatible Python, validate the environment beyond
directory existence, and offer recoverable rebuilding of the exact project
environment when necessary. Add a short startup-success handshake and retain
sanitized startup diagnostics. The simple batch launcher can remain; this does
not require returning to executable packaging.

Evidence: `Start Language Lens.bat:16–41`; `scripts/setup.ps1:5–14`;
`scripts/run.ps1:9–10`; `src/language_lens/app.py:434–459`.

### 8. Mouse selection and arrow navigation disagree — P3, reproduced

Clicking a word pins its popup but does not update the review's keyboard index.
For 'Read and learn a language', pinning 'learn' and pressing Right selected
'Read', not 'a'. After earlier keyboard navigation, the jump can instead start
from a stale keyboard position.

Recommendation: use one current-word occurrence index for both mouse and
keyboard selection, including repeated words and movement between monitors.

Evidence: `src/language_lens/ui/review.py:590–603,843–857`.

### 9. Retrying OCR leaves stale enabled audio controls — P3, reproduced

OCR retry shuts down speech, then clears the recognized text, but does not
refresh audio availability after clearing it. With a ready voice, the probe
found 'Read selection' and the speed slider still enabled while the source
text was empty. 'Read selection' then does nothing. An OCR failure can leave
that misleading state until another successful scan or closing the review.

Recommendation: reset dependent controls after clearing OCR results and keep
them synchronized for pending, empty, failed, and completed scans. Disable
'Hide translation' while there is no translation to hide, too.

Evidence: `src/language_lens/ui/review.py:785–805,959–987,1155–1158`.

### 10. Progress feedback is uneven — P3, usability improvement

Translation/OCR asset downloads have byte counts, speed, elapsed time, and
waiting-for-data feedback. Voice downloads expose percentage/bytes but no
transfer speed or stalled-transfer display. A stalled voice transfer can sit
unchanged until the worker timeout reports failure.

Similarly, selection translation streams individual results, but the main
status normally remains the OCR 'Found N words' message rather than showing
how many word lookups are still pending. Hovering an unfinished word does show
'Translating…', so this is incomplete feedback, not a completely silent task.

Recommendation: reuse the download-metrics presentation for voices, and show
simple completed/pending counts during word translation. Distinguish downloading,
checking, preparing audio, and playing; avoid displaying 100% as overall task
completion while verification remains.

Evidence: `src/language_lens/ui/pronunciation.py:223–227`;
`src/language_lens/services/speech.py:97–114`;
`src/language_lens/services/translation.py:25–44`;
`src/language_lens/ui/review.py:893–924`.

### 11. Routine use competes with maintenance detail — P3, usability improvement

Reinstall/remove actions occupy permanent rows, including when unusable.
Technical segmentation/notation descriptions consume space before pronunciation
settings. This increases scrolling and makes routine setup look more complicated
than it needs to be. The existing tooltips are useful; they need not be removed.

Recommendation: put optional maintenance actions behind a clearly named
'Manage local files' expander. Keep the selected language pair, a plain-language
'Ready to capture' / specific not-ready reason, and the next necessary action
prominent. Put detailed route/segmentation/notation information in an expandable
details section. Retain important IPA/voice caveats at their point of use.

Also fix small documentation drift: README line 57 still describes five speed
presets instead of the current slider; line 47 describes wider search as appearing
after expanding candidates, although it is already directly available. Several
runtime messages still mention `Start Language Lens.bat` without the consistently
requested quoting. These are copy corrections, not reasons to change the user's
chosen controls or terminology again.

Evidence: `src/language_lens/ui/setup.py:203–223,269–282,498–505`;
`README.md:47,57`; `src/language_lens/ui/review.py:966`;
`src/language_lens/app.py:454`.

### 12. Recognized-text inspection and accessibility remain partial — P3, feature opportunity

Users can copy the OCR source and inspect individual popup words, but there is
no selectable recognized-text view alongside the translation. It is harder
than necessary to tell whether an odd result came from OCR or translation,
especially when geometry is approximate. Whole-selection translation is not
configured as selectable text either.

The initial region selection requires pointer dragging; the screenshot and word
outlines are custom painted, rather than an accessible list of recognized words.
Arrow navigation after OCR is useful, but it does not make the entire workflow
keyboard- or screen-reader-accessible. No native screen-reader test was performed.

Recommendation: first add an optional read-only, selectable 'Recognized text'
view and copying of the whole translation, without introducing OCR editing or
changing span alignment. An accessible word list and keyboard-adjustable selection
would be the next accessibility step. Treat full OCR editing as a separate project,
not a prerequisite for these smaller improvements.

Evidence: `src/language_lens/ui/selection.py:96–119`;
`src/language_lens/ui/review.py:552–588,690–697,832–834`;
`src/language_lens/ui/word_popup.py:69–74`.

## What should stay

- The offline-first, screenshot-based interaction and native-resolution capture.
- One visible best word candidate by default, with explicitly requested
  alternatives/wider search and no invented probabilities or language-specific
  stemming rules.
- The whole-selection translation alongside isolated-word candidates.
- Optional pronunciation/IPA, transparent notation limitations, and the persistent
  accent explanation when IPA is enabled.
- The review speed slider, its stable label space, and remembered speed.
- Retry/reselection on the same screenshot, isolated workers, cancel/timeout paths,
  and separate source/target direction readiness.
- The batch launcher and near-instant explanatory tooltips. Neither needs a
  fundamental redesign to address the findings.

## Remaining native acceptance checks

These are validation gaps, not assertions that the features are broken:

1. Windows 10 and 11 live capture: tray menu dismissal, correct screenshot timing,
   and correct return-focus target. Tray capture currently enters the immediate
   external-capture branch; unlike 'Try a capture now', it has no explicit delay.
   Verify whether the menu has fully disappeared before the actual capture.
2. Escape/arrow/modified-key hotkeys during both selection and review, including
   registration conflicts after restoration and different keyboard layouts.
3. Physical mixed-DPI monitors, monitor disconnect/reconnect, display changes
   during review, and fullscreen/borderless apps. Synthetic geometry tests do
   not substitute for those combinations.
4. Narrator/NVDA announcements, focus order and visible focus, plus Windows text
   scaling/high-contrast mode. Offscreen styled previews cannot establish native
   accessibility support.
5. Clean-machine first launch, an incomplete environment, unsupported Python,
   offline first launch versus already-prepared offline use, low disk space,
   unavailable download hosts, and cancellation around verification/installation.

Recommended implementation order: fix **1–7**, then the small interaction fixes
**8–9**. The presentation/features in **10–12** can follow without delaying those
correctness fixes. None of these changes has been implemented by this audit.

Subsequent implementation of points 1–7 is documented in
[workflow-ui-fixes-2026-10-06.md](workflow-ui-fixes-2026-10-06.md).
