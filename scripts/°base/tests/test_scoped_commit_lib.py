"""Tests for `git/°scoped_commit_lib`: the shared, hook-free, scoped auto-commit."""

from __future__ import annotations

import contextlib
import io
import os
import sys
import unittest
from importlib import import_module
from pathlib import Path
from tempfile import TemporaryDirectory

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "git"))

from _git_test_helpers import git, init_repo, make_commit  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "ai" / "hooks"))

scoped_commit_lib = import_module("°scoped_commit_lib")
hooks_lib = import_module("_lib")


class ScopedCommitTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.repo = Path(self.tmp.name).resolve()
        init_repo(self.repo)
        make_commit(self.repo, "base.txt", "base")
    # end def

    def write(self, name: str, content: str) -> None:
        path = self.repo / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content)
    # end def

    def head_files(self, rev: str = "HEAD") -> list[str]:
        return git(["show", "--name-status", "--format=", rev], self.repo).splitlines()
    # end def

    def quiet(self) -> contextlib.AbstractContextManager[io.StringIO]:
        return contextlib.redirect_stderr(io.StringIO())
    # end def
# end class


class CommitBlockerTest(ScopedCommitTestCase):
    def gitdir(self) -> Path:
        return self.repo / ".git"
    # end def

    def test_clean_repo_is_safe(self) -> None:
        self.assertIsNone(scoped_commit_lib.commit_blocker(None, self.repo))
    # end def

    def test_blocking_markers(self) -> None:
        for marker in ("MERGE_HEAD", "CHERRY_PICK_HEAD", "REVERT_HEAD", "BISECT_LOG", "sequencer", "rebase-merge", "rebase-apply", "index.lock"):
            with self.subTest(marker=marker):
                path = self.gitdir() / marker
                path.write_text("")
                self.addCleanup(path.unlink, missing_ok=True)
                self.assertEqual(scoped_commit_lib.commit_blocker(None, self.repo), f"{marker} present")
                path.unlink()
            # end with
        # end for
    # end def

    def test_merge_event_tolerates_merge_head(self) -> None:
        (self.gitdir() / "MERGE_HEAD").write_text("")
        self.assertIsNone(scoped_commit_lib.commit_blocker("merge", self.repo))
        self.assertEqual(scoped_commit_lib.commit_blocker("rebase", self.repo), "MERGE_HEAD present")
    # end def

    def test_rebase_event_tolerates_rebase_dirs(self) -> None:
        (self.gitdir() / "rebase-merge").mkdir()
        self.assertIsNone(scoped_commit_lib.commit_blocker("rebase", self.repo))
        self.assertEqual(scoped_commit_lib.commit_blocker("merge", self.repo), "rebase-merge present")
    # end def

    def test_detached_head(self) -> None:
        git(["checkout", "--detach"], self.repo)
        self.assertEqual(scoped_commit_lib.commit_blocker(None, self.repo), "detached HEAD")
    # end def

    def test_not_a_repo_does_not_raise(self) -> None:
        with TemporaryDirectory() as plain:
            self.assertEqual(scoped_commit_lib.commit_blocker(None, Path(plain)), "not a git repository")
        # end with
    # end def
# end class


