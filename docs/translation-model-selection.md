# Translation model selection

Updated 16 October 2026. **Argos remains the default**, including **European Portuguese→English full text and hover/expanded words**. Selected exceptions cover 25 full-text directions and 6 word directions. English→Dutch full text now uses **yhavinga/t5-small-24L-ccmatrix-multi**, converted to CTranslate2 int8. English→Dutch isolated words and Dutch→English retain Argos.

The English→Dutch decision uses the completed 40-case comparison from 15 October, with the original title and seven other exposed regressions reported separately from 32 fresh cases. On the 32 fresh cases, T5 won 8, tied 20 and lost 4 against Argos in the recorded assistant-led bilingual screening. Mean fidelity was 3.50 versus 3.22 on a 0–4 rubric; these are development review scores, not accuracy percentages or a native-speaker certification. T5 still has concrete semantic regressions. CPU warm short-text median/p95 was 291/464 ms; paragraph median/p95 was 2.06/2.59 seconds on this workstation. Its separate model download is 231.4 MB, occupying 254.5 MB after installation. The frozen corpus and outputs remain in `artifacts/en-nl-quality-campaign-2026-10-15/`; integration evidence is separate. See [production integration](translation-production-integration.md).

Firefox repairs some Portuguese terms and is much faster: the 100-capture test measured median/p95 **9/13 ms**, versus Argos **57/83 ms** on this workstation. However, a regional probe translates university tuition fees as **bribes**, where Argos is correct, and the broader score advantage is modest (+1.19 chrF++). Keep Argos for European Portuguese full text. Argos is also better for the tested isolated Portuguese words. These are best-effort development decisions, with concrete gains and regressions recorded.

| Direction | Firefox checkpoint | chrF++ change | Loaded median / p95 (ms) | Argos median / p95 (ms) |
| --- | --- | ---: | ---: | ---: |
| Arabic → English | ar-en-base-memory-3.0 | +15.95 | 49 / 129 | 285 / 626 |
| English → Arabic | en-ar-base-memory-3.0 | +6.94 | 52 / 118 | 312 / 664 |
| English → Spanish | en-es-base-memory-3.0 | +3.44 | 56 / 116 | 353 / 766 |
| English → Finnish | en-fi-base-memory-3.0 | +6.36 | 52 / 134 | 453 / 963 |
| English → Hindi | en-hi-tiny-3.0 | +4.08 | 31 / 76 | 407 / 890 |
| English → Italian | en-it-base-memory-3.0 | +2.89 | 55 / 124 | 346 / 806 |
| English → Korean | en-ko-base-3.0 | +9.58 | 53 / 113 | 418 / 886 |
| English → Polish | en-pl-base-memory-3.0 | +3.59 | 54 / 124 | 436 / 956 |
| English → Turkish | en-tr-tiny-3.0 | +6.10 | 27 / 64 | 311 / 625 |
| English → Ukrainian | en-uk-base-memory-3.0 | +14.58 | 53 / 113 | 404 / 789 |
| Spanish → English | es-en-base-memory-3.0 | baseline unhealthy | 50 / 118 | held |
| Hindi → English | hi-en-tiny-3.0 | +5.40 | 28 / 66 | 361 / 792 |
| Japanese → English | ja-en-base-3.0 | +6.88 | 42 / 86 | 370 / 793 |
| Korean → English | ko-en-base-3.0 | +11.37 | 42 / 103 | 384 / 819 |
| Swedish → English | sv-en-tiny-3.0 | +4.60 | 27 / 74 | 380 / 825 |
| Turkish → English | tr-en-tiny-3.0 | +9.75 | 25 / 78 | 330 / 778 |
| Ukrainian → English | uk-en-tiny-3.0 | +5.34 | 29 / 76 | 378 / 738 |
| Turkish → Danish | Frozen Firefox tr-en-tiny + Argos en-da | +5.64 | 437 / 1013 | 783 / 1748 |
| Turkish → Greek | Frozen Firefox tr-en-tiny + Argos en-el | +4.21 | 442 / 994 | 788 / 1707 |
| Turkish → Italian | Frozen Firefox tr-en-tiny + Argos en-it | +5.02 | 324 / 768 | 626 / 1466 |
| Turkish → Portuguese (Brazil) | Frozen Firefox tr-en-tiny + Argos en-pb | +4.93 | 407 / 949 | 708 / 1602 |
| Turkish → Portuguese (Portugal) | Frozen Firefox tr-en-tiny + Argos en-pt | +4.45 | 416 / 987 | 727 / 1698 |
| Turkish → Swedish | Frozen Firefox tr-en-tiny + Argos en-sv | +5.20 | 477 / 1085 | 798 / 1734 |
| Turkish → Dutch | Frozen Firefox tr-en-tiny + Argos en-nl | +5.40 | 539 / 1219 | 884 / 2038 |

| Direction | Provider | Compact p95 (ms) | Expanded p95 (ms) |
| --- | --- | ---: | ---: |
| English → Japanese | facebook/m2m100_418M int8 | 205 | 263 |
| English → Korean | alirezamsh/small100 int8 | 86 | 128 |
| Korean → English | alirezamsh/small100 int8 | 83 | 110 |
| Korean → Dutch | alirezamsh/small100 int8 | 96 | 129 |
| Japanese → Korean | facebook/m2m100_418M int8 | 192 | 252 |
| Spanish → English | facebook/m2m100_418M int8 | 178 | 218 |

The user accepts best-effort reference and assistant meaning review; no bilingual reviewer or second-PC test is pending. Roughly 3× slower requests can qualify for a substantial quality gain when use stays responsive. The earlier fixed 2× gate is superseded. Cold load is separated from loaded latency. Models stay loaded throughout a capture; retention between captures is optional and defaults off.

The final extension screens 44 coherent current Firefox releases, expands 24 promising/priority routes to 67 public cases, and compares both word functions on nine directions with two retained multilingual models. The original 600-direction screen and previous broader/OCR/runtime evidence are preserved. One unrelated Turkish reference cell is excluded from current derived summaries, without rewriting the frozen inputs. Public non-English sources are translated surrogates; reference scores are not accuracy percentages. Spanish→English and Japanese→Korean word choices are working fallbacks against unhealthy baseline output.

The 13 October selections above remain integrated alongside the English→Dutch T5 addition: 25 full-text directions and 6 compact/expanded word directions, with Argos elsewhere. Firefox full text uses the same weights through an isolated, local Bergamot WASM runtime; T5 and alternative words use verified CTranslate2 int8 resources. The tables above retain the original Firefox benchmark timings. The production decoder was separately checked on the frozen inputs; sentence-wise decoding prevents omissions observed with whole paragraphs. See [production integration and validation](translation-production-integration.md) for current runtime measurements and model lifecycle. Requested words take priority over speculative prefetch.

[Detailed results, limitations and concrete meaning examples](../artifacts/translation-cross-language-2026-10-13/best-effort-selection/SELECTIONS.md) · [600-direction recommendations](../artifacts/translation-cross-language-2026-10-13/best-effort-selection/direction-recommendations.json) · [Validated evidence and hashes](../artifacts/translation-cross-language-2026-10-13/best-effort-selection/validation.json) · [Research and approach](multilingual-translation-benchmark-plan.md).
