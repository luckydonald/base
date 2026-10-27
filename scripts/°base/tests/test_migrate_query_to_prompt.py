"""Tests for the `query.md` -> `prompt.md` migration: what the hooks do with an old log, and the lookup of the log directories."""
from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_ai_hooks_base_routing import init_repo, run_git, run_hook  # noqa: E402

ROOT = Path(__file__).resolve().parents[3]
PROMPT_HOOK = ROOT / "scripts" / "°base" / "ai" / "hooks" / "save-prompt" / "hook.py"
sys.path.insert(0, str(ROOT / "scripts" / "°base" / "ai"))
import migrate_query_to_prompt  # noqa: E402


def commit_file(repo: Path, rel: str, text: str) -> None:
    path = repo / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    run_git(repo, "add", "--", rel)
    run_git(repo, "commit", "-m", f"add {rel}")


class HookMigrationTests(unittest.TestCase):
    def test_hook_renames_the_old_log_and_appends_to_the_new_one(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp) / "consumer"
            init_repo(repo, "https://github.com/example/consumer.git")
            commit_file(repo, "ai/query.md", "› Old prompt\n\n")

            run_hook(repo, PROMPT_HOOK, {"prompt": "New prompt"}, "codex")

            self.assertFalse((repo / "ai" / "query.md").exists())
            self.assertEqual("› Old prompt\n\n› New prompt\n\n", (repo / "ai" / "prompt.md").read_text(encoding="utf-8"))
            self.assertEqual("", run_git(repo, "status", "--porcelain").stdout)

    def test_hook_keeps_both_logs_up_to_date_while_they_differ(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp) / "consumer"
            init_repo(repo, "https://github.com/example/consumer.git")
            commit_file(repo, "ai/query.md", "› Old prompt\n\n")
            commit_file(repo, "ai/prompt.md", "› Newer log\n\n")

            run_hook(repo, PROMPT_HOOK, {"prompt": "Written twice"}, "codex")

            self.assertEqual("› Old prompt\n\n› Written twice\n\n", (repo / "ai" / "query.md").read_text(encoding="utf-8"))
            self.assertEqual("› Newer log\n\n› Written twice\n\n", (repo / "ai" / "prompt.md").read_text(encoding="utf-8"))
            self.assertEqual("", run_git(repo, "status", "--porcelain").stdout)
            self.assertEqual("ai: updated prompt", run_git(repo, "log", "-1", "--format=%s").stdout.strip())
            self.assertEqual(["ai/prompt.md", "ai/query.md"], run_git(repo, "show", "--name-only", "--format=", "HEAD").stdout.split())

    def test_hook_with_a_dirty_old_log_moves_the_uncommitted_lines_along(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp) / "consumer"
            init_repo(repo, "https://github.com/example/consumer.git")
            commit_file(repo, "ai/query.md", "› Old prompt\n\n")
            (repo / "ai" / "query.md").write_text("› Old prompt\n\n› Typed by hand\n\n", encoding="utf-8")

            run_hook(repo, PROMPT_HOOK, {"prompt": "New prompt"}, "codex")

            self.assertFalse((repo / "ai" / "query.md").exists())
            self.assertEqual(
                "› Old prompt\n\n› Typed by hand\n\n› New prompt\n\n", (repo / "ai" / "prompt.md").read_text(encoding="utf-8"),
            )

    def test_issue_logs_are_migrated_too(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp) / "consumer"
            init_repo(repo, "https://github.com/example/consumer.git")
            commit_file(repo, "ai/by-issue/DEMO-42/query.md", "› Issue prompt\n\n")

            status = migrate_query_to_prompt.migrate_dir(repo / "ai" / "by-issue" / "DEMO-42")

            self.assertEqual(migrate_query_to_prompt.STATUS_MIGRATED, status)
            self.assertEqual("› Issue prompt\n\n", run_git(repo, "show", "HEAD:ai/by-issue/DEMO-42/prompt.md").stdout)
            self.assertEqual("", run_git(repo, "status", "--porcelain").stdout)


class FindLogDirsTests(unittest.TestCase):
    def test_only_real_log_folders_are_found(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp) / "consumer"
            init_repo(repo, "https://github.com/example/consumer.git")
            wanted = ["ai", "ai/°base", "ai/by-issue/A-1", "ai/°base/by-issue/A-2", "sub/ai", "a/b/c/ai"]
            for folder in wanted:
                commit_file(repo, f"{folder}/query.md", "log\n")
            for decoy in ["with/ai/in/its/name", "ai/plans", "docs", "ai/by-issue", "ai/by-issue/A-1/deeper"]:
                commit_file(repo, f"{decoy}/query.md", "not a log\n")
            (repo / "untracked" / "ai").mkdir(parents=True)
            (repo / "untracked" / "ai" / "query.md").write_text("log\n", encoding="utf-8")

            found = [path.relative_to(repo).as_posix() for path in migrate_query_to_prompt.find_log_dirs(repo)]

            self.assertEqual(sorted([*wanted, "untracked/ai"]), sorted(found))
            self.assertEqual("ai", found[0], "the root comes first")


if __name__ == "__main__":
    unittest.main()
