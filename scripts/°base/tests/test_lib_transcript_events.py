"""Tests for the transcript-scanning helpers added to
scripts/°base/ai/hooks/_lib.py: load_transcript_tool_events,
find_interjected_text, is_rejection, rejection_reason, find_tool_rejections.

These recover two things Claude Code never exposes to any hook: a message the
user types while a tool call is in flight (the "note" on an accepted call),
and the reason (if any) behind a denied tool call. Both only ever appear in
the raw session transcript JSONL, confirmed empirically across ExitPlanMode,
Edit, Bash, and Read denials/accepts in this repo's own dev session -- see
ai/°base/plans/067_plan-record-plan-and-command-approval-decision-options-and-v.md.
"""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

_HOOKS_DIR = Path(__file__).resolve().parents[1] / "ai" / "hooks"
if str(_HOOKS_DIR) not in sys.path:
    sys.path.insert(0, str(_HOOKS_DIR))
import _lib  # noqa: E402


def _write_transcript(lines: list[dict]) -> str:
    tmp = tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False, encoding="utf-8")
    for line in lines:
        tmp.write(json.dumps(line) + "\n")
    tmp.close()
    return tmp.name


def _assistant_tool_use(tool_use_id: str, name: str, input_: dict) -> dict:
    return {
        "type": "assistant",
        "message": {"role": "assistant", "content": [
            {"type": "tool_use", "id": tool_use_id, "name": name, "input": input_},
        ]},
    }


def _user_tool_result(tool_use_id: str, content, *, is_error: bool = False, note: str | None = None) -> dict:
    blocks = [{"type": "tool_result", "tool_use_id": tool_use_id, "content": content, "is_error": is_error}]
    if note is not None:
        blocks.append({"type": "text", "text": note})
    return {"type": "user", "message": {"role": "user", "content": blocks}}


class LoadTranscriptToolEventsTests(unittest.TestCase):
    def test_plain_accepted_call_has_no_note(self):
        path = _write_transcript([
            _assistant_tool_use("t1", "ExitPlanMode", {"plan": "..."}),
            _user_tool_result("t1", "ok"),
        ])
        events = _lib.load_transcript_tool_events(path)
        self.assertEqual(events["t1"]["tool_name"], "ExitPlanMode")
        self.assertEqual(events["t1"]["is_error"], False)
        self.assertIsNone(events["t1"]["note"])

    def test_accepted_call_with_interjected_note(self):
        path = _write_transcript([
            _assistant_tool_use("t2", "Bash", {"command": "echo hi"}),
            _user_tool_result("t2", "hi", note="littlepip is best pony"),
        ])
        events = _lib.load_transcript_tool_events(path)
        self.assertEqual(events["t2"]["note"], "littlepip is best pony")

    def test_note_lookup_helper_returns_none_for_unknown_id(self):
        path = _write_transcript([])
        self.assertIsNone(_lib.find_interjected_text(path, "missing"))

    def test_note_lookup_helper_returns_none_for_empty_tool_use_id(self):
        self.assertIsNone(_lib.find_interjected_text("/nonexistent", ""))

    def test_malformed_transcript_lines_are_skipped(self):
        tmp = tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False, encoding="utf-8")
        tmp.write("not json\n")
        tmp.write(json.dumps(_assistant_tool_use("t3", "Read", {"file_path": "/x"})) + "\n")
        tmp.write(json.dumps(_user_tool_result("t3", "content")) + "\n")
        tmp.close()
        events = _lib.load_transcript_tool_events(tmp.name)
        self.assertIn("t3", events)

    def test_missing_transcript_file_returns_empty(self):
        self.assertEqual(_lib.load_transcript_tool_events("/does/not/exist.jsonl"), {})


