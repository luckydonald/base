"""Tests for the pending-decision marker mechanism added to save-decision/hook.py:
capturing an AskUserQuestion call at PreToolUse time so a canceled ("chat about
this") question is still recorded even though Claude Code fires no PostToolUse,
PostToolUseFailure, or PermissionDenied hook for a manual denial. See
scripts/°base/ai/hooks/_lib.py's write_pending_decision/sweep_pending_decisions.
"""
from __future__ import annotations

import importlib
import os
import tempfile
import unittest
from pathlib import Path

_routing = importlib.import_module("scripts.°base.tests.test_ai_hooks_base_routing")
DECISION_HOOK = _routing.DECISION_HOOK
init_repo = _routing.init_repo
last_subject = _routing.last_subject
run_hook = _routing.run_hook

QUESTIONS = [
    {
        "question": "Pick one?",
        "header": "Test",
        "multiSelect": False,
        "options": [
            {"label": "A", "description": "first"},
            {"label": "B", "description": "second"},
        ],
    }
]


def _pending_dir(repo: Path) -> Path:
    return repo / "ai" / "output" / ".pending-decisions"


def _query_md(repo: Path) -> Path:
    return repo / "ai" / "prompt.md"


class PendingDecisionTests(unittest.TestCase):
    def test_pre_tool_use_writes_marker_without_touching_query_md(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp) / "consumer"
            init_repo(repo, "https://github.com/example/consumer.git")

            run_hook(
                repo,
                DECISION_HOOK,
                {
                    "hook_event_name": "PreToolUse",
                    "session_id": "session-a",
                    "tool_name": "AskUserQuestion",
                    "tool_use_id": "toolu_pending_1",
                    "tool_input": {"questions": QUESTIONS},
                },
                "claude",
            )

            markers = list(_pending_dir(repo).glob("*.md"))
            self.assertEqual(len(markers), 1)
            self.assertIn("Pick one?", markers[0].read_text(encoding="utf-8"))
            self.assertIn("canceled", markers[0].read_text(encoding="utf-8"))
            self.assertFalse(_query_md(repo).exists())

    def test_post_tool_use_deletes_marker_and_renders_answered(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp) / "consumer"
            init_repo(repo, "https://github.com/example/consumer.git")

            run_hook(
                repo,
                DECISION_HOOK,
                {
                    "hook_event_name": "PreToolUse",
                    "session_id": "session-a",
                    "tool_name": "AskUserQuestion",
                    "tool_use_id": "toolu_pending_2",
                    "tool_input": {"questions": QUESTIONS},
                },
                "claude",
            )
            self.assertEqual(len(list(_pending_dir(repo).glob("*.md"))), 1)

            run_hook(
                repo,
                DECISION_HOOK,
                {
                    "hook_event_name": "PostToolUse",
                    "session_id": "session-a",
                    "tool_name": "AskUserQuestion",
                    "tool_use_id": "toolu_pending_2",
                    "tool_input": {"questions": QUESTIONS},
                    "tool_response": {"answers": {"Pick one?": "A"}},
                },
                "claude",
            )

            self.assertEqual(list(_pending_dir(repo).glob("*.md")), [])
            content = _query_md(repo).read_text(encoding="utf-8")
            self.assertIn("Question answered", content)
            self.assertNotIn("canceled", content)

    def test_stop_sweeps_leftover_marker_as_canceled(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp) / "consumer"
            init_repo(repo, "https://github.com/example/consumer.git")

            run_hook(
                repo,
                DECISION_HOOK,
                {
                    "hook_event_name": "PreToolUse",
                    "session_id": "session-a",
                    "tool_name": "AskUserQuestion",
                    "tool_use_id": "toolu_pending_3",
                    "tool_input": {"questions": QUESTIONS},
                },
                "claude",
            )

            # No matching PostToolUse ever fires (user picked "chat about this").
            run_hook(
                repo,
                DECISION_HOOK,
                {"hook_event_name": "Stop", "session_id": "session-a"},
                "claude",
            )

            self.assertEqual(list(_pending_dir(repo).glob("*.md")), [])
            content = _query_md(repo).read_text(encoding="utf-8")
            self.assertIn("Question canceled (chat about this)", content)
            self.assertIn("Pick one?", content)
            self.assertEqual(last_subject(repo), "ai: save canceled decision")

    def test_stop_is_a_noop_when_nothing_pending(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp) / "consumer"
            init_repo(repo, "https://github.com/example/consumer.git")

            before = last_subject(repo)
            run_hook(repo, DECISION_HOOK, {"hook_event_name": "Stop"}, "claude")

            self.assertEqual(last_subject(repo), before)
            self.assertFalse(_query_md(repo).exists())


