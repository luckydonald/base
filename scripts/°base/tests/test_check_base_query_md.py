from __future__ import annotations

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
HOOK = ROOT / "scripts" / "°base" / "git" / "hooks" / "push" / "check_base_query_md.py"


def run_git(repo: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args],
        cwd=repo,
        capture_output=True,
        text=True,
        check=True,
    )


def init_repo(repo: Path, origin: str) -> None:
    repo.mkdir(parents=True, exist_ok=True)
    run_git(repo, "init")
    run_git(repo, "config", "user.email", "tester@example.com")
    run_git(repo, "config", "user.name", "Test User")
    run_git(repo, "remote", "add", "origin", origin)


def run_hook(repo: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(HOOK)],
        cwd=repo,
        capture_output=True,
        text=True,
    )


class CheckBaseQueryMdTests(unittest.TestCase):
    def test_blocks_when_repo_dir_named_base_and_origin_is_luckydonald_base(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp) / "base"
            init_repo(repo, "git@github.com:luckydonald/base.git")
            result = run_hook(repo)
            self.assertEqual(result.returncode, 1)
            self.assertIn("ai/query.md", result.stderr)
            self.assertIn("ai/°base/query.md", result.stderr)

    def test_allows_when_origin_is_not_luckydonald_base(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp) / "base"
            init_repo(repo, "git@github.com:luckydonald/sync_todo.git")
            result = run_hook(repo)
            self.assertEqual(result.returncode, 0)
            self.assertEqual(result.stderr, "")

    def test_allows_when_directory_not_named_base_and_not_a_worktree_of_it(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp) / "some-other-dir"
            init_repo(repo, "git@github.com:luckydonald/base.git")
            result = run_hook(repo)
            self.assertEqual(result.returncode, 0)


if __name__ == "__main__":
    unittest.main()
