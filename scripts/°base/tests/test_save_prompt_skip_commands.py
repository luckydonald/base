"""Tests for save-prompt/hook.py's skipped prompts: bare commands and reminders are never logged to ai/query.md."""
from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_ai_hooks_base_routing import init_repo, run_hook  # noqa: E402

ROOT = Path(__file__).resolve().parents[3]
PROMPT_HOOK = ROOT / "scripts" / "°base" / "ai" / "hooks" / "save-prompt" / "hook.py"


class SavePromptSkipCommandsTests(unittest.TestCase):
    def logged_query(self, prompt: str) -> str:
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp) / "consumer"
            init_repo(repo, "https://github.com/example/consumer.git")
            run_hook(repo, PROMPT_HOOK, {"prompt": prompt}, "claude")
            query = repo / "ai" / "query.md"
            return query.read_text(encoding="utf-8") if query.exists() else ""

    def test_fix_it_and_rename_are_skipped(self):
        for prompt in ("fix it", "/rename"):
            with self.subTest(prompt=prompt):
                self.assertNotIn(prompt, self.logged_query(prompt))

    def test_commit_is_skipped(self):
        self.assertNotIn("commit", self.logged_query("commit"))


if __name__ == "__main__":
    unittest.main()
