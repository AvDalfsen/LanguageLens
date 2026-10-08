"""Opt-in multilingual SBD checks and isolated old/new translation comparison."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import time


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--fixtures", type=Path, required=True)
    parser.add_argument("--download", action="store_true")
    parser.add_argument("--legacy", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args()
    root = args.output.resolve()
    root.mkdir(parents=True, exist_ok=True)
    packages = args.fixtures.resolve() / "data/argos-translate/packages"
    os.environ.update(LOCALAPPDATA=str(root), XDG_DATA_HOME=str(root / "data"),
                      XDG_CONFIG_HOME=str(root / "config"), XDG_CACHE_HOME=str(root / "cache"),
                      ARGOS_PACKAGES_DIR=str(packages), ARGOS_MODEL_PROVIDER="OPENNMT",
                      ARGOS_CHUNK_TYPE="ARGOSTRANSLATE" if args.legacy else "MINISBD", ARGOS_DEBUG="0")
    import ctypes
    if sys.platform == "win32":
        ctypes.windll.kernel32.SetErrorMode(3)
    from language_lens.services.offline import no_network
    from language_lens.services import sentence_models
    corpus = json.loads((Path(__file__).resolve().parents[1] / "tests/data/sentence-boundaries.json").read_text("utf-8"))
    if args.legacy:
        import stanza
        import argostranslate.translate as backend
        from argostranslate import package, settings
        settings.device, settings.intra_threads, settings.inter_threads = "cpu", 2, 1
        original = stanza.Pipeline
        def local_pipeline(*positional, **keywords):
            keywords["download_method"] = stanza.DownloadMethod.NONE
            return original(*positional, **keywords)
        stanza.Pipeline = local_pipeline
        translate = backend.translate
    else:
        if args.download:
            sentence_models.prepare([item["language"] for item in corpus], print, lambda _item: None)
        from language_lens.services.translation import ArgosTranslator
        translator = ArgosTranslator()
        package, backend = translator._modules()
        translate = translator.translate
    results = {"boundaries": [], "translations": [], "ok": True}
    started = time.monotonic()
    with no_network():
        for index, item in enumerate(corpus):
            text = item.get("separator", " ").join(item["sentences"])
            if args.legacy:
                if item["language"] not in ("en", "nl", "pt"):
                    continue
                language = item["language"]
                target = "nl" if language == "en" else "en"
                translation = next(lang for lang in backend.get_installed_languages() if lang.code == language).get_translation(
                    next(lang for lang in backend.get_installed_languages() if lang.code == target))
                actual = translation.underlying.sentencizer.split_sentences(text)
            else:
                actual = sentence_models.split(text, item["language"])
            results["boundaries"].append({"case": index, "language": item["language"], "text": text,
                                          "expected": item["sentences"], "actual": actual, "match": actual == item["sentences"]})
            if not args.legacy:
                results["ok"] &= actual == item.get("baseline", item["sentences"])
            for target in ({"en": ("nl",), "nl": ("en",), "pt": ("en", "nl")}.get(item["language"], ())):
                translated = translate(text, item["language"], target)
                results["translations"].append({"case": index, "source": item["language"], "target": target,
                                               "text": text, "output": translated})
                results["ok"] &= bool(translated.strip())
        if not args.legacy:
            # Every language also exercises blank input.
            for language in sentence_models.catalog()["languages"]:
                assert sentence_models.split("", language) == []
            assert not any(name in sys.modules for name in ("stanza", "torch", "spacy"))
    results["seconds"] = round(time.monotonic() - started, 3)
    path = root / ("legacy.json" if args.legacy else "minisbd.json")
    path.write_text(json.dumps(results, ensure_ascii=False, indent=2), "utf-8")
    if not args.legacy:
        child = subprocess.run([sys.executable, __file__, "--legacy", "--output", str(root),
                                "--fixtures", str(args.fixtures.resolve())], capture_output=True, timeout=300)
        if child.returncode:
            (root / "legacy-error.log").write_bytes(child.stdout + child.stderr)
            raise RuntimeError("Legacy comparison failed; see legacy-error.log")
        old = json.loads((root / "legacy.json").read_text("utf-8"))
        previous = {(item["case"], item["target"]): item["output"] for item in old["translations"]}
        changes = [item for item in results["translations"] if item["output"] != previous[(item["case"], item["target"])]]
        results["ok"] &= not changes
        summary = {"sentence_cases": len(results["boundaries"]),
                   "languages": len({item["language"] for item in results["boundaries"]}),
                   "boundary_mismatches": [item for item in results["boundaries"] if not item["match"]],
                   "translation_cases": len(results["translations"]), "translation_changes": changes,
                   "legacy_boundary_mismatches": [item for item in old["boundaries"] if not item["match"]]}
        (root / "comparison.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), "utf-8")
        print(json.dumps({key: len(value) if isinstance(value, list) else value for key, value in summary.items()}))
    return 0 if results["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
