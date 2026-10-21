"""Shared fixtures for the split.py/get-base.py end-to-end test suite
(test_git_split_e2e_smoke_matrix.py, test_git_split_e2e_deep_flow.py).

Builds the 6 repo-preparation variants and 9 branch-checkout variants from
the e2e test plan, a commit manifest recorder, and the "fake curl" helper
that pipes the real get-base.py source into a fresh python3 process --
exactly like `curl -fSL <raw-url> | python3 -`, but hitting this repo's own
on-disk copy instead of GitHub, so tests are hermetic and unaffected by
GitHub potentially being out of sync with local development.
"""

from __future__ import annotations

import atexit
import importlib
import os
import shutil
import subprocess
import sys
import tempfile
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _git_test_helpers import git, init_repo, make_commit  # noqa: E402

LIB_ROOT = Path(__file__).resolve().parents[1] / "git"
sys.path.insert(0, str(LIB_ROOT))

git_ops = importlib.import_module("°split_lib.git_ops")
branches = importlib.import_module("°split_lib.branches")
classify = importlib.import_module("°split_lib.classify")
trailers = importlib.import_module("°split_lib.trailers")


# --------------------------------------------------------------------------
# Manifest schema
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class MergeInfo:
    branch: str  # "empty/init" | "base/base"
    commit_theirs: str
    commit_ours: str
    is_allowed_merge: bool  # True: done as test-fixture prep, not by running split.py


@dataclass
class CommitRecord:
    commit: str
    merge: MergeInfo | None
    code: bool  # touches at least one non-AI path
    ai: bool  # touches at least one AI/base path
    msg: str  # subject + body, up to (not including) the trailer block
    trailer: str  # raw trailer block, "" if none


Manifest = list[CommitRecord]


def record_commit(sha: str, *, merge: MergeInfo | None, cwd: Path) -> CommitRecord:
    """Build a CommitRecord for `sha`. Note: for a real merge commit,
    git_ops.changed_paths_for_commit (`git diff-tree`, no `-m`/`-c`) reports
    no changed paths at all -- git's diff-tree only diffs ordinary commits
    by default -- so `code`/`ai` come back False for merge commits. That's
    fine here: callers pass `merge=MergeInfo(...)` for those and don't rely
    on code/ai for them.
    """
    full_message = git_ops.commit_message(sha, cwd)
    msg_body, trailer_block = trailers.split_trailer_block(full_message)
    subject = git_ops.subject_for_commit(sha, cwd)
    paths = git_ops.changed_paths_for_commit(sha, cwd)
    cls = classify.classify_commit(sha, subject, paths)
    return CommitRecord(
        commit=sha,
        merge=merge,
        code=cls.is_code_containing_commit,
        ai=any(classify.is_ai_base_path(p) for p in paths),
        msg=msg_body,
        trailer=trailer_block,
    )


# --------------------------------------------------------------------------
# Generic fixture helpers
# --------------------------------------------------------------------------


def _init_bare(repo_root: Path) -> None:
    subprocess.run(["git", "init"], cwd=repo_root, capture_output=True, check=True)
    git(["config", "user.email", "test@example.com"], repo_root)
    git(["config", "user.name", "Test"], repo_root)


def make_empty_init_remote(tmp_root: Path) -> Path:
    """A tiny local one-commit repo standing in for the real, hermetic
    `https://github.com/EmptyAAS/empty.git` `init` branch -- offline, and
    unaffected by that remote possibly being out of sync."""
    repo = tmp_root / "empty-init-remote"
    repo.mkdir(parents=True, exist_ok=True)
    init_repo(repo, branch="init")
    make_commit(repo, "EMPTY.md", "empty/init stand-in initial commit")
    return repo


def resolve_this_repo_root() -> Path:
    """The actual on-disk repo containing this test file (never a temp
    fixture) -- used only as a local, offline source for `base`'s real
    content."""
    result = subprocess.run(
        ["git", "-C", str(Path(__file__).resolve().parent), "rev-parse", "--show-toplevel"],
        capture_output=True,
        text=True,
        check=True,
    )
    return Path(result.stdout.strip())


# The e2e scenarios are independent and bound by spawning `git`, so they run in a thread pool.
# `E2E_WORKERS=1` runs them serially, e.g. for debugging.
E2E_WORKERS = int(os.environ.get("E2E_WORKERS") or min(8, os.cpu_count() or 1))


# What the split tooling needs from the fetched `base` ref: get-base.py runs the `°split_lib` that sits in its worktree.
BASE_TOOLING_PATHS = ("scripts/°base/git", ".ai-ignore")

