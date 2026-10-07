# Historical checkpoint — 5 October 2026

The user requested a pause so they could shut down their PC. This records the
state at that pause, not the current to-do list. Work resumed on 6 October;
the completed changes, verification and remaining limits are documented in
[audit-followup.md](audit-followup.md). No commit was made.

## Verified so far

- The native Qt crash occurred in a test that replaced the application-wide
  style while earlier widgets were retained. That test now runs in an isolated
  process matching startup, and fixtures dispose native widgets. Subsequent
  regression runs have completed without the reported native crash. Native
  failures still fail tests; Windows error dialogs are suppressed in tests and
  disposable workers so they cannot block recovery.
- The pinned voice catalogue now covers all 25 language choices (26 voices,
  including UK/US English). Japanese uses OpenJTalk, not eSpeak Japanese.
- `scripts/verify-voices.py --all` passed actual normal-speed and 0.75× synthesis
  for every one of the 26 voices, including model/config/card SHA-256 checks.
  Test models are in ignored `artifacts/voice-validation`, not bundled or
  automatically installed into the user's app voice directory.
- IPA formatting remains audited for the original English/Portuguese accents.
  Other languages preserve and label engine notation; Japanese word readings
  explicitly use isolated fallback rather than claiming contextual alignment.

## Implemented, still needing final integration review

7. Explicit offline preparation (OCR assets, installed translation route,
   auxiliary sentence models, network-disabled verification). Capture task
   workers block networking. Argos provider is forced local, regardless of
   inherited settings. Preparation markers invalidate changed files.
8. OCR/translation moved to bounded, cancellable QProcess workers; sentence and
   word errors are independent. Settings types validated; writes atomic;
   startup/save errors handled; diagnostics omit exception messages and text.
9. Settings capability summary separates offline check, translation route,
   segmentation, voice and notation limitations.
10. Frozen screenshot supports Retry OCR, Select another area, Retry translation
    and Copy source text. In-place source editing has not been added.
11. Whole-selection content scrolls and can collapse; review controls remain
    outside the scrollable content.
12. Separate immediate show/hide alternatives from wider search; counts are
    model suggestions, not senses/probabilities.
13. Hotkey state/pending-change display and pause; per-user single-instance
    reopen; cancellable model tasks, staged installs, repair, recoverable model
    removal with shared-route warning; capture/install exclusion; pronunciation
    speed and Alt+Left/Right word navigation.

## Next work on resume

1. Record the final checkpoint pytest result in this note if not already below.
2. Exercise **real offline preparation and fresh-process OCR/translation** using
   isolated test configuration/model copies. Existing installed Argos models:
   `C:/Users/Fillask/.local/share/argos-translate/packages` includes en↔nl,
   en↔pt and en→pb. Do not alter the user's model installs as a test fixture.
   Offline Stanza must load with `DownloadMethod.NONE`; clear both Argos's
   installed-language LRU and `installed_translates` before verification to
   prevent cached hypotheses from concealing missing resources.
3. Check process lifecycle/stale results, cancellation during model publication,
   remaining staged folders after hard kill, repair rollback, shared pivot
   removal, readonly/disconnected storage, single-instance races, and all
   retry/reselect/focus paths. Model replacement currently keeps recoverable
   backups; interrupted publication needs particular attention.
4. Review preparation marker identity against library/model version changes and
   asset integrity; marker stat checks alone are not hash verification. OCR
   files are hashed again before worker loading.
5. Inspect UI visually on Windows (large/small desktop, long translations,
   settings resizing, pronunciation status, help, keyboard interaction).
   Settings model status still imports Argos synchronously; consider a
   lightweight/off-thread status path. Make model/voice conflict feedback clear.
6. Remove unused legacy install-task/thread plumbing and avoid duplicated OCR
   or translation behavior between unit helpers and production workers.
7. Update README, THIRD_PARTY_SPEECH and IPA documentation for all voices,
   noncommercial/unknown licence warnings, new workflow/recovery controls,
   explicit downloads, privacy, process limits and current support matrix.
   Voice feasibility is not a native-speaker quality or redistribution review.
   Windows 11/other Python versions have not been exercised on this host.
8. Repeat full tests, inspect diff, and deliver the requested point-by-point
   changes with any limitations clearly identified. Do not commit unless asked.

## Last results before the final checkpoint run

- Voice verification: 26/26 passed normal + slower real synthesis.
- Targeted settings/new-audit tests: 52 passed, one installer-validation test
  failed; the metadata/model preflight was then fixed before rerunning.
- Targeted previous regression run: 198 passed, 22 skipped, one settings-width
  test failed; scrollbar-width reservation was subsequently fixed.
- Full checkpoint regression result: **500 passed, 22 skipped in 43.55s**, exit 0.
  The skipped optional audio-fixture tests do not use the new validation asset
  directory; the separate all-voices real synthesis check passed for all 26.
