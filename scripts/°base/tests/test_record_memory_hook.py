from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
HOOK = ROOT / "scripts" / "°base" / "ai" / "hooks" / "record-memory" / "hook.py"


def run_git(repo: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["git", *args], cwd=repo, capture_output=True, text=True, check=True)


class RecordMemoryHookTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        tmp = Path(self._tmp.name).resolve()
        self.repo = tmp / "base"
        self.config = tmp / "claude"
        self.repo.mkdir()
        run_git(self.repo, "init")
        run_git(self.repo, "config", "user.email", "tester@example.com")
        run_git(self.repo, "config", "user.name", "Test User")
        run_git(self.repo, "remote", "add", "origin", "https://luckydonald@github.com/luckydonald/base.git")
        (self.repo / "README.md").write_text("test repo\n", encoding="utf-8")
        run_git(self.repo, "add", "README.md")
        run_git(self.repo, "commit", "-m", "init")
        encoded = re.sub(r"[^a-zA-Z0-9]", "-", str(self.repo))
        self.src_dir = self.config / "projects" / encoded / "memory"
        self.src_dir.mkdir(parents=True)
        self.dst_dir = self.repo / "ai" / "°base" / "memory"

    def run_hook(self, event: str, file_path: Path | None = None) -> None:
        payload: dict = {"hook_event_name": event}
        if file_path is not None:
            payload["tool_name"] = "Write"
            payload["tool_input"] = {"file_path": str(file_path)}
        env = {
            **os.environ,
            "CLAUDE_CONFIG_DIR": str(self.config),
            "CLAUDE_PROJECT_DIR": str(self.repo),
        }
        env.pop("CLAUDE_CODE_PROJECT_DIR_NAME", None)
        subprocess.run(
            [sys.executable, str(HOOK)],
            cwd=self.repo,
            input=json.dumps(payload),
            env=env,
            capture_output=True,
            text=True,
            check=True,
        )

    def commit_count(self) -> int:
        return int(run_git(self.repo, "rev-list", "--count", "HEAD").stdout.strip())

    def dirty(self) -> str:
        return run_git(self.repo, "status", "--porcelain", "--", "ai").stdout.strip()

    def record_new(self, name: str, text: str = "one\n") -> Path:
        src = self.src_dir / name
        src.write_text(text, encoding="utf-8")
        self.run_hook("PostToolUse", src)
        return src

    def test_new_memory_is_committed(self) -> None:
        before = self.commit_count()
        self.record_new("a.md")
        self.assertEqual(self.commit_count(), before + 1)
        self.assertEqual((self.dst_dir / "a.md").read_text(encoding="utf-8"), "one\n")
        self.assertEqual(self.dirty(), "")

    def test_edited_hardlinked_memory_is_committed(self) -> None:
        src = self.record_new("a.md")
        before = self.commit_count()
        src.write_text("two\n", encoding="utf-8")
        self.run_hook("PostToolUse", src)
        self.assertEqual(self.commit_count(), before + 1)
        self.assertEqual(self.dirty(), "")
        self.assertEqual(run_git(self.repo, "show", "HEAD:ai/°base/memory/a.md").stdout, "two\n")

    def test_edited_index_is_committed(self) -> None:
        src = self.record_new("MEMORY.md", "- [a](a.md)\n")
        before = self.commit_count()
        src.write_text("- [a](a.md)\n- [b](b.md)\n", encoding="utf-8")
        self.run_hook("PostToolUse", src)
        self.assertEqual(self.commit_count(), before + 1)
        self.assertEqual(self.dirty(), "")

    def test_clean_memory_creates_no_commit(self) -> None:
        src = self.record_new("a.md")
        before = self.commit_count()
        self.run_hook("PostToolUse", src)
        self.assertEqual(self.commit_count(), before)

    def test_session_start_commits_leftover_dirty_memory(self) -> None:
        src = self.record_new("a.md")
        src.write_text("two\n", encoding="utf-8")
        self.assertNotEqual(self.dirty(), "")
        before = self.commit_count()
        self.run_hook("SessionStart")
        self.assertEqual(self.commit_count(), before + 1)
        self.assertEqual(self.dirty(), "")


if __name__ == "__main__":
    unittest.main()
