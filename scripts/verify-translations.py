"""Offline semantic checks against existing immutable fixtures; no downloads."""
import argparse
from dataclasses import asdict
import json
import os
from pathlib import Path
import re
import sys
import tempfile
import unicodedata


def contains(text, phrase):
    normalized = unicodedata.normalize("NFC", text).casefold().replace("’", "'")
    phrase = unicodedata.normalize("NFC", phrase).casefold().replace("’", "'")
    return re.search(r"(?<!\w)" + re.escape(phrase) + r"(?!\w)", normalized) is not None


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--models", type=Path, required=True)
    parser.add_argument("--sentences", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(root / "src"))
    corpus = json.loads((root / "tests/data/translation-quality.json").read_text("utf-8"))
    with tempfile.TemporaryDirectory(prefix="lens-quality-") as directory:
        data = Path(directory)
        os.environ.update(
            LOCALAPPDATA=str(data), XDG_DATA_HOME=str(data / "data"),
            XDG_CONFIG_HOME=str(data / "config"), XDG_CACHE_HOME=str(data / "cache"),
            ARGOS_PACKAGES_DIR=str(args.models.resolve()),
        )
        from language_lens.services import sentence_models
        from language_lens.services.offline import no_network
        from language_lens.services.translation import ArgosTranslator

        sentence_models.model_root = lambda: args.sentences.resolve()
        translator = ArgosTranslator()
        results = []
        with no_network():
            for case in corpus["cases"]:
                output = translator.translate(case["text"], case["source"], case["target"])
                words = translator.word_candidates(case["word"], case["source"], case["target"])
                missing = [
                    group for group in case["sentence_requires_any"]
                    if not any(contains(output, phrase) for phrase in group)
                ]
                matched = any(
                    contains(candidate, sense)
                    for candidate in words.candidates for sense in case["contextual_word_senses"]
                )
                results.append({
                    **case, "output": output, "words": asdict(words),
                    "missing_meaning_groups": missing, "sentence_ok": not missing,
                    "word_context_match": matched,
                })
    report = {
        "sentence_cases": len(results),
        "sentence_passes": sum(item["sentence_ok"] for item in results),
        "word_context_matches": sum(item["word_context_match"] for item in results),
        "results": results,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", "utf-8")
    print(json.dumps({key: value for key, value in report.items() if key != "results"}))
    return 0 if report["sentence_passes"] == report["sentence_cases"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
