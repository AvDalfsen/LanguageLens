# OCR candidate comparisons

Development scores choose the proposal before fresh validation. Fresh scores are a check, never another selection/tuning round. All scores are balanced CER across the same seventeen scenarios; lower is better. Current settings are the language's policy before this follow-up, including cases where they equal baseline. A model's development-winning settings include challenger tuning when performed.

## Arabic (ar)

Frozen proposal: **arabic-v5**. Applied policy: **arabic-v5**.

| Model | Baseline dev | Current dev | Best dev | Dev false positives | Fresh CER | Fresh upright | Fresh missed / false positives |
|---|---:|---:|---:|---:|---:|---:|---:|
| arabic-v4 | 80.239% | 80.239% | 77.306% | 0 | 79.910% | 80.364% | 9 / 0 |
| arabic-v5 | 33.060% | 33.060% | 33.060% | 0 | 57.430% | 55.978% | 14 / 0 |

Selected settings:

```json
{
  "parameters": {},
  "use_cls": true,
  "preprocessing": "none",
  "id": "9ec8d12fdc12"
}
```

## Chinese (zh)

Frozen proposal: **multilingual-v6-small**. Applied policy: **multilingual-v6-small**.

| Model | Baseline dev | Current dev | Best dev | Dev false positives | Fresh CER | Fresh upright | Fresh missed / false positives |
|---|---:|---:|---:|---:|---:|---:|---:|
| chinese-v4-mobile | 6.253% | 6.253% | 6.253% | 0 | 6.909% | 7.209% | 1 / 0 |
| chinese-v4-server | 6.182% | 6.182% | 6.182% | 0 | 6.480% | 6.819% | 1 / 0 |
| chinese-v5-mobile | 6.443% | 6.443% | 6.443% | 0 | 6.541% | 6.884% | 1 / 0 |
| chinese-v5-server | 6.884% | 6.884% | 6.884% | 0 | 6.878% | 7.243% | 1 / 0 |
| multilingual-v6-tiny | 6.479% | 6.479% | 6.479% | 0 | 6.495% | 6.901% | 1 / 0 |
| multilingual-v6-small | 5.487% | 5.487% | 1.076% | 0 | 2.753% | 2.925% | 0 / 0 |
| multilingual-v6-medium | 5.389% | 5.389% | 5.389% | 0 | 5.299% | 5.630% | 1 / 0 |

Selected settings:

```json
{
  "parameters": {
    "Det.limit_side_len": 128,
    "Det.unclip_ratio": 1.3
  },
  "use_cls": true,
  "preprocessing": "dark-invert",
  "id": "88b5940329fb"
}
```

## Czech (cs)

Frozen proposal: **multilingual-v6-small**. Applied policy: **multilingual-v6-small**.

| Model | Baseline dev | Current dev | Best dev | Dev false positives | Fresh CER | Fresh upright | Fresh missed / false positives |
|---|---:|---:|---:|---:|---:|---:|---:|
| latin-v3 | 13.771% | 11.884% | 13.771% | 0 | 13.451% | 10.615% | 1 / 0 |
| latin-v5 | 9.128% | 3.874% | 3.874% | 0 | 4.760% | 1.798% | 0 / 1 |
| multilingual-v6-tiny | 8.369% | 3.524% | 3.507% | 0 | 5.000% | 2.739% | 0 / 0 |
| multilingual-v6-small | 6.834% | 2.545% | 2.545% | 0 | 4.349% | 1.974% | 0 / 0 |
| multilingual-v6-medium | 11.187% | 2.618% | 11.187% | 0 | 9.524% | 5.732% | 1 / 0 |

Selected settings:

```json
{
  "parameters": {
    "Det.limit_side_len": 256,
    "Det.unclip_ratio": 1.0,
    "Cls.cls_thresh": 0.8
  },
  "use_cls": true,
  "preprocessing": "none",
  "id": "73a2038d1e87"
}
```

