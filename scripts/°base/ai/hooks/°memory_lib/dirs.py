"""Shared resolution of a project's valid memory directories."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from _lib import _is_inside_base_repo  # noqa: E402


def memory_dirs(subproject: Path) -> tuple[Path, Path]:
    """(primary, secondary) memory dirs under `subproject`, primary first.

    Inside the base repo: primary=ai/°base/memory, secondary=ai/memory --
    memories about developing the base tooling itself default there, but a
    memory relevant to consuming repos too can live in the secondary,
    subproject-facing `ai/memory/` instead (see `scripts/°base/ai/memory/promote.py`).
    Elsewhere: primary=ai/memory, secondary=ai/°base/memory (unused/never
    created outside the base repo, but always returned as a Path so callers
    have a uniform two-dir shape to check).
    """
    base_dir = subproject / "ai" / "°base" / "memory"
    root_dir = subproject / "ai" / "memory"
    if _is_inside_base_repo(subproject):
        return base_dir, root_dir
    return root_dir, base_dir
