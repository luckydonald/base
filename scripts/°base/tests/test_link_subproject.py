"""Tests for `scripts/°base/init/link_subproject.py`'s `ai/.env` symlink
state machine and its post-commit-verification-failure purge routine.

Every test builds its own throwaway repo under a pytest/unittest tmp
directory — nothing here ever touches this actual repo's real branches or
tags.
"""

from __future__ import annotations

import importlib
import os
import subprocess
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _git_test_helpers import git, init_repo, make_commit  # noqa: E402

INIT_DIR = Path(__file__).resolve().parents[1] / "init"
sys.path.insert(0, str(INIT_DIR))
link_subproject = importlib.import_module("link_subproject")

REPO_ROOT = Path(__file__).resolve().parents[3]


def build_subproject_repo() -> tuple[TemporaryDirectory, Path, Path]:
    """A minimal throwaway repo with one commit and an (uncreated) `sub/`
    subfolder — enough for `link_env`/`purge_commit_everywhere` in isolation,
    without the cost of a full monorepo checkout.
    """
    tmp = TemporaryDirectory()
    repo_root = Path(tmp.name) / "repo"
    repo_root.mkdir()
    init_repo(repo_root)
    make_commit(repo_root, ".claude/keep", "init")
    sub_dir = repo_root / "sub"
    sub_dir.mkdir()
    return tmp, repo_root, sub_dir


def build_merged_monorepo_fixture() -> tuple[TemporaryDirectory, Path]:
    """A repo built the way `docs/README.md#all-code-for-c-as-a-single-copy-pastable-one`
    documents for adopting `base/base` — simplified to pull straight from
    this checkout instead of GitHub, and dropping the `user.name` check and
    `pre-commit install` (not relevant for a throwaway test repo) — so
    `main()` has genuine `.claude`/`ai/settings`/etc. targets to link
    against, the same as a real subproject would.
    """
    tmp = TemporaryDirectory()
    repo_root = Path(tmp.name) / "repo"
    repo_root.mkdir()
    git(["init", "-q", "-b", "mane"], repo_root)
    git(["config", "user.email", "test@example.com"], repo_root)
    git(["config", "user.name", "Test"], repo_root)
    git(["remote", "add", "base", str(REPO_ROOT)], repo_root)
    git(["fetch", "-q", "base", "base"], repo_root)
    git(["lfs", "install", "--local"], repo_root)
    git(["merge", "-q", "--allow-unrelated-histories", "--no-verify", "base/base"], repo_root)
    return tmp, repo_root
# end def


class LinkEnvTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp, self.repo_root, self.sub_dir = build_subproject_repo()
        self.addCleanup(self.tmp.cleanup)
        link_subproject.sub_dir = self.sub_dir
        link_subproject.git_root = self.repo_root
    # end def

    def target(self) -> Path:
        return self.sub_dir / "ai" / ".env"
    # end def

    def test_fresh_subfolder_gets_symlinked_and_committed(self) -> None:
        link_subproject.link_env()

        target = self.target()
        self.assertTrue(target.is_symlink())
        self.assertEqual(os.path.realpath(target), os.path.realpath(self.repo_root / "ai" / ".env"))
        self.assertTrue(link_subproject.env_symlink_committed("ai/.env", target))
    # end def

    def test_rerun_on_an_already_committed_symlink_is_a_no_op(self) -> None:
        link_subproject.link_env()
        head_before = git(["rev-parse", "HEAD"], self.repo_root)

        link_subproject.link_env()
        head_after = git(["rev-parse", "HEAD"], self.repo_root)

        self.assertEqual(head_before, head_after)
    # end def

    def test_correct_but_uncommitted_symlink_gets_committed_on_rerun(self) -> None:
        (self.sub_dir / "ai").mkdir(parents=True)
        (self.repo_root / "ai").mkdir(exist_ok=True)
        (self.repo_root / "ai" / ".env").touch()
        rel_link = os.path.relpath(self.repo_root / "ai" / ".env", self.sub_dir / "ai")
        self.target().symlink_to(rel_link)

        self.assertFalse(link_subproject.env_symlink_committed("ai/.env", self.target()))

        link_subproject.link_env()

        self.assertTrue(link_subproject.env_symlink_committed("ai/.env", self.target()))
    # end def

    def test_regular_file_target_is_left_untouched(self) -> None:
        (self.sub_dir / "ai").mkdir(parents=True)
        self.target().write_text("SECRET=1")

        link_subproject.link_env()

        self.assertEqual(self.target().read_text(), "SECRET=1")
        staged = git(["diff", "--cached", "--name-only"], self.repo_root)
        self.assertEqual(staged, "", "nothing should have been staged")
    # end def

    def test_symlink_to_something_else_is_left_untouched(self) -> None:
        (self.sub_dir / "ai").mkdir(parents=True)
        other = self.repo_root / "other_target"
        other.write_text("nope")
        rel_link = os.path.relpath(other, self.sub_dir / "ai")
        self.target().symlink_to(rel_link)

        link_subproject.link_env()

        self.assertEqual(os.readlink(self.target()), rel_link)
        staged = git(["diff", "--cached", "--name-only"], self.repo_root)
        self.assertEqual(staged, "", "nothing should have been staged")
    # end def

    def test_post_commit_verification_failure_purges_the_commit(self) -> None:
        with mock.patch.object(link_subproject, "verify_env_symlink", side_effect=[True, False]):
            with self.assertRaises(RuntimeError):
                link_subproject.link_env()
            # end with
        # end with

        target = self.target()
        self.assertTrue(target.is_symlink())
        self.assertFalse(link_subproject.is_tracked("ai/.env"))

        log = git(["log", "--oneline"], self.repo_root)
        self.assertNotIn("link_subproject", log)
    # end def

    def test_purge_failure_never_prints_the_secret_env_content(self) -> None:
        secret = "SUPER_SECRET_TOKEN_MARKER"
        (self.repo_root / "ai").mkdir(exist_ok=True)
        (self.repo_root / "ai" / ".env").write_text(secret)

        import contextlib
        import io

        captured = io.StringIO()
        with contextlib.redirect_stdout(captured), contextlib.redirect_stderr(captured):
            with mock.patch.object(link_subproject, "verify_env_symlink", side_effect=[True, False]):
                with self.assertRaises(RuntimeError):
                    link_subproject.link_env()
                # end with
            # end with
        # end with

        self.assertNotIn(secret, captured.getvalue())
    # end def
