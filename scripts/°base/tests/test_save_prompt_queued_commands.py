"""Tests for save-prompt/hook.py's Claude-specific queued-command capture
(`_queued_commands_before_current_prompt`/`_capture_claude_queued_commands`):
a message sent while Claude is still mid-turn ("type ahead" queueing) never
triggers its own UserPromptSubmit event and shows up in the transcript as a
`type: "attachment"` record instead of a normal `type: "user"` turn -- so
without this scan it's silently never logged to ai/query.md at all.
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


def transcript_user_turn(text: str, prompt_id: str) -> dict:
    return {"type": "user", "promptId": prompt_id, "message": {"role": "user", "content": text}}


def transcript_queued_command(text: str) -> dict:
    return {
        "type": "attachment",
        "attachment": {"type": "queued_command", "prompt": text, "commandMode": "prompt"},
    }


def write_transcript(path: Path, records: list[dict]) -> None:
    path.write_text(
        "".join(json.dumps(record, ensure_ascii=False) + "\n" for record in records),
        encoding="utf-8",
    )


class SavePromptQueuedCommandsTests(unittest.TestCase):
    def test_queued_interjection_between_two_real_prompts_is_captured(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp) / "consumer"
            init_repo(repo, "https://github.com/example/consumer.git")
            transcript = Path(tmp) / "session.jsonl"
            current_prompt = "Second real prompt"
            write_transcript(
                transcript,
                [
                    transcript_user_turn("First real prompt", "prompt-1"),
                    transcript_queued_command("Make sure to load the python style guide"),
                    transcript_queued_command("Make sure to cleanly rebase before merging in `base/base`."),
                    transcript_user_turn(current_prompt, "prompt-2"),
                ],
            )

            run_hook(
                repo,
                PROMPT_HOOK,
                {"prompt": current_prompt, "prompt_id": "prompt-2", "transcript_path": str(transcript)},
                "claude",
            )

            log_text = (repo / "ai" / "query.md").read_text(encoding="utf-8")
            self.assertIn("Make sure to load the python style guide", log_text)
            self.assertIn("Make sure to cleanly rebase before merging in `base/base`.", log_text)
            self.assertIn(current_prompt, log_text)
            # Queued interjections logged before the triggering prompt, each its own commit.
            self.assertEqual(
                log_text.index("Make sure to load the python style guide")
                < log_text.index("Make sure to cleanly rebase")
                < log_text.index(current_prompt),
                True,
            )

    def test_queued_interjection_from_an_earlier_turn_is_not_relogged(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp) / "consumer"
            init_repo(repo, "https://github.com/example/consumer.git")
            transcript = Path(tmp) / "session.jsonl"
            write_transcript(
                transcript,
                [
                    transcript_queued_command("Stale queued message from before turn 1"),
                    transcript_user_turn("First real prompt", "prompt-1"),
                    transcript_user_turn("Second real prompt", "prompt-2"),
                ],
            )

            run_hook(
                repo,
                PROMPT_HOOK,
                {"prompt": "Second real prompt", "prompt_id": "prompt-2", "transcript_path": str(transcript)},
                "claude",
            )

            log_text = (repo / "ai" / "query.md").read_text(encoding="utf-8")
            self.assertNotIn("Stale queued message from before turn 1", log_text)

    def test_no_transcript_path_is_a_noop(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp) / "consumer"
            init_repo(repo, "https://github.com/example/consumer.git")

            run_hook(repo, PROMPT_HOOK, {"prompt": "Just a normal prompt"}, "claude")

            log_text = (repo / "ai" / "query.md").read_text(encoding="utf-8")
            self.assertIn("Just a normal prompt", log_text)


if __name__ == "__main__":
    unittest.main()
