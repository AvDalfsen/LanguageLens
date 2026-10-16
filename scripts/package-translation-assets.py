"""Package verified weights as pinned downloads, outside the app bundle."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil

import zstandard


ROOT = Path(__file__).resolve().parents[1]
CATALOG_PATH = ROOT / "src/language_lens/data/translation-providers.json"


def receipt(path):
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return {"bytes": path.stat().st_size, "sha256": digest.hexdigest()}


def package_models(catalog, source, output, release, *, update=False, models=('small','m2m')):
    output.mkdir(parents=True, exist_ok=True)
    base = f"https://github.com/{release['repository']}/releases/download/{release['tag']}"
    for kind in models:
        for item in catalog["models"][kind]["files"]:
            path = source / kind / item["name"]
            if receipt(path) != {key: item[key] for key in ("bytes", "sha256")}:
                raise RuntimeError(f"Unverified converted resource: {kind}/{item['name']}")
            asset = output / f"{kind}-{item['name']}.zst"
            temporary = asset.with_suffix(".part")
            try:
                with path.open("rb") as raw, temporary.open("wb") as packed:
                    with zstandard.ZstdCompressor(level=6).stream_writer(packed, size=item["bytes"]) as writer:
                        shutil.copyfileobj(raw, writer, length=1024 * 1024)
                compressed = receipt(temporary)
                metadata = {"url": f"{base}/{asset.name}", "compression": "zstd",
                            "compressed_bytes": compressed["bytes"], "compressed_sha256": compressed["sha256"]}
                if not update and any(item.get(key) != value for key, value in metadata.items()):
                    raise RuntimeError(f"Download does not match its pinned catalog: {asset.name}")
                temporary.replace(asset)
                item.pop("bundled", None)
                item.update(metadata)
            finally:
                temporary.unlink(missing_ok=True)
        print(f"{kind}: packaged verified downloads", flush=True)
    (output / "manifest.json").write_text(json.dumps({
        "release": release, "models": {kind: catalog["models"][kind] for kind in models}
    }, indent=2) + "\n", encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=ROOT / "build/translation-word-models")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--update-catalog", action="store_true", help="Deliberately pin a new model release.")
    parser.add_argument("--tag", help="New immutable model release tag; requires --update-catalog.")
    parser.add_argument('--group',choices=['words','en-nl'],default='words')
    args = parser.parse_args()
    catalog = json.loads(CATALOG_PATH.read_text("utf-8"))
    key='word_model_release' if args.group=='words' else 'en_nl_model_release'
    models=('small','m2m') if args.group=='words' else ('t5-en-nl-24l',)
    release = dict(catalog.get(key, {"repository": "AvDalfsen/LanguageLens"}))
    if args.tag:
        if not args.update_catalog:
            parser.error("--tag requires --update-catalog")
        release["tag"] = args.tag
    if not release.get("tag"):
        parser.error("A model release must be pinned with --tag and --update-catalog")
    package_models(catalog, args.source, args.output, release, update=args.update_catalog,models=models)
    shutil.copy2(ROOT / "THIRD_PARTY_TRANSLATION.md", args.output / "THIRD_PARTY_TRANSLATION.md")
    if args.update_catalog:
        catalog[key]=release
        CATALOG_PATH.write_text(json.dumps(catalog, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
