# Repairs following the af23d03 audit — 10 October 2026

All four confirmed defects from the [audit of af23d03](full-audit-af23d03-2026-10-10.md)
are repaired locally. The application and prototype suites pass, and a fresh
portable build passes verification using real executables and disposable offline
fixtures. Changes have not been committed, uploaded, or published.

## Repairs

| Finding | Result | Limits |
| --- | --- | --- |
| F1: uninstall deletes unrelated folder contents | Packaging records shipped files in `_internal/uninstall-files.json`. The helper removes those files individually and removes directories only when empty. Unrelated root/nested files and files added after cleanup planning survive. Paths outside the release, traversal, duplicate entries, and links/reparse points are refused. | Missing or invalid inventories fail closed. Older releases need a fresh complete bundle to use the new uninstaller; it does not automatically identify and remove old application files. App data and explicitly confirmed shared Argos data remain separate cleanup targets. |
| F2: malformed model metadata traps Settings in retry | Status inspection diagnoses damaged package metadata without moving files. Settings exposes **Move damaged models to backup**, names the affected folders, and asks for confirmation. The offline worker rechecks every candidate under the maintenance lock, then moves it to a recoverable backup beside its package root. Healthy packages remain intact and inspection resumes. | Permission failures and other unknown states retain ordinary retry behavior. Shared pairs may be affected. Backup files remain on disk; this does not repair their contents. |
| F3: launcher accepts incompatible Argos/MiniSBD | Launcher health now uses the adapter's exact version check for Argos 1.11.0 and MiniSBD 0.9.5, alongside its existing import/runtime checks. An incompatible environment is rejected before the launcher decides setup can be skipped. | Version checks do not load models or perform inference. The current compatible environment also passes the real PowerShell health function. |
| F4: missing speech runtime raises `NameError` | Imported the existing recovery helper. English missing-runtime requests enter the error state with actionable advice and launch no worker; Japanese missing-pack requests retain their distinct guidance. | Normal UI readiness checks remain in place. |

The uninstall inventory is generated after freezing and refreshed after the
archive script adds documentation and dependency notices. Full cleanup plans
cross the process boundary as JSON files in the helper's diagnostic directory;
only a small encoded handoff appears on the Windows command line. The regression
suite exercises a large inventory to prevent a command-length failure.

The three new recovery messages have entries for all 25 interface languages.
The user and portable guides describe file preservation and damaged-model recovery.

## Dependency and download hardening

