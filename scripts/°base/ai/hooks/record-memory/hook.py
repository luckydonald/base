#!/usr/bin/env python3
"""Hardlink Claude memory files into the project tree and auto-commit them.

Source:  <config-dir>/projects/<encoded-subproject-path>/memory/<name>.md
         (<config-dir> is ~/.claude, or $CLAUDE_CONFIG_DIR when relocated,
         e.g. separate work/private account logins)
Target:  <subproject>/ai/memory/<name>.md
         (or <base>/ai/°base/memory/<name>.md inside the base meta-repo)

Fires on:
  - PostToolUse(Write|Edit): sync the single file the tool just touched, if
    it lives inside the source memory dir.
  - PostToolUse(Bash|shell|unified_exec): if the command `rm`'d an absolute
    `.md` path directly under the source memory dir, and that file is now
    confirmed gone, propagate the deletion to the repo mirror via
    `°memory_lib.delete_memory` -- the same marker-commit mechanism
    `scripts/°base/ai/memory/delete.py` uses. This is the only place a
    deletion is ever *originated* from an observed event; a missing source
    file discovered later (e.g. during `SessionStart`) is never treated as a
    deletion request (see `_sync_all` below and
    `ai/°base/plans/007_prevent-accidental-memory-deletion.md`).
  - SessionStart: bulk-sync every `*.md` under the source memory dir as a
    catch-up, then capture the compact summary from the transcript on older
    Claude versions whose post-compaction payload arrived only through this
    event.

Linking strategy mirrors `scripts/°base/ai/memory/legacy/hardlink_memories.sh` but for
single files: hardlink first, fall back to symlink when hardlinks aren't
supported (e.g. the project and Claude state live on different filesystems).
Bind mounts are skipped — they only make sense at directory granularity.
"""
from __future__ import annotations

import importlib
import os
import re
import shlex
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import compact_result  # noqa: E402
from _lib import (  # noqa: E402
    _chdir_to_git_root,
    _encoded_project_dir,
    _subproject_root,
    dump_debug_payload,
    read_payload,
    running_copilot,
)

memory_lib = importlib.import_module("°memory_lib")
commit_message = importlib.import_module("°commit_style_lib").commit_message


def _memory_dirs(subproject: Path) -> tuple[Path, Path, Path]:
    src = _encoded_project_dir(subproject) / "memory"
    dst, secondary = memory_lib.memory_dirs(subproject)
    return src, dst, secondary


_SHELL_OPERATORS = {"&&", "||", ";"}


def _split_on_shell_operators(argv: list[str]) -> list[list[str]]:
    """Split a shlex-parsed argv on shell operators (&&, ||, ;) into
    sub-commands. Mirrors `.claude/hooks/permission-check.py`'s helper of the
    same shape -- shlex treats these as regular tokens, so they must be split
    out manually."""
    sub_commands: list[list[str]] = []
    current: list[str] = []
    for token in argv:
        if token in _SHELL_OPERATORS:
            if current:
                sub_commands.append(current)
            current = []
        else:
            current.append(token)
    if current:
        sub_commands.append(current)
    return sub_commands


def _rm_targets(command: str) -> list[Path]:
    """Absolute `.md` paths passed as plain arguments to a plain `rm`
    invocation anywhere in `command` (chained via &&/||/;).

    Expands `$HOME`/`~` since the shell would have. Relative paths are
    skipped -- this hook has no reliable view of the Bash tool's cwd, so a
    relative `rm` argument can't be resolved against the right directory.
    """
    try:
        argv = shlex.split(command)
    except ValueError:
        return []

    targets: list[Path] = []
    for sub_argv in _split_on_shell_operators(argv):
        if not sub_argv or sub_argv[0] != "rm":
            continue
        only_paths = False
        for token in sub_argv[1:]:
            if not only_paths and token == "--":
                only_paths = True
                continue
            if not only_paths and token.startswith("-"):
                continue
            expanded = Path(os.path.expandvars(token)).expanduser()
            if expanded.is_absolute() and expanded.suffix == ".md":
                targets.append(expanded)
    return targets


def _git_text(*args: str) -> str:
    result = subprocess.run(["git", *args], capture_output=True, text=True)
    return (result.stdout or "").strip()