_fixture_base_repo: Path | None = None
_fixture_base_repo_lock = threading.Lock()


def _build_fixture_base_repo(this_repo_root: Path) -> Path:
    repo = Path(tempfile.mkdtemp(prefix="split-e2e-base-"))
    atexit.register(shutil.rmtree, repo, ignore_errors=True)
    init_repo(repo, branch="base")

    def commit_all(message: str) -> None:
        git(["add", "--all"], repo)
        git(["commit", "--no-verify", "-m", message], repo)

    # `README.md` and `.gitignore` are what variant 3 conflicts with.
    (repo / "README.md").write_text("base readme\n")
    (repo / ".gitignore").write_text("*.base\n")
    (repo / "ai").mkdir()
    (repo / "ai" / "notes.md").write_text("base ai notes\n")
    commit_all("base: initial readme, gitignore and ai notes")

    # The tooling is copied from the working tree, so uncommitted fixes get exercised, too.
    tracked = git(["ls-files", "-z", "--", *BASE_TOOLING_PATHS], this_repo_root).split("\0")
    for relative in filter(None, tracked):
        source = this_repo_root / relative
        target = repo / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        if source.is_symlink():
            target.symlink_to(os.readlink(source))
        elif source.is_file():
            shutil.copy2(source, target)
        # end if
    # end for
    commit_all("base: split tooling")

    (repo / "src").mkdir()
    (repo / "src" / "base_code.py").write_text("print('base')\n")
    commit_all("base: some code")

    (repo / "ai" / "notes.md").write_text("base ai notes\nmore\n")
    commit_all("base: more ai notes")
    (repo / "src" / "base_code.py").write_text("print('base')\nprint('again')\n")
    commit_all("base: more code")
    return repo


def fixture_base_repo() -> Path:
    """A small local repo with a `base` branch, standing in for this repo's own thousands-of-commits-long `base`
    history, which the e2e scenarios would otherwise fetch, merge and replay every single time.
    Built once per process, thread-safe."""
    global _fixture_base_repo
    with _fixture_base_repo_lock:
        if _fixture_base_repo is None:
            _fixture_base_repo = _build_fixture_base_repo(resolve_this_repo_root())
        # end if
        return _fixture_base_repo


def ensure_base_remote(repo_root: Path) -> None:
    """Make sure `repo_root` has a `base` remote pointed at the fixture base repo (never GitHub) -- a no-op if one
    already exists (e.g. repo variants 4/5/6 already added one while building the fixture).
    """
    existing = subprocess.run(
        ["git", "remote", "get-url", "base"], cwd=repo_root, capture_output=True
    )
    if existing.returncode != 0:
        git(["remote", "add", "base", str(fixture_base_repo())], repo_root)


def add_and_fetch_base_branch(repo_root: Path) -> str:
    """Adds a `base` remote pointed at the fixture base repo and fetches its `base` branch. Returns the freshly-fetched
    tip ("now")."""
    ensure_base_remote(repo_root)
    git(["fetch", "base", "base"], repo_root)
    return git(["rev-parse", "refs/remotes/base/base"], repo_root)


def resolve_base_sha_two_commits_earlier(repo_root: Path) -> str:
    """`base/base`'s tip two first-parent commits back ("now-2") -- must be
    called after `add_and_fetch_base_branch` has fetched. The fixture base repo
    has a longer first-parent history than that, so `~2` is always resolvable."""
    return git(["rev-parse", "refs/remotes/base/base~2"], repo_root)


def run_fake_curl(
    repo_root: Path, *args: str, this_repo_root: Path | None = None
) -> subprocess.CompletedProcess:
    """Feed get-base.py via stdin exactly like the documented curl one-liner
    (`curl -fSL <raw-url> | python3 - [subcommand ...]`) -- no real network
    or HTTP server. Caller must have already pre-added a `base` remote on
    `repo_root` pointed locally (get-base.py's own `ensure_base_remote()`
    never overwrites an existing remote, but `main()` unconditionally
    fetches `base` regardless of explicit argv).
    """
    this_repo_root = this_repo_root or resolve_this_repo_root()
    script_path = this_repo_root / "scripts" / "°base" / "git" / "get-base.py"
    script_text = script_path.read_text()
    return subprocess.run(
        [sys.executable, "-", *args],
        cwd=repo_root,
        input=script_text,
        capture_output=True,
        text=True,
    )


