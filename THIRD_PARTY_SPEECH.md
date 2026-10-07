# Speech dependencies and voice provenance

Language Lens's existing MIT licence describes its own source code. It does not replace the licences of its dependencies or downloaded models.

The speech worker uses **piper-tts 1.8.0**, whose installed package declares **GPL-3.0-or-later** and includes its `COPYING` file. Source and notices: [Piper v1.8.0](https://github.com/OHF-Voice/piper1-gpl/tree/v1.8.0). That package includes eSpeak NG and its pronunciation data. Language Lens calls the installed Python package from a separate worker process; no Piper or eSpeak implementation is copied into this repository. This process boundary is an engineering decision for isolation and cancellation, not a conclusion about distribution obligations.

The initial voice catalogue uses files from `rhasspy/piper-voices`, revision `c10ece1aade47bb51c153c893d14e5bf8e5b7117`. The runtime, model, and training-dataset licences are distinct. The downloaded `MODEL_CARD` is retained alongside each voice, and Settings links to the exact upstream card.

| Voice | Upstream model card and declared dataset provenance |
| --- | --- |
| Lessac, English (US), medium | [Model card](https://huggingface.co/rhasspy/piper-voices/blob/c10ece1aade47bb51c153c893d14e5bf8e5b7117/en/en_US/lessac/medium/MODEL_CARD): refers to the Lessac Blizzard 2013 dataset's separate licence; trained from scratch. |
| Alan, English (UK), medium | [Model card](https://huggingface.co/rhasspy/piper-voices/blob/c10ece1aade47bb51c153c893d14e5bf8e5b7117/en/en_GB/alan/medium/MODEL_CARD): refers to the Mycroft Mimic 3 dataset repository; fine-tuned from Lessac medium. |
| Tugão, Portuguese (Portugal), medium | [Model card](https://huggingface.co/rhasspy/piper-voices/blob/c10ece1aade47bb51c153c893d14e5bf8e5b7117/pt/pt_PT/tug%C3%A3o/medium/MODEL_CARD): declares CC0 for the dataset; fine-tuned from Lessac medium. |
| Faber, Portuguese (Brazil), medium | [Model card](https://huggingface.co/rhasspy/piper-voices/blob/c10ece1aade47bb51c153c893d14e5bf8e5b7117/pt/pt_BR/faber/medium/MODEL_CARD): declares CC0 for the dataset; fine-tuned from Lessac medium. |

These are the four voices tested in the pronunciation prototype, carried into the initial app integration. The catalogue now adds the following 22 voices at the same pinned revision. Labels below summarize upstream model-card declarations, not a legal conclusion about the complete model/training licence chain.

| Additional voice | Source | Model-card licence note |
| --- | --- | --- |
| Kareem — Arabic (Jordan) | [Pinned model card](https://huggingface.co/rhasspy/piper-voices/blob/c10ece1aade47bb51c153c893d14e5bf8e5b7117/ar/ar_JO/kareem/medium/MODEL_CARD) | See URL |
| Jirka — Czech | [Pinned model card](https://huggingface.co/rhasspy/piper-voices/blob/c10ece1aade47bb51c153c893d14e5bf8e5b7117/cs/cs_CZ/jirka/medium/MODEL_CARD) | CC0 |
| Talesyntese — Danish | [Pinned model card](https://huggingface.co/rhasspy/piper-voices/blob/c10ece1aade47bb51c153c893d14e5bf8e5b7117/da/da_DK/talesyntese/medium/MODEL_CARD) | CC0 |
| Pim — Dutch (Netherlands) | [Pinned model card](https://huggingface.co/rhasspy/piper-voices/blob/c10ece1aade47bb51c153c893d14e5bf8e5b7117/nl/nl_NL/pim/medium/MODEL_CARD) | CC0 |
| Harri — Finnish | [Pinned model card](https://huggingface.co/rhasspy/piper-voices/blob/c10ece1aade47bb51c153c893d14e5bf8e5b7117/fi/fi_FI/harri/medium/MODEL_CARD) | CC0 |
| Siwis — French (France) | [Pinned model card](https://huggingface.co/rhasspy/piper-voices/blob/c10ece1aade47bb51c153c893d14e5bf8e5b7117/fr/fr_FR/siwis/medium/MODEL_CARD) | CC-BY 4.0 |
| Thorsten — German | [Pinned model card](https://huggingface.co/rhasspy/piper-voices/blob/c10ece1aade47bb51c153c893d14e5bf8e5b7117/de/de_DE/thorsten/high/MODEL_CARD) | CC0 |
| Rapunzelina — Greek | [Pinned model card](https://huggingface.co/rhasspy/piper-voices/blob/c10ece1aade47bb51c153c893d14e5bf8e5b7117/el/el_GR/rapunzelina/medium/MODEL_CARD) | CC0 |
| Pratham — Hindi | [Pinned model card](https://huggingface.co/rhasspy/piper-voices/blob/c10ece1aade47bb51c153c893d14e5bf8e5b7117/hi/hi_IN/pratham/medium/MODEL_CARD) | CC BY-NC-SA 4.0 (non-commercial) |
| Anna — Hungarian | [Pinned model card](https://huggingface.co/rhasspy/piper-voices/blob/c10ece1aade47bb51c153c893d14e5bf8e5b7117/hu/hu_HU/anna/medium/MODEL_CARD) | CC0 |
| Hi_fi_captain — Japanese | [Pinned model card](https://huggingface.co/rhasspy/piper-voices/blob/c10ece1aade47bb51c153c893d14e5bf8e5b7117/ja/ja_JP/hi_fi_captain/medium/MODEL_CARD) | CC BY-NC-SA 4.0 (non-commercial) |
| Kss — Korean | [Pinned model card](https://huggingface.co/rhasspy/piper-voices/blob/c10ece1aade47bb51c153c893d14e5bf8e5b7117/ko/ko_KR/kss/medium/MODEL_CARD) | CC BY-NC-SA 4.0 (non-commercial) |
| Talesyntese — Norwegian Bokmål | [Pinned model card](https://huggingface.co/rhasspy/piper-voices/blob/c10ece1aade47bb51c153c893d14e5bf8e5b7117/no/no_NO/talesyntese/medium/MODEL_CARD) | CC0 |
| Gosia — Polish | [Pinned model card](https://huggingface.co/rhasspy/piper-voices/blob/c10ece1aade47bb51c153c893d14e5bf8e5b7117/pl/pl_PL/gosia/medium/MODEL_CARD) | CC0 |
| Mihai — Romanian | [Pinned model card](https://huggingface.co/rhasspy/piper-voices/blob/c10ece1aade47bb51c153c893d14e5bf8e5b7117/ro/ro_RO/mihai/medium/MODEL_CARD) | CC0 |
| Denis — Russian | [Pinned model card](https://huggingface.co/rhasspy/piper-voices/blob/c10ece1aade47bb51c153c893d14e5bf8e5b7117/ru/ru_RU/denis/medium/MODEL_CARD) | CC0 |
| Davefx — Spanish (Spain) | [Pinned model card](https://huggingface.co/rhasspy/piper-voices/blob/c10ece1aade47bb51c153c893d14e5bf8e5b7117/es/es_ES/davefx/medium/MODEL_CARD) | CC0 |
| Nst — Swedish | [Pinned model card](https://huggingface.co/rhasspy/piper-voices/blob/c10ece1aade47bb51c153c893d14e5bf8e5b7117/sv/sv_SE/nst/medium/MODEL_CARD) | CC0 |
| Dfki — Turkish | [Pinned model card](https://huggingface.co/rhasspy/piper-voices/blob/c10ece1aade47bb51c153c893d14e5bf8e5b7117/tr/tr_TR/dfki/medium/MODEL_CARD) | CC BY-NC-SA 4.0 (non-commercial) |
| Mykyta — Ukrainian | [Pinned model card](https://huggingface.co/rhasspy/piper-voices/blob/c10ece1aade47bb51c153c893d14e5bf8e5b7117/uk/uk_UA/mykyta/high/MODEL_CARD) | Apache 2.0 |
| Huayan — Mandarin Chinese | [Pinned model card](https://huggingface.co/rhasspy/piper-voices/blob/c10ece1aade47bb51c153c893d14e5bf8e5b7117/zh/zh_CN/huayan/medium/MODEL_CARD) | Unknown |
| Serena — Italian | [Pinned model card](https://huggingface.co/rhasspy/piper-voices/blob/c10ece1aade47bb51c153c893d14e5bf8e5b7117/it/it_IT/serena/medium/MODEL_CARD) | CC-BY-4.0 |

Japanese uses `pyopenjtalk-plus==0.4.1.post9` and Piper's Japanese frontend, instead of eSpeak Japanese. The package includes pronunciation dictionaries; it and its dictionary dependencies have their own notices. See the [pinned package](https://pypi.org/project/pyopenjtalk-plus/0.4.1.post9/) and [Piper Japanese frontend](https://github.com/OHF-Voice/piper1-gpl/blob/v1.8.0/src/piper/phonemize_japanese.py). Audio models remain opt-in downloads, not bundled files. Settings displays the source-card link, download size and licence note for each choice.

Hindi, Japanese, Korean and Turkish cards declare noncommercial terms. Mandarin's card says “Unknown”; Arabic's card refers to a separate URL. These are unresolved distribution concerns, not permission inferred from a successful download. Attribution, share-alike, training provenance and fine-tuning chains also need review where applicable.

The catalogue does not establish that the voices or their training data can be redistributed under Language Lens's MIT licence. A redistribution review remains outstanding before a packaged public release, including the runtime's source/notice requirements and each voice's full licence chain. This change does not include or publish a binary distribution. All 26 voices passed real synthesis/integrity smoke checks, but this is not native-speaker quality validation or licence approval.

Integrity checks use exact file lengths and SHA-256 hashes of the pinned artifacts. The upstream model files were first verified against the prototype's pinned catalogue checksums. The SHA-256 values are not an upstream signature or a substitute for licence review.
