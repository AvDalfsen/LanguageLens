# Multilingual translation model benchmark plan

13 October 2026. Updated to the user's final constraints: best-effort local model selection, prioritizing European Portuguese→English. Independent bilingual review and another PC are not required. The [model selections](translation-model-selection.md) contain the current decisions; earlier protocols and screening outputs remain historical evidence. Application behavior remains unchanged.

The objective is better translations at an acceptable cost relative to the current Argos package for each language direction. Preserve the two existing translation functions: the full selected OCR text, and isolated-word hover suggestions with compact and expanded alternatives. A replacement can win for one direction or one function without becoming the default everywhere.

## Agreed performance requirements

- Compare elapsed time on the **same PC, same inputs and same language direction**. A substantial quality improvement can justify roughly three times Argos's loaded time when requests remain responsive. There is no fixed relative-time exclusion rule. Routine multi-second waits fail the intended learning experience.
- Record initial loading separately. A slower initial load is acceptable when the chosen model stays loaded throughout application use and provides a worthwhile quality/performance tradeoff. Reloading at every screenshot or word request does not qualify.
- Report full-text, compact-word and expanded-word performance separately. A fast full-text result cannot conceal slow word lookups.
- Use this workstation's paired timing distributions. Do not commission another-PC testing. These measurements describe this hardware and workload; they are not universal latency promises.

The current implementation is relevant: `TaskPool.start()` creates a one-shot `ServiceJob`; `ProcessJob` launches a new process; `task_worker.execute()` constructs an `ArgosTranslator` and exits after the request. A screenshot's full-text translation and subsequent word results share that request, but the model is not retained across screenshots. Expanded search starts another request. The initial-load allowance therefore requires a persistent translation worker before a candidate can qualify on that basis. This is a future integration requirement, not a change made by this plan.

For a persistent-worker comparison, keep **both Argos and the candidate loaded** in equivalent isolated workers. Compare loaded request-to-result latency, including queueing, tokenization, splitting, inference, cleanup and IPC. Also compare the proposed candidate session against today's actual one-shot Argos application path. This distinguishes model performance from the benefit of changing worker lifetime.

## What the repository and earlier work establish

There are 25 selectable language labels, hence 600 different-language directions and 25 identity controls. Portuguese (Portugal) uses `pt`; Portuguese (Brazil) uses Argos's `pb`. Norwegian is `nb`; Chinese is `zh`. These labels need explicit mappings for each model and dataset.