def assert_no_unresolved_merge_state(repo_root: Path) -> None:
    """Assert the tool left nothing needing --continue/--abort. Deliberately
    not a fully-clean-tree check: a real run always leaves an untracked
    `.rebase-recovery.tmp` behind."""
    for marker in ("MERGE_HEAD", "CHERRY_PICK_HEAD", "rebase-merge", "rebase-apply"):
        assert not (repo_root / ".git" / marker).exists(), f"{marker} left behind in {repo_root}"
    status = git(["status", "--porcelain"], repo_root)
    for line in status.splitlines():
        assert "U" not in line[:2], f"unresolved path left behind: {line}"


def _random_commits(
    repo_root: Path,
    manifest: Manifest,
    n: int,
    *,
    prefix: str,
    ai: bool = False,
    both: bool = False,
) -> None:
    """Append `n` commits of the requested flavor (code-only by default, or
    ai-only, or touching both a code and an ai path in the same commit),
    recording each in `manifest` as it goes."""
    for i in range(n):
        if both:
            (repo_root / "src").mkdir(parents=True, exist_ok=True)
            (repo_root / "ai").mkdir(parents=True, exist_ok=True)
            code_path = f"src/{prefix}_{i}.py"
            ai_path = f"ai/{prefix}_{i}.md"
            (repo_root / code_path).write_text(f"# {prefix} {i}\n")
            (repo_root / ai_path).write_text(f"{prefix} notes {i}\n")
            git(["add", code_path, ai_path], repo_root)
            git(["commit", "-m", f"{prefix}: touch code and ai {i}"], repo_root)
            sha = git(["rev-parse", "HEAD"], repo_root)
        elif ai:
            sha = make_commit(repo_root, f"ai/{prefix}_{i}.md", f"ai: {prefix} notes {i}")
        else:
            sha = make_commit(repo_root, f"src/{prefix}_{i}.py", f"{prefix}: code change {i}")
        manifest.append(record_commit(sha, merge=None, cwd=repo_root))


# --------------------------------------------------------------------------
# Repo-preparation variants (1.1 - 1.6)
# --------------------------------------------------------------------------


def build_repo_variant_1_random_commits(repo_root: Path, empty_remote: Path) -> Manifest:
    init_repo(repo_root, branch="mane")
    # `mane` itself never merges in `base` (and so never gets its own
    # `.ai-ignore`) -- add the `base` remote so classify.py's fallback chain
    # can still find `.ai-ignore` via the fetched `base/base` ref, matching
    # realistic post-bootstrap state without a live network fetch.
    add_and_fetch_base_branch(repo_root)
    manifest: Manifest = []
    _random_commits(repo_root, manifest, 3, prefix="v1")
    return manifest


def build_repo_variant_2_empty_init_then_random(repo_root: Path, empty_remote: Path) -> Manifest:
    # Literally "start from empty/init" (README.md "Setup: a) Checkout"
    # recipe, using empty/init instead of base/base) -- not a merge.
    _init_bare(repo_root)
    git(["remote", "add", "empty", str(empty_remote)], repo_root)
    git(["fetch", "empty", "init"], repo_root)
    git(["checkout", "-b", "mane", "empty/init"], repo_root)
    add_and_fetch_base_branch(repo_root)
    manifest: Manifest = []
    _random_commits(repo_root, manifest, 3, prefix="v2")
    return manifest


def build_repo_variant_3_readme_gitignore_conflict_setup(repo_root: Path, empty_remote: Path) -> Manifest:
    init_repo(repo_root, branch="mane")
    add_and_fetch_base_branch(repo_root)
    manifest: Manifest = []
    _random_commits(repo_root, manifest, 2, prefix="v3")
    readme_sha = make_commit(repo_root, "README.md", "consumer readme", content="consumer readme\n")
    manifest.append(record_commit(readme_sha, merge=None, cwd=repo_root))
    gitignore_sha = make_commit(repo_root, ".gitignore", "consumer gitignore", content="*.consumer\n")
    manifest.append(record_commit(gitignore_sha, merge=None, cwd=repo_root))
    return manifest


def build_repo_variant_4_based_on_real_base_tip(repo_root: Path, empty_remote: Path) -> Manifest:
    # README.md "Setup: a) Checkout" recipe -- no merge commit, mane starts
    # literally at base/base's tip.
    _init_bare(repo_root)
    base_sha = add_and_fetch_base_branch(repo_root)
    git(["checkout", "-b", "mane", base_sha], repo_root)
    manifest: Manifest = []
    _random_commits(repo_root, manifest, 3, prefix="v4")
    return manifest