Updated pytest to 9.0.3 in the main development range, Windows constraints,
prototype requirements, and active main environment. This addresses the audit's
pytest advisory. The prototype's engine/model baseline and implementation remain
unchanged. [Upstream patched release](https://github.com/pytest-dev/pytest/releases/tag/9.0.3).

The repeated OSV query covered 101 distinct pinned package/version pairs from
the main Windows constraints, build requirements, and prototype requirements.
Only Stanza 1.10.1 remains flagged; its two returned records describe the same
unsafe-checkpoint-loading concern. This is not a clean dependency scan.

Argos 1.11.0 requires exactly Stanza 1.10.1, so installing the advisory's patched
Stanza 1.12.2 would break the declared dependency contract. Both legacy sentence
comparison entry points now require PyTorch 2.6 or newer, clear an inherited
unsafe-load override, and set `TORCH_FORCE_WEIGHTS_ONLY_LOAD=1` before importing
Stanza. Tests prove an explicit `weights_only=False` call rejects a benign
unsupported serialized object while plain tensor weights still load; no exploit
payload was executed. The real old/new comparison also passes with this guard.
[Stanza advisory](https://github.com/stanfordnlp/stanza/security/advisories/GHSA-v5jw-96jm-7h2c).

This is a mitigation for the repository's comparison tools, not an upgrade or
removal of vulnerable Stanza code from the source environment. Normal Lens
inference uses the MiniSBD adapter without importing Stanza/Torch, and executable
verification confirms their code is absent from the portable runtime. A complete
dependency resolution still requires an Argos release supporting patched Stanza
or a separately validated replacement for that dependency contract.

Argos model archive downloads now require HTTPS. The redirect handler rejects
HTTP downgrades before contacting the redirected destination; HTTPS mirrors and
existing retries remain supported. The dynamically fetched Argos index and
package provenance are not authenticated by this change. Pinned asset integrity
checks elsewhere in the app are unchanged.

## Verification

Validated on this Windows x64 development host with Python 3.10.6. Test logs and
generated binaries are local ignored artifacts; they are not committed fixtures.

| Check | Result |
| --- | --- |
| Complete application suite | **1,067 passed** in 178.99 seconds; no skips. Includes 27 new audit regression cases. |
| Independent pronunciation prototype | **32 passed** in 6.43 seconds using pytest 9.0.3. |
| Dependency compatibility | `pip check`: no broken requirements. Real launcher environment health: true. |
| Damaged-metadata source worker | Diagnoses malformed/missing metadata, preserves damaged bytes in backup, keeps healthy metadata unchanged, resumes status inspection, and refuses stale/outside selections before moving any candidate. |
| Windows uninstall helper | Preserves unrelated and late-added files, removes an empty dedicated release, refuses unsafe inventory paths and recursive overlap, and handles a full inventory within Windows command-line limits. |
| Legacy sentence comparison | 38 cases across 25 languages; 15 translation comparisons with no changes. Existing three intended-boundary misses remain; the recorded MiniSBD baseline passes. |
| Recovery interface | 50 rendered views across 25 locales at 960×1000 and 640×480; no potential clipped buttons detected. English and Arabic previews also inspected visually. Small windows scroll. |
| Fresh portable build | Successful freeze and archive with a matching inventory of **1,621 files**. ZIP CRC checks, duplicate-name checks, inventory coverage, and SHA-256 checks pass. |
| Actual executable verification | Passes bundled task/speech dispatch, scratch cleanup, offline OCR, direct/pivot translation, word candidates/wider search, 38 sentence baselines, Japanese/Chinese packs, English/Japanese synthesis, core operation after pack removal, selective uninstall, damaged-model backup/recovery, GUI startup, and single-instance behavior. |

The final portable folder is 463.8 MiB and its local preview ZIP is 205.1 MiB.
OCR, translation, sentence models, voices, and optional packs remain separate
downloads. The test copied existing fixtures; it did not remove or quarantine
the user's installed models. Only the GUI process tree started by the verifier
was stopped during its cleanup.

## Remaining limits

The upstream Stanza advisory remains in the source dependency snapshot with the
mitigation above. The word backend still produces isolated candidates, and the
audit's contextual-sense corpus remains at 6/12. The three Arabic/Chinese/Japanese
sentence-boundary misses are unchanged. New translations, existing interface
wording, IPA, and voices still need native-speaker review.

Clean-machine Windows 11 checks, remote Python 3.11/3.12 CI execution, signing,
and the documented redistribution/provenance review remain outstanding. This
local build does not establish public release clearance or model provenance.

## Local evidence and reproduction

- [Application test log](../artifacts/repair-af23d03/pytest-app.log) and [prototype log](../artifacts/repair-af23d03/pytest-prototype.log).
- [Dependency query and results](../artifacts/repair-af23d03/dependency-scan.json).
- [Guarded sentence comparison](../artifacts/repair-af23d03/sentences/comparison.json).
- [Recovery interface report](../artifacts/repair-af23d03/recovery-previews/report.json).
- [Build log](../artifacts/repair-af23d03/release/build.log), [executable verification](../artifacts/repair-af23d03/release/verification-full.json), and [archive checks](../artifacts/repair-af23d03/release/archive-check.json).
- [Local preview ZIP](../artifacts/repair-af23d03/release/LanguageLens-0.1.0-windows-x64-preview.zip) and [checksum](../artifacts/repair-af23d03/release/LanguageLens-0.1.0-windows-x64-preview.zip.sha256).
- [Regression cases](../tests/test_audit_repairs_current.py).

```powershell
.\.venv\Scripts\python.exe -m pytest -q --tb=short
.\.venv\Scripts\python.exe -m pytest prototypes/pronunciation/tests -q -ra
.\.venv\Scripts\python.exe -m pip check
.\.venv\Scripts\python.exe scripts/freeze-release.py --output artifacts/repair-af23d03/release
.\.venv\Scripts\python.exe scripts/release-report.py `
  --bundle artifacts/repair-af23d03/release/dist/LanguageLens `
  --output artifacts/repair-af23d03/release
.\.venv\Scripts\python.exe scripts/verify-release.py `
  --bundle artifacts/repair-af23d03/release/dist/LanguageLens `
  --output artifacts/repair-af23d03/release/verification-full.json `
  --fixtures artifacts/offline-validation --voices artifacts/voice-validation `
  --language-packs artifacts/pack-validation/LanguageLens/language-packs `
  --sentence-models artifacts/sentence-validation/LanguageLens/offline/sentences `
  --sentence-cases tests/data/sentence-boundaries.json
```

The final command uses existing local fixtures and removes only private copies.
In this session the sandbox prevented stopping the test GUI, so executable
verification used the approved process-cleanup permission established during the
audit. No unattended uninstall was run against a real installation.
