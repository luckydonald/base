"""Tests for save-prompt/hook.py's IDE context: the selected file or lines become a link line in ai/query.md."""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_ai_hooks_base_routing import init_repo, run_hook  # noqa: E402

ROOT = Path(__file__).resolve().parents[3]
PROMPT_HOOK = ROOT / "scripts" / "°base" / "ai" / "hooks" / "save-prompt" / "hook.py"
PROMPT = "rework the parser"
PROMPT_ID = "92a20da0-d9b7-4522-8770-47bae1a752a1"


def selection_attachment(first: int, last: int, filename: str = "/x/todo.md") -> dict:
    return {
        "type": "selected_lines_in_ide",
        "ideName": "PyCharm",
        "lineStart": first,
        "lineEnd": last,
        "filename": filename,
        "content": "some text\n",
        "displayPath": "todo.md",
    }
# end def


def opened_file_attachment(filename: str = "/x/todo.md") -> dict:
    return {"type": "opened_file_in_ide", "filename": filename}
# end def


class SavePromptIdeContextTests(unittest.TestCase):
    def logged_query(self, ai_tool: str, prompt: str, attachments: list[dict] | None = None, prompt_id: str = PROMPT_ID) -> str:
        """Run the hook in a throwaway repo, with a Claude transcript holding `attachments` behind the prompt's user record."""
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp) / "consumer"
            init_repo(repo, "https://github.com/example/consumer.git")
            records: list[dict] = [
                {"type": "file-history-snapshot"},
                {"type": "user", "promptId": PROMPT_ID, "message": {"role": "user", "content": prompt}},
            ]
            records += [{"type": "attachment", "attachment": {"type": "total_tokens_reminder"}}]
            for attachment in attachments or []:
                filename = attachment["filename"].replace("{repo}", str(repo.resolve()))
                records.append({"type": "attachment", "attachment": {**attachment, "filename": filename}})
            # end for
            records += [{"type": "assistant"}]
            transcript = Path(tmp) / "transcript.jsonl"
            transcript.write_text("\n".join(json.dumps(record) for record in records), encoding="utf-8")
            payload = {
                "prompt": prompt,
                "cwd": str(repo.resolve()),
                "transcript_path": str(transcript),
                "prompt_id": prompt_id,
            }
            run_hook(repo, PROMPT_HOOK, payload, ai_tool)
            query = repo / "ai" / "query.md"
            return query.read_text(encoding="utf-8") if query.exists() else ""
        # end with
    # end def

    def test_claude_multiple_lines_selected(self):
        logged = self.logged_query("claude", PROMPT, [selection_attachment(190, 200)])
        self.assertIn("❯ rework the parser\n> • [⧉ File `todo.md`: 11 lines selected](", logged)
        self.assertIn("todo.md#L190-200)", logged)
        self.assertNotIn("some text", logged)
        self.assertIn("](/x/todo.md#L190-200)", logged)
    # end def

    def test_claude_file_inside_the_repo_links_relative(self):
        logged = self.logged_query("claude", PROMPT, [opened_file_attachment("{repo}/src/a b.py")])
        self.assertIn("](../src/a%20b.py)", logged)
    # end def

    def test_claude_single_line_selected(self):
        logged = self.logged_query("claude", PROMPT, [selection_attachment(7, 7)])
        self.assertIn("1 line selected](", logged)
        self.assertIn("todo.md#L7)", logged)
    # end def

    def test_claude_select_all(self):
        logged = self.logged_query("claude", PROMPT, [selection_attachment(1, 284)])
        self.assertIn("284 lines selected](", logged)
        self.assertIn("todo.md#L1-284)", logged)
    # end def

    def test_claude_opened_file_only(self):
        logged = self.logged_query("claude", PROMPT, [opened_file_attachment()])
        self.assertIn("❯ rework the parser\n> • [⧉ File `todo.md`](", logged)
        self.assertNotIn("#L", logged)
    # end def

    def test_claude_selection_wins_over_opened_file(self):
        logged = self.logged_query("claude", PROMPT, [opened_file_attachment("/x/other.md"), selection_attachment(3, 4)])
        self.assertIn("`todo.md`: 2 lines selected](", logged)
        self.assertNotIn("other.md", logged)
    # end def

    def test_claude_attachment_of_another_prompt_is_ignored(self):
        logged = self.logged_query("claude", PROMPT, [selection_attachment(1, 2)], prompt_id="not-this-prompt")
        self.assertNotIn("⧉", logged)
    # end def

    def test_claude_without_attachments_is_unchanged(self):
        logged = self.logged_query("claude", PROMPT)
        self.assertIn("❯ rework the parser\n", logged)
        self.assertNotIn("⧉", logged)
    # end def

    def test_claude_without_transcript_is_unchanged(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp) / "consumer"
            init_repo(repo, "https://github.com/example/consumer.git")
            run_hook(repo, PROMPT_HOOK, {"prompt": PROMPT, "cwd": str(repo.resolve())}, "claude")
            logged = (repo / "ai" / "query.md").read_text(encoding="utf-8")
        # end with
        self.assertIn("❯ rework the parser\n", logged)
        self.assertNotIn("⧉", logged)
    # end def

    def test_codex_active_file(self):
        logged = self.logged_query(
            "codex",
            "# Context from my IDE setup:\n\n## Active file: scripts/a.py\n\n## Open tabs:\n- a.py: scripts/a.py\n\n## My request for Codex:\nrework the parser",
        )
        self.assertIn("› rework the parser\n> • [⧉ File `a.py`](", logged)
        self.assertNotIn("Open tabs", logged)
    # end def

    def test_codex_malformed_block_is_logged_unchanged(self):
        prompt = "# Context from my IDE setup:\n\nrework the parser"
        logged = self.logged_query("codex", prompt)
        self.assertIn("rework the parser", logged)
        self.assertNotIn("⧉", logged)
    # end def
# end class


if __name__ == "__main__":
    unittest.main()
# end if
