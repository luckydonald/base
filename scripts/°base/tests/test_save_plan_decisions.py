"""Tests for save-plan/hook.py's Claude ExitPlanMode decision recording
(accept / accept+auto-mode / accept+note), added alongside the existing plan
text snapshot behavior. See
ai/°base/plans/067_plan-record-plan-and-command-approval-decision-options-and-v.md's
Phase 4 for how each signal was confirmed against real payloads.
"""
from __future__ import annotations

import importlib
import json
import tempfile
import unittest
from pathlib import Path

_routing = importlib.import_module("scripts.°base.tests.test_ai_hooks_base_routing")
PLAN_HOOK = _routing.PLAN_HOOK
init_repo = _routing.init_repo
last_subject = _routing.last_subject
run_hook = _routing.run_hook


def _query_md(repo: Path) -> Path:
    return repo / "ai" / "query.md"


def _write_transcript(tmp_dir: Path, tool_use_id: str, note: str | None) -> str:
    """A minimal transcript with one ExitPlanMode tool_use/tool_result pair,
    optionally followed by a sibling `text` block (the interjected note)."""
    content = [{"type": "tool_result", "tool_use_id": tool_use_id, "content": "ok", "is_error": False}]
    if note is not None:
        content.append({"type": "text", "text": note})
    lines = [
        {"type": "assistant", "message": {"role": "assistant", "content": [
            {"type": "tool_use", "id": tool_use_id, "name": "ExitPlanMode", "input": {"plan": "# Plan\n"}},
        ]}},
        {"type": "user", "message": {"role": "user", "content": content}},
    ]
    path = tmp_dir / "transcript.jsonl"
    path.write_text("\n".join(json.dumps(line) for line in lines) + "\n", encoding="utf-8")
    return str(path)


def _exit_plan_mode_payload(*, session_id: str, tool_use_id: str, transcript_path: str, permission_mode: str = "default") -> dict:
    return {
        "hook_event_name": "PostToolUse",
        "session_id": session_id,
        "tool_name": "ExitPlanMode",
        "tool_use_id": tool_use_id,
        "tool_input": {},
        "tool_response": {"plan": "# Plan\n\nDo the thing.", "isAgent": False, "filePath": "/tmp/plan.md"},
        "permission_mode": permission_mode,
        "transcript_path": transcript_path,
    }


class PlanDecisionRecordingTests(unittest.TestCase):
    def test_plain_accept_records_plain_decision(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp) / "consumer"
            init_repo(repo, "https://github.com/example/consumer.git")
            transcript = _write_transcript(Path(tmp), "toolu_plain", note=None)

            run_hook(
                repo, PLAN_HOOK,
                _exit_plan_mode_payload(session_id="s1", tool_use_id="toolu_plain", transcript_path=transcript),
                "claude",
            )

            content = _query_md(repo).read_text(encoding="utf-8")
            self.assertIn("Plan accepted.", content)
            self.assertNotIn("auto mode", content)

    def test_auto_mode_accept_records_auto_mode_decision(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp) / "consumer"
            init_repo(repo, "https://github.com/example/consumer.git")
            transcript = _write_transcript(Path(tmp), "toolu_auto", note=None)

            run_hook(
                repo, PLAN_HOOK,
                _exit_plan_mode_payload(
                    session_id="s2", tool_use_id="toolu_auto", transcript_path=transcript,
                    permission_mode="auto",
                ),
                "claude",
            )

            content = _query_md(repo).read_text(encoding="utf-8")
            self.assertIn("Plan accepted, auto mode.", content)

    def test_accept_with_note_records_note_text(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp) / "consumer"
            init_repo(repo, "https://github.com/example/consumer.git")
            transcript = _write_transcript(Path(tmp), "toolu_note", note="littlepip is best pony")

            run_hook(
                repo, PLAN_HOOK,
                _exit_plan_mode_payload(
                    session_id="s3", tool_use_id="toolu_note", transcript_path=transcript,
                    permission_mode="auto",
                ),
                "claude",
            )

            content = _query_md(repo).read_text(encoding="utf-8")
            self.assertIn("Plan accepted:", content)
            self.assertIn("littlepip is best pony", content)
            # A note takes precedence over the auto-mode label per the design.
            self.assertNotIn("Plan accepted, auto mode.", content)

    def test_plan_snapshot_file_is_still_written_alongside_the_decision(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp) / "consumer"
            init_repo(repo, "https://github.com/example/consumer.git")
            transcript = _write_transcript(Path(tmp), "toolu_snap", note=None)

            run_hook(
                repo, PLAN_HOOK,
                _exit_plan_mode_payload(session_id="s4", tool_use_id="toolu_snap", transcript_path=transcript),
                "claude",
            )

            plans = list((repo / "ai" / "plans").glob("*.md"))
            self.assertEqual(len(plans), 1)
            self.assertIn("Do the thing.", plans[0].read_text(encoding="utf-8"))
            self.assertIn("Plan accepted.", _query_md(repo).read_text(encoding="utf-8"))

    def test_codex_accept_does_not_record_a_decision(self):
        """Decision recording is Claude-only for now -- Phase 3 found no
        text-carrying decision path for Codex/Copilot to record yet."""
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp) / "consumer"
            init_repo(repo, "https://github.com/example/consumer.git")

            run_hook(
                repo, PLAN_HOOK,
                {
                    "hook_event_name": "PostToolUse",
                    "session_id": "s5",
                    "tool_name": "ExitPlanMode",
                    "tool_use_id": "toolu_codex",
                    "tool_input": {"plan": "# Plan\n\nDo the thing."},
                    "permission_mode": "default",
                },
                "codex",
            )

            self.assertFalse(_query_md(repo).exists())


if __name__ == "__main__":
    unittest.main()
