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
import uuid
from pathlib import Path

_routing = importlib.import_module("scripts.°base.tests.test_ai_hooks_base_routing")
PLAN_HOOK = _routing.PLAN_HOOK
PROMPT_HOOK = _routing.PROMPT_HOOK
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


def _write_rejection_transcript(tmp_dir: Path, tool_use_id: str, reason: str | None) -> str:
    """A minimal transcript with one denied ExitPlanMode tool_use/tool_result
    pair, mirroring Claude Code's actual generic rejection wrapper."""
    if reason:
        content = (
            "The user doesn't want to proceed with this tool use. The tool use was rejected "
            "(eg. if it was a file edit, the new_string was NOT written to the file). "
            f"To tell you how to proceed, the user said:\n{reason}"
        )
    else:
        content = (
            "The user doesn't want to proceed with this tool use. The tool use was rejected "
            "(eg. if it was a file edit, the new_string was NOT written to the file). "
            "STOP what you are doing and wait for the user to tell you how to proceed."
        )
    lines = [
        {"type": "assistant", "message": {"role": "assistant", "content": [
            {"type": "tool_use", "id": tool_use_id, "name": "ExitPlanMode", "input": {"plan": "# Plan\n"}},
        ]}},
        {"type": "user", "message": {"role": "user", "content": [
            {"type": "tool_result", "tool_use_id": tool_use_id, "content": content, "is_error": True},
        ]}},
    ]
    path = tmp_dir / f"transcript-{tool_use_id}.jsonl"
    path.write_text("\n".join(json.dumps(line) for line in lines) + "\n", encoding="utf-8")
    return str(path)


def _user_prompt_submit_payload(*, session_id: str, transcript_path: str, prompt: str = "commit") -> dict:
    # "commit" is in save-prompt/hook.py's SKIP_PROMPTS, so this exercises the
    # rejection scan without also logging an unrelated prompt entry.
    return {
        "hook_event_name": "UserPromptSubmit",
        "session_id": session_id,
        "prompt": prompt,
        "transcript_path": transcript_path,
    }


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


class PlanDenialRecordingTests(unittest.TestCase):
    """save-prompt/hook.py's UserPromptSubmit handler scans the transcript
    for denied ExitPlanMode calls via `_lib.find_tool_rejections`, since no
    hook fires directly on denial -- see Phase 4 in plan 067."""

    def test_deny_with_reason_records_reason(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp) / "consumer"
            init_repo(repo, "https://github.com/example/consumer.git")
            # `_REJECTIONS_STATE_FILE` lives at a fixed path outside `tmp`, so
            # tool_use_ids must be unique across test *runs* (not just within
            # one), or a rerun sees them as already-recorded and no-ops.
            tool_use_id = f"toolu_deny_reason_{uuid.uuid4().hex}"
            transcript = _write_rejection_transcript(Path(tmp), tool_use_id, "change the approach")

            run_hook(
                repo, PROMPT_HOOK,
                _user_prompt_submit_payload(session_id="d1", transcript_path=transcript),
                "claude",
            )

            content = _query_md(repo).read_text(encoding="utf-8")
            self.assertIn("Plan denied:", content)
            self.assertIn("change the approach", content)

    def test_deny_without_reason_records_plain_denial(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp) / "consumer"
            init_repo(repo, "https://github.com/example/consumer.git")
            tool_use_id = f"toolu_deny_plain_{uuid.uuid4().hex}"
            transcript = _write_rejection_transcript(Path(tmp), tool_use_id, None)

            run_hook(
                repo, PROMPT_HOOK,
                _user_prompt_submit_payload(session_id="d2", transcript_path=transcript),
                "claude",
            )

            content = _query_md(repo).read_text(encoding="utf-8")
            self.assertIn("Plan denied.", content)
            self.assertNotIn("Plan denied:", content)

    def test_denial_is_not_recorded_twice(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp) / "consumer"
            init_repo(repo, "https://github.com/example/consumer.git")
            tool_use_id = f"toolu_deny_once_{uuid.uuid4().hex}"
            transcript = _write_rejection_transcript(Path(tmp), tool_use_id, "no thanks")

            payload = _user_prompt_submit_payload(session_id="d3", transcript_path=transcript)
            run_hook(repo, PROMPT_HOOK, payload, "claude")
            run_hook(repo, PROMPT_HOOK, payload, "claude")

            content = _query_md(repo).read_text(encoding="utf-8")
            self.assertEqual(content.count("Plan denied:"), 1)

    def test_accepted_call_is_not_recorded_as_denied(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp) / "consumer"
            init_repo(repo, "https://github.com/example/consumer.git")
            tool_use_id = f"toolu_deny_accept_control_{uuid.uuid4().hex}"
            transcript = _write_transcript(Path(tmp), tool_use_id, note=None)

            run_hook(
                repo, PROMPT_HOOK,
                _user_prompt_submit_payload(session_id="d4", transcript_path=transcript),
                "claude",
            )

            self.assertFalse(_query_md(repo).exists())


class CopilotPlanDecisionRecordingTests(unittest.TestCase):
    def _write_events(self, home: Path, session_id: str, events: list[dict]) -> None:
        path = home / ".copilot" / "session-state" / session_id / "events.jsonl"
        path.parent.mkdir(parents=True)
        path.write_text("\n".join(json.dumps(event) for event in events) + "\n", encoding="utf-8")

    def test_stop_records_manual_and_autopilot_acceptances(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp) / "consumer"
            home = Path(tmp) / "home"
            init_repo(repo, "https://github.com/example/consumer.git")
            session_id = f"copilot-accept-{uuid.uuid4().hex}"
            self._write_events(home, session_id, [
                {"type": "session.mode_changed", "data": {"previousMode": "plan", "newMode": "interactive"}},
                {"type": "session.mode_changed", "data": {"previousMode": "plan", "newMode": "autopilot"}},
            ])

            run_hook(
                repo, PLAN_HOOK,
                {"hook_event_name": "Stop", "session_id": session_id},
                "copilot", extra_env={"HOME": str(home)},
            )

            content = _query_md(repo).read_text(encoding="utf-8")
            self.assertIn("Plan accepted.", content)
            self.assertIn("Plan accepted, autopilot.", content)

    def test_exit_only_is_not_mistaken_for_an_acceptance_on_later_stop(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp) / "consumer"
            home = Path(tmp) / "home"
            init_repo(repo, "https://github.com/example/consumer.git")
            session_id = f"copilot-exit-{uuid.uuid4().hex}"
            self._write_events(home, session_id, [
                {"type": "session.mode_changed", "data": {"previousMode": "plan", "newMode": "interactive"}},
            ])
            exit_payload = {
                "hook_event_name": "PostToolUse",
                "session_id": session_id,
                "tool_name": "exit_plan_mode",
                "tool_use_id": f"exit-{uuid.uuid4().hex}",
                "tool_response": {"sessionLog": "✅ Plan approved, exited plan mode (exit_only)"},
            }

            run_hook(repo, PLAN_HOOK, exit_payload, "copilot", extra_env={"HOME": str(home)})
            run_hook(
                repo, PLAN_HOOK,
                {"hook_event_name": "Stop", "session_id": session_id},
                "copilot", extra_env={"HOME": str(home)},
            )

            content = _query_md(repo).read_text(encoding="utf-8")
            self.assertIn("Plan exited.", content)
            self.assertNotIn("Plan accepted.", content)


if __name__ == "__main__":
    unittest.main()
