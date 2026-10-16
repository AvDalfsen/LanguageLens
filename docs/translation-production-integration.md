# Production translation integration

Updated 16 October 2026. The production tool uses the [accepted selections](translation-model-selection.md): Argos by default, 25 whole-text direction exceptions and 6 compact/expanded word direction exceptions. English → Dutch whole text uses bilingual T5 24L int8; its isolated words, the reverse direction, and European Portuguese → English retain Argos. Directional choices are pinned in `src/language_lens/data/translation-providers.json`; inference never reads benchmark directories.

T5 uses the tested revision `54ba749ada76d8443c0d6e0a6039d9dadfdf04a3`, CTranslate2 4.8.2 CPU int8 with two threads, native tokenizers 0.22.2, the publisher's English→Dutch prefix and beam size 4. MiniSBD splits each line; target tokens are decoded together per line, preserving paragraph breaks and the benchmark's unknown-token handling. Input/output bounds fail explicitly rather than truncating silently. PyTorch and Transformers remain build-only. The model needs neither Node nor Bergamot. English→Dutch preparation still includes Argos for independent word suggestions.

The new resources are packaged separately under `translation-en-nl-2026-10-16-v1`, with compressed and decoded checksums. Existing English→Dutch preparation requires a new **Download required files** step. A failed T5 request shows the translation error and retry; it does not silently substitute another model. Technical OCR/translation errors expose their respective retry buttons inline. Normal results retain editing and another-area selection, without retry or alternate-model actions in the menu.

The integrated source worker and Windows portable executable each reproduced **40/40** frozen T5 outputs exactly. The maintainer conversion path independently reproduced every selected model/tokenizer checksum from the pinned publisher files. The actual asset preparation path verified compressed and decoded files using the staged release payloads in an isolated profile. Public hosting must be published and checked before distributing this app build. Portable startup, subprocess dispatch, model recovery, single-instance behavior and uninstall verification passed. Twelve synthetic review states at desktop and narrow widths were rendered and inspected. These checks establish integration parity; the prior quality study retains its stated limits. Evidence is under `artifacts/t5-error-recovery-2026-10-16/`.

The updated source suite passed **1,154 tests**, including contextual retries, partial failures, worker restart, bilingual routing, bounded generation, dependency previews and damaged-package recovery while T5 files are absent. Dependency consistency and Git whitespace checks passed.