## Danish (da)

Frozen proposal: **multilingual-v6-medium**. Applied policy: **multilingual-v6-small**.

| Model | Baseline dev | Current dev | Best dev | Dev false positives | Fresh CER | Fresh upright | Fresh missed / false positives |
|---|---:|---:|---:|---:|---:|---:|---:|
| latin-v3 | 8.479% | 4.507% | 4.507% | 0 | 8.529% | 6.302% | 1 / 0 |
| latin-v5 | 6.240% | 1.261% | 1.261% | 0 | 5.149% | 2.320% | 0 / 0 |
| multilingual-v6-tiny | 6.097% | 1.384% | 1.384% | 0 | 4.829% | 2.552% | 0 / 0 |
| multilingual-v6-small | 4.140% | 0.098% | 0.098% | 0 | 4.024% | 1.463% | 0 / 0 |
| multilingual-v6-medium | 5.475% | 0.045% | 0.045% | 0 | 3.997% | 1.617% | 1 / 0 |

Selected settings:

```json
{
  "parameters": {
    "Det.limit_side_len": 128,
    "Det.unclip_ratio": 1.0,
    "Det.thresh": 0.4
  },
  "use_cls": true,
  "preprocessing": "none",
  "id": "492d3769eb35"
}
```

## Dutch (nl)

Frozen proposal: **latin-v3**. Applied policy: **multilingual-v6-small**.

| Model | Baseline dev | Current dev | Best dev | Dev false positives | Fresh CER | Fresh upright | Fresh missed / false positives |
|---|---:|---:|---:|---:|---:|---:|---:|
| latin-v3 | 9.441% | 9.441% | 2.631% | 0 | 7.623% | 4.006% | 1 / 0 |
| latin-v5 | 9.591% | 9.591% | 9.591% | 0 | 6.579% | 2.480% | 1 / 0 |
| multilingual-v6-tiny | 10.517% | 10.517% | 10.517% | 0 | 6.367% | 2.819% | 1 / 0 |
| multilingual-v6-small | 8.074% | 8.074% | 8.074% | 0 | 5.796% | 2.139% | 0 / 0 |
| multilingual-v6-medium | 10.755% | 10.755% | 10.755% | 0 | 10.849% | 6.772% | 0 / 0 |

Selected settings:

```json
{
  "parameters": {},
  "use_cls": true,
  "preprocessing": "none",
  "id": "9ec8d12fdc12"
}
```

## English (en)

Frozen proposal: **latin-v5**. Applied policy: **latin-v5**.

