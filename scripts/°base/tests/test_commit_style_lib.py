"""Tests for `°commit_style_lib`'s override lookup (`.py` preferred over
`.md`, `str.format()` placeholder substitution, and save-plan/record-memory
now honoring an override file too — see
scripts/°base/ai/hooks/°commit_style_lib/__init__.py).
"""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
import uuid
from pathlib import Path

import importlib

_routing = importlib.import_module("scripts.°base.tests.test_ai_hooks_base_routing")
MEMORY_HOOK = _routing.MEMORY_HOOK
PLAN_HOOK = _routing.PLAN_HOOK
PROMPT_HOOK = _routing.PROMPT_HOOK
_encode_project_path = _routing._encode_project_path
init_repo = _routing.init_repo
last_subject = _routing.last_subject
run_hook = _routing.run_hook
run_git = _routing.run_git

# Sibling-module import (this package can't be imported as a real package
# because parent dirs contain non-ASCII / hyphenated names) -- same pattern
# `_lib.py` uses to reach `°commit_style_lib`.
_HOOKS_DIR = _routing.ROOT / "scripts" / "°base" / "ai" / "hooks"
sys.path.insert(0, str(_HOOKS_DIR))
_commit_style = importlib.import_module("°commit_style_lib")
_is_inside_base_repo = _commit_style._is_inside_base_repo
base_ai_commit_subject = _commit_style.base_ai_commit_subject


class CommitStyleLibOverrideTests(unittest.TestCase):
    def test_md_override_substitutes_msg_placeholder(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp) / "consumer"
            init_repo(repo, "https://github.com/example/consumer.git")
            template = repo / "ai" / "commit-templates" / "prompt.md"
            template.parent.mkdir(parents=True)
            template.write_text("🤌 {msg}", encoding="utf-8")

            run_hook(repo, PROMPT_HOOK, {"prompt": "Capture this prompt"}, "codex")

            self.assertEqual(last_subject(repo), "🤌 ai: updated prompt")
        # end with
    # end def

    def test_md_override_with_stray_brace_falls_back_to_raw_text(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp) / "consumer"
            init_repo(repo, "https://github.com/example/consumer.git")
            template = repo / "ai" / "commit-templates" / "prompt.md"
            template.parent.mkdir(parents=True)
            template.write_text("literal {unresolved} braces", encoding="utf-8")

            run_hook(repo, PROMPT_HOOK, {"prompt": "Capture this prompt"}, "codex")

            self.assertEqual(last_subject(repo), "literal {unresolved} braces")
        # end with
    # end def

    def test_py_override_preferred_over_md(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp) / "consumer"
            init_repo(repo, "https://github.com/example/consumer.git")
            templates_dir = repo / "ai" / "commit-templates"
            templates_dir.mkdir(parents=True)
            (templates_dir / "prompt.md").write_text("should not be used", encoding="utf-8")
            (templates_dir / "prompt.py").write_text(
                "def format_message(msg, **extra):\n"
                "    return f'PY: {msg}'\n",
                encoding="utf-8",
            )

            run_hook(repo, PROMPT_HOOK, {"prompt": "Capture this prompt"}, "codex")

            self.assertEqual(last_subject(repo), "PY: ai: updated prompt")
        # end with
    # end def

    def test_broken_py_override_falls_back_to_md(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp) / "consumer"
            init_repo(repo, "https://github.com/example/consumer.git")
            templates_dir = repo / "ai" / "commit-templates"
            templates_dir.mkdir(parents=True)
            (templates_dir / "prompt.md").write_text("🤌 {msg}", encoding="utf-8")
            (templates_dir / "prompt.py").write_text("raise RuntimeError('broken')\n", encoding="utf-8")

            run_hook(repo, PROMPT_HOOK, {"prompt": "Capture this prompt"}, "codex")

            self.assertEqual(last_subject(repo), "🤌 ai: updated prompt")
        # end with
    # end def

    def test_save_plan_honors_override_and_keeps_dynamic_slug(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp) / "consumer"
            init_repo(repo, "https://github.com/example/consumer.git")
            template = repo / "ai" / "commit-templates" / "plan.md"
            template.parent.mkdir(parents=True)
            template.write_text("🗺️ {msg}", encoding="utf-8")

            run_hook(
                repo,
                PLAN_HOOK,
                {
                    "hook_event_name": "Stop",
                    "session_id": f"test-{uuid.uuid4()}",
                    "last_assistant_message": (
                        "<proposed_plan>\n# Styled Plan\nBody.\n</proposed_plan>"
                    ),
                },
                "codex",
            )

            self.assertEqual(last_subject(repo), "🗺️ ai: save plan 001_styled-plan")
        # end with
    # end def

    def test_agent_results_honors_prompt_override_and_keeps_dynamic_id(self):
        """Regression test: these `append_and_commit` call sites used to pass
        `commit_template_relpath=""` specifically to avoid a whole-message-
        replacing override clobbering the dynamic agent-id -- no longer
        needed now that overrides preserve it via `{msg}`, but the styling
        was silently skipped until that bypass was removed too (real repro:
        commit a499dd0 landed unstyled, `ai: agent 004.... results`)."""
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp) / "consumer"
            init_repo(repo, "https://github.com/example/consumer.git")
            template = repo / "ai" / "commit-templates" / "prompt.md"
            template.parent.mkdir(parents=True)
            template.write_text("🤌 {msg}", encoding="utf-8")

            output_file = Path(tmp) / "agent.output"
            output_file.write_text(
                json.dumps(
                    {
                        "message": {
                            "content": [
                                {
                                    "type": "tool_use",
                                    "id": "toolu_test",
                                    "name": "Agent",
                                    "input": {"prompt": "Inspect the compose window."},
                                }
                            ]
                        }
                    }
                )
                + "\n",
                encoding="utf-8",
            )

            run_hook(
                repo,
                PROMPT_HOOK,
                {
                    "prompt": (
                        "<task-notification>\n"
                        "<task-id>a6f364ce63ffebb84</task-id>\n"
                        "<tool-use-id>toolu_test</tool-use-id>\n"
                        f"<output-file>{output_file}</output-file>\n"
                        "<status>completed</status>\n"
                        "<summary>Agent came to rest</summary>\n"
                        "<result>Done.</result>\n"
                        "<usage><subagent_tokens>1</subagent_tokens>"
                        "<tool_uses>1</tool_uses><duration_ms>1</duration_ms></usage>\n"
                        "</task-notification>"
                    )
                },
                "claude",
            )

            self.assertEqual(last_subject(repo), "🤌 ai: agent 001.a6f364ce63ffebb84 results")
        # end with
    # end def

    def test_record_memory_honors_override_and_keeps_dynamic_slug(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp) / "consumer"
            home = Path(tmp) / "home"
            init_repo(repo, "https://github.com/example/consumer.git")
            template = repo / "ai" / "commit-templates" / "memory.md"
            template.parent.mkdir(parents=True)
            template.write_text("🧠 {msg}", encoding="utf-8")
            encoded = _encode_project_path(repo.resolve())
            src_dir = home / ".claude" / "projects" / encoded / "memory"
            src_dir.mkdir(parents=True)
            (src_dir / "note.md").write_text("remember this\n", encoding="utf-8")

            run_hook(
                repo,
                MEMORY_HOOK,
                {"hook_event_name": "SessionStart"},
                extra_env={"HOME": str(home)},
            )

            self.assertEqual(last_subject(repo), "🧠 ai: record memory note")
        # end with
    # end def