The [English→Dutch model-resource prerelease](https://github.com/AvDalfsen/LanguageLens/releases/tag/translation-en-nl-2026-10-16-v1) was published on 16 October. All six public assets were verified anonymously. The production preparation path downloaded and verified all four runtime files into a fresh profile; the portable worker then reproduced the original title offline from those downloaded files. Receipts are `publication.json` and `public-preparation.json` in the integration evidence directory.

## Memory and request lifecycle

**Settings → Manage local files → Keep translation models loaded between captures** defaults off and is translated in all 25 interface languages.

- Off: one translation worker belongs to a capture review. Full text, hovered words and expanded searches share its loaded backends. Closing the review releases the worker and its model memory. The next capture starts fresh.
- On: the active pair's worker survives between captures. Disabling retention, changing the language pair, model maintenance or application exit releases it.

Backends load lazily for the current pair and function. Inference threads sleep between requests. Windows Job Objects own the real worker and its helper processes, including the child behind a source installation's Python venv redirector; a forced stop also releases the process tree. OCR retains its existing separate worker.

The GUI schedules whole-text translation, then requested hovered/expanded words, then speculative word prefetch. It dispatches one inference unit at a time, suppresses cancelled results and bounds its queue, input, protocol output and request deadlines. Each new review retains the existing full-selection translation and isolated-word suggestion behavior.

## Local providers and preparation

Firefox weights run through the official Bergamot WASM package 0.4.9 and pinned Node.js 22.23.3 in an isolated child process. Publisher JS/WASM/model files are unmodified and checksummed. The helper reads only local files and disables network fetches. No TranslateLocally executable or shared registry setting is used.

MiniSBD splits full text before decoding each sentence; paragraph breaks are preserved. The initial whole-paragraph integration probe exposed omitted sentences and repeated output in some Hindi/Korean passages. Sentence-wise decoding repaired those concrete cases and restored the broader quality gains. This is a production decoder check, separate from the original native benchmark.

SMaLL-100 and M2M100 418M word checkpoints use the benchmark's exact CTranslate2 int8 files, tokenizer contracts, compact hypotheses and expanded hypotheses. Since 14 October 2026, converted word resources are separate versioned downloads, omitted from portable builds and source startup. **Download required files** fetches only the selected pair's model: approximately 275.4 MB for SMaLL-100 or 460.0 MB for M2M100. Models are shared across pairs; existing verified resources remain compatible. Both compressed downloads and decoded files are checksummed, with streaming decompression to bound memory usage. Model conversion runs only for separate model releases; PyTorch and Transformers are excluded from the portable runtime. Firefox models and their runtime also download only during explicit preparation. [Licenses and provenance](../THIRD_PARTY_TRANSLATION.md).

Readiness records include the provider policy. Existing Argos-only pairs keep their preparation; changed pairs require preparation of their selected assets. Removed alternative models are retained under `%LOCALAPPDATA%/LanguageLens/removed-translation-models`, and can be shared by several directions.

## Validation on this workstation

The final production decoder was evaluated against unchanged benchmark inputs and references: **1,241 full-text cases across all 17 direct Firefox selections**, plus **56 checks across the seven Turkish hybrid selections**. All 16 direct selections with a healthy Argos baseline retained a positive public chrF++ difference; Spanish → English remains a working fallback against the unhealthy baseline. All seven hybrid subsets retained positive differences. These are public-reference, best-effort results, not accuracy percentages or a guarantee on every phrase.

The six word selections reproduced **240/240** recorded compact/expanded outputs exactly. No bilingual review or other-PC check is pending.

The actual GUI process protocol completed **100 English → Korean captures** with Firefox full text and SMaLL-100 expanded words while preserving the same loaded model instances:

| Measurement | Result |
| --- | ---: |
| Loaded full-text median / p95 | 62 / 63 ms |
| Expanded lookup median / p95 | 47 / 139 ms |
| Requested final word, after its full sentence | 47 ms; dispatched before all speculative words |
| Combined loaded worker RSS | 1.13 GiB |
| CPU consumed by the workers during eight idle seconds | No measurable CPU time |
| First capture including full text and two word lookups | 2.13 seconds |
| Three fresh capture-mode preparations | 2.10–2.15 seconds; both workers released each time |

The expanded loop repeats ten words and includes cache hits; full selections use distinct capture numbers. These timings describe this workstation and workload. Cold timings include process/model initialization and use the normal OS file cache. Retention off deliberately trades initialization delay for released memory. The seven hybrid quality checks ran alongside packaging/source verification; their timings are not used as a clean performance claim.

The original frozen executable also passed full-text, compact/expanded word and inspection checks for English → Korean, English → Japanese and Portuguese → English. Both then-bundled word models passed all file/tokenizer hashes; the separate downloads retain those exact decoded bytes. The packaged runtime verifies absence of Torch/Stanza/spaCy, normal GUI startup, single-instance behavior, worker dispatch, model recovery and uninstall checks.

The complete source suite passed **1,094 tests**. Dependency consistency and Git whitespace checks also passed. UI previews were inspected, including the expanded settings section containing the new toggle.

Artifacts are stored under `artifacts/translation-production-integration-2026-10-13/`: `production-segmented-full-text.json`, `production-hybrids.json`, `decoder-parity.json`, `residency-and-latency.json`, `frozen-translation.json`, and `release-verification.json`. The earlier whole-paragraph probe remains preserved as `production-full-text.json`. Original benchmark inputs and selection evidence are retained.
