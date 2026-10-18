"""Scoped, hook-free auto-commit shared by the hooks and `init/link_subproject.py`.

Commits exactly the given paths on top of `HEAD` with git plumbing, refuses while a merge/rebase/cherry-pick/revert/bisect is underway or
on a detached HEAD, and never raises: on any problem the paths simply stay staged.
"""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from pathlib import Path


def rev_parse_quiet(rev: str, cwd: Path) -> str | None:
    result = subprocess.run(
        ["git", "-C", str(cwd), "rev-parse", "--verify", "--quiet", rev],
        capture_output=True,
        text=True,
    )
    return result.stdout.strip() if result.returncode == 0 else None
# end def


def commit_blocker(event: str | None = None, cwd: Path | None = None) -> str | None:
    # why an automatic commit must not happen right now, or None if it is safe.
    # `event` is the git hook calling us: "merge" (post-merge) tolerates
    # `MERGE_HEAD`, since git runs that hook before it removes the merge state;
    # "rebase" (post-rewrite) tolerates the rebase directories, since git runs
    # that hook once, after the last pick, when the branch ref has moved.
    # A manual run (None) tolerates neither.
    cwd = cwd or Path.cwd()
    result = subprocess.run(["git", "-C", str(cwd), "rev-parse", "--absolute-git-dir"], capture_output=True, text=True)
    if result.returncode != 0:
        return "not a git repository"
    # end if
    gdir = Path(result.stdout.strip())
    in_progress = ["CHERRY_PICK_HEAD", "REVERT_HEAD", "BISECT_LOG", "sequencer"]
    if event != "merge":
        in_progress.append("MERGE_HEAD")
    # end if
    if event != "rebase":
        in_progress += ["rebase-merge", "rebase-apply"]
    # end if
    for name in in_progress:
        if (gdir / name).exists():
            return f"{name} present"
        # end if
    # end for
    if (gdir / "index.lock").exists():
        return "index.lock present"
    # end if
    head = subprocess.run(["git", "-C", str(cwd), "symbolic-ref", "--quiet", "HEAD"], capture_output=True)
    if head.returncode != 0:
        return "detached HEAD"
    # end if
    return None
# end def


def commit_staged_paths(
    paths: list[str], message: str, *, event: str | None = None, cwd: Path | None = None
) -> str | None:
    # commits exactly `paths` (cwd-relative, already staged) on top of HEAD
    # and nothing else. Done with plumbing instead of `git commit`: that would
    # refuse a partial commit (and make a two-parent commit) while `MERGE_HEAD`
    # still exists, which it does inside post-merge. A temporary index starts at
    # HEAD, takes the staged entries of just these paths, and becomes the new
    # commit; the real index and working tree are not touched (the staged links
    # already match the new commit), no hooks run. Never raises; on any problem
    # the links are simply left staged.
    cwd = cwd or Path.cwd()
    blocker = commit_blocker(event, cwd)
    if blocker:
        print(f"not committing {message!r} ({blocker}); left staged.", file=sys.stderr)
        return None
    # end if
    head = rev_parse_quiet("HEAD", cwd)
    if head is None:
        print(f"not committing {message!r} (no commits yet); left staged.", file=sys.stderr)
        return None
    # end if

    def run(args: list[str], *, env: dict[str, str], stdin: str | None = None) -> str:
        return subprocess.run(
            ["git", "-C", str(cwd), *args], capture_output=True, text=True, check=True, input=stdin, env=env
        ).stdout
    # end def

    try:
        literal = {**os.environ, "GIT_LITERAL_PATHSPECS": "1"}
        # `paths` may be files or directories (cwd-relative), `--index-info` wants every file root-relative: take the staged entries
        # below them, plus a removal for every file `HEAD` has below them that is no longer staged (deleted files).
        staged: dict[str, str] = {}
        for entry in run(["ls-files", "-z", "-s", "--full-name", "--", *paths], env=literal).split("\0"):
            meta, _, path = entry.partition("\t")
            if meta:
                mode, sha, stage = meta.split(" ")
                staged[path] = f"{mode} {sha}"
            # end if
        # end for
        for entry in run(["ls-tree", "-r", "-z", "--full-name", head, "--", *paths], env=literal).split("\0"):
            meta, _, path = entry.partition("\t")
            if meta and path not in staged:
                staged[path] = "0 " + "0" * 40
            # end if
        # end for
        index_info = "".join(f"{value}\t{path}\0" for path, value in staged.items())

        with tempfile.TemporaryDirectory() as tmp:
            env = {**literal, "GIT_INDEX_FILE": os.path.join(tmp, "index")}
            run(["read-tree", head], env=env)
            run(["update-index", "-z", "--index-info"], env=env, stdin=index_info)
            tree = run(["write-tree"], env=env).strip()
        # end with

        if tree == run(["rev-parse", f"{head}^{{tree}}"], env=literal).strip():
            return None
        # end if
        new_sha = run(["commit-tree", tree, "-p", head, "-m", message], env=literal).strip()
        run(["update-ref", "-m", message, "HEAD", new_sha, head], env=literal)
    except subprocess.CalledProcessError as e:
        print(f"committing {message!r} failed, left staged: {e.stderr.strip()}", file=sys.stderr)
        return None
    # end try
    return new_sha
# end def


def stage_and_commit(
    paths: list[str], message: str, *, event: str | None = None, cwd: Path | None = None
) -> str | None:
    # `git add` each of `paths` (cwd-relative; a deleted tracked path stages its deletion, an ignored or
    # unknown one is skipped with a note), then commits just those with `commit_staged_paths`.
    # Never raises. Returns the new sha, or None if nothing was committed (the staged paths stay staged).
    cwd = cwd or Path.cwd()
    added: list[str] = []
    for path in paths:
        result = subprocess.run(["git", "-C", str(cwd), "add", "--", path], capture_output=True, text=True)
        if result.returncode != 0:
            # a path someone already `git rm`ed is unknown to `git add`, yet its staged deletion is still ours to commit.
            staged = subprocess.run(["git", "-C", str(cwd), "diff", "--cached", "--quiet", "--", path])
            if staged.returncode == 0:
                print(f"not staging {path}: {result.stderr.strip()}", file=sys.stderr)
                continue
            # end if
        # end if
        added.append(path)
    # end for
    if not added:
        return None
    # end if
    return commit_staged_paths(added, message, event=event, cwd=cwd)
# end def