| Model | Baseline dev | Current dev | Best dev | Dev false positives | Fresh CER | Fresh upright | Fresh missed / false positives |
|---|---:|---:|---:|---:|---:|---:|---:|
| latin-v3 | 6.019% | 1.465% | 1.465% | 0 | 2.373% | 2.498% | 0 / 0 |
| latin-v5 | 5.737% | 0.101% | 0.101% | 0 | 0.520% | 0.553% | 0 / 0 |
| english-v4 | 7.997% | 1.936% | 1.936% | 0 | 2.870% | 3.027% | 0 / 0 |
| english-v5 | 10.620% | 0.785% | 0.785% | 0 | 0.809% | 0.860% | 0 / 0 |
| multilingual-v6-tiny | 4.956% | 0.345% | 0.345% | 0 | 0.967% | 1.028% | 0 / 0 |
| multilingual-v6-small | 4.726% | 0.183% | 0.140% | 0 | 2.783% | 2.956% | 0 / 0 |
| multilingual-v6-medium | 7.873% | 0.259% | 0.259% | 0 | 0.667% | 0.709% | 0 / 0 |
| cyrillic-v3 | 9.229% | 4.320% | 4.320% | 0 | 7.631% | 7.503% | 0 / 0 |
| arabic-v4 | 9.074% | 4.282% | 4.282% | 0 | 12.242% | 12.828% | 6 / 0 |
| hindi-v4 | 8.832% | 3.763% | 3.763% | 0 | 6.226% | 6.436% | 0 / 0 |
| korean-v4 | 10.554% | 5.146% | 5.146% | 0 | 6.705% | 6.856% | 0 / 0 |
| chinese-v4-mobile | 7.415% | 5.268% | 5.268% | 0 | 4.271% | 4.538% | 0 / 0 |
| chinese-v4-server | 8.413% | 3.159% | 3.159% | 0 | 3.426% | 3.595% | 0 / 0 |
| cyrillic-v5 | 6.554% | 0.472% | 0.472% | 0 | 1.278% | 1.358% | 0 / 0 |
| east-slavic-v5 | 6.834% | 0.782% | 0.782% | 0 | 1.274% | 1.354% | 0 / 0 |
| chinese-v5-mobile | 5.537% | 0.630% | 0.630% | 0 | 1.261% | 1.339% | 0 / 0 |
| chinese-v5-server | 46.084% | 8.782% | 8.782% | 0 | 8.821% | 9.372% | 0 / 0 |
| japanese-v4 | 7.344% | 2.646% | 2.646% | 0 | 4.326% | 4.462% | 0 / 0 |
| arabic-v5 | 7.550% | 0.706% | 0.706% | 0 | 1.289% | 1.369% | 0 / 0 |
| greek-v5 | 6.380% | 1.653% | 1.653% | 0 | 1.921% | 2.041% | 0 / 0 |
| hindi-v5 | 5.820% | 0.798% | 0.798% | 0 | 1.306% | 1.387% | 0 / 0 |
| korean-v5 | 6.832% | 0.873% | 0.873% | 0 | 1.494% | 1.587% | 0 / 0 |

Selected settings:

```json
{
  "parameters": {
    "Det.limit_side_len": 64,
    "Det.unclip_ratio": 1.0,
    "Cls.cls_thresh": 0.8
  },
  "use_cls": true,
  "preprocessing": "none",
  "id": "381c9ba61c1f"
}
```

## Finnish (fi)

Frozen proposal: **multilingual-v6-small**. Applied policy: **multilingual-v6-small**.

| Model | Baseline dev | Current dev | Best dev | Dev false positives | Fresh CER | Fresh upright | Fresh missed / false positives |
|---|---:|---:|---:|---:|---:|---:|---:|
| latin-v3 | 12.621% | 5.452% | 5.452% | 0 | 8.293% | 5.312% | 0 / 0 |
| latin-v5 | 7.659% | 0.740% | 0.740% | 0 | 4.483% | 1.317% | 0 / 0 |
| multilingual-v6-tiny | 6.289% | 0.495% | 0.368% | 0 | 3.881% | 1.425% | 0 / 0 |
| multilingual-v6-small | 5.129% | 0.100% | 0.100% | 0 | 3.586% | 0.979% | 0 / 0 |
| multilingual-v6-medium | 8.209% | 0.907% | 0.907% | 0 | 4.060% | 1.029% | 0 / 0 |

Selected settings:

```json
{
  "parameters": {
    "Det.limit_side_len": 64,
    "Det.unclip_ratio": 1.0
  },
  "use_cls": true,
  "preprocessing": "none",
  "id": "8635c5f2037e"
}
```

## French (fr)

Frozen proposal: **latin-v5**. Applied policy: **latin-v5**.

| Model | Baseline dev | Current dev | Best dev | Dev false positives | Fresh CER | Fresh upright | Fresh missed / false positives |
|---|---:|---:|---:|---:|---:|---:|---:|
| latin-v3 | 10.715% | 5.460% | 10.715% | 0 | 10.148% | 6.514% | 0 / 0 |
| latin-v5 | 7.745% | 2.348% | 2.348% | 0 | 1.373% | 1.459% | 0 / 0 |
| multilingual-v6-tiny | 7.040% | 2.740% | 7.040% | 0 | 6.470% | 3.148% | 0 / 0 |
| multilingual-v6-small | 6.209% | 2.331% | 4.482% | 0 | 4.043% | 1.631% | 0 / 0 |
| multilingual-v6-medium | 8.226% | 3.893% | 8.226% | 0 | 7.200% | 2.839% | 0 / 0 |

