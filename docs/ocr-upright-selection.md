# Upright OCR policy adoption — 12 October 2026

LanguageLens uses an explicit accuracy-first policy for all 25 source languages. Models, preprocessing, batch size, image scale and confidence floors travel together. Larger or newer models are not automatically more accurate. Latency did not veto measured accuracy improvements.

The separately retained real-screen benchmark is in `artifacts/ocr-upright-2026-10-11`. Its frozen policies and predictions remain unchanged. Compatible RapidOCR recognizers and Tesseract best/fast families were compared and tuned on development data, independently validated, and frozen before the final comparison. Source-balanced CER weights collected source families equally; case, marks and punctuation remain significant.

## Adopted assignments

Chinese, Dutch, German and Italian retain their original profiles after final regressions. Other validation-selected defaults are adopted, including slower English v6-small. This deployment decision uses final results; composed adoption scores are not another unbiased held-out estimate.

| Language | Production recognizer | Settings | Current → adopted final source CER |
| --- | --- | --- | --- |
| Arabic (`ar`) | arabic-v5 | Measured upright | 34.15% → 4.47% |
| Chinese (`zh`) | multilingual-v6-small | Retained | 1.51% → 1.51% |
| Czech (`cs`) | multilingual-v6-small | Measured upright | 4.66% → 0.76% |
| Danish (`da`) | multilingual-v6-small | Measured upright | 2.25% → 2.23% |
| Dutch (`nl`) | multilingual-v6-small | Retained | 1.03% → 1.03% |
| English (`en`) | multilingual-v6-small | Measured upright | 1.05% → 0.21% |
| Finnish (`fi`) | multilingual-v6-small | Measured upright | 1.39% → 0.17% |
| French (`fr`) | latin-v5 | Retained | 1.56% → 1.56% |
| German (`de`) | latin-v5 | Retained | 0.60% → 0.60% |
| Greek (`el`) | greek-v5 | Retained | 3.51% → 3.51% |
| Hindi (`hi`) | hindi-v5 | Retained | 2.94% → 2.94% |
| Hungarian (`hu`) | multilingual-v6-medium | Measured upright | 6.68% → 0.14% |
| Italian (`it`) | latin-v5 | Retained | 0.76% → 0.76% |
| Japanese (`ja`) | multilingual-v6-small | Measured upright | 7.73% → 2.54% |
| Korean (`ko`) | korean-v5 | Measured upright | 5.29% → 2.64% |
| Norwegian (`nb`) | multilingual-v6-small | Measured upright | 2.27% → 0.82% |
| Polish (`pl`) | multilingual-v6-small | Retained | 0.11% → 0.11% |
| Portuguese (Portugal) (`pt`) | latin-v5 | Measured upright | 4.83% → 0.31% |
| Portuguese (Brazil) (`pb`) | multilingual-v6-small | Measured upright | 0.17% → 0.04% |
| Romanian (`ro`) | multilingual-v6-small | Measured upright | 2.31% → 1.19% |
| Russian (`ru`) | tesseract-best/rus+eng | Measured upright | 1.63% → 1.01% |
| Spanish (`es`) | latin-v5 | Measured upright | 0.29% → 0.14% |
| Swedish (`sv`) | multilingual-v6-small | Measured upright | 0.00% → 0.00% |
| Turkish (`tr`) | multilingual-v6-small | Measured upright | 6.65% → 2.37% |
| Ukrainian (`uk`) | cyrillic-v5 | Measured upright | 11.13% → 10.75% |

## English tradeoff and evidence limits

English improved from 1.05% to 0.21% source-balanced CER on the broader final sample. Warm median latency increased from 37.0 to 122.1 ms. The separate ORME game-font diagnostic favored the old Latin-v5 pipeline: 0.79% versus 1.24% mean CER. The default follows the broader sample; v6 does not win every game font.