A fresh read of the [Argos catalogue](https://raw.githubusercontent.com/argosopentech/argospm-index/main/index.json) contains 100 packages across its wider language set. Under Lens's installation policy, all 600 directions are potentially routable: **50 direct, 550 through English**. The direct routes are 48 directions touching English plus Portuguese↔Spanish. Availability in a catalogue is not installed availability, quality, or a verified download. At runtime, actual installed Argos routes must be recorded; do not assume every inferred route matches the installer policy.

The existing English→Dutch experiments should be reused as historical evidence. They support keeping Argos among the tested options, not a claim that Argos is universally best. Round two measured Argos at 0.35 seconds and MADLAD 3B at 9.38 seconds on the same warm game passage: about **27×** the translation time, so retaining MADLAD in memory would not solve that case. Small OPUS alternatives had mixed quality; one dedicated Marian model reproduced all 94 exposed development outputs of an Argos decoder profile. Repackaging identical weights is not a distinct quality experiment.

Earlier broader judgments were mostly assistant assessments, with human review of a small seed set. Preserve that provenance and the documented LibreOffice partition quarantine. Previously exposed final examples are useful regressions, but cannot become fresh final evidence for another model selection. Some older experiment reports recommend phrase features; those recommendations are outside the current request.

Evidence: [original results](../artifacts/translation-accuracy-2026-10-12/RESULTS.md), [additional model results and timings](../artifacts/translation-accuracy-2026-10-12/execution-v2/RESULTS.md), [model and route audit](../artifacts/translation-accuracy-2026-10-12/MODEL-ROUTE-INVENTORY.md).

## Existing resources worth using

| Resource | What is useful | What it does not establish |
| --- | --- | --- |
| [OPUS-MT dashboard](https://opus.nlpl.eu/dashboard/) and [score repository](https://github.com/Helsinki-NLP/OPUS-MT-leaderboard) | Direction-specific scores, model identifiers, multiple test sets, and comparisons with external systems. Best starting point for distinct bilingual or language-group checkpoints. | A current, complete ranking against Lens's installed Argos packages; isolated-word quality; Windows response time. Compare matching test sets and metric versions. |
| [Mozilla final evaluations](https://mozilla.github.io/translations/final-evals/) and [pipeline documentation](https://mozilla.github.io/translations/docs/training/final-evaluations/) | Shared evaluations of Firefox/Bergamot, OPUS-MT and NLLB on FLORES+, WMT24++ and BOUQuET, including COMET22 and chrF++. Exported model identities and release flags help make a concrete shortlist. | The pipeline supports Argos, but **the retrieved public database has no Argos evaluation rows**. It is a source of leads, not proof of superiority to our baseline. |
| [FLORES+](https://huggingface.co/datasets/openlanguagedata/flores_plus) | Broad multilingual coverage and aligned segment IDs permit both English-centric and cross-language evaluation. There are 997 development and 1,012 devtest sentences per variety. | Predominantly English-origin nonfiction is not a game/UI corpus. Its Portuguese variety is Brazilian, so it cannot establish European Portuguese quality. Current access requires accepting dataset conditions. |
| [WMT24++](https://huggingface.co/datasets/google/wmt24pp) | English-source evaluation across 55 languages/dialects with document/domain metadata; explicitly distinguishes `pt_PT` and `pt_BR`. Useful regional and general-text checks. | Native non-English source coverage or complete 600-direction evidence. Filter canary and bad-source rows according to the dataset protocol. |
| [BOUQuET](https://huggingface.co/datasets/facebook/bouquet) | Multilingual, multi-domain and multi-register references, including texts originally authored in several languages. Useful complement to English-origin benchmarks. | A ready-made hover-word benchmark. Verify overlapping language varieties and accept access conditions before downloading data. |
| [TranslateLocally paper](https://aclanthology.org/2021.emnlp-demo.20/) | A direct published Argos comparison demonstrates that small CPU-oriented models can improve quality: on WMT19 English→German it reports BLEU 41.8 versus 34.9. | The 2021 runtime and package versions are historical. Its throughput/CPU-time results cannot predict current interactive latency. |
| [SMaLL-100 paper](https://aclanthology.org/2022.emnlp-main.571/) and [model card](https://huggingface.co/alirezamsh/small100) | A smaller many-to-many candidate with published multilingual evaluations and a permissive MIT model-card license. Useful lead where direct bilingual coverage is weak. | Improvement over the actual Argos route. Its published comparison is principally against other multilingual models; its tokenizer has a special language-code contract. |

Execution research also found the [Argos maintainer's December 2024 OPUS comparison](https://community.libretranslate.com/t/opus-mt-language-models-port-thread/757/12). It identifies specific OPUS wins, similar results and models already used inside Argos. This is relevant evidence for bounded second chances, with an important version caveat: a current Argos package may already include the compared OPUS replacement. Check checkpoint provenance before redownloading a nominally different backend.

The retrieved Mozilla database contains exact-code scores for **49 Lens directions**: Bergamot and NLLB cover 49, OPUS-MT covers 39. Only three covered directions avoid English: German→French, French→German and Italian→German. `pb` is absent; generic `pt` requires regional checking. The much larger OPUS dashboard can help fill other directions, but no comprehensive current Argos comparison was found during this investigation.

Examples from Mozilla's FLORES+ COMET22 scores illustrate possible leads, not Argos wins or losses:

| Direction | Released Firefox/Bergamot | OPUS-MT | NLLB 600M |
| --- | ---: | ---: | ---: |
| English→French | 0.8653 | 0.8617 | 0.8587 |
| English→German | 0.8670 | 0.8470 | 0.8425 |
| French→English | 0.8860 | 0.8835 | 0.8801 |
| Japanese→English | 0.8621 | 0.8259 | 0.8511 |

Higher is better for this metric; these are not percentages of correct translations. The Firefox entries use the retrieved Release/Release Desktop variants, not the maximum across experimental runs. Small score differences alone do not establish a useful application improvement. Exact model names, metric metadata and public result URLs are retained in the [score snapshot](../artifacts/translation-research-2026-10-13/mozilla-public-scores.json), sourced from [Mozilla's public database](https://storage.googleapis.com/moz-fx-translations-data--303e-prod-translations-data/db/db.sqlite).

## Candidate policy

Prioritize distinct **small OPUS-MT checkpoints**, including direct cross-language models, and **released Firefox/Bergamot models**. OPUS candidates fit the existing CTranslate2 approach relatively well; Bergamot's optimized student architecture may need its own backend. [CTranslate2's supported conversions](https://opennmt.net/CTranslate2/guides/transformers.html) and [Bergamot's native/WASM build documentation](https://github.com/browsermt/bergamot-translator) are feasibility references, not proof of portable integration.

Keep **SMaLL-100** as a second-tier direct many-to-many lead. For Hindi↔English, also inspect the small [IndicTrans2 distilled models](https://huggingface.co/ai4bharat/indictrans2-en-indic-dist-200M) and their reverse-direction counterpart. They introduce preprocessing/backend work and gated access; their publisher now points to a newer Indic-Translate family. Examine its current small-checkpoint options before committing to this older candidate.

Treat **NLLB 600M** as a conditional research comparator: the [model card](https://huggingface.co/facebook/nllb-200-distilled-600M) specifies CC-BY-NC and research-oriented use. Its suitability for distribution requires a separate decision, and interactive responsiveness still matters. It is not the default deployment shortlist for a freely reusable application.

**MADLAD 3B** is excluded from the immediate shortlist by existing loaded-runtime evidence. **TranslateGemma 4B** has [published WMT24++ results](https://huggingface.co/google/translategemma-4b-it), but those results do not establish CPU latency competitive with Argos; place it behind an inexpensive feasibility screen rather than launching another large-model benchmark. Newly published tiny models such as [TranslatePsy-EuroNano](https://github.com/tether-ai-research/qvac-translatepsy-euro-nano) belong on a watch list until reproducible checkpoint-specific scores and deployment evidence are found.

Do not require proof that a model is better before running any local comparison: that would exclude improvements for directions lacking published Argos scores. Require a **credible reason to test**: a matched public quality lead, a distinct direct route replacing a pivot, or documented improvement for a relevant language/domain. Reject known duplicates and clearly unsuitable candidates early. Missing scores mean unknown, not inferior.

Decoder settings do exist. CTranslate2 exposes beam search, length penalties, quantization and related controls; [its decoding documentation](https://github.com/OpenNMT/CTranslate2/blob/master/docs/decoding.md) describes the speed tradeoff. Earlier English→Dutch settings sweeps produced small inconsistent gains. This project should focus on model/route choices with one registered practical configuration per candidate, not repeat a broad settings search. Any later configuration adjustment uses development data only and counts as a separate experiment.

## Staged execution approach

### 1. Complete the 600-direction research register

Start from the [saved route matrix](../artifacts/translation-research-2026-10-13/route-research-matrix.json). It already records every direction, catalogue legs/package versions and Mozilla score coverage. Add concrete candidate IDs, checkpoint revisions/hashes, model provenance, exact language varieties, matching published datasets/scores, license, backend and n-best support.

Give each direction an explicit outcome: credible candidate; small exploratory comparison needed; known duplicate/inferior candidate; unsupported variety/backend; or no candidate found. Preserve reverse directions separately. English→Dutch stays a historical/regression direction unless genuinely new evidence appears.

Research all directions, but do not benchmark every model on all directions. Normally limit the first local screen to Argos plus **two credible challengers per direction**. A small additional feasibility check can follow a concrete published lead or reuse an already available checkpoint; record that exception rather than opening an unrestricted search. Batch work by shared model to avoid repeated downloads and conversions. Measure composite routes end to end; never add their component quality scores to predict combined quality.

### 2. Verify feasibility and loaded speed before expensive quality review

Begin with a manageable six-direction pilot: English→French, French→English, Japanese→English, Hindi→English, French→Dutch and Portuguese (Portugal)→Dutch. These cover English-centric models, different scripts and two English pivots. This order is practical, not based on usage statistics or established superiority. Then cover the remaining English directions and the other cross-language directions that have credible candidates.

Begin with two fundamental sentences and two isolated words, expanding leads to six of each. This cheap prefix permits early elimination; it cannot establish general quality. Published evidence can earn a bounded independent second batch as requested. Only promising routes need a larger development screen of approximately 50 full-text inputs plus 50 distinct lookup units, spanning fragments, short sentences and paragraphs. All candidates see exactly the same input bytes and selected lookup units. Use the existing CPU configuration as the primary comparison; record effective precision, inference threads and memory. Alternate run order to reduce desktop-load and file-cache effects in the fuller finalist benchmark.

For loaded full-text, compact-word and expanded-word requests, compare median and p95 times with warmed Argos in each input-length/route stratum. Judge absolute waiting time alongside quality and relative time; do not reject a useful subsecond lookup just because Argos was much faster. Use multiple repeats and sufficient independent inputs before rejecting a near-boundary result. Cache hits are a separate check and cannot qualify an otherwise slow model.

Record startup, first-use, memory after load, session memory growth, time to first full translation, time to first/all word suggestions, and queue delay when captures are repeated. Stop candidates that clearly fail the loaded gate before commissioning broad reference review.

For slower startup, require a documented persistent-worker feasibility check. A process that survives while reloading weights each request fails the residency condition. Measure load counts and keep the chosen route's weights resident across screenshots, expanded lookups and ordinary cancellation; language-pair changes are explicit preparation events. Compare persistent Argos too before crediting the model. Faster loaded operation is welcome but no longer mandatory when quality justifies the cost.

### 3. Screen translation quality on public and application text

Use matched FLORES+/OPUS test sets for broad coverage, WMT24++ for applicable English/region checks, and BOUQuET for multiple origins/registers. Freeze dataset versions and segment IDs. Score the actual Argos baseline on the same samples; historical upstream Argos scores are insufficient.

Retain candidates with promising paired improvements and acceptable speed. Use chrF++ plus COMET22 where the metric supports the languages; pin metric models, versions and signatures. Metric values are comparable only under matching evaluation conditions. Run metric computation outside translation timing. Published scores and metrics narrow the search; neither decides correctness of an isolated word or proves improved game comprehension.

Reuse the retained OCR corpus's 2,921 positive selections across 25 labels as an application-text bank. Its annotations are **source transcripts**, not reviewed target translations. Prepare target-language references only for promising comparisons and retain multiple valid phrasings. Reuse screenshots and original frozen OCR; avoid rerunning OCR or choosing its output using candidate translations.

Keep two input tracks: annotated source text for translation quality, and the same designated frozen OCR text for application impact. Do not feed surrounding screenshot text or reference answers that production does not supply. Existing source-family partitions apply across every language and crop; fill missing unseen game/UI families with new material assigned before inference.

### 4. Review the two functions independently

For whole text, use best-effort assistant review of actions, actors, relationships, negation, numbers, names, instructions and omissions. Awkward but understandable wording can pass. Report game/UI/web and individual families separately; do not treat contractions, capitalization or synonymous phrasing as meaningful improvements.

For hover words, pass the **word alone** to the model. Reviewers may see its sentence/screenshot to identify useful meanings. Measure top-1 usefulness, correct-sense availability among the displayed top four, expanded-alternative recall, invalid/misleading suggestions and duplicate alternatives. Also use an acceptable isolated-sense list so ambiguity is not mistaken for a request for contextual inference. A correct meaning somewhere in twelve alternatives is different from a useful first suggestion.

Preserve the current n-best behavior when assessing a word-model replacement: compact search asks for five hypotheses and displays up to four distinct candidates; expanded search asks for twelve. A backend without usable alternatives can still be a full-text candidate while Argos supplies words. Report genuinely fewer valid senses rather than requiring meaningless list padding. Do not add phrase buttons, context extraction or new word flows.

Use the available references, published evaluations and best-effort assistant meaning judgments for final recommendations. The user explicitly accepts this evidence level. Do not leave decisions waiting for bilingual review, and do not describe assistant judgments or reference scores as independently certified accuracy.

### 5. Select useful improvements from the completed evidence

Make a best-effort recommendation when paired examples show useful meaning repairs across the relevant function, broader comparisons support them, and known regressions do not outweigh the repairs. Keep Argos for marginal or mixed outcomes. Record concrete repairs and regressions rather than invent a precise correctness percentage from assistant review.

Reuse completed broader and application comparisons. The final released-Firefox screen freezes six fundamentals and a prefix of public inputs, expanding promising directions to the fixed 67 public inputs. Portuguese adds regional probes and frozen native-source OCR examples. Word providers use both compact and expanded outputs, including source-language homographs. These are development comparisons with selection bias, not fresh sealed evaluation.

A sentence-model improvement may retain Argos for words; a word-only improvement must preserve full-text behavior. Evaluate any mixed configuration as a complete session, including two resident models/routes, memory and queueing. Keep Argos where no candidate meets both quality and speed requirements.

The final output is a per-direction decision table: baseline package/route; chosen full-text and word providers; paired quality gains/losses; loaded latency ratios; startup and memory; review provenance; and retain/change/provisional status. It can motivate a later implementation proposal. It does not automatically authorize production replacement.

## Scope and saved research

The planning phase produced this document, a fresh Argos catalogue snapshot, a complete 600-direction route/coverage register and extracted public Mozilla scores. The metadata extraction script is not a benchmark runner. The user subsequently authorized isolated model downloads, staged translation inference, and removal of rejected experiment weights; execution is recorded separately under `artifacts/translation-cross-language-2026-10-13`. No application behavior changes are part of that authorization.

Keep original screenshots, annotations, frozen predictions, references and checkpoints. Future candidates should use an isolated model store and a bounded download budget; preserve receipts/hashes and remove reproducible rejected weights after their results are secured. This avoids rebuilding the large artifact folder from the previous experiment.

[Research summary and source hashes](../artifacts/translation-research-2026-10-13/research-summary.json) · [600-direction matrix](../artifacts/translation-research-2026-10-13/route-research-matrix.json) · [Public scores](../artifacts/translation-research-2026-10-13/mozilla-public-scores.json) · [Local metadata extractor](../artifacts/translation-research-2026-10-13/extract_public_metadata.py).
