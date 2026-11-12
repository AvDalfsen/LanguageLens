# Translation route rollout — 5 November 2026

The main rollout changes 80 directions: 42 with larger public-text evidence and 38 supported by smaller development tests. The especially strong 12 are a subset of the 42. A subsequent bounded repair pass adds four routes below. Together with the earlier 40 choices, 124 routes use the same selected full-text model or explicit model chain for scalar words. Other routes are unchanged.

Arabic and Korean remain excluded. These are relative quality choices; remaining game/UI regressions and imperfect translations do not imply that a worse incumbent is preferable. The smaller-test choices carry more uncertainty.

## Four targeted repairs

| Direction | Selected route | Same-case serious flags: previous → selected |
|---|---|---|
| Finnish → Spanish | `marian-gap-fi-en` → `marian-wave-opus-en-es` | 11 → 4 / 40 development texts |
| Hindi → Ukrainian | `hi-en-tiny-3.0` → `en-uk-base-memory-3.0` | 24 → 11 / 40 development texts |
| Dutch → Ukrainian | reverse `t5-en-nl-24l` → `en-uk-base-memory-3.0` | 14 → 6 / 24 game texts |
| Japanese → Hungarian | direct `m2m-full-m2m12b-native-int8-v1` | 21 → 12 / 40 development texts |

The three English compositions repair existing pivots whose individual Argos legs
were traced to specific errors. They are explicit catalog choices, not automatic
pivot discovery or a policy for other pairs. Preparation and file previews include
both models and the intermediate English sentence splitter. Both components share
the existing keep-loaded lifecycle, and words use the entire same route.

These finite development/game comparisons and small practical supplements do not
certify error-free translation or broad prose superiority for Dutch → Ukrainian.
New failures remain, including filenames/letter changes in Finnish → Spanish,
rectangle and condition wording in Hindi → Ukrainian, lethal-hit warnings in
Dutch → Ukrainian, and UI labels/attack timing in Japanese → Hungarian. Both
Ukrainian compositions can confuse saving data with saving money. These are
relative improvements with explicit regressions.

## Runtime behavior

Only models for the active pair are loaded. Shared model files are reused across directions, including the same 418M M2M weights for sentence and scalar-word calls. More reuses the scalar result; this rollout does not claim a tested multi-suggestion generator. Dutch → English uses the existing bilingual T5 weights with the publisher reverse prefix. Dutch → French uses that first leg plus the actual Argos English → French package.

The existing keep-loaded setting controls model retention. Selecting a new route invalidates its old readiness record, so use Download required files before capturing. Models are CPU-only; translations never download files or send selected text over the network.

Generic Portuguese outputs from the family/M2M models are not certified as European or Brazilian wording. Some prose gains coexist with game/UI losses, notably Dutch → English and Danish → Ukrainian; this rollout prioritizes the authorized relative gains while retaining those limitations.

## Build and supply a model pack

The production catalog pins publisher revisions, input-file hashes, converted-file hashes, native tokenizers and route settings. Do not substitute another conversion simply because it has the same model name. Ordinary wheels/builds do not include weights.

Install the build requirements into a separate environment; the application environment does not need Transformers:

```powershell
python -m venv build/model-builder
build/model-builder/Scripts/python.exe -m pip install -e . -r constraints/translation-model-build.txt
build/model-builder/Scripts/python.exe scripts/build-production-translation-models.py --models marian-wave-opus-en-fr m2m madlad400-3b-native
```

Use model identifiers from the table below. The builder reuses verified outputs, checks every download and requires byte-identical converted output. Large publisher source weights are removed after successful conversion unless --keep-source is supplied. Existing verified native resources from the earlier rollout remain part of the pack.

The default destination is src/language_lens/_translation_assets/providers, used by source checkouts. For another installation, supply the same directory through LANGUAGE_LENS_MODEL_PACK before preparing required files. The pack is ignored by Git. New Marian converted resources still require that separate pack until a public model release is explicitly prepared and published. MADLAD publisher resources and existing M2M/T5 files have pinned direct downloads.

This change stages local resources; it does not publish a release, push code or replace installed user packages.

## The 80 changed directions

