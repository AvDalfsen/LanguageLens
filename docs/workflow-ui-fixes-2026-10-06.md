# Workflow/UI audit points 1–12 — implementation follow-up

Follow-up to [the 6 October workflow/UI audit](workflow-ui-audit-2026-10-06.md).
Its findings describe the pre-fix state. Existing working-tree changes were
preserved; no commit, executable package, or public release was created.
Point 12 covers the approved first pass only: read-only inspection and basic
focus/accessibility improvements, not a full accessible-capture redesign.

## Changes

1. **Review obstruction (simplified after user feedback):** removed the added
   'Move'/'Hide controls'/'Show controls' toolbar, duplicate close buttons,
   automatic folding and Ctrl+H toggle. The existing panel stays visible and
   can be dragged by its background/non-selectable text, without interfering
   with buttons, sliders or scrollbars. It retains one existing close button
   outside scrolling actions. Measured action-button reflow, separate content/
   action scrolling and narrow monitor viewport sizing remain. Manual placement
   lasts for the current screenshot; new captures anchor to their selection.

2. **Action availability:** one shared state covers verified assets, capture,
   translation maintenance, voice maintenance, shutdown, and shortcut validity.
   Settings buttons, tray actions, hotkey registration and capture dispatch use
   it. Capture cannot start during file maintenance, nor can maintenance start
   during capture/review. Voice cancellation and pausing requested listening
   remain available. A voice download temporarily suspends, then restores a
   requested listener when asset readiness has not been invalidated.

3. **Custom shortcut conflicts:** global registration is suspended before
   selection/review and while Settings is visible, including reselection. It
   restores after returning to the external application unless the user paused
   or readiness was lost. Restore conflicts clear the requested listener and
   explain how to retry. Tray status distinguishes temporary suspension from
   an active registration. The listener creates its Windows message queue
   before publishing readiness, making immediate stop/restart reliable.

4. **Persistence:** language, capture scope, voice, audio/IPA and other valid
   preferences autosave after 300 ms; hide and shutdown flush pending changes.
   A separate deep-copied settings snapshot is passed to the active capture.
   Review-speed changes save through the current Settings preferences rather
   than replacing newer choices with the capture snapshot. The first close
   explains close-to-tray behavior, and remembers that notice.

5. **Settings sizing:** automatically measures wider candidate layouts before
   enabling scrolling when vertical space is exhausted. Desktop limits and
   explicit remembered/manual sizes still take precedence. No extra manual
   'Fit to contents' action was needed for this fix.

6. **Failures and recovery:** inspection exceptions propagate to the worker
   protocol; the UI shows unknown status with 'Retry file check', not false
   missing-model claims. Privacy-safe categories distinguish network, timeout,
   disk, access, missing/damaged assets, unavailable routes, runtime and generic
   task/inspection failures. Download retries preserve their causal exception
   for categorization. Diagnostic-folder actions are offered on Settings and
   review failures. Captured text and arbitrary exception messages are not
   exposed by categorization or diagnostic logging.

7. **Launcher recovery:** the batch file delegates to a PowerShell launcher
   that checks Windows x64 Python 3.10–3.12 and package/frontend health. Setup
   checks health rather than directory existence. It locates a compatible
   interpreter before moving an incomplete/unhealthy environment to a unique,
   recoverable project-local backup; linked environment directories are refused.
   No existing environment is recursively deleted. Atomic, uniquely named
   startup reporting distinguishes initialized UI/reopened instance, early exit,
   reported error and timeout. Only the launcher's own unready child is stopped
   on failure. Pre-Qt import failures retain sanitized startup diagnostics.

8. **Mouse/keyboard word position:** clicking a word updates the same current
   occurrence used by arrow navigation. Matching uses source-text spans, not
   spelling or object equality, so repeated words and translated hit copies
   remain distinct. A click on another monitor dismisses the previous monitor's
   popup; arrows continue in reading order across monitors. Passive hovering
   does not move this explicit navigation position. OCR retry resets it.
   Clicking a word also focuses its popup, so a previously focused pronunciation
   speed slider no longer consumes subsequent arrow keys.

9. **OCR retry readiness:** recognized source text and the active word are
   cleared before speech shutdown emits playback-state changes. Audio buttons
   and the speed slider immediately refresh to their disabled state; prepared
   pronunciation and word popups are cleared. Failed/empty retries leave audio
   disabled, while new recognized text restores it when the voice is available.
   'Hide translation'/'Show translation' is also disabled while no translation
   content exists, without discarding the user's hidden/visible preference.