Selected settings:

```json
{
  "parameters": {
    "Det.limit_side_len": 384
  },
  "use_cls": true,
  "preprocessing": "none",
  "id": "c369bb547dc3"
}
```

## German (de)

Frozen proposal: **multilingual-v6-small**. Applied policy: **latin-v5**.

| Model | Baseline dev | Current dev | Best dev | Dev false positives | Fresh CER | Fresh upright | Fresh missed / false positives |
|---|---:|---:|---:|---:|---:|---:|---:|
| latin-v3 | 3.875% | 3.875% | 3.875% | 0 | 3.727% | 3.935% | 0 / 0 |
| latin-v5 | 1.483% | 1.483% | 1.483% | 0 | 0.352% | 0.374% | 0 / 0 |
| multilingual-v6-tiny | 1.392% | 1.392% | 1.245% | 0 | 1.865% | 1.957% | 1 / 0 |
| multilingual-v6-small | 1.201% | 1.201% | 0.159% | 0 | 1.444% | 1.534% | 0 / 0 |
| multilingual-v6-medium | 1.455% | 1.455% | 1.455% | 0 | 2.264% | 2.406% | 0 / 0 |

Selected settings:

```json
{
  "parameters": {},
  "use_cls": true,
  "preprocessing": "none",
  "id": "9ec8d12fdc12"
}
```

## Greek (el)

Frozen proposal: **greek-v5**. Applied policy: **greek-v5**.

| Model | Baseline dev | Current dev | Best dev | Dev false positives | Fresh CER | Fresh upright | Fresh missed / false positives |
|---|---:|---:|---:|---:|---:|---:|---:|
| greek-v5 | 8.636% | 8.636% | 8.636% | 0 | 10.263% | 7.691% | 3 / 0 |

Selected settings:

```json
{
  "parameters": {},
  "use_cls": true,
  "preprocessing": "none",
  "id": "9ec8d12fdc12"
}
```

## Hindi (hi)

Frozen proposal: **hindi-v5**. Applied policy: **hindi-v5**.

| Model | Baseline dev | Current dev | Best dev | Dev false positives | Fresh CER | Fresh upright | Fresh missed / false positives |
|---|---:|---:|---:|---:|---:|---:|---:|
| hindi-v4 | 49.827% | 40.243% | 40.162% | 0 | 42.387% | 39.837% | 0 / 0 |
| hindi-v5 | 24.689% | 8.792% | 8.792% | 0 | 10.804% | 5.364% | 0 / 0 |

Selected settings:

```json
{
  "parameters": {
    "Det.limit_side_len": 64,
    "Det.unclip_ratio": 1.4,
    "Det.thresh": 0.2,
    "Det.box_thresh": 0.45,
    "Det.use_dilation": false,
    "Global.use_vertical_padding": false
  },
  "use_cls": false,
  "preprocessing": "none",
  "id": "1b7feed34e9e"
}
```

## Hungarian (hu)

Frozen proposal: **multilingual-v6-medium**. Applied policy: **multilingual-v6-medium**.

