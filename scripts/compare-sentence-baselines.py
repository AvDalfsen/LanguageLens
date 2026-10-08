"""Compare the multilingual fixture against Stanza's default tokenizer models.

Stanza/Torch are development-only dependencies for this opt-in comparison.
Existing Argos-package baseline comparisons remain in verify-sentences.py.
"""
import argparse
import json
import os
from pathlib import Path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--languages", nargs="+", default=["ar", "zh", "ja"])
    parser.add_argument("--download", action="store_true")
    args = parser.parse_args()
    root = args.output.resolve()
    root.mkdir(parents=True, exist_ok=True)
    os.environ["LOCALAPPDATA"] = str(root)
    from language_lens.services.offline import no_network
    import stanza
    corpus = json.loads((Path(__file__).resolve().parents[1] / "tests/data/sentence-boundaries.json").read_text("utf-8"))
    results = []
    for language in args.languages:
        code = {"pb": "pt", "zh": "zh-hans"}.get(language, language)
        if args.download:
            stanza.download(code, model_dir=str(root / "stanza"), processors="tokenize", verbose=False)
        with no_network():
            pipeline = stanza.Pipeline(code, dir=str(root / "stanza"), processors="tokenize",
                                       download_method=stanza.DownloadMethod.NONE, use_gpu=False,
                                       logging_level="ERROR")
            for index, item in enumerate(corpus):
                if item["language"] != language:
                    continue
                text = item.get("separator", " ").join(item["sentences"])
                actual = [sentence.text for sentence in pipeline(text).sentences]
                results.append({"case": index, "language": language, "text": text,
                                "expected": item["sentences"], "actual": actual, "match": actual == item["sentences"]})
    (root / "stanza-comparison.json").write_text(json.dumps(results, ensure_ascii=False, indent=2), "utf-8")
    print(json.dumps({"cases": len(results), "mismatches": sum(not item["match"] for item in results)}))


if __name__ == "__main__":
    main()