10. **Progress feedback:** model and voice transfers share smoothed speed,
    byte/percentage, elapsed/estimated remaining time and waiting-for-data
    formatting. Voice workers report separate checking/downloading/verifying
    phases; checked cached bytes do not count as transferred bytes in the speed
    calculation, and verification does not show a completed download as readiness.
    Cancellation stops the metrics timer. Review status reports completed/pending
    unique word lookups, retains keyboard instructions and identifies failed
    lookups/whole-selection translation without counting them as successful.

11. **Routine setup versus maintenance:** 'Manage local files' contains optional
    checks/reinstall/removal, and 'Technical details' contains route/segmentation/
    notation explanations. Readiness and any needed download/retry action remain
    prominent. Model progress, diagnostic actions and cancellation remain outside
    disclosures. Reparented check buttons retain visual Tab order. Pronunciation
    controls, licence information and the persistent IPA accent explanation are
    retained. README now describes the speed slider and directly available wider
    candidate search; the remaining unquoted launcher message is corrected.

12. **Read-only inspection and basic accessibility:** the review's collapsed
    'Recognized text' section precedes the translation so it stays discoverable
    even with a long translation. Both text views support mouse/keyboard selection
    and 'Copy selection'/'Copy all' context actions, copying exact plain text rather
    than presentation HTML. Retry clears both views/copy sources; no source edits
    or alignment changes are introduced. Settings fields, screenshot, popup words/
    IPA and progress have descriptive names; disclosures work with the keyboard,
    focus order follows visual order, and focus has visible styling. No native
    Narrator/NVDA validation or fully accessible word list/region selector is
    claimed; those remain a separate accessibility project.

## Verification

- Regression tests use actual Qt widgets/controllers with capture, persistence,
  downloads, and voice-job boundaries mocked. They exercise state transitions,
  shortcut suspension/restoration/conflicts, Escape cancellation, reselection,
  autosave/close/shutdown, immutable capture preferences, background dragging,
  bounds, small-screen reflow, wider Settings fitting, inspection retry, and
  exception classification without text leaks. Added click-to-arrow regression
  cases cover both directions, wraparound, repeated words, translated hit copies
  and secondary monitors. OCR retry cases cover idle/generating/playing audio,
  immediate control disabling, failed/empty results and successful recovery.
- PowerShell tests execute environment preflight, a recoverable backup of a
  disposable incomplete environment, preflight failure before moving anything,
  and mocked startup acknowledgement/error/early-exit/timeout scenarios. No
  dependencies or models are downloaded by these tests.
- The real existing environment passes the new health check. All PowerShell
  scripts parse without errors. The user's environment was not rebuilt.
- A native Windows test registers an uncommon Ctrl+Shift+F23 shortcut and
  repeatedly stops/restarts it without injecting input, leaving no live thread.
- Synthetic offscreen rendered previews were inspected at normal and constrained
  sizes, including 640×360 and 320×480 review layouts. Outputs remain under
  ignored `artifacts/ui-review/`.

Verification after points 8 and 9: **647 passed, 22 skipped in 121.71 seconds**.
The skipped checks are the existing optional audio fixtures, not new failures.
After that run, explicit popup focus on word clicks was added and checked with
the focused Qt navigation/review tests. `git diff --check` is clean. PowerShell
scripts were unchanged by these two points; their earlier parsing checks remain
applicable.

Final verification after points 10–12: **655 passed, 22 skipped in 132.32
seconds**. The new cases cover voice phases, cached-file speed accounting,
stalled transfers, cancellation/timer cleanup, shared metrics, optional
maintenance visibility, unique lookup/failure counts, exact plain-text copying,
retry clearing and visual keyboard focus order. Focused speech/UI checks also
passed (165 passed, 22 optional fixtures skipped). Re-rendered normal and small
settings/review layouts were inspected after the source-disclosure placement
change. `git diff --check` remains clean. No user settings, actual desktop capture
or model downloads were needed for this follow-up's verification.

## Remaining acceptance limits

Offscreen tests and native registration lifecycle checks do not establish actual
Escape/arrow key routing across other applications, Windows return-focus rules,
Windows 11 behavior, physical mixed-DPI/hot-plug monitors, fullscreen games,
screen readers, or every Windows text-scaling configuration. A clean-machine
network installation and real low-disk/access-denied recovery have not been
performed; failure categories and disposable recovery paths were tested instead.
These checks remain as listed in the audit. No universal support claim for
Windows 7/8/Vista or older Python versions is introduced.