def _has_memory_delete_marker(commit: str, name: str) -> bool:
    marker = f"Deleted Memory: {name}"
    message = _git_text("show", "-s", "--format=%B", commit)
    return any(line.rstrip("\r") == marker for line in message.splitlines())


def _is_marked_deleted(dst_dir_rel: str, name: str) -> bool:
    relpath = f"{dst_dir_rel}/{name}"
    commits = _git_text("log", "--diff-filter=D", "--format=%H", "--", relpath)
    for commit in commits.splitlines():
        return _has_memory_delete_marker(commit, name)
    return False


def _unlink_file(path: Path) -> bool:
    if path.is_symlink() or path.exists():
        path.unlink()
        return True
    return False


def _sync_all(src_dir: Path, dst_dir: Path, secondary_dir: Path, dst_dir_rel: str) -> list[str]:
    """Sync memory files without treating a missing source as a delete.

    Repo memory is the durable copy, and it wins on content conflicts too: a
    genuinely new Claude source file (no repo counterpart yet) still
    propagates src -> dst, but once both sides exist, the Claude source has no
    audit trail (unlike the repo's git history), so a diverging source is
    treated as untracked drift and overwritten from the repo (dst -> src)
    instead of being committed. A missing Claude source file is recreated
    from the repo file. A stale Claude source file is removed only when git
    history has an explicit `Deleted Memory: <name>.md` marker for that file.

    `secondary_dir` is the repo's *other* valid memory dir (see
    `°memory_lib.memory_dirs`) — inside the base repo, a memory may have been
    deliberately promoted/demoted between `ai/°base/memory/` and `ai/memory/`
    via `scripts/°base/ai/memory/promote.py`. When the primary `dst` is
    missing but the file already lives in `secondary_dir`, that's the
    authoritative copy: re-point the Claude-side hardlink there instead of
    resurrecting a duplicate in `dst_dir`.
    """
    changed: list[str] = []
    src_names: set[str] = set()
    if src_dir.is_dir():
        for src in sorted(src_dir.glob("*.md")):
            src_names.add(src.name)
            dst = dst_dir / src.name
            secondary = secondary_dir / src.name
            if not dst.exists():
                if secondary.is_file():
                    if not memory_lib.same_inode(secondary, src):
                        memory_lib.link_file(secondary, src)
                    continue
                if _is_marked_deleted(dst_dir_rel, src.name):
                    _unlink_file(src)
                    continue
                if memory_lib.link_file(src, dst):
                    changed.append(src.name)
                continue
            if not memory_lib.same_inode(dst, src):
                memory_lib.link_file(dst, src)

    if dst_dir.is_dir():
        for dst in sorted(dst_dir.glob("*.md")):
            if dst.name in src_names:
                continue
            memory_lib.link_file(dst, src_dir / dst.name)
    return changed


_MEMORY_LINK_RE = re.compile(r"\(([^()\s]+\.md)\)")


def _check_memory_index_consistency(dst_dir: Path) -> None:
    """Warn (never auto-fix) when MEMORY.md's index and the files actually on
    disk in ``dst_dir`` disagree: an orphaned file with no index entry, or an
    index entry pointing at a file that no longer exists. Purely diagnostic —
    inferring a deletion or resurrection from this mismatch is exactly the
    accidental-loss failure mode `require_memory_delete_marker.py` exists to
    prevent, so this only ever prints."""
    memory_md = dst_dir / "MEMORY.md"
    if not memory_md.is_file():
        return
    referenced = set(_MEMORY_LINK_RE.findall(memory_md.read_text(encoding="utf-8")))
    on_disk = {p.name for p in dst_dir.glob("*.md") if p.name != "MEMORY.md"}

    for name in sorted(on_disk - referenced):
        print(
            f"record-memory: {dst_dir / name} is orphaned -- not referenced by "
            f"MEMORY.md. Add it back to the index or delete it properly via "
            f"scripts/°base/ai/memory/delete.py.",
            file=sys.stderr,
        )
    for name in sorted(referenced - on_disk):
        print(
            f"record-memory: MEMORY.md references {name}, which doesn't exist "
            f"in {dst_dir} (dangling link).",
            file=sys.stderr,
        )


