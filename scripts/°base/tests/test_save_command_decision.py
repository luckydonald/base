"""Tests for transcript/event-log recording of command-approval decisions."""
from __future__ import annotations

import importlib
import json
import tempfile
import unittest
import uuid
from pathlib import Path

_routing = importlib.import_module("scripts.°base.tests.test_ai_hooks_base_routing")
COMMAND_DECISION_HOOK = _routing.COMMAND_DECISION_HOOK
init_repo = _routing.init_repo
run_hook = _routing.run_hook


def write_claude_transcript(path: Path, tool_use_id: str, *, denied: bool, text: str | None = None) -> str:
    result = "completed"
    if denied:
        result = "The user doesn't want to proceed with this tool use."
        if text:
            result += f" To tell you how to proceed, the user said:\n{text}"
        else:
            result += " STOP what you are doing and wait for the user to tell you how to proceed."
        # end if
    # end if
    blocks = [{"type": "tool_result", "tool_use_id": tool_use_id, "content": result, "is_error": denied}]
    if not denied and text:
        blocks.append({"type": "text", "text": text})
    # end if
    records = [
        {"type": "assistant", "message": {"role": "assistant", "content": [
            {"type": "tool_use", "id": tool_use_id, "name": "Bash", "input": {"command": "echo hi"}},
        ]}},
        {"type": "user", "message": {"role": "user", "content": blocks}},
    ]
    path.write_text("\n".join(json.dumps(record) for record in records) + "\n", encoding="utf-8")
    return str(path)
# end def


class ClaudeCommandDecisionTests(unittest.TestCase):
    def test_denial_reason_is_recovered_from_transcript(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp) / "consumer"
            init_repo(repo, "https://github.com/example/consumer.git")
            tool_use_id = f"command-denial-{uuid.uuid4().hex}"
            transcript = write_claude_transcript(Path(tmp) / "claude.jsonl", tool_use_id, denied=True, text="do not run it")

            run_hook(repo, COMMAND_DECISION_HOOK, {"transcript_path": transcript}, "claude")

            content = (repo / "ai" / "query.md").read_text(encoding="utf-8")
            self.assertIn("Command denied: `Bash`", content)
            self.assertIn("do not run it", content)

    def test_completed_tool_instructions_are_recovered_once(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp) / "consumer"
            init_repo(repo, "https://github.com/example/consumer.git")
            tool_use_id = f"command-note-{uuid.uuid4().hex}"
            transcript = write_claude_transcript(Path(tmp) / "claude.jsonl", tool_use_id, denied=False, text="also explain it")
            payload = {"tool_use_id": tool_use_id, "transcript_path": transcript}

            run_hook(repo, COMMAND_DECISION_HOOK, payload, "claude")
            run_hook(repo, COMMAND_DECISION_HOOK, payload, "claude")

            content = (repo / "ai" / "query.md").read_text(encoding="utf-8")
            self.assertEqual(content.count("Instructions for `Bash`:"), 1)
            self.assertIn("also explain it", content)


class CopilotCommandDecisionTests(unittest.TestCase):
    def test_event_log_denial_records_command_and_feedback(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp) / "consumer"
            home = Path(tmp) / "home"
            init_repo(repo, "https://github.com/example/consumer.git")
            session_id = f"copilot-{uuid.uuid4().hex}"
            event_path = home / ".copilot" / "session-state" / session_id / "events.jsonl"
            event_path.parent.mkdir(parents=True)
            event_path.write_text("\n".join(json.dumps(event) for event in [
                {"type": "permission.requested", "data": {"permissionRequest": {
                    "toolCallId": session_id, "fullCommandText": "python3 -c 'print(1)'",
                }}},
                {"type": "permission.completed", "data": {"toolCallId": session_id, "result": {
                    "kind": "denied-interactively-by-user", "feedback": "use a safer command",
                }}},
            ]) + "\n", encoding="utf-8")

            run_hook(repo, COMMAND_DECISION_HOOK, {"sessionId": session_id}, "copilot", extra_env={"HOME": str(home)})

            content = (repo / "ai" / "query.md").read_text(encoding="utf-8")
            self.assertIn("Command denied: `python3 -c 'print(1)'`", content)
            self.assertIn("use a safer command", content)


if __name__ == "__main__":
    unittest.main()