# end class


class IsInsideBaseRepoTests(unittest.TestCase):
    """Coverage for `_is_inside_base_repo`, including the `True` branch (no
    prior test exercised it at all) and the linked-`git worktree` regression:
    a worktree's own directory is never named `base`, even when it belongs to
    a `base` main checkout, so detection has to look past the directory name.
    """

    def test_true_from_real_base_named_checkout(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp) / "base"
            init_repo(repo, "git@github.com:luckydonald/base.git")

            self.assertTrue(_is_inside_base_repo(repo))
            self.assertTrue(base_ai_commit_subject("do a thing").startswith("[base] "))
        # end with
    # end def

    def test_true_from_linked_worktree_not_named_base(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp) / "base"
            init_repo(repo, "git@github.com:luckydonald/base.git")
            worktree_dir = Path(tmp) / "some-feature-branch"
            run_git(repo, "worktree", "add", "-b", "some-feature-branch", str(worktree_dir))

            self.assertTrue(_is_inside_base_repo(worktree_dir))

            run_hook(worktree_dir, PROMPT_HOOK, {"prompt": "Capture this prompt"}, "codex")
            self.assertTrue(last_subject(worktree_dir).startswith("[base] "))
            self.assertTrue((worktree_dir / "ai" / "°base" / "query.md").is_file())
            self.assertFalse((worktree_dir / "ai" / "query.md").exists())
        # end with
    # end def

    def test_false_from_worktree_of_non_base_repo(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp) / "consumer"
            init_repo(repo, "https://github.com/example/consumer.git")
            worktree_dir = Path(tmp) / "some-feature-branch"
            run_git(repo, "worktree", "add", "-b", "some-feature-branch", str(worktree_dir))

            self.assertFalse(_is_inside_base_repo(worktree_dir))
        # end with
    # end def

    def test_false_from_worktree_of_bare_repo(self):
        """Deliberate non-goal: a bare `base` repo's `--git-common-dir` points
        at the bare dir itself (e.g. `base.git`), not a `.git` inside a
        checkout, so there's no sibling checkout root to resolve -- this must
        fall back to False rather than crash or misreport, even when the bare
        dir is itself named to look like `base`."""
        with tempfile.TemporaryDirectory() as tmp:
            src = Path(tmp) / "src"
            init_repo(src, "git@github.com:luckydonald/base.git")
            bare_dir = Path(tmp) / "base.git"
            run_git(Path(tmp), "clone", "--bare", str(src), str(bare_dir))
            worktree_dir = Path(tmp) / "some-feature-branch"
            run_git(bare_dir, "worktree", "add", str(worktree_dir), "HEAD")

            self.assertFalse(_is_inside_base_repo(worktree_dir))
        # end with
    # end def
# end class


if __name__ == "__main__":
    unittest.main()
