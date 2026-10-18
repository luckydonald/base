from __future__ import annotations

import contextlib
import importlib.util
import io
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _git_test_helpers import git, init_repo, make_commit  # noqa: E402

SCRIPT = Path(__file__).resolve().parents[1] / "git" / "get-base.py"
SPLIT_PY = Path(__file__).resolve().parents[1] / "git" / "split.py"
SPLIT_LIB_ROOT = Path(__file__).resolve().parents[1] / "git" / "°split_lib"


def load_script_module():
    spec = importlib.util.spec_from_file_location("get_base", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _purge_split_lib_cache() -> None:
    """Each test seeds its own `°split_lib` copy under a fresh temp worktree,
    but `import_module("°split_lib...")` caches the package (and its
    `__path__`) globally in `sys.modules` -- so a later test's worktree,
    once its own temp dir is cleaned up, would resolve submodules against a
    now-deleted stale path. Drop the cache so every test re-imports fresh."""
    for name in list(sys.modules):
        if name == "°split_lib" or name.startswith("°split_lib."):
            del sys.modules[name]


def _seed_real_split_tooling(base_repo: Path) -> None:
    """Copy the real `split.py` + full `°split_lib` package into a fake
    `base` remote's tree, so a checked-out worktree of it can actually run
    `update-history-master`/`bootstrap-branch` end to end, not just resolve
    `°split_lib.branches` for auto-mode's own decision-making."""
    git_dir = base_repo / "scripts" / "°base" / "git"
    dest = git_dir / "°split_lib"
    dest.mkdir(parents=True, exist_ok=True)
    for path in SPLIT_LIB_ROOT.glob("*.py"):
        (dest / path.name).write_text(path.read_text())
    (git_dir / "split.py").write_text(SPLIT_PY.read_text())


class GetBaseTests(unittest.TestCase):
    def setUp(self):
        self.module = load_script_module()
        _purge_split_lib_cache()
        self.addCleanup(_purge_split_lib_cache)

        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.repo = Path(self._tmp.name)
        init_repo(self.repo)
        make_commit(self.repo, "README.md", "initial commit")

        # A fake "base" remote, cloned from this repo so history is shared
        # (mirrors the pattern used in test_git_split_history_master.py).
        base_tmp = tempfile.TemporaryDirectory()
        self.addCleanup(base_tmp.cleanup)
        self.base_repo = Path(base_tmp.name)
        git(["clone", str(self.repo), str(self.base_repo)], self.repo)
        git(["config", "user.email", "test@example.com"], self.base_repo)
        git(["config", "user.name", "Test"], self.base_repo)
        make_commit(self.base_repo, "scripts/°base/git/split.py", "pretend tool", content="# stand-in\n")
        git(["branch", "-m", "base"], self.base_repo)

    def _add_real_base_remote(self):
        git(["remote", "add", "base", str(self.base_repo)], self.repo)

    def _seed_real_split_lib(self):
        """Copy the real branches.py/__init__.py into the fake base remote's
        tree, so auto_argv's `importlib.import_module("°split_lib.branches")`
        (against the worktree, once created) actually resolves."""
        dest = self.base_repo / "scripts" / "°base" / "git" / "°split_lib"
        dest.mkdir(parents=True, exist_ok=True)
        for name in ("__init__.py", "branches.py"):
            (dest / name).write_text((SPLIT_LIB_ROOT / name).read_text())
        git(["add", "."], self.base_repo)
        git(["commit", "-m", "seed real °split_lib.branches"], self.base_repo)

    def test_ensure_base_remote_adds_when_missing(self):
        stderr = io.StringIO()
        with contextlib.redirect_stderr(stderr):
            self.module.ensure_base_remote(self.repo, "someuser")

        url = git(["remote", "get-url", "base"], self.repo)
        self.assertEqual(url, self.module.remote_url("someuser"))
        self.assertIn(f"get-base.py: adding base remote: {url}", stderr.getvalue())

    def test_ensure_base_remote_leaves_existing_url_untouched(self):
        self._add_real_base_remote()
        stderr = io.StringIO()
        with contextlib.redirect_stderr(stderr):
            self.module.ensure_base_remote(self.repo, "someuser")

        url = git(["remote", "get-url", "base"], self.repo)
        self.assertEqual(url, str(self.base_repo))
        self.assertIn(f"get-base.py: base remote already exists: {self.base_repo}", stderr.getvalue())

    def test_run_reports_git_stderr_without_called_process_error_traceback(self):
        completed = subprocess.CompletedProcess(
            args=["git", "worktree", "add"],
            returncode=128,
            stdout="",
            stderr="fatal: the worktree path is already registered\n",
        )
        with mock.patch.object(self.module.subprocess, "run", return_value=completed):
            with self.assertRaises(SystemExit) as raised:
                self.module._run(["worktree", "add"])
            # end with
        # end with

        message = str(raised.exception)
        self.assertIn("Git command failed with exit code 128: git worktree add", message)
        self.assertIn("fatal: the worktree path is already registered", message)
        self.assertNotIn("CalledProcessError", message)
    # end def

    def test_extract_base_ref_default_when_absent(self):
        ref, remaining = self.module._extract_base_ref(["bootstrap-branch", "feature"], "base")
        self.assertEqual(ref, "base")
        self.assertEqual(remaining, ["bootstrap-branch", "feature"])

    def test_extract_base_ref_space_form_is_consumed_not_forwarded(self):
        ref, remaining = self.module._extract_base_ref(
            ["--base-ref", "my-branch", "bootstrap-branch", "feature"], "base",
        )
        self.assertEqual(ref, "my-branch")
        self.assertEqual(remaining, ["bootstrap-branch", "feature"])

    def test_extract_base_ref_equals_form_is_consumed_not_forwarded(self):
        ref, remaining = self.module._extract_base_ref(
            ["bootstrap-branch", "--base-ref=deadbeef", "feature"], "base",
        )
        self.assertEqual(ref, "deadbeef")
        self.assertEqual(remaining, ["bootstrap-branch", "feature"])

    def test_extract_base_ref_missing_value_raises(self):
        with self.assertRaises(SystemExit):
            self.module._extract_base_ref(["--base-ref"], "base")

    def test_ensure_worktree_checks_out_custom_ref(self):
        self._add_real_base_remote()
        make_commit(self.base_repo, "other.txt", "on another branch", content="other\n")
        git(["checkout", "-b", "other-branch"], self.base_repo)
        make_commit(self.base_repo, "only-on-other.txt", "distinguishing commit", content="x\n")
        git(["checkout", "base"], self.base_repo)

        stderr = io.StringIO()
        with contextlib.redirect_stderr(stderr):
            self.module.fetch_base(self.repo, "other-branch")
            path = self.module.ensure_worktree(self.repo, "other-branch")

        self.assertTrue((path / "only-on-other.txt").exists())
        self.assertIn("get-base.py: fetching base/other-branch", stderr.getvalue())

    def test_ensure_worktree_checks_out_specific_commit(self):
        self._add_real_base_remote()
        make_commit(self.base_repo, "pinned.txt", "pinned commit", content="pin\n")
        pinned_sha = git(["rev-parse", "HEAD"], self.base_repo)
        make_commit(self.base_repo, "after-pin.txt", "moves base forward", content="later\n")

        self.module.fetch_base(self.repo, pinned_sha)
        path = self.module.ensure_worktree(self.repo, pinned_sha)

        self.assertTrue((path / "pinned.txt").exists())
        self.assertFalse((path / "after-pin.txt").exists())

    def test_main_forwards_base_ref_env_var_to_worktree(self):
        self._add_real_base_remote()
        make_commit(self.base_repo, "env-ref.txt", "on env-selected branch", content="e\n")
        git(["checkout", "-b", "env-branch"], self.base_repo)
        make_commit(self.base_repo, "only-via-env.txt", "distinguishing commit", content="e2\n")
        git(["checkout", "base"], self.base_repo)

        stderr = io.StringIO()
        with contextlib.redirect_stderr(stderr), \
             mock.patch.object(self.module, "find_repo_root", return_value=self.repo), \
             mock.patch.object(self.module, "delegate"), \
             mock.patch.dict(os.environ, {"BASE_GIT_REF": "env-branch"}):
            self.module.main(["update-history-master", "--yes"])

        worktree = self.module.worktree_path(self.repo)
        self.assertTrue((worktree / "only-via-env.txt").exists())

    def test_ensure_worktree_creates_then_refreshes(self):
        self._add_real_base_remote()
        self.module.fetch_base(self.repo)

        stderr = io.StringIO()
        with contextlib.redirect_stderr(stderr):
            path = self.module.ensure_worktree(self.repo)
        self.assertTrue(path.exists())
        self.assertIn(f"get-base.py: creating worktree: {path}", stderr.getvalue())
        first_tip = git(["rev-parse", "HEAD"], path)

        make_commit(self.base_repo, "more.txt", "base advances", content="more\n")
        self.module.fetch_base(self.repo)
        stderr = io.StringIO()
        with contextlib.redirect_stderr(stderr):
            path_again = self.module.ensure_worktree(self.repo)

        self.assertEqual(path, path_again)
        self.assertIn(f"get-base.py: refreshing worktree: {path}", stderr.getvalue())
        second_tip = git(["rev-parse", "HEAD"], path_again)
        self.assertNotEqual(first_tip, second_tip)

    def test_ensure_worktree_replaces_only_its_unique_stale_path(self):
        self._add_real_base_remote()
        self.module.fetch_base(self.repo)
        path = self.module.worktree_path(self.repo)
        stale_file = path / "stale.txt"
        stale_file.parent.mkdir(parents=True)
        stale_file.write_text("stale\n")
        sibling_file = path.parent / "user-workspace" / "keep.txt"
        sibling_file.parent.mkdir()
        sibling_file.write_text("keep\n")

        stderr = io.StringIO()
        with contextlib.redirect_stderr(stderr):
            result = self.module.ensure_worktree(self.repo)
        # end with

        self.assertEqual(result, path)
        self.assertFalse(stale_file.exists())
        self.assertEqual(sibling_file.read_text(), "keep\n")
        self.assertEqual(git(["rev-parse", "--show-toplevel"], path), str(path.resolve()))
        self.assertIn(f"get-base.py: removing stale worktree: {path}", stderr.getvalue())
    # end def

    def test_main_delegates_with_repo_root_and_forwarded_argv(self):
        self._add_real_base_remote()

        captured = {}
        stderr = io.StringIO()

        def fake_exec_module(self_loader, module):
            def fake_main(argv):
                captured["argv"] = argv
                return 0

            module.main = fake_main

        with contextlib.redirect_stderr(stderr), \
             mock.patch.object(self.module.importlib.util.spec_from_file_location("x", SPLIT_PY).loader.__class__, "exec_module", fake_exec_module), \
             mock.patch.object(self.module, "find_repo_root", return_value=self.repo), \
             self.assertRaises(SystemExit) as exit_ctx:
            self.module.main(["bootstrap-branch", "feature"])

        self.assertEqual(exit_ctx.exception.code, 0)
        argv = captured["argv"]
        self.assertIn("--repo-root", argv)
        self.assertEqual(argv[argv.index("--repo-root") + 1], str(self.repo))
        self.assertEqual(argv[-2:], ["bootstrap-branch", "feature"])

        self.assertIsNotNone(git(["remote", "get-url", "base"], self.repo))
        progress = stderr.getvalue()
        self.assertIn(f"get-base.py: repo root: {self.repo}", progress)
        self.assertIn(f"get-base.py: {self.module.REMOTE_NAME} remote already exists: {self.base_repo}", progress)
        self.assertIn("get-base.py: fetching base/base", progress)
        self.assertIn(f"get-base.py: creating worktree: {self.module.worktree_path(self.repo)}", progress)
        self.assertIn("get-base.py: delegating:", progress)
        self.assertIn("bootstrap-branch feature", progress)

    def test_never_touches_current_checkout(self):
        self._add_real_base_remote()
        (self.repo / "untracked.txt").write_text("scratch")
        status_before = git(["status", "--porcelain"], self.repo)
        head_before = git(["rev-parse", "HEAD"], self.repo)

        def fake_exec_module(self_loader, module):
            module.main = lambda argv: 0

        with mock.patch.object(self.module.importlib.util.spec_from_file_location("x", SPLIT_PY).loader.__class__, "exec_module", fake_exec_module), \
             mock.patch.object(self.module, "find_repo_root", return_value=self.repo), \
             self.assertRaises(SystemExit):
            self.module.main(["update-history-master", "--yes"])

        self.assertEqual(git(["status", "--porcelain"], self.repo), status_before)
        self.assertEqual(git(["rev-parse", "HEAD"], self.repo), head_before)


class AutoArgvTests(unittest.TestCase):
    def setUp(self):
        self.module = load_script_module()
        _purge_split_lib_cache()
        self.addCleanup(_purge_split_lib_cache)

        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.repo = Path(self._tmp.name)
        init_repo(self.repo, branch="master")
        make_commit(self.repo, "README.md", "initial commit")

        base_tmp = tempfile.TemporaryDirectory()
        self.addCleanup(base_tmp.cleanup)
        self.base_repo = Path(base_tmp.name)
        git(["clone", str(self.repo), str(self.base_repo)], self.repo)
        git(["config", "user.email", "test@example.com"], self.base_repo)
        git(["config", "user.name", "Test"], self.base_repo)
        _seed_real_split_tooling(self.base_repo)
        git(["add", "."], self.base_repo)
        git(["commit", "-m", "seed real split tooling"], self.base_repo)
        git(["branch", "-m", "base"], self.base_repo)

        git(["remote", "add", "base", str(self.base_repo)], self.repo)
        self.module.fetch_base(self.repo)
        self.worktree = self.module.ensure_worktree(self.repo)

    def test_on_main_branch_runs_update_history_master(self):
        git(["checkout", "master"], self.repo)
        self.assertEqual(
            self.module.auto_argv(self.repo, self.worktree),
            ["update-history-master", "--yes"],
        )

    def test_on_history_master_runs_update_history_master(self):
        git(["checkout", "-b", "ai/history/master"], self.repo)
        self.assertEqual(
            self.module.auto_argv(self.repo, self.worktree),
            ["update-history-master", "--yes"],
        )

    def test_on_clean_feature_branch_runs_bootstrap_branch(self):
        git(["checkout", "-b", "feature"], self.repo)

        self.assertEqual(
            self.module.auto_argv(self.repo, self.worktree),
            ["bootstrap-branch", "feature"],
        )

        # `ai/history/master` never existed -- auto mode must have run
        # update-history-master as a prerequisite before deciding to
        # bootstrap, rather than handing back a doomed command.
        self.assertIsNotNone(git(["rev-parse", "ai/history/master"], self.repo))

    def test_on_clean_feature_branch_skips_update_history_master_if_present(self):
        git(["checkout", "-b", "feature"], self.repo)
        self.module.run_split(self.repo, self.worktree, ["update-history-master", "--yes"])
        self.assertIsNotNone(git(["rev-parse", "ai/history/master"], self.repo))

        with mock.patch.object(self.module, "run_split") as run_split:
            self.assertEqual(
                self.module.auto_argv(self.repo, self.worktree),
                ["bootstrap-branch", "feature"],
            )
        run_split.assert_not_called()

    def test_on_clean_feature_branch_aborts_if_update_history_master_fails(self):
        git(["checkout", "-b", "feature"], self.repo)

        with mock.patch.object(self.module, "run_split", return_value=1) as run_split:
            self.assertIsNone(self.module.auto_argv(self.repo, self.worktree))
        run_split.assert_called_once_with(
            self.repo, self.worktree, ["update-history-master", "--yes"],
        )

    def test_on_unclean_branch_runs_forward_sync(self):
        git(["checkout", "-b", "ai/UNCLEAN/feature"], self.repo)
        self.assertEqual(
            self.module.auto_argv(self.repo, self.worktree),
            ["sync-splits", "feature", "--direction=to-clean-history"],
        )

        # `ai/history/master` never existed -- auto mode must have run
        # update-history-master as a prerequisite first (sync-splits forks
        # each branch's own history branch from it), rather than handing
        # back a command doomed to crash with an AssertionError.
        self.assertIsNotNone(git(["rev-parse", "ai/history/master"], self.repo))

    def test_on_unclean_branch_skips_update_history_master_if_present(self):
        git(["checkout", "-b", "ai/UNCLEAN/feature"], self.repo)
        self.module.run_split(self.repo, self.worktree, ["update-history-master", "--yes"])
        self.assertIsNotNone(git(["rev-parse", "ai/history/master"], self.repo))

        with mock.patch.object(self.module, "run_split") as run_split:
            self.assertEqual(
                self.module.auto_argv(self.repo, self.worktree),
                ["sync-splits", "feature", "--direction=to-clean-history"],
            )
        run_split.assert_not_called()

    def test_on_unclean_branch_aborts_if_update_history_master_fails(self):
        git(["checkout", "-b", "ai/UNCLEAN/feature"], self.repo)

        with mock.patch.object(self.module, "run_split", return_value=1) as run_split:
            self.assertIsNone(self.module.auto_argv(self.repo, self.worktree))
        run_split.assert_called_once_with(
            self.repo, self.worktree, ["update-history-master", "--yes"],
        )

    def test_on_non_master_history_branch_runs_forward_sync(self):
        git(["checkout", "-b", "ai/history/feature"], self.repo)
        self.assertEqual(
            self.module.auto_argv(self.repo, self.worktree),
            ["sync-splits", "feature", "--direction=to-clean-history"],
        )
        self.assertIsNotNone(git(["rev-parse", "ai/history/master"], self.repo))

    def test_detached_head_refuses(self):
        head_sha = git(["rev-parse", "HEAD"], self.repo)
        git(["checkout", "--detach", head_sha], self.repo)
        self.assertIsNone(self.module.auto_argv(self.repo, self.worktree))


class MainAutoModeTests(unittest.TestCase):
    def setUp(self):
        self.module = load_script_module()
        _purge_split_lib_cache()
        self.addCleanup(_purge_split_lib_cache)

        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.repo = Path(self._tmp.name)
        init_repo(self.repo, branch="master")
        make_commit(self.repo, "README.md", "initial commit")

        base_tmp = tempfile.TemporaryDirectory()
        self.addCleanup(base_tmp.cleanup)
        self.base_repo = Path(base_tmp.name)
        git(["clone", str(self.repo), str(self.base_repo)], self.repo)
        git(["config", "user.email", "test@example.com"], self.base_repo)
        git(["config", "user.name", "Test"], self.base_repo)
        _seed_real_split_tooling(self.base_repo)
        git(["add", "."], self.base_repo)
        git(["commit", "-m", "seed"], self.base_repo)
        git(["branch", "-m", "base"], self.base_repo)

        git(["remote", "add", "base", str(self.base_repo)], self.repo)

    def test_empty_argv_triggers_auto_detection(self):
        git(["checkout", "-b", "feature"], self.repo)

        stderr = io.StringIO()

        with contextlib.redirect_stderr(stderr), \
             mock.patch.object(self.module, "find_repo_root", return_value=self.repo), \
             self.assertRaises(SystemExit) as exit_ctx:
            self.module.main([])

        self.assertEqual(exit_ctx.exception.code, 0)
        progress = stderr.getvalue()
        self.assertIn("get-base.py: auto mode: current branch feature", progress)
        self.assertIn(
            "get-base.py: auto mode: 'ai/history/master' missing -- running update-history-master first",
            progress,
        )
        self.assertIn("get-base.py: auto mode: selected bootstrap-branch feature", progress)
        self.assertIsNotNone(git(["rev-parse", "ai/history/master"], self.repo))

    def test_nonempty_argv_bypasses_auto_detection(self):
        git(["checkout", "-b", "feature"], self.repo)

        stderr = io.StringIO()

        with contextlib.redirect_stderr(stderr), \
             mock.patch.object(self.module, "find_repo_root", return_value=self.repo), \
             self.assertRaises(SystemExit) as exit_ctx:
            self.module.main(["update-history-master", "--yes"])

        self.assertEqual(exit_ctx.exception.code, 0)
        progress = stderr.getvalue()
        self.assertNotIn("auto mode", progress)
        self.assertIsNotNone(git(["rev-parse", "ai/history/master"], self.repo))

    def test_detached_head_with_empty_argv_refuses(self):
        head_sha = git(["rev-parse", "HEAD"], self.repo)
        git(["checkout", "--detach", head_sha], self.repo)

        with mock.patch.object(self.module.os, "execvp") as execvp, \
             mock.patch.object(self.module, "find_repo_root", return_value=self.repo):
            code = self.module.main([])

        self.assertEqual(code, 1)
        execvp.assert_not_called()

    def test_auto_failure_on_attached_branch_does_not_claim_detached_head(self):
        git(["checkout", "-b", "feature"], self.repo)
        stderr = io.StringIO()

        with contextlib.redirect_stderr(stderr), \
             mock.patch.object(self.module, "run_split", return_value=1), \
             mock.patch.object(self.module, "find_repo_root", return_value=self.repo):
            code = self.module.main([])

        self.assertEqual(code, 1)
        self.assertIn("auto mode could not complete", stderr.getvalue())
        self.assertNotIn("detached HEAD?", stderr.getvalue())


if __name__ == "__main__":
    unittest.main()