Validation positives are mostly web text. Most languages lack multiple unseen native game/font families. Assistant pixel review is not independent native-speaker annotation. These are the best-supported defaults among tested policies, not a guarantee across every image or future release. New models need a new representative comparison before assignments change. Capture does not automatically switch or download models.

## Production integration

RapidOCR 3.9.2 is pinned to preserve the measured model catalogue. Policies carry batch size (including batch 1), detector controls, input scaling and per-language confidence floors. Cubic resizing maps line and character geometry back into screenshot coordinates before Qt empty-result fallback and monitor mapping. A customized confidence value still overrides the measured default. Detection remains v6-small; orientation uses v4-mobile where enabled.

Russian uses Tesseract 5.5.2 via tesserocr 2.10.0: tessdata_best Russian plus English, LSTM-only, sparse text mode 11, 2× Pillow bicubic scaling, dark-background inversion and Sauvola thresholding (`thresholding_method=2`). Dictionaries are enabled at initialization. One native text block preserves reading order; lexical spans carry native word boxes, including words next to punctuation. Native confidence values are reported without RapidOCR's unrelated floor. This policy does not run an unmeasured padded empty-result fallback.

Both Russian model files are pinned to official repository revision `e12c65a915945e4c28e237a9b52bc4a8f39a0cec` and verified by SHA-256. Offline preparation and inference share the selected backend factory. Capture remains network-disabled. The source launcher checks the native dependency. Portable packaging collects native DLLs and the Cython signal extension. Policy/runtime changes invalidate previous readiness markers: use **Check required files**, or **Download required files** for absent assets. Retry reruns the chosen production policy; experimental alternates are not deployed by this change.

Windows Python 3.10–3.12 use the [Windows builds recommended by tesserocr](https://github.com/sirfz/tesserocr#windows). The [exact release](https://github.com/simonflueckiger/tesserocr-windows_build/releases/tag/tesserocr-v2.10.0-tesseract-5.5.2) bundles Tesseract 5.5.2 and Leptonica 1.87.0; each wheel URL and SHA-256 is pinned in `pyproject.toml`. The benchmark's Python 3.10 wheel hash matches the production dependency. Python 3.11/3.12 wheel availability and hashes were verified; native execution was checked locally on Python 3.10.

Runtime/model provenance: [tesserocr](https://github.com/sirfz/tesserocr) (MIT), [Tesseract](https://github.com/tesseract-ocr/tesseract) and [tessdata_best](https://github.com/tesseract-ocr/tessdata_best) (Apache-2.0), [Leptonica](https://github.com/DanBloomberg/leptonica) (BSD-style), and the Windows wheel's [cysignals](https://github.com/sagemath/cysignals) extension (LGPL-3.0). The wheel release lists its bundled image-codec versions; the Python wrapper's MIT license does not describe every bundled library. Installed distribution notices remain collected by the release-report script.

## Reproduction

Run `.venv/Scripts/python.exe -m pytest`. With the separate benchmark retained:

```powershell
.venv/Scripts/python.exe -X utf8 scripts/audit-ocr-upright.py `
  --benchmark artifacts/ocr-upright-2026-10-11 `
  --output artifacts/ocr-upright-production-audit
```

The audit stages verified assets in a workspace-local cache, checks crop hashes, exercises the production factory, OCR task, reading order and hover builder offline, and compares transcripts with frozen predictions. User assets and benchmark predictions are untouched. `docs/ocr-upright-policy-evidence.json` records adopted controls and provenance without screenshot contents.

Local implementation verification: 1,081 tests passed; all 1,288 final selections across 25 languages reproduced their adopted frozen transcripts; all 37 Russian selections passed a separate native-adapter rerun, including 144 lexical hover-box checks. Offline worker subprocess smoke checks matched the Arabic, English, Japanese, Korean and Russian references. A frozen native-runtime executable matched the equivalent unfrozen Tesseract output. Dependency checks passed. These checks validate integration and reproduction, rather than adding independent model-quality evidence. A full new portable application release was not built or published by this change.