# end class


class PurgeCommitEverywhereTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp, self.repo_root, self.sub_dir = build_subproject_repo()
        self.addCleanup(self.tmp.cleanup)
        link_subproject.sub_dir = self.sub_dir
        link_subproject.git_root = self.repo_root
        self.base_sha = git(["rev-parse", "HEAD"], self.repo_root)
    # end def

    def test_rewinds_a_branch_pointing_directly_at_the_bad_commit(self) -> None:
        bad_sha = make_commit(self.sub_dir, "ai/.env", "bad env symlink stand-in")

        link_subproject.purge_commit_everywhere(bad_sha, "sub/ai/.env")

        self.assertEqual(git(["rev-parse", "master"], self.repo_root), self.base_sha)
    # end def

    def test_rewrites_a_tag_pointing_at_the_bad_commit(self) -> None:
        bad_sha = make_commit(self.sub_dir, "ai/.env", "bad env symlink stand-in")
        git(["tag", "mytag"], self.repo_root)

        link_subproject.purge_commit_everywhere(bad_sha, "sub/ai/.env")

        self.assertEqual(git(["rev-parse", "mytag"], self.repo_root), self.base_sha)
    # end def

    def test_replays_descendants_committed_on_top_of_the_bad_commit(self) -> None:
        bad_sha = make_commit(self.sub_dir, "ai/.env", "bad env symlink stand-in")
        make_commit(self.sub_dir, "other/file.txt", "unrelated later work")

        link_subproject.purge_commit_everywhere(bad_sha, "sub/ai/.env")

        new_tip = git(["rev-parse", "master"], self.repo_root)
        self.assertTrue(link_subproject.is_ancestor(self.base_sha, new_tip, self.repo_root))
        self.assertFalse(link_subproject.is_ancestor(bad_sha, new_tip, self.repo_root))

        tree_files = git(["ls-tree", "-r", "--name-only", new_tip], self.repo_root).splitlines()
        self.assertNotIn("sub/ai/.env", tree_files)
        self.assertIn("sub/other/file.txt", tree_files)
    # end def

    def test_leaves_a_still_reachable_shared_blob_alone(self) -> None:
        content = "../../ai/.env"
        bad_sha = make_commit(self.sub_dir, "ai/.env", "bad env symlink stand-in", content=content)

        git(["branch", "sibling", self.base_sha], self.repo_root)
        git(["checkout", "-q", "sibling"], self.repo_root)
        make_commit(self.repo_root, "other_subproject/ai/.env", "identical content elsewhere", content=content)
        git(["checkout", "-q", "master"], self.repo_root)

        blob_sha = git(["rev-parse", f"{bad_sha}:sub/ai/.env"], self.repo_root)

        link_subproject.purge_commit_everywhere(bad_sha, "sub/ai/.env")

        result = subprocess.run(
            ["git", "-C", str(self.repo_root), "cat-file", "-e", blob_sha], capture_output=True
        )
        self.assertEqual(result.returncode, 0, "blob should still be reachable via the sibling branch")
    # end def

    def test_never_shells_out_to_gc_prune_or_repack(self) -> None:
        source = (INIT_DIR / "link_subproject.py").read_text()
        for forbidden in ('"gc"', '"prune"', '"repack"'):
            self.assertNotIn(forbidden, source)
        # end for
    # end def
# end class


class LinkSubprojectEndToEndTests(unittest.TestCase):
    def test_main_links_and_commits_against_a_real_merged_monorepo(self) -> None:
        tmp, repo_root = build_merged_monorepo_fixture()
        self.addCleanup(tmp.cleanup)
        sub_dir = repo_root / "some_project"
        sub_dir.mkdir()

        result = subprocess.run(
            [sys.executable, str(INIT_DIR / "link_subproject.py")],
            cwd=sub_dir,
            capture_output=True,
            text=True,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue((sub_dir / ".claude").is_symlink())
        self.assertTrue((sub_dir / "ai" / ".env").is_symlink())

        # Everything link_subproject touched should be staged (or, for
        # ai/.env, already committed) — nothing left untracked or unstaged.
        status_lines = git(["status", "--porcelain"], repo_root).splitlines()
        for line in status_lines:
            self.assertFalse(line.startswith("??"), f"untracked leftover: {line}")
            self.assertEqual(line[1], " ", f"unstaged leftover: {line}")
        # end for

        # idempotent rerun
        rerun = subprocess.run(
            [sys.executable, str(INIT_DIR / "link_subproject.py")],
            cwd=sub_dir,
            capture_output=True,
            text=True,
        )
        self.assertEqual(rerun.returncode, 0, rerun.stderr)
    # end def
# end class


if __name__ == "__main__":
    unittest.main()
# end if
