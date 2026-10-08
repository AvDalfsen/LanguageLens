"""Maintainer command: pin MiniSBD release assets for every Lens text language."""
import json
from pathlib import Path
from urllib.request import Request, urlopen

from language_lens.config import LANGUAGES

RELEASE = "v0.0.1"


def main():
    request = Request(f"https://api.github.com/repos/LibreTranslate/MiniSBD/releases/tags/{RELEASE}",
                      headers={"User-Agent": "LanguageLens-catalog"})
    with urlopen(request, timeout=30) as response:
        release = json.load(response)
    available = {item["name"]: item for item in release["assets"]}
    languages = {code: {"pb": "pt", "zh": "zh-hans"}.get(code, code) for _name, code in LANGUAGES}
    models = {}
    for code in sorted(set(languages.values())):
        item = available[f"{code}.onnx"]
        digest = item.get("digest") or ""
        if not digest.startswith("sha256:"):
            raise RuntimeError(f"Upstream does not publish a SHA-256 for {code}; review and hash this artifact explicitly.")
        models[code] = {"url": item["browser_download_url"], "bytes": item["size"],
                        "sha256": digest.removeprefix("sha256:")}
    path = Path(__file__).resolve().parents[1] / "src/language_lens/data/sentence-models.json"
    path.write_text(json.dumps({"schema": 1, "release": RELEASE, "languages": languages, "models": models}, indent=2) + "\n", "utf-8")
    print(f"Pinned {len(models)} models for {len(languages)} language choices; total {sum(item['bytes'] for item in models.values()) / 1e6:.1f} MB")


if __name__ == "__main__":
    main()