| Model | Baseline dev | Current dev | Best dev | Dev false positives | Fresh CER | Fresh upright | Fresh missed / false positives |
|---|---:|---:|---:|---:|---:|---:|---:|
| latin-v3 | 10.369% | 6.787% | 6.787% | 0 | 7.669% | 7.910% | 1 / 0 |
| latin-v5 | 7.060% | 1.695% | 1.695% | 0 | 3.057% | 3.195% | 0 / 0 |
| multilingual-v6-tiny | 6.717% | 1.863% | 1.863% | 0 | 3.612% | 3.784% | 0 / 0 |
| multilingual-v6-small | 5.000% | 0.831% | 0.811% | 0 | 2.344% | 2.464% | 0 / 0 |
| multilingual-v6-medium | 7.174% | 0.785% | 0.785% | 0 | 2.815% | 2.965% | 0 / 0 |

Selected settings:

```json
{
  "parameters": {
    "Det.limit_side_len": 128,
    "Det.unclip_ratio": 1.0,
    "Det.thresh": 0.4,
    "Cls.cls_thresh": 0.8
  },
  "use_cls": true,
  "preprocessing": "none",
  "id": "0b6b1fdde618"
}
```

## Italian (it)

Frozen proposal: **latin-v5**. Applied policy: **latin-v5**.

| Model | Baseline dev | Current dev | Best dev | Dev false positives | Fresh CER | Fresh upright | Fresh missed / false positives |
|---|---:|---:|---:|---:|---:|---:|---:|
| latin-v3 | 9.574% | 2.567% | 2.567% | 0 | 6.493% | 3.635% | 0 / 0 |
| latin-v5 | 6.404% | 0.103% | 0.103% | 0 | 3.225% | 0.163% | 0 / 0 |
| multilingual-v6-tiny | 6.028% | 0.413% | 0.413% | 0 | 2.752% | 0.394% | 0 / 0 |
| multilingual-v6-small | 5.465% | 0.145% | 0.145% | 0 | 2.789% | 0.154% | 0 / 0 |
| multilingual-v6-medium | 8.922% | 0.257% | 0.219% | 0 | 2.982% | 0.082% | 0 / 0 |

Selected settings:

```json
{
  "parameters": {
    "Det.limit_side_len": 128,
    "Det.unclip_ratio": 1.0
  },
  "use_cls": true,
  "preprocessing": "none",
  "id": "932c97a84994"
}
```

## Japanese (ja)

Frozen proposal: **multilingual-v6-medium**. Applied policy: **multilingual-v6-medium**.

| Model | Baseline dev | Current dev | Best dev | Dev false positives | Fresh CER | Fresh upright | Fresh missed / false positives |
|---|---:|---:|---:|---:|---:|---:|---:|
| chinese-v5-mobile | 5.412% | 5.412% | 5.412% | 0 | 11.996% | 12.462% | 7 / 0 |
| chinese-v5-server | 7.482% | 7.482% | 7.482% | 0 | 15.017% | 15.103% | 8 / 0 |
| japanese-v4 | 6.653% | 6.653% | 6.653% | 0 | 15.317% | 15.763% | 7 / 0 |
| multilingual-v6-small | 5.094% | 5.094% | 4.484% | 0 | 10.238% | 10.878% | 7 / 0 |
| multilingual-v6-medium | 4.242% | 4.242% | 4.242% | 0 | 10.691% | 11.302% | 7 / 0 |

Selected settings:

```json
{
  "parameters": {},
  "use_cls": true,
  "preprocessing": "none",
  "id": "9ec8d12fdc12"
}
```

## Korean (ko)

Frozen proposal: **korean-v5**. Applied policy: **korean-v5**.

| Model | Baseline dev | Current dev | Best dev | Dev false positives | Fresh CER | Fresh upright | Fresh missed / false positives |
|---|---:|---:|---:|---:|---:|---:|---:|
| korean-v4 | 49.692% | 29.668% | 29.668% | 0 | 37.980% | 34.897% | 13 / 0 |
| korean-v5 | 37.215% | 9.099% | 9.099% | 0 | 21.366% | 16.731% | 13 / 0 |

Selected settings:

```json
{
  "parameters": {
    "Det.unclip_ratio": 1.0,
    "Det.use_dilation": false
  },
  "use_cls": false,
  "preprocessing": "none",
  "id": "730416ca68a7"
}
```

