# Multilingual translation: historical initial screening outcome

The [current best-effort model selections](translation-model-selection.md) supersede the adoption requirements below. The user waived bilingual review and another-PC testing and replaced the fixed 2× speed gate with practical responsiveness. The original screen remains unchanged for provenance. Its external stages were skipped rather than passed, and its scores are not all-language accuracy measurements.

13 October 2026. The [benchmark plan](multilingual-translation-benchmark-plan.md) and initial staged campaign are complete. Application behavior is unchanged. Full selected-text translation, isolated-word hover suggestions and expanded alternatives remain the required functions.

The larger [survivor campaign](../artifacts/translation-cross-language-2026-10-13/scheduled/SURVIVOR-CAMPAIGN.md) has finished the available local work: all 83 broader comparisons, 63 clean/frozen-OCR application comparisons, and 41 resident runtime tests. It separates 18 broader quality eliminations, 23 word-baseline holds and one startup hold, and records both repairs and lost word alternatives. All 41 measured resident routes pass the runtime conditions; they remain provisional quality candidates. The original screen below remains unchanged. The earlier [32-term Korean→Dutch follow-up](../artifacts/translation-cross-language-2026-10-13/phase2/SURVIVOR-FOLLOWUP.md) is retained.

All 600 different-language directions have an explicit outcome. English→Dutch reuses previous evidence. SMaLL-100 has 529 valid new direction comparisons; 47 Brazilian-Portuguese combinations are unsupported, and 23 Spanish-source routes are held because the fresh Argos es→en package produced repeated unrelated output. Those holds are not credited as challenger wins.

The final development shortlist contains **nine full-text leads and 72 word-translation leads**. These are small-sample reference-metric leads requiring bilingual meaning review, not confirmed replacement decisions. The strongest practical starting points are:

| Candidate and function | Direction | Evidence to investigate next |
| --- | --- | --- |
| Tiny Bergamot full text; Argos words | Turkish→English and Turkish→Spanish | Repeated public-reference gains with loaded time around 0.08× and 0.11× Argos respectively. |
| Native Turkish→English, then Argos English→target | Turkish→Danish, Greek, Italian, Brazilian/European Portuguese, Swedish | Composite full-text leads; entire routes timed, words remain with Argos. |
| OPUS West Germanic full text | German→Dutch | +3.43 chrF++ points over 24 public cases, loaded time 1.20× Argos; fresh-worker startup 0.84×. |
| SMaLL-100 isolated words | Korean→Dutch, among other routes | Independent water/book/house/buy probes improved first suggestions; compact and expanded loaded times 0.43× and 0.16× Argos. |

Turkish→Dutch remains a near-cutoff review lead: +4.03 chrF++ over both public batches, +2.96 in the latest batch, and loaded time 0.70× Argos. It missed the registered +3 latest-batch gate and is recorded separately rather than described as proven inferior. German→English OPUS words are held under the startup condition: requests were slower, while three fresh-worker load comparisons were near parity at 1.02× Argos.

The English→German native candidate received additional public tests despite failing fundamentals because a historical published comparison favored TranslateLocally over Argos. The advantage did not repeat against this current baseline/checkpoint, so the route was eliminated. This does not invalidate the paper or newer Firefox models. [Mozilla evaluations](https://mozilla.github.io/translations/final-evals/) and the [OPUS-MT dashboard](https://opus.nlpl.eu/dashboard/) provide further leads; the retrieved Mozilla database contained no Argos rows.

The experiment occupies about **5.43 GiB**, leaving about 296 GiB free. Redundant original weights and temporary archives were removed after verification; 23 additional rejected weight/lexical files reclaimed 0.44 GiB. Promising checkpoints and every output were preserved. Earlier experiments and production models were retained. Temporary native CPU/cache settings were restored.

Mechanical faults were quarantined and repaired, including invalid native cache-hit timings caused by a sandbox/user Windows-profile mismatch. All 67 native/native-Argos route timings were replaced with verified two-worker, uncached measurements; translation outputs did not change. Validation confirms complete direction accounting, no unfinished metric follow-ups, isolated word units, tokenizer parity and cleanup receipts.

The [direct queue](translation-benchmark-queue.md) records completed local work. Earlier external review requirements have been superseded by the user's best-effort policy. The current application starts one-shot workers; the slower-startup allowance requires the [resident production lifecycle](translation-provider-residency-design.md) before integration. These benchmarks demonstrate experimental residency, not production integration.

The detailed [results and limitations](../artifacts/translation-cross-language-2026-10-13/RESULTS.md), [route shortlist](../artifacts/translation-cross-language-2026-10-13/reports/shortlist.md), [600-direction register](../artifacts/translation-cross-language-2026-10-13/reports/direction-register.json), and [blinded review packet](../artifacts/translation-cross-language-2026-10-13/reports/blinded-review-packet.json) are retained locally. The large experiment data is Git-ignored; these documentation files are available for version control.
