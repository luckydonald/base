#!/usr/bin/env python3
"""Migrate the old prompt log name `query.md` to `prompt.md`, in the root and in every subproject.

A log lives in `ai/`, `ai/°base/`, `ai/by-issue/<KEY>/` or `ai/°base/by-issue/<KEY>/`, at any depth of the repo. Per such directory:

1. no `query.md`: nothing to do.
2. no `prompt.md` (or one that is still the shipped template, or a stale link): `query.md` is renamed, delete + rename as separate commits.
3. both are the same content: the one with the longer history in _this_ repo (so without the commits of `base/base`) stays.
4. both differ, or one of them is dirty: nothing is migrated, the hooks append to both files until the user merges them.

The commits take the committed (`HEAD`) content, so a dirty `query.md` is carried over by moving the working tree file, with its uncommitted lines.
A `query.md` that is a symlink (to the root's log) is renamed as a link and re-pointed to the root's `prompt.md`.
Run it without arguments from inside a repo to migrate all of it, or import `migrate_dir` for a single directory (what `resolve_log_path` does).
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from importlib import import_module
from pathlib import Path, PurePosixPath
from typing import Callable

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "git"))
scoped_commit_lib = import_module("°scoped_commit_lib")

LEGACY_NAME = "query.md"
CURRENT_NAME = "prompt.md"
TEMPLATE_RELPATH = "scripts/°base/init/templates/prompt.md"
BASE_REF = "refs/remotes/base/base"
BASE_TEMPLATE_RELPATHS = ("ai/prompt.md", TEMPLATE_RELPATH)

STATUS_NONE = "none"  # no query.md
STATUS_MIGRATED = "migrated"
STATUS_BOTH = "both"  # both files stay, write to both
STATUS_SKIPPED = "skipped"  # could not commit right now, nothing was changed

Subject = Callable[[str], str]


def git(args: list[str], cwd: Path, *, input: bytes | None = None, check: bool = True) -> subprocess.CompletedProcess[bytes]:
    env = {**os.environ, "GIT_LITERAL_PATHSPECS": "1"}
    return subprocess.run(["git", "-C", str(cwd), *args], capture_output=True, input=input, check=check, env=env)
# end def


def git_root_of(directory: Path) -> Path:
    return Path(git(["rev-parse", "--show-toplevel"], directory).stdout.decode().strip())
# end def


def rev_blob(rev_path: str, cwd: Path) -> str | None:
    result = git(["rev-parse", "--verify", "--quiet", rev_path], cwd, check=False)
    if result.returncode != 0:
        return None
    # end if
    return result.stdout.decode().strip() or None
# end def


def head_entry(rel: str, root: Path) -> tuple[str, str] | None:
    # (mode, blob sha) of `rel` in HEAD, or None if HEAD does not have it.
    out = git(["ls-tree", "-z", "HEAD", "--", rel], root, check=False).stdout.decode()
    if not out:
        return None
    # end if
    meta, _, _ = out.partition("\t")
    mode, _, sha = meta.split(" ")
    return mode, sha
# end def


def index_sha(rel: str, root: Path) -> str | None:
    out = git(["ls-files", "-z", "-s", "--", rel], root).stdout.decode()
    if not out:
        return None
    # end if
    return out.partition("\t")[0].split(" ")[1]
# end def


def working_bytes(path: Path) -> bytes:
    # what git stores for the path: the link target of a symlink, the content of a file.
    if path.is_symlink():
        return os.readlink(path).encode()
    # end if
    return path.read_bytes()
# end def


def working_sha(path: Path, root: Path) -> str:
    return git(["hash-object", "--no-filters", "--stdin"], root, input=working_bytes(path)).stdout.decode().strip()
# end def


def is_clean(rel: str, root: Path) -> bool:
    # in HEAD, and the index and the working tree still hold exactly that.
    head = head_entry(rel, root)
    if head is None:
        return False
    # end if
    return index_sha(rel, root) == head[1] and working_sha(root / rel, root) == head[1]
# end def


def history_length(rel: str, root: Path) -> int:
    # commits touching `rel` in this repo, not counting those that came with `base/base`. Not `--follow`: it takes a new file with the
    # content of another one for a rename of it, and would count that other file's history as its own.
    args = ["log", "--format=%H"]
    if rev_blob(BASE_REF, root):
        args.append(f"^{BASE_REF}")
    # end if
    return len(git([*args, "--", rel], root, check=False).stdout.decode().split())
# end def


def shipped_templates(root: Path) -> list[bytes]:
    found: list[bytes] = []
    template = root / TEMPLATE_RELPATH
    if template.is_file():
        found.append(template.read_bytes())
    # end if
    for rel in BASE_TEMPLATE_RELPATHS:
        blob = git(["show", f"{BASE_REF}:{rel}"], root, check=False)
        if blob.returncode == 0:
            found.append(blob.stdout)
        # end if
    # end for
    return found
# end def


def readable(path: Path) -> bytes | None:
    # content through links, None for a dangling link.
    try:
        return path.read_bytes()
    except OSError:
        return None
    # end try
# end def


def retargeted_link(path: Path) -> str | None:
    # the target of a `query.md` link renamed to `prompt.md`, None if `path` is no link or points elsewhere.
    if not path.is_symlink():
        return None
    # end if
    target = os.readlink(path)
    if os.path.basename(target) != LEGACY_NAME:
        return None
    # end if
    return target[: -len(LEGACY_NAME)] + CURRENT_NAME
# end def


def commit_paths(rels: list[str], message: str, root: Path, event: str | None) -> None:
    scoped_commit_lib.commit_staged_paths(rels, message, event=event, cwd=root)
# end def


def delete_file(rel: str, root: Path, subject: Subject, event: str | None) -> None:
    # `git rm`, but only touching the one path, as its own commit.
    path = root / rel
    if head_entry(rel, root) is not None:
        git(["rm", "--cached", "--force", "--quiet", "--", rel], root)
        path.unlink(missing_ok=True)
        commit_paths([rel], subject(f"ai: Removed the unused `{rel}`."), root, event)
        return
    # end if
    git(["rm", "--cached", "--force", "--quiet", "--ignore-unmatch", "--", rel], root)
    path.unlink(missing_ok=True)
# end def


def rename_file(old_rel: str, new_rel: str, root: Path, subject: Subject, event: str | None) -> None:
    # the committed content moves, the working tree file (dirty lines and all) moves with it.
    old, new = root / old_rel, root / new_rel
    link_target = retargeted_link(old)
    head = head_entry(old_rel, root)
    staged = index_sha(old_rel, root)

    if head is None:
        # never committed: nothing to commit, just the file (and its index entry) moves.
        if staged is None:
            old.rename(new)
        else:
            git(["mv", "--", old_rel, new_rel], root)
        # end if
    else:
        mode, head_sha = head
        if link_target is not None:
            head_sha = git(["hash-object", "-w", "--stdin"], root, input=link_target.encode()).stdout.decode().strip()
        # end if
        git(["rm", "--cached", "--force", "--quiet", "--", old_rel], root)
        git(["update-index", "--add", "--cacheinfo", f"{mode},{head_sha},{new_rel}"], root)
        commit_paths([old_rel, new_rel], subject(f"ai: Renamed `{old_rel}` to `{CURRENT_NAME}`."), root, event)
        old.rename(new)
        if staged is not None and staged != head[1] and link_target is None:
            git(["update-index", "--cacheinfo", f"{mode},{staged},{new_rel}"], root)
        # end if
    # end if

    if link_target is not None:
        new.unlink()
        new.symlink_to(link_target)
    # end if
# end def


def migrate_dir(directory: Path, *, subject: Subject = str, event: str | None = None) -> str:
    """Migrate `directory/query.md` to `directory/prompt.md`, returns one of the `STATUS_*`."""
    old, new = directory / LEGACY_NAME, directory / CURRENT_NAME
    if not os.path.lexists(old):
        return STATUS_NONE
    # end if
    root = git_root_of(directory)
    old_rel = (directory.resolve() / LEGACY_NAME).relative_to(root.resolve()).as_posix()
    new_rel = PurePosixPath(old_rel).with_name(CURRENT_NAME).as_posix()

    blocker = scoped_commit_lib.commit_blocker(event, root)
    if blocker:
        print(f"not migrating {old_rel} ({blocker}).", file=sys.stderr)
        return STATUS_SKIPPED
    # end if

    if not os.path.lexists(new):
        rename_file(old_rel, new_rel, root, subject, event)
        return STATUS_MIGRATED
    # end if

    if old.is_symlink() and readable(old) is None:
        # a stale link whose root file has been migrated already.
        delete_file(old_rel, root, subject, event)
        return STATUS_MIGRATED
    # end if

    if not (is_clean(old_rel, root) and is_clean(new_rel, root)):
        return STATUS_BOTH
    # end if

    old_content, new_content = readable(old), readable(new)
    if new_content in shipped_templates(root):
        delete_file(new_rel, root, subject, event)
        rename_file(old_rel, new_rel, root, subject, event)
        return STATUS_MIGRATED
    # end if
    if old_content != new_content:
        return STATUS_BOTH
    # end if

    if history_length(old_rel, root) > history_length(new_rel, root):
        delete_file(new_rel, root, subject, event)
        rename_file(old_rel, new_rel, root, subject, event)
    else:
        delete_file(old_rel, root, subject, event)
    # end if
    return STATUS_MIGRATED
# end def


def is_log_dir(parts: tuple[str, ...]) -> bool:
    # `ai`, `ai/°base`, `ai/by-issue/<KEY>` or `ai/°base/by-issue/<KEY>`, at the end of the folder names.
    for start, part in enumerate(parts):
        if part != "ai":
            continue
        # end if
        rest = parts[start + 1:]
        if rest in ((), ("°base",)):
            return True
        # end if
        if len(rest) == 2 and rest[0] == "by-issue":
            return True
        # end if
        if len(rest) == 3 and rest[0] == "°base" and rest[1] == "by-issue":
            return True
        # end if
    # end for
    return False
# end def


def find_log_dirs(root: Path) -> list[Path]:
    # every directory below the repo root holding a `query.md` log, root first, NUL-delimited as names can hold anything.
    raw = git(["ls-files", "-z", "--cached", "--others", "--exclude-standard"], root).stdout.decode()
    dirs: set[Path] = set()
    for rel in raw.split("\0"):
        pure = PurePosixPath(rel)
        if pure.name != LEGACY_NAME or not is_log_dir(pure.parent.parts):
            continue
        # end if
        if os.path.lexists(root / rel):
            dirs.add(root / pure.parent)
        # end if
    # end for
    return sorted(dirs, key=lambda path: (len(path.parts), str(path)))
# end def


def migrate_all(root: Path, *, subject: Subject = str, event: str | None = None) -> dict[Path, str]:
    return {directory: migrate_dir(directory, subject=subject, event=event) for directory in find_log_dirs(root)}
# end def


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--event", choices=["merge", "rebase"], help="the git hook calling, which tolerates its own merge/rebase state")
    args = parser.parse_args()

    root = git_root_of(Path.cwd())
    results = migrate_all(root, event=args.event)
    for directory, status in results.items():
        print(f"{status}: {directory.relative_to(root)}")
        if status == STATUS_BOTH:
            print(f"  both {LEGACY_NAME} and {CURRENT_NAME} stay, the hooks write to both. Merge them by hand.", file=sys.stderr)
        # end if
    # end for
    return 0
# end def


if __name__ == "__main__":
    sys.exit(main())
# end if