def build_repo_variant_5_empty_and_base_merge(repo_root: Path, empty_remote: Path) -> Manifest:
    init_repo(repo_root, branch="mane")
    manifest: Manifest = []
    _random_commits(repo_root, manifest, 2, prefix="v5a")

    git(["remote", "add", "empty", str(empty_remote)], repo_root)
    git(["fetch", "empty", "init"], repo_root)
    ours_before = git(["rev-parse", "HEAD"], repo_root)
    theirs = git(["rev-parse", "empty/init"], repo_root)
    git(["merge", "--allow-unrelated-histories", "--no-verify", "--no-edit", "empty/init"], repo_root)
    empty_merge_sha = git(["rev-parse", "HEAD"], repo_root)
    manifest.append(
        record_commit(empty_merge_sha, merge=MergeInfo("empty/init", theirs, ours_before, True), cwd=repo_root)
    )

    # Real repos sharing the *actual* empty/init ancestor wouldn't need
    # --allow-unrelated-histories here (per the README's own note) -- but
    # this fixture's empty/init stand-in is a fresh, hermetic repo, not a
    # clone of the real one, so it never shares real ancestry with this
    # repo's actual `base` branch regardless of the merge above.
    base_sha = add_and_fetch_base_branch(repo_root)
    ours_before = git(["rev-parse", "HEAD"], repo_root)
    git(["merge", "--allow-unrelated-histories", "--no-ff", "--no-verify", "--no-edit", base_sha], repo_root)
    base_merge_sha = git(["rev-parse", "HEAD"], repo_root)
    manifest.append(
        record_commit(base_merge_sha, merge=MergeInfo("base/base", base_sha, ours_before, True), cwd=repo_root)
    )

    _random_commits(repo_root, manifest, 2, prefix="v5b")
    return manifest


def build_repo_variant_6_double_base_merge(repo_root: Path, empty_remote: Path) -> Manifest:
    init_repo(repo_root, branch="mane")
    manifest: Manifest = []
    _random_commits(repo_root, manifest, 2, prefix="v6a")

    git(["remote", "add", "empty", str(empty_remote)], repo_root)
    git(["fetch", "empty", "init"], repo_root)
    ours_before = git(["rev-parse", "HEAD"], repo_root)
    theirs = git(["rev-parse", "empty/init"], repo_root)
    git(["merge", "--allow-unrelated-histories", "--no-verify", "--no-edit", "empty/init"], repo_root)
    empty_merge_sha = git(["rev-parse", "HEAD"], repo_root)
    manifest.append(
        record_commit(empty_merge_sha, merge=MergeInfo("empty/init", theirs, ours_before, True), cwd=repo_root)
    )

    # Two genuinely different commits from base's own history ("now-2" then
    # "now") -- git merge --no-ff on an already-fully-merged ref is a no-op
    # ("Already up to date", no commit), so merging the identical tip twice
    # wouldn't actually produce two merge commits.
    base_now = add_and_fetch_base_branch(repo_root)
    base_earlier = resolve_base_sha_two_commits_earlier(repo_root)

    # Same reasoning as variant 5: this fixture's mane never shares real
    # ancestry with this repo's actual `base` branch, so the *first* base
    # merge needs --allow-unrelated-histories. The *second* merge (base_now)
    # is a first-parent descendant of base_earlier, already an ancestor of
    # mane after the first merge, so it doesn't need the flag again.
    ours_before = git(["rev-parse", "HEAD"], repo_root)
    git(["merge", "--allow-unrelated-histories", "--no-ff", "--no-verify", "--no-edit", base_earlier], repo_root)
    first_base_merge_sha = git(["rev-parse", "HEAD"], repo_root)
    manifest.append(
        record_commit(first_base_merge_sha, merge=MergeInfo("base/base", base_earlier, ours_before, True), cwd=repo_root)
    )

    ours_before = git(["rev-parse", "HEAD"], repo_root)
    git(["merge", "--no-ff", "--no-verify", "--no-edit", base_now], repo_root)
    second_base_merge_sha = git(["rev-parse", "HEAD"], repo_root)
    manifest.append(
        record_commit(second_base_merge_sha, merge=MergeInfo("base/base", base_now, ours_before, True), cwd=repo_root)
    )

    _random_commits(repo_root, manifest, 2, prefix="v6_ai", ai=True)
    _random_commits(repo_root, manifest, 2, prefix="v6_code")
    _random_commits(repo_root, manifest, 2, prefix="v6_both", both=True)
    return manifest


