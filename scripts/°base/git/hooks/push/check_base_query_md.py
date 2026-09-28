#!/usr/bin/env python3
"""Pre-push guard (pre-commit `stages: [pre-push]`, `files: ^ai/query\\.md$`):
reject a push from the `luckydonald/base` repo itself if `ai/query.md` is part
of the pushed diff -- this repo must log to `ai/°base/query.md` instead (see
`scripts/°base/ai/hooks/_lib.py`'s `resolve_log_path`).

Deliberately self-contained: duplicates the small `_is_inside_base_repo`/
`_main_checkout_root` helpers from
`scripts/°base/ai/hooks/°commit_style_lib/__init__.py` rather than importing
across the `ai/hooks` <-> `git` tree boundary (this codebase's existing
convention for tiny helpers; see that module's own docstring and
`°split_lib/classify.py`'s comment about duplicating constants from
`get-base.py`).

Invocation contract: pre-commit only runs this hook when `ai/query.md` is
already known to have changed in the pushed range (via the `files:` filter),
so this script only needs to answer "is this the base repo" -- no separate
"did the diff touch ai/query.md" check is needed here.
"""
from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path


def _git_text(*args: str, cwd: Path | str | None = None) -> str:
    result = subprocess.run(["git", *args], capture_output=True, text=True, cwd=cwd)
    return (result.stdout or "").strip()


def _main_checkout_root(cwd: Path) -> Path | None:
    common_dir_text = _git_text("rev-parse", "--git-common-dir", cwd=cwd)
    if not common_dir_text:
        return None
    common_dir = Path(common_dir_text)
    if not common_dir.is_absolute():
        common_dir = cwd / common_dir
    common_dir = common_dir.resolve()
    if common_dir.name != ".git":
        return None
    return common_dir.parent


def _is_inside_base_repo(cwd: Path) -> bool:
    root = cwd
    if root.name != "base":
        root = _main_checkout_root(cwd)
        if root is None or root.name != "base":
            return False
    origin = _git_text("remote", "get-url", "origin", cwd=root)
    return bool(re.search(r"(^|[:/])luckydonald/base(\.git)?/?$", origin, re.I))


def main(argv: list[str] | None = None) -> int:
    if not _is_inside_base_repo(Path.cwd()):
        return 0

    print(
        "Push blocked: ai/query.md is part of this push, but this is the "
        "luckydonald/base repo itself, which must log to ai/°base/query.md "
        "instead (see resolve_log_path() in scripts/°base/ai/hooks/_lib.py). "
        "Move the content there before pushing.",
        file=sys.stderr,
    )
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
