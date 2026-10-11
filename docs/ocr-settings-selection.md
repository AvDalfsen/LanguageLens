# OCR settings selection

This records the historical fixed-model tuning phase. The active policy also
incorporates [joint model/settings validation](ocr-joint-selection.md).

Recognizers remain fixed at the previously selected language assignments.
The search evaluated 1432 language/configuration combinations on 3750 rendered selections across all 25 languages.
Independent validation accepted changes for 13 languages; the remaining languages retain their previous settings.

## Published guidance

[RapidOCR's maintainer guidance for PP-OCRv6](https://github.com/RapidAI/RapidOCR/discussions/703) proposes a 64-pixel minimum detection side, disabled dilation, a box threshold of 0.6 and expansion of 1.5 when aligning output with PaddleOCR. This is a useful starting point for this model family, not a validated per-language optimum.

[PaddleOCR's small detector configuration](https://github.com/PaddlePaddle/PaddleOCR/blob/main/configs/det/PP-OCRv6/PP-OCRv6_small_det.yml) supplies another seed: pixel threshold 0.2, box threshold 0.45 and expansion 1.4. These were tested with the existing detector and with low and moderate upscaling.

[PaddleOCR's detection guide](https://github.com/PaddlePaddle/PaddleOCR/blob/main/docs/version3.x/module_usage/text_detection.en.md) discusses minimum-side 960 for low-resolution images and larger scales such as 1216. Both scales enter the search. [RapidOCR's parameter documentation](https://rapidai.github.io/RapidOCRDocs/v3.9.0/install_usage/rapidocr/parameters/) explains the general controls but does not establish best settings for each supported language. No validated 25-language settings table was found in the reviewed resources.

[An older PaddleOCR Arabic detection discussion](https://github.com/PaddlePaddle/PaddleOCR/issues/7623) suggests increasing expansion to reduce fragmented text. This motivates the additional Arabic 2.5/3.0 trials; it does not establish those values as suitable for the current model.

## Workload and selection

Each language has 132 selections: 120 single-line crops (12 authored challenge passages under ten conditions), eight multi-line panels, and four blank/decorative controls. Conditions include clean sans/serif/monospace, small light/dark text, italics, blur, JPEG compression, low contrast and downscaling. Panels include light/dark interfaces, closely spaced rows and upside-down text. Public UI strings provide panel text, with separate messages for development and validation.

Six challenge passages are used for development and six different passages for validation. Every rendering of a passage stays in its partition. A small development screening set covers all 14 positive scenarios plus negatives. Resizing/expansion and published presets are screened first, followed by up to two rounds of other controls. Three shortlisted alternatives and the baseline are evaluated on the full development partition. The development winner is frozen before validation.

The score is the mean of 14 scenario-level mean character error rates (CER). Case, accents and punctuation count; Unicode NFC and whitespace are normalized. Missing all text counts as 100% error. Negative samples are scored separately. The original Dependency heading has no role in settings selection.

Acceptance requires at least 0.1 percentage point improvement in validation CER, no more than 0.2 percentage point upright-text regression, no more than 1 point clean-text regression, and no increase in completely missed selections or false-positive negative samples. A final guard tests all six validation passages with blue/red text on light backgrounds and green text on a dark colored background (18 additional selections per language); a regression over 1 point retains the baseline. Grayscale is removed when it leaves every development and validation pixel unchanged, avoiding an unsupported transformation of future colored captures. The chosen configuration can still worsen an individual scenario; all scenario scores and validation predictions remain in the machine-readable report.

The benchmark uses the app's default 0.45 minimum confidence. A user's different confidence preference changes which recognized lines survive and was not independently optimized here.

## Measured validation results

Across equally weighted languages, balanced CER falls from 12.484% to 9.137%. Excluding the rotated-panel scenario, upright CER falls from 9.069% to 6.603%. These are corpus error rates, not word accuracy or a general real-world accuracy promise.

| Language | Validation CER: previous → selected | Upright CER: previous → selected | Selected controls differing from previous defaults |
|---|---:|---:|---|
| Arabic | 47.936% → 47.936% | 46.261% → 46.261% | Retained defaults |
| Chinese | 4.491% → 4.491% | 4.837% → 4.837% | Retained defaults |
| Czech | 7.739% → 5.953% | 4.475% → 4.040% | det_limit_side_len=256; unclip_ratio=1.0; cls_thresh=0.8 |
| Danish | 5.680% → 4.399% | 2.403% → 2.393% | det_limit_side_len=128; unclip_ratio=1.0; det_thresh=0.4 |
| Dutch | 2.804% → 2.804% | 1.525% → 1.525% | Retained defaults |
| English | 9.609% → 2.991% | 4.643% → 3.193% | det_limit_side_len=64; unclip_ratio=1.0; cls_thresh=0.8 |
| Finnish | 5.885% → 4.497% | 2.449% → 2.400% | det_limit_side_len=64; unclip_ratio=1.0 |
| French | 9.017% → 3.033% | 2.018% → 1.532% | det_limit_side_len=384 |
| German | 2.727% → 2.727% | 1.175% → 1.175% | Retained defaults |
| Greek | 12.568% → 12.568% | 9.492% → 9.492% | Retained defaults |
| Hindi | 29.853% → 11.846% | 27.250% → 5.820% | det_limit_side_len=64; unclip_ratio=1.4; det_thresh=0.2; box_thresh=0.45; dilation=False; vertical_padding=False; use_cls=False |
| Hungarian | 9.857% → 2.516% | 5.969% → 2.644% | det_limit_side_len=128; unclip_ratio=1.0; det_thresh=0.4; cls_thresh=0.8 |
| Italian | 14.602% → 3.371% | 8.033% → 3.591% | det_limit_side_len=128; unclip_ratio=1.0 |
| Japanese | 8.919% → 8.919% | 9.559% → 9.559% | Retained defaults |
| Korean | 32.793% → 17.133% | 32.477% → 11.216% | unclip_ratio=1.0; dilation=False; use_cls=False |
| Norwegian | 8.958% → 4.535% | 3.211% → 2.923% | det_limit_side_len=128; unclip_ratio=1.3 |
| Polish | 11.431% → 8.370% | 8.561% → 5.504% | det_limit_side_len=128 |
| Portuguese (Portugal) | 7.148% → 7.148% | 1.306% → 1.306% | Retained defaults |
| Portuguese (Brazil) | 9.976% → 9.976% | 4.337% → 4.337% | Retained defaults |
| Romanian | 9.331% → 9.331% | 6.192% → 6.192% | Retained defaults |
| Russian | 12.792% → 10.089% | 6.084% → 3.329% | det_limit_side_len=128; unclip_ratio=1.0; use_cls=False; preprocessing=dark-invert |
| Spanish | 8.332% → 8.332% | 6.725% → 6.725% | Retained defaults |
| Swedish | 5.853% → 5.853% | 2.389% → 2.389% | Retained defaults |
| Turkish | 9.400% → 5.207% | 6.715% → 4.045% | det_limit_side_len=64; unclip_ratio=1.3; width_height_ratio=16 |
| Ukrainian | 24.392% → 24.392% | 18.644% → 18.644% | Retained defaults |

## Integration and reproducibility

[The settings registry](../src/language_lens/services/ocr_settings.py) feeds both inference and offline preparation. Its identity is included in prepared markers alongside the recognition assignments. The shared detector (v6 small), orientation classifier (v4 mobile), and preprocessing limits are explicit to preserve the tested configuration across library-default changes. Restart Lens and run **Check required files** for the selected pair to verify the revised policy. Model assignments and the user's minimum-confidence preference are preserved.

The search tests minimum-side 64/128/256/384/736/960/1216, automatic maximum-side detection, expansion 1.0/1.3/1.4/1.5/1.6/2.0 (also 2.5/3.0 for Arabic), segmentation and box thresholds, dilation, scoring mode, padding, rotation thresholds/enabling, recognition minimum widths, higher confidence filters, grayscale, contrast stretching and dark-background inversion. Not every combination is exhaustive. Recognition height stays at the model's trained 48 pixels and CPU thread limits stay fixed. The existing capture retry behavior is preserved.

The shared detector's input normalization stays at RapidOCR's mean/std 0.5, preprocessing limits stay at 30/2000 pixels, the orientation input stays at 48×192, and recognition batch size stays at six. These settings, detector weights, and crop retry behavior are held fixed rather than searched in this stage.

| Control | Role | Values or alternatives tested |
|---|---|---|
| Detector resize | How much detail reaches the shared detector | Minimum side 64, 128, 256, 384, 736, 960, 1216; automatic maximum-side mode |
| Crop expansion (`unclip_ratio`) | How far detection contours expand into recognition crops | 1.0, 1.3, 1.4, 1.5, 1.6, 2.0; Arabic also 2.5, 3.0 |
| Pixel/box thresholds | Which probability pixels become contours and which boxes survive | Pixel 0.2/0.3/0.4; box 0.35/0.45/0.5/0.6/0.65 |
| Dilation / box scoring | Whether nearby probability pixels merge and how box confidence is measured | Dilation on/off; fast/slow scoring |
| Vertical padding | Extra background around wide or short selections | On/off; width-to-height triggers 8/16/disabled |
| Orientation classification | Whether and when a crop rotates 180 degrees | On/off; thresholds 0.8/0.9/0.98 |
| Recognition minimum width | How narrow crops are padded in recognition batches | 64/320/640; trained height kept at 48 |
| Text confidence floor | Drop unreliable recognized lines | Library 0.35/0.6/0.75, combined with app floor 0.45 |
| Color preprocessing | Change contrast without moving source coordinates | None; grayscale; dark-background inversion; percentile contrast stretching |

RapidOCR 3.9.2 ignores the configured detector side length in `max` mode, instead selecting 960/1500/2000 from the image dimensions. Actual detector tensor shapes are retained in the results. The previous temporary 'max-side 736' experiment should therefore be understood as automatic maximum-side detection, not a 736-pixel cap.

Detector probability maps are cached at full float32 precision, and recognition outputs are cached only for identical pixel crops and recognition settings. Caches accelerate the experiment; application inference uses the normal uncached pipeline. Benchmark timings include caching and concurrent jobs and are not production latency measurements.

```powershell
.venv/Scripts/python.exe scripts/verify-ocr-settings.py --output artifacts/ocr-settings
.venv/Scripts/python.exe scripts/finalize-ocr-settings.py --runs artifacts/ocr-settings
.venv/Scripts/python.exe scripts/report-ocr-settings.py --runs artifacts/ocr-settings-final --check-assignments
.venv/Scripts/python.exe scripts/audit-ocr-settings.py --runs artifacts/ocr-settings-final
.venv/Scripts/python.exe scripts/audit-ocr-workers.py --runs artifacts/ocr-settings-final
```

[Machine-readable results](ocr-settings-benchmark.json) retain model checksums, runtime versions, corpus fingerprints, candidate settings/scores, actual detector input shapes, acceptance gates and both validation predictions. Detailed screening predictions remain in ignored experiment outputs.

## Limits

These are the best validated configurations from this search. The corpus covers rendered screen text, not arbitrary photos, handwriting, natural scene backgrounds or native vertical CJK composition. There is one multi-line panel per layout in each partition; close wins and orientation gains need independent real captures. The rotated case has equal scenario weight, so upright results are shown separately. Holding models fixed does not prove these models would win every future joint model/settings search.

Arabic, Ukrainian, Korean and Greek retain substantial errors on this workload. Retaining defaults can mean that a proposal failed a safety gate, not that defaults have the lowest observed CER in every scenario. In particular, Arabic's monochrome improvement failed the color check, and Ukrainian's improvement increased fully missed selections. A future broader development corpus or joint model/settings comparison may find better choices.

The original pre-overlay selection remains unavailable for an identical reproduction of the reported extra I. Synthetic heading checks can demonstrate behavior but cannot establish that exact screenshot as fixed.

## Application verification

The real uncached adapter matched recorded predictions on 150 validation selections across all 25 languages, with finite line/character geometry and valid span offsets. The offline subprocess protocol matched 25 dark multi-line selections, one per language. Audit fingerprints are retained in the machine-readable report.