## Norwegian (nb)

Frozen proposal: **multilingual-v6-small**. Applied policy: **multilingual-v6-small**.

| Model | Baseline dev | Current dev | Best dev | Dev false positives | Fresh CER | Fresh upright | Fresh missed / false positives |
|---|---:|---:|---:|---:|---:|---:|---:|
| latin-v3 | 11.291% | 4.974% | 4.974% | 0 | 7.576% | 6.894% | 0 / 0 |
| latin-v5 | 9.650% | 2.190% | 2.190% | 0 | 5.431% | 4.458% | 2 / 0 |
| multilingual-v6-tiny | 9.787% | 2.031% | 2.031% | 0 | 4.684% | 3.900% | 1 / 0 |
| multilingual-v6-small | 7.511% | 0.931% | 0.931% | 0 | 4.042% | 3.192% | 0 / 0 |
| multilingual-v6-medium | 10.511% | 1.008% | 0.985% | 0 | 4.300% | 3.649% | 0 / 0 |

Selected settings:

```json
{
  "parameters": {
    "Det.limit_side_len": 128,
    "Det.unclip_ratio": 1.3
  },
  "use_cls": true,
  "preprocessing": "none",
  "id": "bf0c12009a77"
}
```

## Polish (pl)

Frozen proposal: **multilingual-v6-medium**. Applied policy: **multilingual-v6-small**.

| Model | Baseline dev | Current dev | Best dev | Dev false positives | Fresh CER | Fresh upright | Fresh missed / false positives |
|---|---:|---:|---:|---:|---:|---:|---:|
| latin-v3 | 16.729% | 11.614% | 11.614% | 0 | 11.950% | 8.822% | 0 / 0 |
| latin-v5 | 14.972% | 8.770% | 8.770% | 0 | 8.563% | 4.323% | 0 / 0 |
| multilingual-v6-tiny | 11.485% | 5.690% | 5.690% | 0 | 7.015% | 3.653% | 0 / 0 |
| multilingual-v6-small | 9.376% | 3.372% | 3.372% | 0 | 4.714% | 1.459% | 0 / 0 |
| multilingual-v6-medium | 12.083% | 4.290% | 3.341% | 0 | 10.098% | 6.579% | 0 / 0 |

Selected settings:

```json
{
  "parameters": {
    "Det.limit_side_len": 128
  },
  "use_cls": true,
  "preprocessing": "none",
  "id": "20ac88f23b1c"
}
```

## Portuguese (Portugal) (pt)

Frozen proposal: **multilingual-v6-tiny**. Applied policy: **latin-v5**.

| Model | Baseline dev | Current dev | Best dev | Dev false positives | Fresh CER | Fresh upright | Fresh missed / false positives |
|---|---:|---:|---:|---:|---:|---:|---:|
| latin-v3 | 9.142% | 9.142% | 9.142% | 0 | 11.217% | 7.802% | 1 / 0 |
| latin-v5 | 4.683% | 4.683% | 4.683% | 0 | 5.745% | 1.486% | 1 / 0 |
| multilingual-v6-tiny | 4.701% | 4.701% | 2.493% | 0 | 2.315% | 1.380% | 0 / 0 |
| multilingual-v6-small | 4.524% | 4.524% | 2.550% | 0 | 1.622% | 0.694% | 0 / 0 |
| multilingual-v6-medium | 6.467% | 6.467% | 6.467% | 0 | 7.311% | 2.898% | 1 / 0 |

Selected settings:

```json
{
  "parameters": {},
  "use_cls": true,
  "preprocessing": "none",
  "id": "9ec8d12fdc12"
}
```

## Portuguese (Brazil) (pb)

Frozen proposal: **multilingual-v6-small**. Applied policy: **latin-v5**.

