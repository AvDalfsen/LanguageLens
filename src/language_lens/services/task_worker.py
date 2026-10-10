"""Protocol worker. Text/image payloads are never logged or sent over the network."""
from __future__ import annotations

import argparse
from contextlib import nullcontext, redirect_stdout, redirect_stderr
from dataclasses import asdict
import json
import os
from pathlib import Path
import sys

from language_lens.config import validate_settings
from language_lens.services.offline import no_network, prepare


def execute(command, payload, scratch, emit):
    settings = validate_settings(payload["settings"])
    source, target = settings.source_language, settings.target_language
    from language_lens.services import language_packs as packs
    report = lambda text: emit({"progress": text})
    progress = lambda item: emit({"download": asdict(item)})
    if command in ("pack-install", "pack-remove"):
        pack = payload["pack"]
        if command == "pack-install":
            packs.install(pack, report, progress)
        else:
            packs.remove(pack)
        return
    from language_lens.services.translation import ArgosTranslator
    translator = ArgosTranslator()
    if command == "status":
        from language_lens.services.offline import offline_ready
        ready, route, packages = False, [], []
        ready = translator.is_pair_installed(source, target)
        if ready:
            packages = translator.route(source, target)
            route = [packages[0].from_code, *(item.to_code for item in packages)] if packages else [source]
        emit({"result": {"source": source, "target": target, "ready": ready,
                          "route": route, "prepared": offline_ready(source, target, route=packages), "packs": packs.inventory()}})
        return
    if command in ("install", "repair", "remove", "prepare"):
        package, _backend = translator._modules()
        from language_lens.services.model_download import configure_cache
        configure_cache(package, scratch)
        from filelock import FileLock
        from language_lens.services.model_management import recover_transactions, remove_route
        root = Path(package.settings.package_data_dir)
        root.parent.mkdir(parents=True, exist_ok=True)
        with FileLock(str(root.parent / "language-lens-models.lock"), timeout=10):
            recover_transactions(root)
            if command == "prepare":
                prepare(source, target, report, progress)
            elif command == "remove":
                remove_route(source, target, report)
            elif command == "repair":
                translator.install_pair(source, target, report, progress, staged=True, force=True)
            else:
                translator.install_pair(source, target, report, progress, staged=True)
        return
    if command == "ocr":
        from PySide6.QtCore import QPoint, QSize
        from PySide6.QtGui import QImage
        from language_lens.services.tasks import OcrTask, create_ocr_engine, recognize_regions
        if not payload["regions"]:
            emit({"result": []})
            return
        engine = create_ocr_engine(settings)
        regions = []
        for region in payload["regions"]:
            task = OcrTask(QImage(str(scratch / region["image"])), settings,
                retry_image=QImage(str(scratch / region["retry"])) if region["retry"] else None,
                retry_offset=QPoint(*region["offset"]), selection_size=QSize(*region["size"]),
                retry_scale=region.get("retry_scale", 2.0))
            regions.append((task, region["mapping"]))
        lines = recognize_regions(regions, QSize(*payload["selection_size"]), engine, report, source)
        emit({"result": [asdict(line) for line in lines]})
    elif command == "more":
        emit({"result": asdict(translator.word_candidates(payload["word"], source, target, expanded=True))})
    elif command == "translate":
        from language_lens.services.translation import selection_results
        for sentence, translations in selection_results(translator, payload["text"], payload["words"], source, target, report):
            emit({"result": {"sentence": sentence, "words": {word: asdict(value) for word, value in translations.items()}}})
    else:
        raise ValueError("Unknown task command.")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=("status", "ocr", "translate", "more", "install", "prepare", "repair", "remove", "pack-install", "pack-remove"))
    parser.add_argument("--scratch", type=Path, required=True)
    args = parser.parse_args()
    output = sys.stdout
    emit = lambda message: print(json.dumps(message, ensure_ascii=True), file=output, flush=True)
    # Suppress third-party debug output, including possible captured text.
    if sys.platform == "win32":
        import ctypes
        ctypes.windll.kernel32.SetErrorMode(3)
    with open(os.devnull, "w", encoding="utf-8") as discard:
        try:
            payload = json.loads(sys.stdin.buffer.read(4 * 1024 * 1024))
            with redirect_stdout(discard), redirect_stderr(discard):
                from language_lens.services.diagnostics import initialize
                initialize(f"worker-{args.command}")
                online = args.command in ("install", "prepare", "repair", "remove", "pack-install", "pack-remove")
                with nullcontext() if online else no_network():
                    execute(args.command, payload, args.scratch, emit)
            emit({"ok": True})
            return 0
        except Exception as exc:
            from language_lens.services.diagnostics import record_failure
            record_failure(f"worker-{args.command}", exc)
            # Exception strings may contain screenshots' words; never expose them.
            from language_lens.services.errors import describe_failure
            emit(describe_failure(exc, args.command).event())
            return 1


if __name__ == "__main__":
    raise SystemExit(main())