class ConcurrentSessionTests(unittest.TestCase):
    """Two Claude Code instances sharing one non-worktree checkout, each with
    its own in-flight AskUserQuestion, must not step on each other's marker.
    """

    def test_distinct_sessions_get_distinct_markers(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp) / "consumer"
            init_repo(repo, "https://github.com/example/consumer.git")

            for session, tool_use_id in (("session-a", "toolu_a"), ("session-b", "toolu_b")):
                run_hook(
                    repo,
                    DECISION_HOOK,
                    {
                        "hook_event_name": "PreToolUse",
                        "session_id": session,
                        "tool_name": "AskUserQuestion",
                        "tool_use_id": tool_use_id,
                        "tool_input": {"questions": QUESTIONS},
                    },
                    "claude",
                )

            markers = {p.name for p in _pending_dir(repo).glob("*.md")}
            self.assertEqual(markers, {"session-a__toolu_a.md", "session-b__toolu_b.md"})

    def test_own_session_stop_does_not_sweep_other_sessions_fresh_marker(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp) / "consumer"
            init_repo(repo, "https://github.com/example/consumer.git")

            # Session A asks, still unanswered.
            run_hook(
                repo,
                DECISION_HOOK,
                {
                    "hook_event_name": "PreToolUse",
                    "session_id": "session-a",
                    "tool_name": "AskUserQuestion",
                    "tool_use_id": "toolu_a",
                    "tool_input": {"questions": QUESTIONS},
                },
                "claude",
            )
            # Session B (no question of its own) finishes its turn first.
            run_hook(
                repo,
                DECISION_HOOK,
                {"hook_event_name": "Stop", "session_id": "session-b"},
                "claude",
            )

            # B's Stop had nothing of its own to sweep -> prompt.md untouched.
            self.assertFalse(_query_md(repo).exists())
            # A's still-live, still-fresh marker survives untouched.
            markers = {p.name for p in _pending_dir(repo).glob("*.md")}
            self.assertEqual(markers, {"session-a__toolu_a.md"})

            # A later answers for real -> the real answer, no spurious "canceled" entry.
            run_hook(
                repo,
                DECISION_HOOK,
                {
                    "hook_event_name": "PostToolUse",
                    "session_id": "session-a",
                    "tool_name": "AskUserQuestion",
                    "tool_use_id": "toolu_a",
                    "tool_input": {"questions": QUESTIONS},
                    "tool_response": {"answers": {"Pick one?": "A"}},
                },
                "claude",
            )
            content = _query_md(repo).read_text(encoding="utf-8")
            self.assertIn("Question answered", content)
            self.assertNotIn("canceled", content)

    def test_stale_marker_from_a_different_session_is_swept_as_orphan(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp) / "consumer"
            init_repo(repo, "https://github.com/example/consumer.git")

            run_hook(
                repo,
                DECISION_HOOK,
                {
                    "hook_event_name": "PreToolUse",
                    "session_id": "session-dead",
                    "tool_name": "AskUserQuestion",
                    "tool_use_id": "toolu_dead",
                    "tool_input": {"questions": QUESTIONS},
                },
                "claude",
            )
            marker = _pending_dir(repo) / "session-dead__toolu_dead.md"
            self.assertTrue(marker.is_file())
            old = marker.stat().st_atime - 2 * 60 * 60  # 2h old -> past the staleness threshold
            os.utime(marker, (old, old))

            run_hook(
                repo,
                DECISION_HOOK,
                {"hook_event_name": "Stop", "session_id": "session-alive"},
                "claude",
            )

            self.assertEqual(list(_pending_dir(repo).glob("*.md")), [])
            content = _query_md(repo).read_text(encoding="utf-8")
            self.assertIn("stale", content)
            self.assertIn("orphaned session", content)


if __name__ == "__main__":
    unittest.main()