REPO_VARIANTS: list[tuple[str, Callable[[Path, Path], Manifest]]] = [
    ("1_random_commits", build_repo_variant_1_random_commits),
    ("2_empty_init_then_random", build_repo_variant_2_empty_init_then_random),
    ("3_readme_gitignore_conflict", build_repo_variant_3_readme_gitignore_conflict_setup),
    ("4_based_on_real_base_tip", build_repo_variant_4_based_on_real_base_tip),
    ("5_empty_and_base_merge", build_repo_variant_5_empty_and_base_merge),
    ("6_double_base_merge", build_repo_variant_6_double_base_merge),
]


# --------------------------------------------------------------------------
# Branch-checkout variants (2.1 - 2.9)
# --------------------------------------------------------------------------


def checkout_variant_1_stay_on_mane(repo_root: Path, manifest: Manifest) -> Manifest:
    git(["checkout", "mane"], repo_root)
    return manifest


def checkout_variant_2_mane_plus_commits(repo_root: Path, manifest: Manifest) -> Manifest:
    git(["checkout", "mane"], repo_root)
    _random_commits(repo_root, manifest, 2, prefix="ckpt2")
    return manifest


def checkout_variant_3_feature_foobar(repo_root: Path, manifest: Manifest) -> Manifest:
    git(["checkout", "mane"], repo_root)
    git(["checkout", "-b", "feature/foobar"], repo_root)
    _random_commits(repo_root, manifest, 2, prefix="ckpt3")
    return manifest


def checkout_variant_4_test_idk_lol(repo_root: Path, manifest: Manifest) -> Manifest:
    git(["checkout", "mane"], repo_root)
    git(["checkout", "-b", "test_idk_lol"], repo_root)
    _random_commits(repo_root, manifest, 2, prefix="ckpt4")
    return manifest


def checkout_variant_5_unclean_code_only(repo_root: Path, manifest: Manifest) -> Manifest:
    git(["checkout", "mane"], repo_root)
    git(["checkout", "-b", "ai/UNCLEAN/feature/batz"], repo_root)
    _random_commits(repo_root, manifest, 2, prefix="ckpt5")
    return manifest


def checkout_variant_6_unclean_ai_only(repo_root: Path, manifest: Manifest) -> Manifest:
    git(["checkout", "mane"], repo_root)
    git(["checkout", "-b", "ai/UNCLEAN/feature/batz"], repo_root)
    _random_commits(repo_root, manifest, 2, prefix="ckpt6", ai=True)
    return manifest


def checkout_variant_7_unclean_both(repo_root: Path, manifest: Manifest) -> Manifest:
    git(["checkout", "mane"], repo_root)
    git(["checkout", "-b", "ai/UNCLEAN/feature/batz"], repo_root)
    _random_commits(repo_root, manifest, 2, prefix="ckpt7", both=True)
    return manifest


def checkout_variant_8_unclean_mixed_ai_code_both(
    repo_root: Path, manifest: Manifest, *, branch_name: str = "ai/UNCLEAN/feature/batz"
) -> Manifest:
    git(["checkout", "mane"], repo_root)
    git(["checkout", "-b", branch_name], repo_root)
    _random_commits(repo_root, manifest, 2, prefix="ckpt8_ai", ai=True)
    _random_commits(repo_root, manifest, 2, prefix="ckpt8_code")
    _random_commits(repo_root, manifest, 2, prefix="ckpt8_both", both=True)
    return manifest


def checkout_variant_9_history_master_plus_unclean_mixed(repo_root: Path, manifest: Manifest) -> Manifest:
    git(["checkout", "mane"], repo_root)
    git(["checkout", "-b", "ai/history/mane"], repo_root)
    _random_commits(repo_root, manifest, 2, prefix="ckpt9_history", ai=True)
    return checkout_variant_8_unclean_mixed_ai_code_both(repo_root, manifest)


BRANCH_VARIANTS: list[tuple[str, Callable[[Path, Manifest], Manifest]]] = [
    ("1_stay_on_mane", checkout_variant_1_stay_on_mane),
    ("2_mane_plus_commits", checkout_variant_2_mane_plus_commits),
    ("3_feature_foobar", checkout_variant_3_feature_foobar),
    ("4_test_idk_lol", checkout_variant_4_test_idk_lol),
    ("5_unclean_code_only", checkout_variant_5_unclean_code_only),
    ("6_unclean_ai_only", checkout_variant_6_unclean_ai_only),
    ("7_unclean_both", checkout_variant_7_unclean_both),
    ("8_unclean_mixed", checkout_variant_8_unclean_mixed_ai_code_both),
    ("9_history_master_plus_unclean_mixed", checkout_variant_9_history_master_plus_unclean_mixed),
]