class RejectionParsingTests(unittest.TestCase):
    def test_is_rejection_true_for_standard_wrapper(self):
        content = "The user doesn't want to proceed with this tool use. The tool use was rejected."
        self.assertTrue(_lib.is_rejection(content))

    def test_is_rejection_false_for_ordinary_content(self):
        self.assertFalse(_lib.is_rejection("root:x:0:0:root:/root:/bin/bash"))

    def test_rejection_reason_extracts_typed_text(self):
        content = (
            "The user doesn't want to proceed with this tool use. The tool use was rejected "
            "(eg. if it was a file edit, the new_string was NOT written to the file). "
            "To tell you how to proceed, the user said:\nthis is a no"
        )
        self.assertEqual(_lib.rejection_reason(content), "this is a no")

    def test_rejection_reason_none_when_no_reason_given(self):
        content = (
            "The user doesn't want to proceed with this tool use. The tool use was rejected "
            "(eg. if it was a file edit, the new_string was NOT written to the file). "
            "STOP what you are doing and wait for the user to tell you how to proceed."
        )
        self.assertIsNone(_lib.rejection_reason(content))

    def test_rejection_reason_preserves_multiline_text(self):
        content = "The user doesn't want to proceed with this tool use. the user said:\nline one\nline two"
        self.assertEqual(_lib.rejection_reason(content), "line one\nline two")


class FindToolRejectionsTests(unittest.TestCase):
    def test_finds_denied_exit_plan_mode_with_reason(self):
        path = _write_transcript([
            _assistant_tool_use("p1", "ExitPlanMode", {}),
            _user_tool_result(
                "p1",
                "The user doesn't want to proceed with this tool use. the user said:\nchange the approach",
                is_error=True,
            ),
        ])
        found = _lib.find_tool_rejections(path, {"ExitPlanMode"}, set())
        self.assertEqual(len(found), 1)
        self.assertEqual(found[0]["tool_use_id"], "p1")
        self.assertEqual(found[0]["reason"], "change the approach")

    def test_finds_denied_exit_plan_mode_without_reason(self):
        path = _write_transcript([
            _assistant_tool_use("p2", "ExitPlanMode", {}),
            _user_tool_result(
                "p2",
                "The user doesn't want to proceed with this tool use. STOP what you are doing "
                "and wait for the user to tell you how to proceed.",
                is_error=True,
            ),
        ])
        found = _lib.find_tool_rejections(path, {"ExitPlanMode"}, set())
        self.assertEqual(len(found), 1)
        self.assertIsNone(found[0]["reason"])

    def test_accepted_call_is_not_a_rejection(self):
        path = _write_transcript([
            _assistant_tool_use("p3", "ExitPlanMode", {}),
            _user_tool_result("p3", "plan approved"),
        ])
        self.assertEqual(_lib.find_tool_rejections(path, {"ExitPlanMode"}, set()), [])

    def test_wrong_tool_name_is_excluded(self):
        path = _write_transcript([
            _assistant_tool_use("p4", "Bash", {"command": "rm -rf /"}),
            _user_tool_result(
                "p4",
                "The user doesn't want to proceed with this tool use. the user said:\nno",
                is_error=True,
            ),
        ])
        self.assertEqual(_lib.find_tool_rejections(path, {"ExitPlanMode"}, set()), [])

    def test_already_recorded_ids_are_skipped(self):
        path = _write_transcript([
            _assistant_tool_use("p5", "ExitPlanMode", {}),
            _user_tool_result(
                "p5",
                "The user doesn't want to proceed with this tool use. the user said:\nno thanks",
                is_error=True,
            ),
        ])
        self.assertEqual(_lib.find_tool_rejections(path, {"ExitPlanMode"}, {"p5"}), [])

    def test_multiple_tool_names_and_multiple_rejections(self):
        path = _write_transcript([
            _assistant_tool_use("p6", "Bash", {"command": "echo bogus"}),
            _user_tool_result(
                "p6", "The user doesn't want to proceed with this tool use. the user said:\nbogus", is_error=True,
            ),
            _assistant_tool_use("p7", "ExitPlanMode", {}),
            _user_tool_result(
                "p7", "The user doesn't want to proceed with this tool use. the user said:\nplan no", is_error=True,
            ),
        ])
        found = _lib.find_tool_rejections(path, {"Bash", "ExitPlanMode"}, set())
        self.assertEqual({f["tool_use_id"] for f in found}, {"p6", "p7"})


if __name__ == "__main__":
    unittest.main()
