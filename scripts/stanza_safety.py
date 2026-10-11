"""Fail closed when source comparison tools load legacy PyTorch checkpoints."""
from importlib.metadata import version
import os

from packaging.version import Version


def require_safe_checkpoint_loading():
    # Torch applies this override even when a Stanza fallback explicitly passes
    # weights_only=False. Old Torch versions without the override are refused.
    if Version(version("torch")) < Version("2.6"):
        raise RuntimeError("Stanza comparisons require PyTorch 2.6 or newer for safe checkpoint loading.")
    os.environ.pop("TORCH_FORCE_NO_WEIGHTS_ONLY_LOAD", None)
    os.environ["TORCH_FORCE_WEIGHTS_ONLY_LOAD"] = "1"
