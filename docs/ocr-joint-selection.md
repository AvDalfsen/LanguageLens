# Joint OCR model and settings validation

This follow-up compares 127 recognizer/language pairs across all 25 supported languages, including all-catalogue English probes. Every model receives both the previous baseline and the current tuned settings when those differ. 30 challengers receive a separate settings search.

Fresh validation accepts 2 model changes and 2 settings changes. Source assignments reflect only accepted frozen proposals.

## Protocol

Initial comparison uses the complete preceding development partition: six authored passages × ten renderings, four interface panels, two negative controls and eighteen color variants (84 selections per language). All compatible models see identical pixels, settings, default confidence floor 0.45 and application reading order/fragment suppression. Shared detector v6 small and orientation classifier v4 mobile remain fixed.

An audit of [PaddleOCR's model documentation](https://github.com/PaddlePaddle/PaddleOCR/blob/main/docs/version3.x/module_usage/text_recognition.en.md) found that several recognizers labelled for other scripts also support English. The earlier English comparison omitted these. This follow-up therefore probes all 22 catalogue recognizers on English, including models whose full English repertoire is not promised. Seven models' identical development checkpoints are reused; earlier English validation and its frozen choice are discarded. English receives a replacement set of eight fresh passages, and the expanded proposal is frozen again before evaluating that set. Other languages use their documented script-family candidates.

For each language, the strongest non-incumbent gets resize/expansion and published-preset screening, then up to two rounds of other controls. A second challenger also gets this search when its initial score is within 0.2 percentage points of the incumbent. The full development set chooses among baseline/current settings and the top three screening alternatives. Incumbents retain the benefit of the preceding comprehensive settings search; this stage checks both their baseline and current settings. This is a bounded joint search, not an exhaustive Cartesian search of every parameter for every model.

The proposed model/settings pair is frozen in the result file with a SHA256 fingerprint before any fresh validation inference. Fresh validation evaluates every compatible model with its development-winning settings, including tuned challengers, for a complete comparison; those results never feed another tuning round. Only the single development-selected proposal can replace the incumbent. A runner-up with a better final score is reported without being selected from the holdout.

Eight new passages per language cover everyday vocabulary, orthography, a short label, quotation, measurements, technical notation, long context and mixed text. Ten renderings per passage plus three colors per passage, four multi-line layouts and two blank/decorative controls give 110 selections per language (2750 total). All variants of fresh passages stay outside development. The final set adds vocabulary evidence; it shares rendering recipes with development and is not a collection of real desktop captures.

The primary score averages seventeen positive scenario CERs: ten font/degradation cases, four layouts and three colors. Each scenario has equal weight; each passage within a scenario has equal weight. NFC and whitespace are normalized; case, accents and punctuation count. Missing text counts as error. The preceding settings report used fourteen scenarios plus a separate color guard, so its percentages are not directly comparable with this report.

During development ranking, each negative selection containing hallucinated text adds a 0.10 penalty to balanced CER. This can keep a model with lower positive-text CER from entering the challenger shortlist. Negative results, plain CER and settings are all retained, so this practical selection rule is visible rather than mistaken for a universal model ranking.

Acceptance requires at least 0.1 percentage point lower fresh CER, upright regression ≤0.2 points, clean and color regression ≤1 point, and no increase in completely missed positive selections or false-positive negative selections. These practical gates are not statistical significance tests. The limited number of passages/layouts means close rankings remain uncertain.

## Fresh validation results

[All candidate comparisons](ocr-joint-candidates.md) show baseline, current and development-winning settings scores for each compatible model, followed by fresh validation scores.

Across equally weighted languages, balanced CER changes from 7.615% to 7.289%; upright CER changes from 5.483% to 5.289%.

| Language | Previous → selected recognizer | Fresh CER: previous → selected | Frozen proposal / decision |
|---|---|---:|---|
| Arabic | arabic-v5 → arabic-v5 | 57.430% → 57.430% | arabic-v5: retained (development winner) |
| Chinese | multilingual-v6-medium → multilingual-v6-small | 5.299% → 2.753% | multilingual-v6-small: accepted |
| Czech | multilingual-v6-small → multilingual-v6-small | 4.349% → 4.349% | multilingual-v6-small: retained (development winner) |
| Danish | multilingual-v6-small → multilingual-v6-small | 4.024% → 4.024% | multilingual-v6-medium: rejected: cer_improves, empty_safe |
| Dutch | multilingual-v6-small → multilingual-v6-small | 5.796% → 5.796% | latin-v3: rejected: cer_improves, upright_safe, clean_safe, color_safe, empty_safe |
| English | latin-v5 → latin-v5 | 0.520% → 0.520% | latin-v5: retained (development winner) |
| Finnish | multilingual-v6-small → multilingual-v6-small | 3.586% → 3.586% | multilingual-v6-small: retained (development winner) |
| French | latin-v5 → latin-v5 | 1.373% → 1.373% | latin-v5: retained (development winner) |
| German | latin-v5 → latin-v5 | 0.352% → 0.352% | multilingual-v6-small: rejected: cer_improves, upright_safe, color_safe |
| Greek | greek-v5 → greek-v5 | 10.263% → 10.263% | greek-v5: retained (development winner) |
| Hindi | hindi-v5 → hindi-v5 | 10.804% → 10.804% | hindi-v5: retained (development winner) |
| Hungarian | multilingual-v6-medium → multilingual-v6-medium | 2.815% → 2.815% | multilingual-v6-medium: retained (development winner) |
| Italian | latin-v5 → latin-v5 | 3.225% → 3.225% | latin-v5: retained (development winner) |
| Japanese | multilingual-v6-medium → multilingual-v6-medium | 10.691% → 10.691% | multilingual-v6-medium: retained (development winner) |
| Korean | korean-v5 → korean-v5 | 21.366% → 21.366% | korean-v5: retained (development winner) |
| Norwegian | multilingual-v6-small → multilingual-v6-small | 4.042% → 4.042% | multilingual-v6-small: retained (development winner) |
| Polish | multilingual-v6-small → multilingual-v6-small | 4.714% → 4.714% | multilingual-v6-medium: rejected: cer_improves, upright_safe, color_safe |
| Portuguese (Portugal) | latin-v5 → latin-v5 | 5.745% → 5.745% | multilingual-v6-tiny: rejected: clean_safe |
| Portuguese (Brazil) | latin-v5 → latin-v5 | 6.163% → 6.163% | multilingual-v6-small: rejected: upright_safe |
| Romanian | multilingual-v6-small → multilingual-v6-medium | 7.569% → 1.954% | multilingual-v6-medium: accepted |
| Russian | cyrillic-v5 → cyrillic-v5 | 6.074% → 6.074% | cyrillic-v5: retained (development winner) |
| Spanish | latin-v5 → latin-v5 | 0.442% → 0.442% | multilingual-v6-tiny: rejected: cer_improves |
| Swedish | multilingual-v6-small → multilingual-v6-small | 5.859% → 5.859% | multilingual-v6-medium: rejected: cer_improves |
| Turkish | multilingual-v6-small → multilingual-v6-small | 2.608% → 2.608% | multilingual-v6-small: retained (development winner) |
| Ukrainian | cyrillic-v5 → cyrillic-v5 | 5.272% → 5.272% | east-slavic-v5: rejected: cer_improves |

## Reproducibility and integration

[Machine-readable evidence](ocr-joint-benchmark.json) includes every model's initial settings scores, tuning scores, fresh predictions, model checksums, runtime/corpus fingerprints, frozen proposals and acceptance gates. Detailed development predictions and full-precision detector caches remain in ignored artifacts. Recognition caches never cross model instances. Resume rejects changes to protocol, scripts, runtime, corpus pixels and current policy.

```powershell
.venv/Scripts/python.exe scripts/verify-ocr-joint.py --output artifacts/ocr-joint
.venv/Scripts/python.exe scripts/verify-ocr-joint-english.py --output artifacts/ocr-joint-english --development-checkpoint artifacts/ocr-joint/en.json
.venv/Scripts/python.exe scripts/report-ocr-joint.py --runs artifacts/ocr-joint artifacts/ocr-joint-english --check-assignments
.venv/Scripts/python.exe scripts/audit-ocr-joint.py --runs artifacts/ocr-joint artifacts/ocr-joint-english
```

These commands repeat the search against the policy currently in the checkout. After accepted assignments change, a new run has a different incumbent and fingerprint. The checked-in evidence retains the exact earlier policy and corpus fingerprints; resuming its raw checkpoints against a changed policy is deliberately rejected.

Model/settings selection uses the same pipeline as normal inference, with word geometry disabled during bulk scoring. Final adapter checks enable actual word geometry and final worker checks exercise the application subprocess protocol. Timings from concurrent cached runs are not evidence about production speed.

The uncached adapter matched 200 representative fresh predictions across all languages. The offline worker matched 25 fresh dark panels. Span offsets and geometry were checked for finite, valid coordinates.

## Limits

This establishes the best accepted configuration within this bounded search and rendered-text corpus. It does not establish a universal optimum. Photographs, handwriting, native vertical CJK layouts and broad real-screen fonts/backgrounds remain untested. Some scripts still have substantial error. A rejected proposal or fresh runner-up may have lower aggregate CER while failing a regression gate; the report preserves that evidence.

The original Dependency heading has no role in screening, tuning or validation. Its screenshot alone cannot reproduce the original pre-overlay pixels. User settings, confidence preferences and installed assets are not changed by the experiment. Restart from this checkout and run **Check required files** to prepare the current policy.
