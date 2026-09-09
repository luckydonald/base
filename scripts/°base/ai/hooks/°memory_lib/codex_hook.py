"""Load `record-codex-memory/hook.py` as a module for reuse by CLI scripts."""
from __future__ import annotations

import importlib.util
from pathlib import Path


def load_codex_hook_module() -> object:
    hook = Path(__file__).resolve().parents[1] / "record-codex-memory" / "hook.py"
    specification = importlib.util.spec_from_file_location("record_codex_memory", hook)
    if specification is None or specification.loader is None:
        raise RuntimeError(f"cannot load {hook}")
    module = importlib.util.module_from_spec(specification)
    specification.loader.exec_module(module)
    return module
