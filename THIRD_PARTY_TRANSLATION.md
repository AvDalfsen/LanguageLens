# Local translation components

Language Lens routes only the selected language/function exceptions to these
providers. Other routes retain Argos. Inference uses local files and processes;
model preparation downloads public model assets, never captured text.

| Component | License | Source |
| --- | --- | --- |
| Firefox translation weights, lexical shortlists and vocabularies | MPL-2.0 | https://github.com/mozilla/translations |
| Bergamot WebAssembly runtime, npm package 0.4.9 | MPL-2.0 | https://github.com/browsermt/bergamot-translator |
| SMaLL100, revision 8ab680e26a596d2e3d2d2d17ae0f68df1037328c | MIT | https://huggingface.co/alirezamsh/small100 |
| M2M100 418M, revision 55c2e61bbf05dfb8d7abccdc3fae6fc8512fd636 | MIT | https://huggingface.co/facebook/m2m100_418M |
| Node.js v22.23.3, Windows x64 | MIT and bundled third-party notices | https://nodejs.org/ |
| CTranslate2 | MIT | https://github.com/OpenNMT/CTranslate2 |
| SentencePiece | Apache-2.0 | https://github.com/google/sentencepiece |
| Zstandard Python binding | BSD-3-Clause | https://github.com/indygreg/python-zstandard |

The production catalogue, `language_lens/data/translation-providers.json`, pins
publisher revisions, download URLs, lengths and SHA-256 checksums. Firefox
model files are downloaded unmodified during explicit preparation. The two word
models are converted to CTranslate2 int8 by a separate model-release build and
distributed as versioned Zstandard downloads on GitHub. Their tokenizer and
converted file hashes match the benchmark assets. **Download required files**
fetches only the selected pair's model and verifies both compressed and decoded
files. Conversion dependencies are model-build-only; app releases omit weights.

The Bergamot runtime and model sources are available through the links above.
The unmodified publisher JavaScript and WASM files are checksummed after
download. Language Lens's separate `bergamot_host.cjs` supplies local file
loading and a bounded text protocol; it does not modify the publisher files.
The Node distribution's complete LICENSE and third-party notices are stored
alongside `node.exe`. Model license notices and links are also retained in the
catalogue. The Mozilla Public License text is at https://www.mozilla.org/MPL/2.0/.

No TranslateLocally executable or shared TranslateLocally settings are used in
production. Only active-pair backends enter memory. The Settings retention
toggle controls whether they survive between captures; it defaults to off.
