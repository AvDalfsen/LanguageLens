"""Expand English to all 22 existing catalogue recognizers with a new holdout.

Only development checkpoints can be reused. Earlier English validation is
discarded. Every candidate, including cross-script probes, sees identical
English pixels, baseline/current settings and fresh validation passages.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import sys

spec = importlib.util.spec_from_file_location("joint_benchmark", Path(__file__).with_name("verify-ocr-joint.py"))
joint = importlib.util.module_from_spec(spec)
spec.loader.exec_module(joint)
joint.bench.CANDIDATES["en"] = list(joint.bench.MODELS)
joint.FRESH_TEXTS = Path(__file__).parent / "data/ocr-joint-english-validation-texts.json"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path("artifacts/ocr-joint-english"))
    parser.add_argument("--development-checkpoint", type=Path)
    parser.add_argument("--model-cache", type=Path, default=Path("artifacts/ocr-models/models"))
    args = parser.parse_args()
    original_fingerprint = joint.fingerprint
    checkpoint = (json.loads(args.development_checkpoint.read_text(encoding="utf-8"))
                  if args.development_checkpoint else None)

    def fingerprint(language, development, fresh, incumbent, current):
        _identity, inputs = original_fingerprint(language, development, fresh, incumbent, current)
        inputs["english_catalogue_probe"] = {
            "script_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            "fresh_text_sha256": hashlib.sha256(joint.FRESH_TEXTS.read_bytes()).hexdigest(),
            "development_checkpoint": str(args.development_checkpoint) if checkpoint else None,
            "checkpoint_sha256": hashlib.sha256(args.development_checkpoint.read_bytes()).hexdigest() if checkpoint else None,
            "discarded_checkpoint_validation": True,
        }
        identity = hashlib.sha256(json.dumps(inputs, sort_keys=True).encode()).hexdigest()
        target = args.output / "en.json"
        if checkpoint and not target.exists():
            assert checkpoint["language"] == "en" and checkpoint["incumbent"] == incumbent
            assert checkpoint["current"] == current
            assert checkpoint["inputs"]["runtime"] == inputs["runtime"]
            assert json.dumps(checkpoint["inputs"]["development"]) == json.dumps(inputs["development"])
            assert json.dumps(checkpoint["inputs"]["shared_models"]) == json.dumps(inputs["shared_models"])
            # Reuse only identical development observations, never the prior
            # frozen choice, validation rows, gates, or summary.
            models = {model: {key: copy.deepcopy(value[key]) for key in
                             ("assets", "initial", "winner", "tuning") if key in value}
                      for model, value in checkpoint["models"].items()}
            joint.experiment.write_json(target, {"language": "en", "identity": identity, "inputs": inputs,
                                                "incumbent": incumbent, "current": current, "models": models})
        return identity, inputs

    joint.fingerprint = fingerprint
    sys.argv = [sys.argv[0], "--output", str(args.output), "--model-cache", str(args.model_cache),
                "--languages", "en", "--resume"]
    joint.main()


if __name__ == "__main__":
    main()
