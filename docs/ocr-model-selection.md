# OCR recognition model selection

This records the historical recognition-only phase. The active policy also
incorporates [joint model/settings validation](ocr-joint-selection.md), which
expands the English candidate matrix and evaluates complete-pipeline behavior.

This comparison selects recognizers for Language Lens's existing RapidOCR/ONNX
backend. Selection uses a broad screen-text workload, not the original
“Dependency and download hardening” example. That heading is excluded from the
ranking and retained only as a pipeline demonstration.

## What was compared

Twenty-two compatible recognition models were checked against RapidOCR 3.9.2's
published SHA256 catalogue. The candidates include script-specific v5 models,
the English and East Slavic alternatives, Chinese mobile/server models,
Japanese v4, older script models, and multilingual v6 tiny/small/medium.
Only models supporting the relevant script enter that language's ranking.
Greek has one suitable recognizer in this catalogue, so its result establishes
a tested baseline rather than a comparative win.

Each language has 228 ranked crops: 27 public UI messages in four renderings
and 12 original challenge passages in ten renderings. Across 25 languages this
is 5,700 ranked images. The eight original English diagnostic crops are
additional demonstrations, not ranking inputs.

[The challenge text](../scripts/data/ocr-challenge-texts.json) covers diacritics,
uppercase letters, conversation, names/places, instructions, quotations, code,
prices/numbers, dates, confusable characters, long passages and mixed text.
Its ten conditions are clean sans serif, clean serif, a monospace or
script-appropriate alternate font, 12 px light text, 14 px dark text,
18 px italic text, Gaussian blur (sigma 0.65), JPEG quality 35, low contrast
(foreground 110/background 170), and 65% downscaling. Arabic and Hindi use
Qt's shaping and bidi layout; CJK uses installed native fonts. Representative
Arabic, Hindi, Chinese, Japanese and Korean images were inspected visually.

## How selection works

Every candidate sees identical complete line crops. Detection, box expansion,
rotation classification, confidence rejection and word geometry are excluded
from recognition ranking. The recognizer's input normalization, 48 px height,
batch size and CPU thread limits remain the same for all candidates. Scores
include low-confidence predictions, avoiding an artificial accuracy gain from
discarding difficult text.

Ground truth is the literal rendered text. Scoring normalizes Unicode to NFC
and collapses whitespace, while retaining case, accents and punctuation.
Character error rate (CER) counts insertions, deletions and substitutions.
The overall score is the mean of 14 scenario scores: four UI renderings and
ten challenge renderings. Within each scenario, each passage's CER receives
equal weight. This prevents long passages or repeated easy headings from
dominating the result. The lowest observed score wins; exact ties retain the
previous model. Character-weighted CER, exact-line counts and individual
scenario scores are also recorded in [the results](ocr-model-benchmark.json).

## Assignments after recognition-only comparison

The percentages below are the balanced CER defined above, not word accuracy.
They include deliberately difficult text and degraded images.

| Language | Selected recognizer | Previous score | Selected score |
|---|---|---:|---:|
| Arabic | Arabic v5 mobile | 28.381% | 28.381% |
| Chinese | Multilingual v6 medium | 2.841% | 1.507% |
| Czech | Multilingual v6 small | 3.994% | 2.807% |
| Danish | Multilingual v6 small | 2.711% | 1.152% |
| Dutch | Multilingual v6 small | 0.852% | 0.744% |
| English | Latin v5 mobile | 1.316% | 1.316% |
| Finnish | Multilingual v6 small | 2.961% | 1.658% |
| French | Latin v5 mobile | 1.035% | 1.035% |
| German | Latin v5 mobile | 0.575% | 0.575% |
| Greek | Greek v5 mobile | 3.059% | 3.059% |
| Hindi | Devanagari v5 mobile | 6.074% | 6.074% |
| Hungarian | Multilingual v6 medium | 2.716% | 2.699% |
| Italian | Latin v5 mobile | 0.558% | 0.558% |
| Japanese | Multilingual v6 medium | 4.617% | 2.531% |
| Korean | Korean v5 mobile | 8.126% | 8.126% |
| Norwegian | Multilingual v6 small | 2.918% | 1.466% |
| Polish | Multilingual v6 small | 6.421% | 2.381% |
| Portuguese (Portugal) | Latin v5 mobile | 0.430% | 0.430% |
| Portuguese (Brazil) | Latin v5 mobile | 0.608% | 0.608% |
| Romanian | Multilingual v6 small | 7.071% | 2.078% |
| Russian | Cyrillic v5 mobile | 1.765% | 1.765% |
| Spanish | Latin v5 mobile | 0.366% | 0.366% |
| Swedish | Multilingual v6 small | 1.675% | 1.219% |
| Turkish | Multilingual v6 small | 4.941% | 2.027% |
| Ukrainian | Cyrillic v5 mobile | 2.780% | 2.780% |

This changes 12 languages and retains 13 existing assignments. In particular,
v6 small wins on the clean English UI subset, but Latin v5 wins the broader
ranking. English-specific v5 did worse in both tests; a language-specific name
does not establish a quality advantage. Italian, Portuguese and Spanish also
retain Latin v5 after testing the harder passages. Polish switches to small
after medium's initial clean-text lead failed to hold on the broader workload.

