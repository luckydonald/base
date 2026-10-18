#!/usr/bin/env python3
"""Standalone, dependency-free bootstrap launcher.

Adds/fetches the `base` remote and sets up a local worktree so the full
`°split_lib` tooling becomes reachable, then delegates to it -- without
needing `base` merged into the current repo/branch at all, and without ever
touching the currently checked-out branch or working tree.

Deliberately stdlib-only (no imports from `°split_lib`), since none of that
exists yet when this file is fetched standalone -- it's meant to be run as:

    curl -fSL https://raw.githubusercontent.com/luckydonald/base/refs/heads/base/scripts/%C2%B0base/git/get-base.py | python3 - bootstrap-branch feature

or locally, once a copy is reachable on disk:

    python3 scripts/°base/git/get-base.py update-history-master --yes

With no arguments at all, it figures out what to do from the branch you're
currently on (see `auto_argv`) -- e.g. on your main branch it runs
`update-history-master --yes`; on a clean feature branch it runs
`bootstrap-branch <branch>`.

Pass `--base-ref <branch-or-commit>` (consumed here, not forwarded) to pin
the `base` tooling to something other than the `base` branch -- handy for
testing an unmerged branch or a specific commit before it lands:

    curl -fSL .../get-base.py | python3 - --base-ref my-feature-branch bootstrap-branch feature

Env:
    BASE_GIT_USERNAME  GitHub username/org the `base` remote points at (default: luckydonald)
    BASE_GIT_REF       Same as `--base-ref`, for when you can't pass a flag (default: base)

The remote is always named literally "base" -- not configurable -- so it's
never confused with `origin` or some unrelated remote that happens to have
its own branch called `base`.
"""

from __future__ import annotations

import importlib
import importlib.util
import os
import shlex
import shutil
import subprocess
import sys
from pathlib import Path

REMOTE_NAME = "base"
REMOTE_BRANCH = "base"
DEFAULT_USERNAME = "luckydonald"
WORKTREE_RELATIVE_PATH = Path(".git") / "luckydonald" / "base#get-base.py"
# Fixed local ref the fetched `--base-ref` (branch, tag, or raw commit) lands
# under -- so checkout/worktree-add never has to guess whether the ref is a
# remote-tracking branch name, since an arbitrary commit never gets one.
LOCAL_TARGET_REF = "refs/get-base/target"


def status(message: str) -> None:
    print(f"get-base.py: {message}", file=sys.stderr, flush=True)


def _run(args: list[str], cwd: Path | None = None, *, check: bool = True) -> subprocess.CompletedProcess:
    command = ["git", *args]
    result = subprocess.run(command, cwd=cwd, capture_output=True, text=True)
    if check and result.returncode != 0:
        details = result.stderr.strip() or result.stdout.strip() or "Git produced no output."
        raise SystemExit(
            f"get-base.py: Git command failed with exit code {result.returncode}: "
            f"{shlex.join(command)}\n{details}"
        )
    # end if
    return result
# end def


def find_repo_root(cwd: Path | None = None) -> Path:
    result = _run(["rev-parse", "--show-toplevel"], cwd=cwd, check=False)
    if result.returncode != 0:
        raise SystemExit(f"get-base.py: not inside a git repository ({result.stderr.strip()})")
    return Path(result.stdout.strip())


def remote_url(username: str) -> str:
    return f"https://{username}@github.com/{username}/base.git"


def ensure_base_remote(repo_root: Path, username: str) -> None:
    existing = _run(["remote", "get-url", REMOTE_NAME], cwd=repo_root, check=False)
    if existing.returncode == 0:
        status(f"{REMOTE_NAME} remote already exists: {existing.stdout.strip()}")
        return  # already configured -- respect whatever URL is there, never overwrite
    url = remote_url(username)
    status(f"adding {REMOTE_NAME} remote: {url}")
    _run(["remote", "add", REMOTE_NAME, url], cwd=repo_root)


