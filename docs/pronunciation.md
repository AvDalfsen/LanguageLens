# Pronunciation

[Documentation](README.md) · [Language support](languages.md)

## Download a voice

1. Turn on the read-aloud checkbox in Settings.
2. Choose a voice for **Text language**. English offers US/UK voices; Portuguese (Portugal/Brazil) follows the selected text language.
3. Read **Voice details and licence**, then click **Download voice**. The button shows the download size.
4. Wait for verification, and use **Hear sample** to preview it.

The upcoming interface calls the checkbox **Enable read aloud**; earlier previews use a longer label. All 25 text-language choices have a catalogue voice. Availability is not a native-speaker quality rating.

Voices usually need about 63–114 MB each; Japanese pronunciation also needs a separate pack. Settings displays missing components and progress. Downloads can be cancelled and retried; completed files are retained. **Check voice files** verifies installed data and fetches missing/damaged files.

No Windows voice packs, cloud API keys, or paid speech service are required. Runtime and model terms are separate from the app's MIT licence. Some voices have noncommercial terms or incomplete licence information; see [speech notices](../THIRD_PARTY_SPEECH.md).

## Play words and sentences

Capture text and choose **Read selection** to hear the original OCR text, even before translation finishes. A pinned word popup offers **Pronounce word**. Nothing plays on hover or automatically.

**Cancel audio** stops preparation; **Stop audio** stops playback. Closing the screenshot cancels both. The first playback prepares audio locally; subsequent playback of the same text, voice, and speed within that review reuses it. Selections are limited to 2,000 characters for speech.

**Pronunciation speed** ranges from 0.5× to 1.5× without changing pitch. Adjusting it stops current audio; play again at the new speed. The choice is remembered and also applies to samples.

## Optional phonetic notation

Turn on the pronunciation-notation checkbox to show sound symbols in word popups. Earlier previews call it **Show IPA in word popups**. It is off by default and independent of audio. Most languages do not require a downloaded audio model for notation; Japanese needs its pronunciation pack.

English US/UK and Portuguese Portugal/Brazil use audited **Estimated IPA** display conventions. Other languages preserve frontend output labelled **Engine notation**. Japanese isolated readings are not advertised as reliable sentence-context pitch accent.

**From selected sentence** means the word's exact occurrence was aligned with sentence phonemes. **Word in isolation** marks a fallback. Alignment does not guarantee linguistic correctness: names, OCR errors, ambiguous words, and code-switching can still produce mistakes.

IPA is an estimate, not a measurement of the voice or an authoritative dictionary. Use it alongside listening and other learning references. The [IPA audit](ipa-audit.md) preserves the conventions, tests, and known limits.

## Storage

Voices live under %LOCALAPPDATA%/LanguageLens/voices. Replay audio is kept in memory and cleared when the review closes; there is no permanent recording history. [Privacy and local files](privacy.md) covers temporary data and crash leftovers.