Hungarian's medium-model advantage is only 0.017 percentage points and is not
a decisive general improvement. Its assignment follows the measured minimum;
it deserves independent real-capture validation. Medium is a larger, slower CPU
recognizer, so that small quality margin is a material tradeoff. Arabic, Hindi
and Korean retain their strongest tested script models, but still have
substantial errors on difficult text. Arabic's especially high challenge score
means this selection must not be presented as equally strong language support.

## Published evidence

[PaddleOCR's v5 multilingual documentation](https://github.com/PaddlePaddle/PaddleOCR/blob/main/docs/version3.x/algorithm/PP-OCRv5/PP-OCRv5_multi_languages.en.md)
describes language coverage and the English-specific recognizer. Its accuracy
figures use each model's corresponding dataset, so they cannot establish
English versus Latin or East Slavic versus Cyrillic winners directly.

[PaddleOCR's v6 report](https://github.com/PaddlePaddle/PaddleOCR/blob/main/docs/version3.x/algorithm/PP-OCRv6/PP-OCRv6.en.md)
reports improved recognition on the same multi-scenario benchmark and expanded
diacritic coverage. Small/medium support Latin languages, Chinese and Japanese;
tiny excludes Japanese. These findings justify testing v6, while the local
comparison determines the assignments for this app.

Inspection of the verified ONNX dictionaries also found missing Romanian
`ă`, `ș`, `ț` in Latin v5. V6 small/medium include them. Alphabet coverage is a
model limitation that detector thresholds cannot repair.

## Integration and asset readiness

[The shared recognition policy](../src/language_lens/services/ocr_profiles.py)
drives engine construction, verified model downloads and offline preparation.
Prepared markers include the policy fingerprint, so a changed assignment
requires a new offline check. Native character boxes remain available for
Latin/CJK models; other scripts retain their existing shaped geometry fallback.

Arabic validation exposed RapidOCR's missing `python-bidi` dependency. It is
now declared, pinned, included in launcher health checks and explicitly
included in portable packaging. The tested source environment has it installed.

After restarting Lens, use **Check required files** or **Download required
files** for the selected language pair to prepare the newly assigned assets.
Capture inference continues to run with networking disabled.

## Limits and next stage

These are the best observed assignments within the tested RapidOCR candidates
and this corpus. Rendered public text provides exact ground truth but is not
a representative natural-image dataset or a universal accuracy guarantee.
The corpus does not establish handwriting or arbitrary photo performance.
Close scores should be rechecked against independent real captures.

Pipeline checks with production detector defaults and temporary automatic
maximum-side / unclip 1.0 overrides were recorded separately. Both exposed
missing or damaged text crops in some scripts. RapidOCR 3.9.2 ignores the
configured side length in `max` mode and instead chooses 960/1500/2000 from
image dimensions; the earlier “max-side 736” description was inaccurate.
These checks did not select detector settings. The subsequent fixed-model
[settings comparison](ocr-settings-selection.md) evaluates that separate stage.
The original pre-overlay screenshot crop was not available for an identical
reproduction of the reported error.
With the final English model and baseline detector settings, the serif heading
produced `Dependency: and download hardening` in the full pipeline, adding a
colon, while recognition-only tests read the complete line correctly. This
shows that choosing the strongest recognizer does not by itself eliminate
full-pipeline errors; it does not reproduce the reported `Ihardening` error.

## Reproduce

Run these opt-in commands in the source development environment with its
optional CJK segmentation dependencies installed. Model downloads require
network access; inference does not. Outputs stay under ignored `artifacts/`.

```powershell
.venv/Scripts/python.exe scripts/verify-ocr-models.py --download
.venv/Scripts/python.exe scripts/verify-ocr-models.py --holdout --output artifacts/ocr-models/holdout --model-cache artifacts/ocr-models/models
.venv/Scripts/python.exe scripts/verify-ocr-models.py --challenge --output artifacts/ocr-models/challenge --model-cache artifacts/ocr-models/models
.venv/Scripts/python.exe scripts/report-ocr-models.py --runs artifacts/ocr-models/results.json artifacts/ocr-models/holdout/results.json artifacts/ocr-models/challenge/results.json --check-assignments
.venv/Scripts/python.exe scripts/verify-ocr-models.py --pipeline --output artifacts/ocr-models/pipeline --model-cache artifacts/ocr-models/models
.venv/Scripts/python.exe scripts/verify-ocr-models.py --pipeline --neutral-detection --output artifacts/ocr-models/neutral-pipeline --model-cache artifacts/ocr-models/models
```

Pipeline commands intentionally return nonzero if any test crop yields no
text; inspect `pipeline.json` rather than treating that as a recognizer ranking.
The recorded comparison used split model runs; the report script accepts
multiple results for each partition and rejects incomplete/duplicate samples.
Runtime versions, corpus hashes, model hashes and scenario metrics are retained
in the results. Concurrent benchmark timings are diagnostic only and do not
determine model selection.