def _commit(dst_dir_rel: str, names: list[str]) -> None:
    if not names:
        return
    subprocess.run(["git", "add", "--", dst_dir_rel], capture_output=True)
    if len(names) == 1:
        msg = f"ai: record memory {Path(names[0]).stem}"
    else:
        head = ", ".join(Path(n).stem for n in names[:3])
        extra = f" (+{len(names) - 3} more)" if len(names) > 3 else ""
        msg = f"ai: record memories {head}{extra}"
    msg = commit_message("ai/commit-templates/memory", msg)
    subprocess.run(["git", "commit", "--no-verify", "--only", dst_dir_rel, "-m", msg], capture_output=True)


def _git_root() -> Path | None:
    result = subprocess.run(
        ["git", "rev-parse", "--show-toplevel"], capture_output=True, text=True
    )
    if result.returncode != 0 or not result.stdout.strip():
        return None
    return Path(result.stdout.strip())


def _is_bind_mount(p: Path) -> bool:
    """Best-effort detect of a bind mount at ``p``."""
    try:
        result = subprocess.run(
            ["mountpoint", "-q", str(p)], capture_output=True
        )
        return result.returncode == 0
    except (OSError, FileNotFoundError):
        # `mountpoint` is Linux-only. Fall back to stat: a mountpoint sits on
        # a different device than its parent directory.
        try:
            return p.stat().st_dev != p.parent.stat().st_dev
        except OSError:
            return False


# ─────────────────────────────────────────────────────────────────────────────
# DANGER ZONE — legacy whole-folder link cleanup.
#
# The functions below remove the whole-folder memory link planted by
# `scripts/°base/ai/memory/legacy/hardlink_memories.sh` so the new per-file hardlinks
# don't duplicate state. Sounds innocent — it isn't. Things you must NOT
# "simplify":
#
# 1. `_legacy_link_candidates` uses `.absolute()`, not `.resolve()`.
#    `.resolve()` follows symlinks, so a candidate `<root>/.claude/memory` that
#    IS a symlink to the source dir resolves to the source itself — and we'd
#    happily delete it.
#
# 2. `_uninstall_legacy` checks the symlink case FIRST and short-circuits with
#    `legacy.unlink()` (which removes the symlink, not its target). Don't move
#    this check below the directory branches, and don't replace `unlink` with
#    anything that recurses.
#
# 3. NEVER `shutil.rmtree()` (or `rm -rf`) a path that has the same inode as
#    the source dir. Directory hardlinks share the inode and ALL contents —
#    rmtree walks into the shared inode and removes the source files too.
#    Past me did this; the only reason it isn't catastrophic is that those
#    memories were already committed to git on the destination side and we
#    could `git checkout` them back. Don't rely on that next time.
#
# Bind mounts and directory hardlinks therefore return `None` and warn the user
# to run `unlink_memories.sh` interactively. That script has the sudo/systemd/
# fstab unwind logic; this hook does not, deliberately.
# ─────────────────────────────────────────────────────────────────────────────


def _legacy_link_candidates(subproject: Path) -> list[Path]:
    """Plausible legacy locations where ``hardlink_memories.sh`` would have
    planted a whole-folder link to the source memory dir.

    Uses ``absolute()`` (not ``resolve()``) — see the DANGER ZONE notice above.
    The candidate must be the legacy entry itself, not what its symlink
    follows to."""
    seen: set[Path] = set()
    out: list[Path] = []
    git_root = _git_root()
    for base in (subproject, git_root):
        if base is None:
            continue
        legacy = (base / ".claude" / "memory").absolute()
        if legacy in seen:
            continue
        seen.add(legacy)
        out.append(legacy)
    return out


