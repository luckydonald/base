"""Tests for save-prompt/hook.py's IDE context: the selected file or lines become a link line instead of raw tags in ai/query.md."""
from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_ai_hooks_base_routing import init_repo, run_hook  # noqa: E402

ROOT = Path(__file__).resolve().parents[3]
PROMPT_HOOK = ROOT / "scripts" / "°base" / "ai" / "hooks" / "save-prompt" / "hook.py"


class SavePromptIdeContextTests(unittest.TestCase):
    def logged_query(self, ai_tool: str, prompt: str) -> str:
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp) / "consumer"
            init_repo(repo, "https://github.com/example/consumer.git")
            run_hook(repo, PROMPT_HOOK, {"prompt": prompt, "cwd": str(repo.resolve())}, ai_tool)
            query = repo / "ai" / "query.md"
            return query.read_text(encoding="utf-8") if query.exists() else ""
        # end with
    # end def

    def claude_selection(self, first: int, last: int) -> str:
        return (
            f"<ide_selection>The user selected the lines {first} to {last} from /x/todo.md:\nsome text\n\n"
            "This may or may not be related to the current task.</ide_selection>\nrework the parser"
        )
    # end def

    def test_claude_multiple_lines_selected(self):
        logged = self.logged_query("claude", self.claude_selection(190, 200))
        self.assertIn("❯ rework the parser\n> • [⧉ File `todo.md`: 11 lines selected](", logged)
        self.assertIn("todo.md#L190-200)", logged)
        self.assertNotIn("ide_selection", logged)
        self.assertNotIn("some text", logged)
    # end def

    def test_claude_single_line_selected(self):
        logged = self.logged_query("claude", self.claude_selection(7, 7))
        self.assertIn("1 line selected](", logged)
        self.assertIn("todo.md#L7)", logged)
    # end def

    def test_claude_opened_file_only(self):
        logged = self.logged_query(
            "claude",
            "<ide_opened_file>The user opened the file /x/todo.md in the IDE. This may or may not be related to the current task.</ide_opened_file>\nrework the parser",
        )
        self.assertIn("❯ rework the parser\n> • [⧉ File `todo.md`](", logged)
        self.assertNotIn("#L", logged)
    # end def

    def test_codex_active_file(self):
        logged = self.logged_query(
            "codex",
            "# Context from my IDE setup:\n\n## Active file: scripts/a.py\n\n## Open tabs:\n- a.py: scripts/a.py\n\n## My request for Codex:\nrework the parser",
        )
        self.assertIn("› rework the parser\n> • [⧉ File `a.py`](", logged)
        self.assertNotIn("Open tabs", logged)
    # end def

    def test_prompt_without_tags_is_unchanged(self):
        logged = self.logged_query("claude", "rework the parser")
        self.assertIn("❯ rework the parser\n", logged)
        self.assertNotIn("⧉", logged)
    # end def

    def test_malformed_tag_is_logged_unchanged(self):
        prompt = "<ide_selection>garbled</ide_selection> rework the parser"
        logged = self.logged_query("claude", prompt)
        self.assertIn(prompt, logged)
        self.assertNotIn("⧉", logged)
    # end def
# end class


if __name__ == "__main__":
    unittest.main()
# end if
