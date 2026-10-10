# Supported languages

[Documentation](README.md) · [Pronunciation](pronunciation.md)

## Language choices

Choose the language written on screen under **Text language**, and the language you know under **Translate into**. These choices control text processing. **UI language**, in the top right of Settings, independently changes the interface language in the source app and next portable build.

The interface offers the same 25 choices, including both Portuguese variants. Languages appear under their own names, such as Nederlands, 日本語 and العربية. English is the default; changes apply immediately and are saved automatically. Arabic uses a right-to-left layout, with the selector still in the top right. No model or voice download is needed for UI translation.

Controls, status messages and tooltips are translated using the complete English messages as the reference. The longer user guides remain in English, as do upstream model/voice names, licence notices and some technical diagnostics. These are initial translations; native-speaker corrections are welcome.

| | | |
| --- | --- | --- |
| Arabic | Chinese | Czech |
| Danish | Dutch | English |
| Finnish | French | German |
| Greek | Hindi | Hungarian |
| Italian | Japanese | Korean |
| Norwegian | Polish | Portuguese (Portugal) |
| Portuguese (Brazil) | Romanian | Russian |
| Spanish | Swedish | Turkish |
| Ukrainian | | |

These are the 25 selectable text-language choices. They do not establish that every source/target pair is available or that all languages have equal recognition, translation, or pronunciation quality.

## What Settings checks

| Capability | What to expect |
| --- | --- |
| OCR | A local model selected for the text language's script. Small, stylized, curved, or vertical text can be difficult. |
| Translation | Directional Argos models. A direct route is used when available; other pairs can use two models through English. |
| Word lookup | OCR alignment and word segmentation. Japanese/Chinese use additional dictionary packs. |
| Read aloud | A downloadable catalogue voice for each text-language choice; 26 catalogue voices including both English accents. |
| Phonetic display | Audited estimated IPA conventions for English and Portuguese accents; labelled engine notation for other languages. |

Click **Download required files** for the chosen pair and wait for verification. Settings reports route/capabilities under **Technical details**. A missing route may need another target language or an upstream model that does not currently exist. A dropdown entry is not a promise of every possible translation direction.

## Optional language packs

Japanese and Chinese word dictionaries are downloaded with required files only when those are the text languages. Translating into Japanese/Chinese from another source does not require their source dictionaries.

Japanese pronunciation has an additional pack, downloaded with its voice or separately for notation. Other languages use the bundled pronunciation runtime. Packs and audio weights are separate; Settings shows missing sizes.

Packs are shared across language pairs and pinned to compatible versions. Updates can require another pack check. Use **Manage local files** to inspect or remove them. See [pack management](language-packs.md).

## Accuracy and validation

Word suggestions use words in isolation; the sentence translation provides context. Dictionary segmentation remains an estimate for names and unfamiliar compounds. Notation and audio can be wrong even when their source offsets align correctly.

Development checks cover multilingual sentence fixtures and selected OCR/translation/speech routes; this is not comprehensive native-speaker validation across all pairs. The [release verification record](release-building.md) and [sentence corpus](sentence-splitting.md) describe tested cases and limits.

If a language fails, [report the language pair and steps](https://github.com/AvDalfsen/LanguageLens/issues/new/choose). Include sanitized diagnostics if available; a private screenshot is not required.