def _uninstall_legacy(legacy: Path, src_dir: Path) -> bool | None:
    """Remove a legacy whole-folder link at ``legacy`` pointing at ``src_dir``.

    See the DANGER ZONE notice above before changing this function.

    Only the symlink case is removed automatically — that's what
    ``hardlink_memories.sh`` falls back to when directory hardlinks aren't
    allowed (macOS always; Linux outside root). Bind mounts and directory
    hardlinks need `unlink_memories.sh` to undo safely.

    Returns:
      - ``True``  → a symlink was unlinked,
      - ``False`` → nothing legacy-shaped is here (path missing, real
        unrelated directory, etc.),
      - ``None``  → bind mount or directory hardlink detected; caller warns
        and leaves it alone.
    """
    # Symlink case FIRST — don't reorder. `.unlink()` removes the symlink
    # entry itself, not the directory it points at.
    if legacy.is_symlink():
        try:
            if legacy.resolve() == src_dir.resolve():
                legacy.unlink()
                return True
        except OSError:
            pass
        return False

    if not legacy.exists():
        return False

    # Past this point `legacy` is a real (non-symlink) filesystem entry.
    # Defense in depth: never act on the source dir itself, even if some
    # exotic path equivalence got us here.
    try:
        if legacy.resolve() == src_dir.resolve():
            return False
    except OSError:
        pass

    if _is_bind_mount(legacy):
        return None

    # Directory hardlink: same inode as source. We CANNOT remove this from
    # here. `os.rmdir` only works on empty dirs; `shutil.rmtree` would follow
    # the shared inode and delete the source contents. Hand off to the user.
    if legacy.is_dir() and memory_lib.same_inode(legacy, src_dir):
        return None

    return False


def _uninstall_legacy_all(subproject: Path, src_dir: Path) -> None:
    for legacy in _legacy_link_candidates(subproject):
        result = _uninstall_legacy(legacy, src_dir)
        if result is True:
            print(
                f"record-memory: removed legacy whole-folder memory symlink at {legacy}",
                file=sys.stderr,
            )
        elif result is None:
            print(
                f"record-memory: a bind mount or directory hardlink remains at {legacy}; "
                f"the new per-file hooks won't disturb it, but it duplicates memory "
                f"state in your repo. Run `scripts/°base/ai/memory/legacy/unlink_memories.sh` "
                f"to remove it.",
                file=sys.stderr,
            )


def main() -> int:
    # Copilot Memory is a cloud/server-side feature with no local file
    # representation to hardlink from (confirmed via official docs), and
    # `.github/hooks/generated.json` unconditionally renders this hook's
    # entries alongside Claude's — stay a safe no-op under Copilot rather
    # than doing wasted (and, via the `.claude/settings.json` cross-read,
    # duplicated) work that can never find a source directory.
    if running_copilot():
        return 0
    if _git_root() is None:
        return 0
    subproject = _subproject_root()
    src_dir, dst_dir, secondary_dir = _memory_dirs(subproject)
    _chdir_to_git_root()
    dst_dir_rel = str(dst_dir.relative_to(Path.cwd()))

    payload = read_payload()
    dump_debug_payload(payload, "record-memory")
    event = payload.get("hook_event_name") or ""

    if event == "PostToolUse":
        tool_input = payload.get("tool_input") or {}
        command = tool_input.get("command") or ""
        if command:
            resolved_src_dir = src_dir.resolve()
            for target in _rm_targets(command):
                if target.parent != resolved_src_dir:
                    continue
                if target.exists():
                    continue  # rm didn't actually remove it -- nothing to do
                memory_lib.delete_memory(
                    target.name, src_dir=src_dir, dst_dir=dst_dir, dst_dir_rel=dst_dir_rel
                )
            _check_memory_index_consistency(dst_dir)
            return 0

        raw = tool_input.get("file_path") or ""
        if not raw:
            return 0
        src_file = Path(raw).resolve()
        try:
            rel = src_file.relative_to(src_dir.resolve())
        except (OSError, ValueError):
            return 0
        # If this memory was already promoted/demoted to the other valid
        # dir, keep updating it there instead of creating a second copy.
        target_dir = secondary_dir if (secondary_dir / rel).is_file() and not (dst_dir / rel).is_file() else dst_dir
        if memory_lib.link_file(src_file, target_dir / rel):
            _commit(str(target_dir.relative_to(Path.cwd())), [str(rel)])
        _check_memory_index_consistency(target_dir)
        return 0

    # SessionStart (and any other event) — full catch-up sync.
    # Clean up any legacy whole-folder link planted by `hardlink_memories.sh`
    # so the new per-file hardlinks don't duplicate memory state in the repo.
    _uninstall_legacy_all(subproject, src_dir)
    changed = _sync_all(src_dir, dst_dir, secondary_dir, dst_dir_rel)
    _commit(dst_dir_rel, changed)
    _check_memory_index_consistency(dst_dir)
    compact_result.capture_session_start(payload)
    return 0


if __name__ == "__main__":
    sys.exit(main())