| Direction | Model identifier | Evidence |
|---|---|---|
| cs-tr | `m2m` | 89–90 public texts |
| da-uk | `marian-direct-gmq-zle-v1` | 89–90 public texts |
| el-ja | `m2m-full-m2m12b-native-int8-v1` | 89–90 public texts |
| el-uk | `m2m` | 89–90 public texts |
| en-da | `marian-wave-opus-en-gmq` | 89–90 public texts |
| en-es | `marian-wave-opus-en-es` | 89–90 public texts |
| en-fi | `marian-gap-en-fi` | 40 development texts |
| en-fr | `marian-wave-opus-en-fr` | 89–90 public texts |
| en-it | `marian-wave-opus-en-it` | 40 development texts |
| en-nb | `marian-wave-opus-en-gmq` | 89–90 public texts |
| en-pb | `marian-wave-opus-en-pt` | 89–90 public texts |
| en-ru | `marian-wave-opus-en-zle` | 89–90 public texts |
| en-sv | `marian-wave-opus-en-gmq` | 89–90 public texts |
| en-tr | `marian-wave-opus-en-tr` | 89–90 public texts |
| es-ja | `hy-mt2-1.8b-q4` | 40 development texts |
| es-uk | `hy-mt2-1.8b-q4` | 89–90 public texts |
| fr-en | `marian-opus-fr-en-big` | 89–90 public texts |
| fr-pb | `marian-family-itc` | 89–90 public texts |
| fr-pt | `marian-family-itc` | 89–90 public texts |
| fr-uk | `hy-mt2-1.8b-q4` | 89–90 public texts |
| hi-ja | `m2m` | 40 development texts |
| hi-tr | `m2m` | 40 development texts |
| hu-en | `marian-selected-hu-en-big-20261104-v1` | 89–90 public texts |
| hu-tr | `m2m-full-m2m12b-native-int8-v1` | 40 development texts |
| hu-uk | `m2m-full-m2m12b-native-int8-v1` | 40 development texts |
| it-fr | `marian-family-itc` | 89–90 public texts |
| it-pb | `marian-family-itc` | 89–90 public texts |
| it-pt | `marian-family-itc` | 89–90 public texts |
| it-tr | `m2m` | 89–90 public texts |
| it-uk | `m2m` | 89–90 public texts |
| ja-es | `m2m` | 40 development texts |
| ja-hi | `m2m` | 89–90 public texts |
| ja-it | `m2m` | 89–90 public texts |
| ja-nl | `m2m` | 40 development texts |
| ja-pb | `m2m` | 40 development texts |
| ja-pt | `m2m` | 40 development texts |
| ja-ru | `m2m` | 40 development texts |
| ja-sv | `m2m` | 40 development texts |
| ja-tr | `m2m-full-m2m12b-native-int8-v1` | 40 development texts |
| ja-uk | `m2m` | 40 development texts |
| ja-zh | `m2m` | 89–90 public texts |
| nl-en | `t5-en-nl-24l` | 89–90 public texts |
| nl-fr | `t5-en-nl-24l`; then Argos en-fr | 89–90 public texts |
| pb-fr | `marian-family-itc` | 89–90 public texts |
| pb-it | `marian-family-itc` | 89–90 public texts |
| pb-ro | `marian-family-itc` | 40 development texts |
| pb-uk | `m2m` | 89–90 public texts |
| pl-ru | `marian-direct-zlw-zle-v1` | 89–90 public texts |
| pl-tr | `m2m` | 40 development texts |
| pt-en | `madlad400-3b-native` | 89–90 public texts |
| pt-es | `marian-family-itc` | 89–90 public texts |
| pt-fr | `marian-family-itc` | 89–90 public texts |
| pt-it | `marian-family-itc` | 89–90 public texts |
| pt-ro | `marian-family-itc` | 89–90 public texts |
| pt-uk | `m2m` | 89–90 public texts |
| ro-it | `marian-family-itc` | 40 development texts |
| ro-pb | `marian-family-itc` | 40 development texts |
| ro-uk | `m2m` | 40 development texts |
| sv-ro | `marian-direct-sv-ro-b2-v1` | 89–90 public texts |
| sv-ru | `marian-direct-gmq-zle-v1` | 89–90 public texts |
| tr-cs | `m2m` | 40 development texts |
| tr-hi | `m2m` | 40 development texts |
| tr-ja | `m2m` | 40 development texts |
| tr-pl | `m2m` | 40 development texts |
| uk-cs | `m2m` | 40 development texts |
| uk-da | `m2m` | 40 development texts |
| uk-de | `m2m` | 40 development texts |
| uk-es | `m2m` | 40 development texts |
| uk-hu | `m2m` | 40 development texts |
| uk-it | `m2m` | 40 development texts |
| uk-ja | `m2m-full-m2m12b-native-int8-v1` | 40 development texts |
| uk-nl | `m2m` | 40 development texts |
| uk-pb | `m2m` | 40 development texts |
| uk-pl | `m2m` | 40 development texts |
| uk-pt | `m2m` | 40 development texts |
| uk-ro | `m2m` | 40 development texts |
| uk-sv | `m2m` | 40 development texts |
| uk-tr | `m2m-full-m2m12b-native-int8-v1` | 40 development texts |
| zh-tr | `m2m` | 89–90 public texts |
| zh-uk | `m2m` | 89–90 public texts |
