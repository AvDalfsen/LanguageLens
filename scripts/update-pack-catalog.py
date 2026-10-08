"""Maintainer-only: pin official PyPI artifacts; never resolves versions at app runtime."""
import json
from pathlib import Path
from urllib.request import urlopen

PINS = {"janome": "0.5.0", "jieba": "0.42.1", "pyopenjtalk-plus": "0.4.1.post9",
        "sudachipy": "0.7.0", "sudachidict-core": "20260723.1"}


def main():
    artifacts = {}
    for package, version in PINS.items():
        with urlopen(f"https://pypi.org/pypi/{package}/{version}/json", timeout=30) as response:
            files = json.load(response)["urls"]
        for tag in (("cp310", "cp311", "cp312") if package == "pyopenjtalk-plus" else ("any",)):
            candidates = [f for f in files if (
                f["filename"] == f"jieba-{version}.tar.gz" if package == "jieba" else
                f["filename"].endswith(f"{tag}-{tag}-win_amd64.whl") if package == "pyopenjtalk-plus" else
                f["filename"].endswith("cp310-abi3-win_amd64.whl") if package == "sudachipy" else
                f["filename"].endswith("none-any.whl"))]
            if len(candidates) != 1:
                raise RuntimeError(f"Expected exactly one artifact for {package}/{tag}")
            item = candidates[0]
            artifacts[f"{package}-{tag}"] = {"distribution": package, "version": version,
                "filename": item["filename"], "url": item["url"], "bytes": item["size"],
                "sha256": item["digests"]["sha256"], "format": "sdist" if package == "jieba" else "wheel"}
    catalog = {"schema": 1, "artifacts": artifacts, "packs": {
        "ja-text": {"name": "Japanese word lookup", "artifacts": ["janome-any"], "modules": ["janome"]},
        "zh-text": {"name": "Chinese word lookup", "artifacts": ["jieba-any"], "modules": ["jieba"]},
        "ja-speech": {"name": "Japanese pronunciation", "artifacts": ["pyopenjtalk-plus-{python}", "sudachipy-any", "sudachidict-core-any"],
                      "modules": ["pyopenjtalk", "sudachipy", "sudachidict_core"]}}}
    path = Path(__file__).resolve().parents[1] / "src/language_lens/data/language-packs.json"
    path.write_text(json.dumps(catalog, indent=2) + "\n", encoding="utf-8")
    print(f"Pinned {len(artifacts)} official artifacts in {path}")


if __name__ == "__main__":
    main()
