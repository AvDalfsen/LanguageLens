"""Read-only upstream catalogue inspection; never downloads audio models."""
import hashlib
import json
import sys
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import quote
from urllib.request import urlopen

from language_lens.services.voices import REVISION, REPOSITORY

IDS = (
    "ar_JO-kareem-medium", "cs_CZ-jirka-medium", "da_DK-talesyntese-medium",
    "nl_NL-pim-medium", "fi_FI-harri-medium", "fr_FR-siwis-medium",
    "de_DE-thorsten-high", "el_GR-rapunzelina-medium", "hi_IN-pratham-medium",
    "hu_HU-anna-medium", "it_IT-paola-medium", "ja_JP-hi_fi_captain-medium",
    "ko_KR-kss-medium", "no_NO-talesyntese-medium", "pl_PL-gosia-medium",
    "ro_RO-mihai-medium", "ru_RU-denis-medium", "es_ES-davefx-medium",
    "sv_SE-nst-medium", "tr_TR-dfki-medium", "uk_UA-mykyta-high", "zh_CN-huayan-medium",
    "it_IT-serena-medium",
)


def read(url):
    with urlopen(url, timeout=30) as response:
        return response.read()


def main():
    if "--japanese-package" in sys.argv:
        info = json.loads(read("https://pypi.org/pypi/pyopenjtalk-plus/json"))
        print(json.dumps(dict(version=info["info"]["version"],
                             requirements=info["info"]["requires_dist"],
                             windows=[x["filename"] for x in info["urls"] if "win_amd64" in x["filename"]])))
        return
    catalogue = json.loads(read(f"{REPOSITORY}/resolve/{REVISION}/voices.json"))
    metadata = json.loads(read(f"https://huggingface.co/api/models/rhasspy/piper-voices/revision/{REVISION}?blobs=true"))
    siblings = {item["rfilename"]: item for item in metadata["siblings"]}

    def inspect(voice_id):
        voice = catalogue[voice_id]
        model_path = next(path for path in voice["files"] if path.endswith(".onnx"))
        directory = model_path.rsplit("/", 1)[0]
        files = []
        config = None
        card = ""
        for path in (model_path, model_path + ".json", directory + "/MODEL_CARD"):
            if path.endswith(".onnx"):
                lfs = siblings[path]["lfs"]
                size, checksum = lfs["size"], lfs["sha256"]
            else:
                data = read(f"{REPOSITORY}/resolve/{REVISION}/{quote(path)}")
                size, checksum = len(data), hashlib.sha256(data).hexdigest()
                if path.endswith(".json"):
                    config = json.loads(data)
                else:
                    card = data.decode("utf-8")
            files.append([path.rsplit("/", 1)[1], size, checksum])
        return dict(id=voice_id, directory=directory, locale=voice["language"]["code"],
                    espeak=config.get("espeak"), phoneme_type=config.get("phoneme_type"),
                    vowel_clusters=config.get("vowel_clusters"), files=files, card=card)

    with ThreadPoolExecutor(max_workers=4) as pool:
        for item in pool.map(inspect, IDS):
            print(json.dumps(item, ensure_ascii=True), flush=True)


if __name__ == "__main__":
    main()