class CommitStagedPathsTest(ScopedCommitTestCase):
    def test_commits_only_the_given_paths(self) -> None:
        self.write("mine.txt", "mine")
        self.write("other.txt", "other")
        git(["add", "mine.txt", "other.txt"], self.repo)
        self.write("unstaged.txt", "unstaged")

        sha = scoped_commit_lib.commit_staged_paths(["mine.txt"], "ai: mine.", cwd=self.repo)

        self.assertEqual(sha, git(["rev-parse", "HEAD"], self.repo))
        self.assertEqual(git(["log", "-1", "--format=%s"], self.repo), "ai: mine.")
        self.assertEqual(self.head_files(), ["A\tmine.txt"])
        self.assertEqual(git(["diff", "--cached", "--name-only"], self.repo), "other.txt")
        self.assertIn("?? unstaged.txt", git(["status", "--porcelain"], self.repo))
    # end def

    def test_committed_path_leaves_a_clean_status(self) -> None:
        self.write("mine.txt", "mine")
        git(["add", "mine.txt"], self.repo)
        scoped_commit_lib.commit_staged_paths(["mine.txt"], "ai: mine.", cwd=self.repo)
        self.assertEqual(git(["status", "--porcelain"], self.repo), "")
    # end def

    def test_staged_deletion(self) -> None:
        git(["rm", "--quiet", "base.txt"], self.repo)
        scoped_commit_lib.commit_staged_paths(["base.txt"], "ai: drop.", cwd=self.repo)
        self.assertEqual(self.head_files(), ["D\tbase.txt"])
    # end def

    def test_unchanged_tree_makes_no_commit(self) -> None:
        before = git(["rev-parse", "HEAD"], self.repo)
        self.assertIsNone(scoped_commit_lib.commit_staged_paths(["base.txt"], "ai: nothing.", cwd=self.repo))
        self.assertEqual(git(["rev-parse", "HEAD"], self.repo), before)
    # end def

    def test_cwd_in_subdirectory_uses_relative_paths(self) -> None:
        self.write("sub/file.txt", "x")
        git(["add", "sub/file.txt"], self.repo)
        scoped_commit_lib.commit_staged_paths(["file.txt"], "ai: sub.", cwd=self.repo / "sub")
        self.assertEqual(self.head_files(), ["A\tsub/file.txt"])
    # end def

    def test_pathspec_characters_are_literal(self) -> None:
        self.write("a*.txt", "star")
        self.write("ab.txt", "other")
        git(["add", "--", "a*.txt", "ab.txt"], self.repo)
        scoped_commit_lib.commit_staged_paths(["a*.txt"], "ai: star.", cwd=self.repo)
        self.assertEqual(self.head_files(), ["A\ta*.txt"])
    # end def

    def test_directory_path_commits_additions_and_deletions_below_it(self) -> None:
        make_commit(self.repo, "dir/old.txt", "old")
        self.write("dir/new.txt", "new")
        self.write("outside.txt", "outside")
        git(["rm", "--quiet", "dir/old.txt"], self.repo)
        git(["add", "dir/new.txt", "outside.txt"], self.repo)

        scoped_commit_lib.commit_staged_paths(["dir"], "ai: dir.", cwd=self.repo)

        self.assertEqual(sorted(self.head_files()), ["A\tdir/new.txt", "D\tdir/old.txt"])
        self.assertEqual(git(["diff", "--cached", "--name-only"], self.repo), "outside.txt")
    # end def

    def test_does_not_commit_while_blocked(self) -> None:
        self.write("mine.txt", "mine")
        git(["add", "mine.txt"], self.repo)
        before = git(["rev-parse", "HEAD"], self.repo)
        (self.repo / ".git" / "MERGE_HEAD").write_text("")
        with self.quiet():
            self.assertIsNone(scoped_commit_lib.commit_staged_paths(["mine.txt"], "ai: mine.", cwd=self.repo))
        # end with
        self.assertEqual(git(["rev-parse", "HEAD"], self.repo), before)
        self.assertEqual(git(["diff", "--cached", "--name-only"], self.repo), "mine.txt")
    # end def

    def test_does_not_commit_on_detached_head(self) -> None:
        self.write("mine.txt", "mine")
        git(["add", "mine.txt"], self.repo)
        git(["checkout", "--detach"], self.repo)
        before = git(["rev-parse", "HEAD"], self.repo)
        with self.quiet():
            self.assertIsNone(scoped_commit_lib.commit_staged_paths(["mine.txt"], "ai: mine.", cwd=self.repo))
        # end with
        self.assertEqual(git(["rev-parse", "HEAD"], self.repo), before)
        self.assertEqual(git(["diff", "--cached", "--name-only"], self.repo), "mine.txt")
    # end def

    def test_plumbing_failure_leaves_paths_staged(self) -> None:
        self.write("mine.txt", "mine")
        git(["add", "mine.txt"], self.repo)
        before = git(["rev-parse", "HEAD"], self.repo)
        objects = self.repo / ".git" / "objects"
        objects.chmod(0o500)
        self.addCleanup(objects.chmod, 0o700)
        with self.quiet():
            result = scoped_commit_lib.commit_staged_paths(["mine.txt"], "ai: mine.", cwd=self.repo)
        # end with
        objects.chmod(0o700)
        self.assertIsNone(result)
        self.assertEqual(git(["rev-parse", "HEAD"], self.repo), before)
        self.assertEqual(git(["diff", "--cached", "--name-only"], self.repo), "mine.txt")
    # end def

    def test_hooks_do_not_run(self) -> None:
        hook = self.repo / ".git" / "hooks" / "pre-commit"
        hook.write_text("#!/bin/sh\nexit 1\n")
        hook.chmod(0o755)
        self.write("mine.txt", "mine")
        git(["add", "mine.txt"], self.repo)
        self.assertIsNotNone(scoped_commit_lib.commit_staged_paths(["mine.txt"], "ai: mine.", cwd=self.repo))
    # end def
# end class


