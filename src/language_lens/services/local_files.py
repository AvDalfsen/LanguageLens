"""Read-only file previews, collected in the status worker without networking."""
from pathlib import Path
from language_lens.config import settings_path
from language_lens.services import translation_assets as assets, sentence_models, language_packs


def pair_file_summary(settings, translator, route):
    rows, download, unknown = [], 0, False
    locations = [str(settings_path().parent / "removed-translation-models")]
    for model_id in assets.model_ids(settings.source_language, settings.target_language):
        model = assets.catalog()["models"][model_id]
        rows.append({"name": model_id, "size": sum(item["bytes"] for item in model["files"]),
                     "installed": all(assets.valid(assets.model_path(model_id) / item["name"], item) for item in model["files"])})
        for item in model["files"]:
            if not assets.valid(assets.model_path(model_id) / item["name"], item):
                download += item["compressed_bytes"]
    if assets.selection(settings.source_language, settings.target_language)["full"]:
        for kind in ("node_runtime", "bergamot_runtime"):
            info = assets.catalog()[kind]
            installed = all(assets.valid(assets.root() / kind / item["name"], item) for item in info["files"])
            rows.append({"name": kind, "size": sum(item["bytes"] for item in info["files"]), "installed": installed})
            if not installed:
                if info.get("bytes") is not None:
                    download += info["bytes"]
                else:
                    unknown = True
    if route:
        for item in route:
            root = Path(item.package_path)
            rows.append({"name": f"{item.from_code} → {item.to_code}",
                         "size": sum(path.stat().st_size for path in root.rglob("*") if path.is_file()), "installed": True})
    elif translator.argos_required(settings.source_language, settings.target_language):
        unknown = True
    if translator.argos_required(settings.source_language, settings.target_language):
        package, _ = translator._modules()
        locations.append(str(Path(package.settings.package_data_dir).parent / "language-lens-removed-models"))
    langs = dict.fromkeys([settings.source_language, *(item.from_code for item in route)])
    for lang in langs:
        info = sentence_models.catalog()["models"][sentence_models.model_code(lang)]
        path = sentence_models.model_path(lang)
        from language_lens.services.voices import valid_file
        installed = valid_file(path, info["bytes"], info["sha256"])
        rows.append({"name": f"{lang} · MiniSBD", "size": info["bytes"], "installed": installed})
        if not installed:
            download += info["bytes"]
    from language_lens.services.offline import ocr_models, matches
    for name, path, _url, digest, existing in ocr_models(settings.source_language):
        if path.exists():
            rows.append({"name": f"OCR · {name}", "size": path.stat().st_size, "installed": True})
        elif not matches(existing, digest):
            unknown = True
    pack = language_packs.text_pack(settings.source_language, settings.word_lookup_enabled)
    if pack and not language_packs.ready(pack):
        download += language_packs.download_bytes(pack)
    return {"files": rows, "download_bytes": download, "download_unknown": unknown,
            "backup_locations": locations}
