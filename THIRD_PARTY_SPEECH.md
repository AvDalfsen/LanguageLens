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

These are the four voices tested in the pronunciation prototype, carried into the initial app integration. The catalogue does not establish that the voices or their training data can be redistributed under Language Lens's MIT licence. A redistribution review remains outstanding before a packaged public release, including the runtime's source/notice requirements and each voice's full licence chain. This change does not include or publish a binary distribution.

Integrity checks use exact file lengths and SHA-256 hashes of the pinned artifacts. The upstream model files were first verified against the prototype's pinned catalogue checksums. The SHA-256 values are not an upstream signature or a substitute for licence review.
