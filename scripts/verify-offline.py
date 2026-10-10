"""Opt-in integration check using isolated copies, never the user's installations."""
import argparse
from dataclasses import asdict
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile


def main():
    sys.stdout.reconfigure(encoding="utf-8", errors="backslashreplace")
    parser = argparse.ArgumentParser()
    parser.add_argument("--models", type=Path, required=True, help="Existing Argos packages to copy for testing.")
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1] / "artifacts" / "offline-validation"
    root.mkdir(parents=True, exist_ok=True)
    env = dict(os.environ, LOCALAPPDATA=str(root), XDG_DATA_HOME=str(root / "data"),
               XDG_CONFIG_HOME=str(root / "config"), XDG_CACHE_HOME=str(root / "cache"), QT_QPA_PLATFORM="offscreen",
               ARGOS_MODEL_PROVIDER="LIBRETRANSLATE")  # Lens must override this inherited cloud preference
    packages = root / "data" / "argos-translate" / "packages"
    env["ARGOS_PACKAGES_DIR"] = str(packages)
    packages.mkdir(parents=True, exist_ok=True)
    for name in ("translate-pt_en-1_9", "translate-en_nl-1_8", "translate-nl_en-1_8"):
        if not (packages / name).exists():
            shutil.copytree(args.models / name, packages / name)
    # The test harness imports Qt only after choosing its own app-data directory.
    os.environ.update({key: env[key] for key in ("LOCALAPPDATA", "XDG_DATA_HOME", "XDG_CONFIG_HOME", "XDG_CACHE_HOME", "QT_QPA_PLATFORM", "ARGOS_PACKAGES_DIR")})
    from PySide6.QtCore import QEventLoop, QRect, QTimer
    from PySide6.QtCore import Qt
    from PySide6.QtGui import QFont, QFontDatabase, QImage, QPainter, QPixmap
    from PySide6.QtWidgets import QApplication
    from language_lens.config import Settings
    from language_lens.services.offline import offline_ready
    app = QApplication([])
    QFontDatabase.addApplicationFont("C:/Windows/Fonts/segoeui.ttf")

    def worker(command, payload, scratch):
        process = subprocess.Popen([sys.executable, "-m", "language_lens.services.task_worker", command,
            "--scratch", str(scratch)], env=env, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        output, errors = process.communicate(json.dumps(payload, ensure_ascii=True).encode(), timeout=300)
        messages = [json.loads(line) for line in output.splitlines() if line.startswith(b"{")]
        for message in messages:
            if "progress" in message:
                print(message["progress"], flush=True)
        if process.returncode or not any(item.get("ok") for item in messages):
            raise RuntimeError(f"{command} failed: {messages[-2:]} {errors[-500:]!r}")
        return [message["result"] for message in messages if "result" in message]

    for source, target, text in (("pt", "en", "Olá! Este texto funciona sem internet."),
            ("nl", "en", "Dit is een zin. De vertaling werkt zonder internet."),
            ("pt", "nl", "Olá! Esta frase usa dois modelos locais.")):
        settings = Settings(source_language=source, target_language=target, speech_enabled=False)
        payload = {"settings": asdict(settings)}
        with tempfile.TemporaryDirectory(dir=root) as temporary:
            scratch = Path(temporary)
            print(f"PREPARE {source} → {target}", flush=True)
            worker("prepare", payload, scratch)
            assert offline_ready(source, target)
            results = worker("translate", {**payload, "text": text, "words": text.split()}, scratch)
            words = {word: value for result in results for word, value in result["words"].items()}
            assert results[0]["sentence"] and words and all(value["candidates"] for value in words.values())
            more = worker("more", {**payload, "word": text.split()[1]}, scratch)
            assert more[-1]["candidates"]
            image = QImage(1200, 120, QImage.Format.Format_RGB32)
            image.fill(Qt.GlobalColor.white)
            painter = QPainter(image)
            font = QFont("Segoe UI")
            font.setPixelSize(32)
            painter.setFont(font)
            painter.setPen(Qt.GlobalColor.black)
            painter.drawText(20, 65, text)
            painter.end()
            assert image.save(str(scratch / "crop.png"))
            lines = worker("ocr", {**payload, "selection_size": [1200, 120], "regions": [
                {"image": "crop.png", "retry": None, "offset": [0, 0], "size": [1200, 120], "mapping": [0, 0, 1, 1]}]}, scratch)
            assert lines[-1] and any("texto" in line["text"] or "zin" in line["text"] or "frase" in line["text"] for line in lines[-1])
            print(f"PASS {source} → {target}: fresh-process OCR + sentence + words + wider search", flush=True)
    # Exercise the actual Qt supervisor/result wiring too, not just worker CLI.
    from language_lens.ui.review import ReviewWindow
    desktop = QPixmap(1200, 600)
    desktop.fill(Qt.GlobalColor.white)
    painter = QPainter(desktop)
    painter.drawImage(0, 220, image)
    painter.end()
    window = ReviewWindow(desktop, QRect(0, 220, 1200, 120), settings)
    def wait_jobs():
        loop = QEventLoop()
        timer = QTimer()
        timer.setInterval(50)
        timer.timeout.connect(lambda: loop.quit() if not any(job.active for job in window._jobs if job) else None)
        deadline = QTimer()
        deadline.setSingleShot(True)
        deadline.timeout.connect(loop.quit)
        timer.start()
        deadline.start(150000)
        loop.exec()
        timer.stop()
        deadline.stop()
        assert all(not job.active for job in window._jobs if job), "Qt worker timed out"
    try:
        window.show()
        wait_jobs()
        assert window._hits and all(hit.translation and hit.translation.candidates for hit in window.canvas._hits)
        assert window.translation.text() and window.copy_button.isEnabled()
        original = window.canvas.capture
        window._retry_ocr()
        wait_jobs()
        assert window.canvas.capture is original and window._hits
        assert all(hit.translation and hit.translation.candidates for hit in window.canvas._hits)
        canvas = window.canvas
        canvas._hovered = canvas._hits[0]
        canvas._refresh_bubble()
        canvas._search_candidates()
        wait_jobs()
        assert canvas._hovered.lookup_text in canvas._expanded_translations
        print("PASS Qt review: OCR → translation → retry same screenshot → wider search", flush=True)
    finally:
        window.close()
        window.deleteLater()
        app.processEvents()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
