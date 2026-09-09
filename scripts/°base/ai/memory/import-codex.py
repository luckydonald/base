#!/usr/bin/env python3
"""Assign one native Codex ad-hoc note to the current project."""
from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path


def load_hook():
    hook = Path(__file__).resolve().parents[1] / "hooks" / "record-codex-memory" / "hook.py"
    specification = importlib.util.spec_from_file_location("record_codex_memory", hook)
    if specification is None or specification.loader is None:
        raise RuntimeError(f"cannot load {hook}")
    # end if
    module = importlib.util.module_from_spec(specification)
    specification.loader.exec_module(module)
    return module
# end def


def project_root() -> Path:
    result = subprocess.run(
        ["git", "rev-parse", "--show-toplevel"], capture_output=True, text=True
    )
    if result.returncode != 0 or not result.stdout.strip():
        raise RuntimeError("run this command from a Git repository")
    # end if
    return Path(result.stdout.strip()).resolve()
# end def


def main(argv: list[str] | None = None) -> int:
    args = argv if argv is not None else sys.argv[1:]
    ignored = "--ignore" in args
    positional = [arg for arg in args if arg != "--ignore"]
    as_name: str | None = None
    if "--as" in positional:
        index = positional.index("--as")
        if index + 1 >= len(positional):
            print("--as requires a markdown filename", file=sys.stderr)
            return 2
        # end if
        as_name = positional[index + 1]
        del positional[index:index + 2]
    # end if
    if len(positional) != 1:
        print("Usage: import-codex.py <note.md> [--as <filename.md>] [--ignore]", file=sys.stderr)
        return 2
    # end if
    try:
        module = load_hook()
        repository = module.codex_memory_dir()
        if repository is None:
            raise RuntimeError("Codex memory directory is unavailable")
        # end if
        root = project_root()
        changes = module.import_native_note(
            repository, root, positional[0], ignored=ignored, as_name=as_name
        )
        module.commit_project_memory(root, changes)
    except RuntimeError as exc:
        print(f"import-codex-memory: {exc}", file=sys.stderr)
        return 1
    # end try
    return 0
# end def


if __name__ == "__main__":
    raise SystemExit(main())
# end if