def fetch_base(repo_root: Path, ref: str = REMOTE_BRANCH) -> None:
    status(f"fetching {REMOTE_NAME}/{ref}")
    _run(["fetch", REMOTE_NAME, f"+{ref}:{LOCAL_TARGET_REF}"], cwd=repo_root)


def worktree_path(repo_root: Path) -> Path:
    return repo_root / WORKTREE_RELATIVE_PATH


def remove_stale_worktree(repo_root: Path) -> None:
    """Remove only this launcher's invalid worktree path."""
    path = worktree_path(repo_root)
    if not path.exists() and not path.is_symlink():
        return
    # end if

    status(f"removing stale worktree: {path}")
    result = _run(["worktree", "remove", "--force", str(path)], cwd=repo_root, check=False)
    if result.returncode == 0:
        return
    # end if

    if path.is_dir() and not path.is_symlink():
        shutil.rmtree(path)
    else:
        path.unlink()
    # end if
# end def


def _is_valid_worktree(path: Path) -> bool:
    if not path.exists():
        return False
    result = _run(["rev-parse", "--show-toplevel"], cwd=path, check=False)
    # git reports the resolved toplevel, so compare against the resolved path (symlinked checkouts, macOS `/var` -> `/private/var`)
    return result.returncode == 0 and Path(result.stdout.strip()).resolve() == path.resolve()


def ensure_worktree(repo_root: Path, ref: str = REMOTE_BRANCH) -> Path:
    path = worktree_path(repo_root)

    if _is_valid_worktree(path):
        status(f"refreshing worktree: {path}")
        _run(["fetch", REMOTE_NAME, f"+{ref}:{LOCAL_TARGET_REF}"], cwd=path)
        _run(["checkout", "--detach", LOCAL_TARGET_REF], cwd=path)
        return path

    remove_stale_worktree(repo_root)
    status(f"creating worktree: {path}")
    _run(["worktree", "add", "--force", "--detach", str(path), LOCAL_TARGET_REF], cwd=repo_root)
    return path


def _split_command(repo_root: Path, worktree: Path, argv: list[str]) -> list[str]:
    split_py = worktree / "scripts" / "°base" / "git" / "split.py"
    return [sys.executable, str(split_py), "--repo-root", str(repo_root), *argv]


def delegate(repo_root: Path, worktree: Path, argv: list[str]) -> None:
    command = _split_command(repo_root, worktree, argv)
    status(f"delegating: {shlex.join(command)}")
    file = command[1]
    args = command[2:]
    spec = importlib.util.spec_from_file_location("°split_lib.split", file)
    split_py = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(split_py)
    result = split_py.main(args)
    sys.exit(result)


def run_split(repo_root: Path, worktree: Path, argv: list[str]) -> int:
    """Like `delegate()`, but blocks and returns the exit code instead of
    replacing the current process -- for auto mode's own prerequisite steps
    (e.g. running `update-history-master` before `bootstrap-branch`), where
    something still needs to happen afterwards in this process."""
    command = _split_command(repo_root, worktree, argv)
    status(f"running: {shlex.join(command)}")
    return subprocess.run(command).returncode


def current_branch(repo_root: Path) -> str:
    result = _run(["branch", "--show-current"], cwd=repo_root, check=False)
    return result.stdout.strip() if result.returncode == 0 else ""


