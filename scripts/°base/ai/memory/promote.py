#!/usr/bin/env python3
"""Move a base-repo memory between `ai/°base/memory/` and root `ai/memory/`.

`ai/°base/memory/` holds memories about developing/maintaining the base
tooling itself. Root `ai/memory/` is the same directory name consuming repos
use for their own memory, so a memory promoted there becomes "available to
subprojects" through base's normal template-propagation, instead of staying
base-tooling-only.

Promoting (the default) moves `ai/°base/memory/<name>` -> `ai/memory/<name>`.
`--demote` reverses that. `ai/°base/memory/MEMORY.md` is the superset index
(own + promoted memories): promoting rewrites its entry to a relative-link
stub instead of deleting it, and demoting rewrites that stub back to a bare
link. Root `ai/memory/MEMORY.md` only ever lists memories that actually live
there -- demoting removes its entry outright (a stub pointing into
`ai/°base/` would be a dangling link for subprojects, which have no such
dir). Any matching `.codex-sync.json` `sources`/`ignored` entry is relocated
to the destination directory's file (the two files otherwise stay fully
independent -- see `ai/memory/project_codex_memory_orphan_resource_bug.md`
and `°memory_lib/dirs.py`).
"""
from __future__ import annotations

import importlib
import json
import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "hooks"))
from _lib import (  # noqa: E402
    _chdir_to_git_root,
    _is_inside_base_repo,
    _subproject_root,
    base_ai_commit_subject,
)

memory_lib = importlib.import_module("°memory_lib")

_LINK_LINE_RE = re.compile(r"^(?P<prefix>-\s*\[[^\]]*\]\()(?P<target>[^()]+)(?P<suffix>\).*)$")


def _usage() -> str:
    return "Usage: python3 scripts/°base/ai/memory/promote.py <filename-or-path> [--demote]"


def _read_lines(path: Path) -> list[str]:
    if not path.is_file():
        return []
    return path.read_text(encoding="utf-8").splitlines(keepends=True)


def _extract_entry_line(memory_md: Path, name: str) -> str | None:
    for line in _read_lines(memory_md):
        match = _LINK_LINE_RE.match(line.rstrip("\n"))
        if match and match.group("target") == name:
            return line if line.endswith("\n") else line + "\n"
    return None


def _append_entry(memory_md: Path, line: str) -> None:
    memory_md.parent.mkdir(parents=True, exist_ok=True)
    text = memory_md.read_text(encoding="utf-8") if memory_md.is_file() else "# Memory\n"
    if text and not text.endswith("\n"):
        text += "\n"
    memory_md.write_text(text + line, encoding="utf-8")


def _rewrite_entry_target(memory_md: Path, *, old_target: str, new_target: str) -> bool:
    """Rewrite the first entry line whose target is exactly `old_target` to
    use `new_target` instead, keeping title/description untouched. Returns
    True if a line was rewritten."""
    lines = _read_lines(memory_md)
    rewritten = []
    found = False
    for line in lines:
        match = _LINK_LINE_RE.match(line.rstrip("\n"))
        if not found and match and match.group("target") == old_target:
            rewritten.append(f"{match.group('prefix')}{new_target}{match.group('suffix')}\n")
            found = True
        else:
            rewritten.append(line)
    if found:
        memory_md.write_text("".join(rewritten), encoding="utf-8")
    return found


def _remove_entry(memory_md: Path, name: str) -> None:
    """Delete the entry line whose bare target is exactly `name`."""
    lines = _read_lines(memory_md)
    kept = [
        line for line in lines
        if not (
            (match := _LINK_LINE_RE.match(line.rstrip("\n")))
            and match.group("target") == name
        )
    ]
    if kept != lines:
        memory_md.write_text("".join(kept), encoding="utf-8")


def _read_codex_sync(path: Path) -> dict[str, object]:
    if not path.is_file():
        return {"version": 1, "sources": {}, "ignored": {}}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"version": 1, "sources": {}, "ignored": {}}
    if not isinstance(data, dict):
        return {"version": 1, "sources": {}, "ignored": {}}
    sources = data.get("sources") if isinstance(data.get("sources"), dict) else {}
    ignored = data.get("ignored") if isinstance(data.get("ignored"), dict) else {}
    return {"version": 1, "sources": sources, "ignored": ignored}


def _write_codex_sync(path: Path, data: dict[str, object]) -> None:
    rendered = json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(rendered, encoding="utf-8")


def _relocate_codex_sync_entry(src_dir: Path, dst_dir: Path, name: str) -> list[Path]:
    """Move a `sources`/`ignored` entry whose `target == name` from
    `src_dir/.codex-sync.json` to `dst_dir/.codex-sync.json`, if present.
    Returns the paths written (for `git add`)."""
    src_path = src_dir / ".codex-sync.json"
    src_data = _read_codex_sync(src_path)
    moved_key = None
    moved_bucket = None
    for bucket in ("sources", "ignored"):
        entries = src_data[bucket]
        for identity, entry in list(entries.items()):
            if isinstance(entry, dict) and entry.get("target") == name:
                moved_key, moved_bucket = identity, bucket
                break
        if moved_key is not None:
            break
    if moved_key is None:
        return []

    entry = src_data[moved_bucket].pop(moved_key)
    dst_path = dst_dir / ".codex-sync.json"
    dst_data = _read_codex_sync(dst_path)
    dst_data[moved_bucket][moved_key] = entry

    _write_codex_sync(src_path, src_data)
    _write_codex_sync(dst_path, dst_data)
    return [src_path, dst_path]


