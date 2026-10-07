# Workflow/UI points 10–12 — completed checkpoint

User approved points 10, 11 and the first pass of 12 on 6 October 2026.
No commit or release is requested. Preserve all earlier working-tree changes.

## Scope

- 10: shared download metrics for models/voices; explicit checking/downloading/
  verifying phases; translation lookup completion/failure counts.
- 11: collapsed maintenance and technical-details sections; prominent readiness
  and missing-file action; cancellation/progress remain visible; correct copy.
- 12: optional read-only recognized text; selectable/copyable translation;
  accessible names, focus order and visible focus. No OCR editing, accessible
  word-list redesign or keyboard-adjustable capture rectangle in this pass.

## Checkpoint

Initial implementation added in `ui/progress.py`, `ui/sections.py`, Settings,
review, speech worker/supervisor and app focus styling. Shared transfer metrics,
voice phase protocol, disclosures, source inspection/copy menus, lookup counts
and accessible labels/focus order are in place. The fake speech job in tests now
supports the phase signal. Added eight regression tests in `tests/test_ui_finish.py`.
An initial run found five changed expectations/interactions: status wording,
metrics moving to their own label, viewport centre hitting the new disclosure,
and keyboard guidance disappearing while translating. These were corrected;
147 focused checks then passed. A further speech/focus run passed 165 tests,
with 22 existing optional audio fixtures skipped. The last cancellation/timer
edge-case changes passed all eight new tests. README and implementation report
updated. The final full suite passed: **655 passed, 22 skipped in 132.32 seconds**.
`git diff --check` is clean. The approved implementation is complete.
Synthetic settings/review previews were rendered; initial layout inspection moved
the source disclosure above long translations and removed an unnecessary readiness
glyph. Re-rendered source-expanded and missing-model previews were inspected at
1280×720 and 640×360; close/actions remain reachable and required downloads stay
prominent. No user settings, model
downloads or real desktop captures were used.
The latest previous full run (points 8/9) was 647 passed, 22 skipped. Do not
interpret that result as verification of this new work.

## Resume

No implementation work remains within the approved scope. The point-by-point
changes and validation limits are in `workflow-ui-fixes-2026-10-06.md`. Future
work requires a new user request: native Narrator/NVDA acceptance testing, an
accessible word list, and keyboard-adjustable region selection were deliberately
not implemented. The user should fully quit Lens from the tray and relaunch it
to load these changes. No commit or public release was created.