def auto_argv(repo_root: Path, worktree: Path) -> list[str] | None:
    """Figure out what to run from the currently checked-out branch (in the
    *original* repo, not the worktree), reusing `°split_lib.branches` from
    the worktree (which already exists by the time this is called) rather
    than duplicating its classification regexes.

    Returns None when it can't confidently decide (detached HEAD, or the
    branch can't be resolved) -- callers should refuse rather than guess.
    """
    branch = current_branch(repo_root)
    status(f"auto mode: current branch {branch or '<detached>'}")
    if not branch:
        return None

    sys.path.insert(0, str(worktree / "scripts" / "°base" / "git"))
    branches = importlib.import_module("°split_lib.branches")
    git_ops = importlib.import_module("°split_lib.git_ops")

    main_branch = branches.detect_main_branch(repo_root)

    if branch == main_branch:
        argv = ["update-history-master", "--yes"]
        status(f"auto mode: selected {shlex.join(argv)}")
        return argv

    classification = branches.classify_branch(branch, main_branch=main_branch)

    if classification.is_history_master:
        argv = ["update-history-master", "--yes"]
        status(f"auto mode: selected {shlex.join(argv)}")
        return argv

    if classification.format is branches.BranchFormat.CLEAN:
        history_main_ref = branches.history_name(main_branch)
        if git_ops.rev_parse(history_main_ref, repo_root) is None:
            status(f"auto mode: {history_main_ref!r} missing -- running update-history-master first")
            rc = run_split(repo_root, worktree, ["update-history-master", "--yes"])
            if rc != 0:
                status("auto mode: update-history-master failed; aborting")
                return None

        argv = ["bootstrap-branch", classification.base_name]
        status(f"auto mode: selected {shlex.join(argv)}")
        return argv

    # UNCLEAN or non-master HISTORY: both mean "push my latest commits
    # forward into clean+history for this branch". sync-splits needs
    # ai/history/{main} to already exist (it forks each branch's own history
    # branch from it) -- same prerequisite as the CLEAN case above, so this
    # repo's very first action ever being an ai/UNCLEAN/* branch doesn't
    # crash instead of just bootstrapping history-master first.
    history_main_ref = branches.history_name(main_branch)
    if git_ops.rev_parse(history_main_ref, repo_root) is None:
        status(f"auto mode: {history_main_ref!r} missing -- running update-history-master first")
        rc = run_split(repo_root, worktree, ["update-history-master", "--yes"])
        if rc != 0:
            status("auto mode: update-history-master failed; aborting")
            return None

    argv = ["sync-splits", classification.base_name, "--direction=to-clean-history"]
    status(f"auto mode: selected {shlex.join(argv)}")
    return argv


USAGE = """\
get-base.py: could not determine what to do from the current branch (detached HEAD?).
Run a subcommand explicitly, e.g.:
  get-base.py bootstrap-branch <branch>
  get-base.py update-history-master --yes
  get-base.py sync-splits <branch> --direction=to-clean-history
  get-base.py rebase-branches-to-master <branch>
"""


def _extract_base_ref(argv: list[str], default: str) -> tuple[str, list[str]]:
    """Pull `--base-ref <ref>`/`--base-ref=<ref>` out of argv -- it's consumed
    here, not forwarded to `split.py`, whose own argparse doesn't know it."""
    ref = default
    remaining: list[str] = []
    i = 0
    while i < len(argv):
        arg = argv[i]
        if arg == "--base-ref":
            if i + 1 >= len(argv):
                raise SystemExit("get-base.py: --base-ref requires a value")
            ref = argv[i + 1]
            i += 2
            continue
        if arg.startswith("--base-ref="):
            ref = arg.split("=", 1)[1]
            i += 1
            continue
        remaining.append(arg)
        i += 1
    return ref, remaining


def main(argv: list[str] | None = None) -> int:
    argv = argv if argv is not None else sys.argv[1:]
    username = os.environ.get("BASE_GIT_USERNAME", DEFAULT_USERNAME)
    ref, argv = _extract_base_ref(argv, os.environ.get("BASE_GIT_REF", REMOTE_BRANCH))

    repo_root = find_repo_root()
    status(f"repo root: {repo_root}")
    ensure_base_remote(repo_root, username)
    fetch_base(repo_root, ref)
    worktree = ensure_worktree(repo_root, ref)

    if not argv:
        argv = auto_argv(repo_root, worktree)
        if argv is None:
            if current_branch(repo_root):
                status("auto mode could not complete; see the delegated command error above")
            else:
                print(USAGE, file=sys.stderr, end="")
            # end if
            return 1

    delegate(repo_root, worktree, argv)
    return 0  # unreachable once delegate() execs, kept for testability


if __name__ == "__main__":
    raise SystemExit(main())