| Model | Baseline dev | Current dev | Best dev | Dev false positives | Fresh CER | Fresh upright | Fresh missed / false positives |
|---|---:|---:|---:|---:|---:|---:|---:|
| latin-v3 | 11.017% | 11.017% | 11.017% | 0 | 10.515% | 7.734% | 1 / 0 |
| latin-v5 | 6.705% | 6.705% | 6.705% | 0 | 6.163% | 2.707% | 1 / 0 |
| multilingual-v6-tiny | 5.977% | 5.977% | 0.110% | 0 | 5.185% | 5.383% | 0 / 0 |
| multilingual-v6-small | 6.173% | 6.173% | 0.056% | 0 | 4.910% | 5.191% | 0 / 0 |
| multilingual-v6-medium | 7.148% | 7.148% | 7.148% | 0 | 7.930% | 4.234% | 1 / 0 |

Selected settings:

```json
{
  "parameters": {},
  "use_cls": true,
  "preprocessing": "none",
  "id": "9ec8d12fdc12"
}
```

## Romanian (ro)

Frozen proposal: **multilingual-v6-medium**. Applied policy: **multilingual-v6-medium**.

| Model | Baseline dev | Current dev | Best dev | Dev false positives | Fresh CER | Fresh upright | Fresh missed / false positives |
|---|---:|---:|---:|---:|---:|---:|---:|
| latin-v3 | 14.055% | 14.055% | 14.055% | 0 | 16.637% | 11.895% | 2 / 0 |
| latin-v5 | 10.621% | 10.621% | 10.621% | 0 | 13.429% | 8.018% | 2 / 0 |
| multilingual-v6-tiny | 8.059% | 8.059% | 8.059% | 0 | 11.001% | 6.819% | 2 / 0 |
| multilingual-v6-small | 4.295% | 4.295% | 4.295% | 0 | 7.569% | 3.172% | 1 / 0 |
| multilingual-v6-medium | 7.772% | 7.772% | 1.857% | 0 | 1.954% | 1.035% | 0 / 0 |

Selected settings:

```json
{
  "parameters": {
    "Det.limit_side_len": 128,
    "Det.unclip_ratio": 1.0,
    "Det.thresh": 0.4
  },
  "use_cls": true,
  "preprocessing": "dark-invert",
  "id": "a23c5f0800df"
}
```

## Russian (ru)

Frozen proposal: **cyrillic-v5**. Applied policy: **cyrillic-v5**.

| Model | Baseline dev | Current dev | Best dev | Dev false positives | Fresh CER | Fresh upright | Fresh missed / false positives |
|---|---:|---:|---:|---:|---:|---:|---:|
| cyrillic-v3 | 32.650% | 28.732% | 28.732% | 0 | 41.827% | 38.925% | 0 / 0 |
| cyrillic-v5 | 11.801% | 6.465% | 6.465% | 0 | 6.074% | 0.608% | 0 / 0 |
| east-slavic-v5 | 13.298% | 7.150% | 7.034% | 0 | 6.558% | 1.098% | 0 / 0 |

Selected settings:

```json
{
  "parameters": {
    "Det.limit_side_len": 128,
    "Det.unclip_ratio": 1.0
  },
  "use_cls": false,
  "preprocessing": "dark-invert",
  "id": "ca10c087512b"
}
```

## Spanish (es)

Frozen proposal: **multilingual-v6-tiny**. Applied policy: **latin-v5**.

| Model | Baseline dev | Current dev | Best dev | Dev false positives | Fresh CER | Fresh upright | Fresh missed / false positives |
|---|---:|---:|---:|---:|---:|---:|---:|
| latin-v3 | 4.009% | 4.009% | 4.009% | 0 | 3.999% | 4.178% | 0 / 0 |
| latin-v5 | 2.785% | 2.785% | 2.785% | 0 | 0.442% | 0.446% | 0 / 0 |
| multilingual-v6-tiny | 2.171% | 2.171% | 1.496% | 0 | 2.644% | 0.257% | 0 / 0 |
| multilingual-v6-small | 2.156% | 2.156% | 1.529% | 0 | 2.554% | 0.065% | 0 / 0 |
| multilingual-v6-medium | 3.426% | 3.426% | 3.426% | 0 | 1.268% | 1.347% | 0 / 0 |

