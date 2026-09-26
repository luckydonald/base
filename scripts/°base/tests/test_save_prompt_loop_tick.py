"""Tests for save-prompt/hook.py's autonomous-/loop-tick condensation:

The harness resends a fixed instructional block verbatim on every autonomous
`/loop` tick (ScheduleWakeup's `<<autonomous-loop-dynamic>>` sentinel, or
CronCreate's `<<autonomous-loop>>` equivalent), starting with a
`# Autonomous loop tick ...` header. Logging that in full every tick would
make ai/query.md pure repeated boilerplate, so it's written once under
output/loop/ (reusing the same file across identical ticks) and query.md
gets a single short linked entry instead.
"""
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

DYNAMIC_TICK_PROMPT = (
    "# Autonomous loop tick (dynamic pacing)\n\n"
    "Run the autonomous check using the loop instructions established earlier "
    "in this conversation. If you cannot find them, treat this as a no-op tick.\n\n"
    "You scheduled this tick via the ScheduleWakeup tool (not a recurring cron)."
)


class SavePromptLoopTickTests(unittest.TestCase):
    def test_first_tick_writes_output_file_and_links_it(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp) / "consumer"
            init_repo(repo, "https://github.com/example/consumer.git")

            run_hook(repo, PROMPT_HOOK, {"prompt": DYNAMIC_TICK_PROMPT}, "claude")

            loop_dir = repo / "ai" / "output" / "loop"
            files = sorted(loop_dir.glob("*.md"))
            self.assertEqual(len(files), 1)
            self.assertEqual(files[0].read_text(encoding="utf-8"), DYNAMIC_TICK_PROMPT.strip())
            self.assertIn("autonomous-loop-tick-dynamic-pacing", files[0].name)

            query = (repo / "ai" / "query.md").read_text(encoding="utf-8")
            self.assertNotIn("Run the autonomous check", query)
            self.assertIn(f"output/loop/{files[0].name}", query)
            self.assertIn("Autonomous loop tick (dynamic pacing)", query)

    def test_repeated_identical_tick_reuses_same_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp) / "consumer"
            init_repo(repo, "https://github.com/example/consumer.git")

            run_hook(repo, PROMPT_HOOK, {"prompt": DYNAMIC_TICK_PROMPT}, "claude")
            run_hook(repo, PROMPT_HOOK, {"prompt": DYNAMIC_TICK_PROMPT}, "claude")

            loop_dir = repo / "ai" / "output" / "loop"
            files = sorted(loop_dir.glob("*.md"))
            self.assertEqual(len(files), 1, "identical tick text must not create a second file")

            query = (repo / "ai" / "query.md").read_text(encoding="utf-8")
            self.assertEqual(query.count(f"output/loop/{files[0].name}"), 2)

    def test_tick_after_task_notification_is_condensed_too(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp) / "consumer"
            output_file = Path(tmp) / "agent.output"
            init_repo(repo, "https://github.com/example/consumer.git")
            output_file.write_text("", encoding="utf-8")

            run_hook(
                repo,
                PROMPT_HOOK,
                {
                    "prompt": (
                        "<task-notification>\n"
                        "<task-id>loop_wake_001</task-id>\n"
                        "<tool-use-id>toolu_loop</tool-use-id>\n"
                        f"<output-file>{output_file}</output-file>\n"
                        "<status>completed</status>\n"
                        "<summary>Monitor fired</summary>\n"
                        "<result>Done.</result>\n"
                        "</task-notification>\n"
                        f"{DYNAMIC_TICK_PROMPT}"
                    )
                },
                "claude",
            )

            query = (repo / "ai" / "query.md").read_text(encoding="utf-8")
            self.assertIn("❯ Task Notification:\n", query)
            self.assertNotIn("Run the autonomous check", query)
            loop_dir = repo / "ai" / "output" / "loop"
            files = sorted(loop_dir.glob("*.md"))
            self.assertEqual(len(files), 1)
            self.assertIn(f"output/loop/{files[0].name}", query)


if __name__ == "__main__":
    unittest.main()
