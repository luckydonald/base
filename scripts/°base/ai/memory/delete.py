#!/usr/bin/env python3
"""Delete one AI memory and create the required marked deletion commit."""

from __future__ import annotations

import importlib
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "hooks"))
from _lib import (  # noqa: E402
    _chdir_to_git_root,
    _encoded_project_dir,
    _subproject_root,
)

memory_lib = importlib.import_module("°memory_lib")


def _git_text(*args: str) -> str:
    result = subprocess.run(["git", *args], capture_output=True, text=True)
    return (result.stdout or "").strip()


def _usage() -> str:
    return "Usage: python3 scripts/°base/ai/memory/delete.py <filename-or-path>"


def main(argv: list[str] | None = None) -> int:
    args = argv if argv is not None else sys.argv[1:]
    if len(args) != 1:
        print(_usage(), file=sys.stderr)
        return 2

    name = Path(args[0]).name
    if not name.endswith(".md") or name in {"", ".", ".."}:
        print("Memory name must be a markdown filename ending in .md.", file=sys.stderr)
        return 2

    subproject = _subproject_root()
    src_dir = _encoded_project_dir(subproject) / "memory"
    _chdir_to_git_root()

    dst_dir = None
    dst_dir_rel = ""
    dst_rel = ""
    for candidate in memory_lib.memory_dirs(subproject):
        candidate_rel = str(candidate.relative_to(Path.cwd()))
        candidate_file_rel = f"{candidate_rel}/{name}"
        if memory_lib.is_tracked(candidate_file_rel):
            dst_dir, dst_dir_rel, dst_rel = candidate, candidate_rel, candidate_file_rel
            break

    if dst_dir is None:
        primary, secondary = memory_lib.memory_dirs(subproject)
        print(f"Memory is not tracked in {primary} or {secondary}: {name}", file=sys.stderr)
        return 1

    if not memory_lib.delete_memory(name, src_dir=src_dir, dst_dir=dst_dir, dst_dir_rel=dst_dir_rel):
        print(f"Failed to commit deletion of {dst_rel}", file=sys.stderr)
        return 1

    try:
        hook = memory_lib.load_codex_hook_module()
        repository = hook.codex_memory_repo()
        if repository is not None:
            changed = hook.delete_scoped_memory(repository, subproject, name)
            hook.commit_project_memory(subproject, changed)
        # end if
    except (OSError, RuntimeError) as exc:
        print(f"Deleted repo/Claude memory but could not remove Codex mirror: {exc}", file=sys.stderr)
        return 1
    # end try

    commit = _git_text("rev-parse", "--short", "HEAD")
    print(f"Deleted memory {name} in {commit}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