Selected settings:

```json
{
  "parameters": {},
  "use_cls": true,
  "preprocessing": "none",
  "id": "9ec8d12fdc12"
}
```

## Swedish (sv)

Frozen proposal: **multilingual-v6-medium**. Applied policy: **multilingual-v6-small**.

| Model | Baseline dev | Current dev | Best dev | Dev false positives | Fresh CER | Fresh upright | Fresh missed / false positives |
|---|---:|---:|---:|---:|---:|---:|---:|
| latin-v3 | 11.649% | 11.649% | 11.649% | 0 | 10.544% | 6.901% | 2 / 0 |
| latin-v5 | 10.597% | 10.597% | 10.597% | 0 | 8.012% | 3.755% | 0 / 0 |
| multilingual-v6-tiny | 11.443% | 11.443% | 11.443% | 0 | 8.049% | 3.466% | 2 / 0 |
| multilingual-v6-small | 8.672% | 8.672% | 8.672% | 0 | 5.859% | 2.455% | 0 / 0 |
| multilingual-v6-medium | 10.386% | 10.386% | 1.150% | 0 | 6.032% | 1.576% | 0 / 0 |

Selected settings:

```json
{
  "parameters": {},
  "use_cls": true,
  "preprocessing": "none",
  "id": "9ec8d12fdc12"
}
```

## Turkish (tr)

Frozen proposal: **multilingual-v6-small**. Applied policy: **multilingual-v6-small**.

| Model | Baseline dev | Current dev | Best dev | Dev false positives | Fresh CER | Fresh upright | Fresh missed / false positives |
|---|---:|---:|---:|---:|---:|---:|---:|
| latin-v3 | 12.255% | 8.927% | 8.927% | 0 | 12.714% | 12.783% | 0 / 0 |
| latin-v5 | 8.015% | 4.716% | 4.716% | 0 | 5.684% | 5.677% | 0 / 0 |
| multilingual-v6-tiny | 7.459% | 3.618% | 3.618% | 0 | 4.442% | 4.412% | 0 / 0 |
| multilingual-v6-small | 4.140% | 1.308% | 1.308% | 0 | 2.608% | 2.743% | 0 / 0 |
| multilingual-v6-medium | 7.820% | 3.349% | 3.349% | 0 | 3.171% | 3.313% | 1 / 0 |

Selected settings:

```json
{
  "parameters": {
    "Det.limit_side_len": 64,
    "Det.unclip_ratio": 1.3,
    "Global.width_height_ratio": 16
  },
  "use_cls": true,
  "preprocessing": "none",
  "id": "93ce781daa2e"
}
```

## Ukrainian (uk)

Frozen proposal: **east-slavic-v5**. Applied policy: **cyrillic-v5**.

| Model | Baseline dev | Current dev | Best dev | Dev false positives | Fresh CER | Fresh upright | Fresh missed / false positives |
|---|---:|---:|---:|---:|---:|---:|---:|
| cyrillic-v3 | 48.846% | 48.846% | 48.846% | 0 | 43.888% | 43.891% | 1 / 0 |
| cyrillic-v5 | 11.345% | 11.345% | 11.345% | 0 | 5.272% | 4.032% | 3 / 0 |
| east-slavic-v5 | 13.220% | 13.220% | 8.437% | 0 | 7.765% | 2.213% | 0 / 0 |

Selected settings:

```json
{
  "parameters": {},
  "use_cls": true,
  "preprocessing": "none",
  "id": "9ec8d12fdc12"
}
```