class StageAndCommitTest(ScopedCommitTestCase):
    def test_stages_and_commits_new_file(self) -> None:
        self.write("new.txt", "new")
        self.write("untouched.txt", "untouched")
        sha = scoped_commit_lib.stage_and_commit(["new.txt"], "ai: new.", cwd=self.repo)
        self.assertEqual(sha, git(["rev-parse", "HEAD"], self.repo))
        self.assertEqual(self.head_files(), ["A\tnew.txt"])
        self.assertIn("?? untouched.txt", git(["status", "--porcelain"], self.repo))
    # end def

    def test_modified_tracked_file(self) -> None:
        self.write("base.txt", "changed")
        scoped_commit_lib.stage_and_commit(["base.txt"], "ai: change.", cwd=self.repo)
        self.assertEqual(self.head_files(), ["M\tbase.txt"])
    # end def

    def test_deleted_tracked_file(self) -> None:
        (self.repo / "base.txt").unlink()
        scoped_commit_lib.stage_and_commit(["base.txt"], "ai: drop.", cwd=self.repo)
        self.assertEqual(self.head_files(), ["D\tbase.txt"])
    # end def

    def test_already_removed_path_is_still_committed(self) -> None:
        git(["rm", "--quiet", "base.txt"], self.repo)
        scoped_commit_lib.stage_and_commit(["base.txt"], "ai: drop.", cwd=self.repo)
        self.assertEqual(self.head_files(), ["D\tbase.txt"])
    # end def

    def test_directory_with_new_files(self) -> None:
        self.write("dir/a.txt", "a")
        self.write("dir/b.txt", "b")
        scoped_commit_lib.stage_and_commit(["dir"], "ai: dir.", cwd=self.repo)
        self.assertEqual(sorted(self.head_files()), ["A\tdir/a.txt", "A\tdir/b.txt"])
    # end def

    def test_gitignored_path_is_skipped(self) -> None:
        self.write(".gitignore", "ignored.txt\n")
        git(["add", ".gitignore"], self.repo)
        git(["commit", "-m", "ignore"], self.repo)
        self.write("ignored.txt", "x")
        self.write("kept.txt", "y")
        with self.quiet():
            scoped_commit_lib.stage_and_commit(["ignored.txt", "kept.txt"], "ai: both.", cwd=self.repo)
        # end with
        self.assertEqual(self.head_files(), ["A\tkept.txt"])
    # end def

    def test_blocked_state_only_stages(self) -> None:
        self.write("new.txt", "new")
        before = git(["rev-parse", "HEAD"], self.repo)
        git(["checkout", "--detach"], self.repo)
        with self.quiet():
            self.assertIsNone(scoped_commit_lib.stage_and_commit(["new.txt"], "ai: new.", cwd=self.repo))
        # end with
        self.assertEqual(git(["rev-parse", "HEAD"], self.repo), before)
        self.assertEqual(git(["diff", "--cached", "--name-only"], self.repo), "new.txt")
    # end def

    def test_nothing_stageable_returns_none(self) -> None:
        with self.quiet():
            self.assertIsNone(scoped_commit_lib.stage_and_commit(["missing.txt"], "ai: none.", cwd=self.repo))
        # end with
    # end def
# end class


class AppendAndCommitHookTest(ScopedCommitTestCase):
    def append(self) -> None:
        previous = Path.cwd()
        os.chdir(self.repo)
        self.addCleanup(os.chdir, previous)
        hooks_lib.append_and_commit(
            self.repo / "log.md", "entry\n", commit_template_relpath="ai/commit-templates/none", default_commit_msg="ai: log"
        )
    # end def

    def test_commits_the_log_on_a_branch(self) -> None:
        self.append()
        self.assertEqual(git(["log", "-1", "--format=%s"], self.repo), "ai: log")
        self.assertEqual(git(["status", "--porcelain"], self.repo), "")
    # end def

    def test_only_stages_the_log_on_a_detached_head(self) -> None:
        git(["checkout", "--detach"], self.repo)
        before = git(["rev-parse", "HEAD"], self.repo)
        with self.quiet():
            self.append()
        # end with
        self.assertEqual(git(["rev-parse", "HEAD"], self.repo), before)
        self.assertEqual(git(["diff", "--cached", "--name-only"], self.repo), "log.md")
    # end def

    def test_only_stages_the_log_during_a_merge(self) -> None:
        (self.repo / ".git" / "MERGE_HEAD").write_text(git(["rev-parse", "HEAD"], self.repo) + "\n")
        before = git(["rev-parse", "HEAD"], self.repo)
        with self.quiet():
            self.append()
        # end with
        self.assertEqual(git(["rev-parse", "HEAD"], self.repo), before)
        self.assertEqual(git(["diff", "--cached", "--name-only"], self.repo), "log.md")
    # end def
# end class


if __name__ == "__main__":
    unittest.main()
# end if
