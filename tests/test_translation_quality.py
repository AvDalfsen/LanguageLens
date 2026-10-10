"""Optional real-model meaning checks run in an isolated fresh process."""
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest


def test_real_translation_meanings_with_existing_fixtures(tmp_path):
    root=Path(__file__).resolve().parents[1]
    models=Path(os.environ.get("LANGUAGE_LENS_TEST_TRANSLATIONS",root/"artifacts/offline-validation/data/argos-translate/packages"))
    sentences=Path(os.environ.get("LANGUAGE_LENS_TEST_SENTENCES",root/"artifacts/sentence-validation/LanguageLens/offline/sentences"))
    if not models.is_dir() or not sentences.is_dir():
        pytest.skip("Requires local Argos and MiniSBD fixtures; never downloads")
    output=tmp_path/"translation-quality.json"
    child=subprocess.run([sys.executable,str(root/"scripts/verify-translations.py"),"--models",str(models),
                          "--sentences",str(sentences),"--output",str(output)],capture_output=True,timeout=120)
    assert output.exists(),child.stderr.decode("utf-8",errors="replace")
    report=json.loads(output.read_text("utf-8"))
    failed=[item for item in report["results"] if not item["sentence_ok"]]
    assert child.returncode==0,failed or child.stderr.decode("utf-8",errors="replace")
    assert report["sentence_cases"]==len(report["results"])>=10
    # Word-context failures are visible quality debt, not fabricated contextual guarantees.
    assert report["sentence_passes"]==report["sentence_cases"]