def _run(*args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["git", *args], capture_output=True, text=True, check=check)


def main(argv: list[str] | None = None) -> int:
    args = argv if argv is not None else sys.argv[1:]
    demote = "--demote" in args
    positional = [a for a in args if a != "--demote"]
    if len(positional) != 1:
        print(_usage(), file=sys.stderr)
        return 2

    name = Path(positional[0]).name
    if not name.endswith(".md") or name in {"", ".", ".."}:
        print("Memory name must be a markdown filename ending in .md.", file=sys.stderr)
        return 2

    subproject = _subproject_root()
    if not _is_inside_base_repo(subproject):
        print("promote.py only applies inside the base repo (no ai/°base/memory there).", file=sys.stderr)
        return 2

    base_dir, root_dir = memory_lib.memory_dirs(subproject)  # (ai/°base/memory, ai/memory)
    if demote:
        src_dir, dst_dir = root_dir, base_dir
        stub_target = f"../°base/memory/{name}"
        verb = "Demoted"
    else:
        src_dir, dst_dir = base_dir, root_dir
        stub_target = f"../../memory/{name}"
        verb = "Promoted"

    _chdir_to_git_root()
    src_rel = str(src_dir.relative_to(Path.cwd()))
    dst_rel = str(dst_dir.relative_to(Path.cwd()))

    if not memory_lib.is_tracked(f"{src_rel}/{name}"):
        print(f"Memory is not tracked: {src_rel}/{name}", file=sys.stderr)
        return 1
    if (dst_dir / name).exists():
        print(f"Destination already has {dst_rel}/{name}; refusing to overwrite.", file=sys.stderr)
        return 1

    dst_dir.mkdir(parents=True, exist_ok=True)
    moved = _run("mv", f"{src_rel}/{name}", f"{dst_rel}/{name}", check=False)
    if moved.returncode != 0:
        print(moved.stderr.strip() or "git mv failed", file=sys.stderr)
        return 1

    # `ai/°base/memory/MEMORY.md` is the superset index (own + promoted): the
    # entry it holds for a promoted memory becomes a relative-link stub
    # rather than being deleted. Root `ai/memory/MEMORY.md` only ever lists
    # memories that actually live there -- a stub pointing into `ai/°base/`
    # would be a dangling link for subprojects (which have no such dir), so
    # demoting removes the root entry outright instead of stubbing it.
    if not demote:
        # promote: base (src) keeps a stub; root (dst) gets a fresh real entry.
        entry_line = _extract_entry_line(src_dir / "MEMORY.md", name)
        if entry_line is not None:
            _append_entry(dst_dir / "MEMORY.md", entry_line)
            _rewrite_entry_target(src_dir / "MEMORY.md", old_target=name, new_target=stub_target)
    else:
        # demote: root (src) entry is removed outright; base (dst) either
        # already has a stub from an earlier promote (rewrite it back to a
        # bare link) or never had one (append a fresh bare entry).
        entry_line = _extract_entry_line(src_dir / "MEMORY.md", name)
        if entry_line is not None:
            _remove_entry(src_dir / "MEMORY.md", name)
        promoted_stub_target = f"../../memory/{name}"
        if not _rewrite_entry_target(dst_dir / "MEMORY.md", old_target=promoted_stub_target, new_target=name):
            if entry_line is not None:
                _append_entry(dst_dir / "MEMORY.md", entry_line)

    codex_sync_paths = _relocate_codex_sync_entry(src_dir, dst_dir, name)

    add_paths = [f"{dst_rel}/MEMORY.md", f"{src_rel}/MEMORY.md"]
    add_paths += [str(p.relative_to(Path.cwd())) for p in codex_sync_paths]
    _run("add", "--", *add_paths, check=False)

    subject = base_ai_commit_subject(f"ai: {verb.lower()} memory {Path(name).stem}")
    committed = _run(
        "commit", "--only",
        f"{src_rel}/{name}", f"{dst_rel}/{name}", f"{dst_rel}/MEMORY.md", f"{src_rel}/MEMORY.md",
        *[str(p.relative_to(Path.cwd())) for p in codex_sync_paths],
        "-m", subject,
        check=False,
    )
    if committed.returncode != 0:
        print(committed.stderr.strip() or committed.stdout.strip() or "git commit failed", file=sys.stderr)
        return 1

    commit = _run("rev-parse", "--short", "HEAD").stdout.strip()
    print(f"{verb} memory {name} in {commit}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
