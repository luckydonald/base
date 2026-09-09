from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
PROMOTE_HELPER = ROOT / "scripts" / "°base" / "ai" / "memory" / "promote.py"
MARKER_HOOK = (
    ROOT / "scripts" / "°base" / "git" / "hooks" / "commit" / "require_memory_delete_marker.py"
)


def run_git(repo: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args],
        cwd=repo,
        capture_output=True,
        text=True,
        check=True,
    )


def init_repo(repo: Path) -> None:
    repo.mkdir(parents=True, exist_ok=True)
    run_git(repo, "init")
    run_git(repo, "config", "user.email", "tester@example.com")
    run_git(repo, "config", "user.name", "Test User")
    run_git(repo, "remote", "add", "origin", "https://luckydonald@github.com/luckydonald/base.git")
    (repo / "README.md").write_text("test repo\n", encoding="utf-8")
    run_git(repo, "add", "README.md")
    run_git(repo, "commit", "-m", "init")


def seed_base_memory(repo: Path, name: str, *, entry_desc: str = "a description.") -> Path:
    memory_dir = repo / "ai" / "°base" / "memory"
    memory_dir.mkdir(parents=True, exist_ok=True)
    path = memory_dir / name
    path.write_text(f"# {name}\n\ncontent\n", encoding="utf-8")
    index = memory_dir / "MEMORY.md"
    title = Path(name).stem.replace("_", " ").title()
    line = f"- [{title}]({name}) — {entry_desc}\n"
    if index.is_file():
        index.write_text(index.read_text(encoding="utf-8") + line, encoding="utf-8")
    else:
        index.write_text("# Memory\n" + line, encoding="utf-8")
    run_git(repo, "add", str(path.relative_to(repo)), str(index.relative_to(repo)))
    run_git(repo, "commit", "-m", f"seed {name}")
    return path


def run_promote(repo: Path, *args: str) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env.pop("CLAUDE_CONFIG_DIR", None)
    env["CLAUDE_PROJECT_DIR"] = str(repo.resolve())
    return subprocess.run(
        [sys.executable, str(PROMOTE_HELPER), *args],
        cwd=repo,
        env=env,
        capture_output=True,
        text=True,
    )


def run_marker_hook(repo: Path, message: str) -> subprocess.CompletedProcess[str]:
    msg = repo / "COMMIT_EDITMSG"
    msg.write_text(message, encoding="utf-8")
    return subprocess.run(
        [sys.executable, str(MARKER_HOOK), str(msg)],
        cwd=repo,
        capture_output=True,
        text=True,
    )


class MemoryPromoteTests(unittest.TestCase):
    def test_promote_moves_file_and_rewrites_both_memory_md(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp) / "base"
            init_repo(repo)
            seed_base_memory(repo, "mynote.md")

            result = run_promote(repo, "mynote.md")

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertFalse((repo / "ai" / "°base" / "memory" / "mynote.md").exists())
            self.assertEqual(
                (repo / "ai" / "memory" / "mynote.md").read_text(encoding="utf-8"),
                "# mynote.md\n\ncontent\n",
            )
            root_index = (repo / "ai" / "memory" / "MEMORY.md").read_text(encoding="utf-8")
            self.assertIn("- [Mynote](mynote.md) — a description.", root_index)
            base_index = (repo / "ai" / "°base" / "memory" / "MEMORY.md").read_text(encoding="utf-8")
            self.assertIn("- [Mynote](../../memory/mynote.md) — a description.", base_index)

            tracked = run_git(repo, "ls-files").stdout
            self.assertNotIn("ai/°base/memory/mynote.md", tracked)
            self.assertIn("ai/memory/mynote.md", tracked)

            message = run_git(repo, "log", "-1", "--pretty=%B").stdout
            marker_result = run_marker_hook(repo, message)
            self.assertEqual(marker_result.returncode, 0, marker_result.stderr)

    def test_demote_reverses_promote(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp) / "base"
            init_repo(repo)
            seed_base_memory(repo, "mynote.md")
            promoted = run_promote(repo, "mynote.md")
            self.assertEqual(promoted.returncode, 0, promoted.stderr)

            result = run_promote(repo, "mynote.md", "--demote")

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertFalse((repo / "ai" / "memory" / "mynote.md").exists())
            self.assertEqual(
                (repo / "ai" / "°base" / "memory" / "mynote.md").read_text(encoding="utf-8"),
                "# mynote.md\n\ncontent\n",
            )
            base_index = (repo / "ai" / "°base" / "memory" / "MEMORY.md").read_text(encoding="utf-8")
            self.assertIn("- [Mynote](mynote.md) — a description.", base_index)
            self.assertNotIn("../../memory/mynote.md", base_index)
            root_index = (repo / "ai" / "memory" / "MEMORY.md").read_text(encoding="utf-8")
            self.assertNotIn("mynote.md", root_index)

            message = run_git(repo, "log", "-1", "--pretty=%B").stdout
            marker_result = run_marker_hook(repo, message)
            self.assertEqual(marker_result.returncode, 0, marker_result.stderr)

    def test_promote_relocates_codex_sync_entry_when_present(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp) / "base"
            init_repo(repo)
            seed_base_memory(repo, "mynote.md")
            sync_path = repo / "ai" / "°base" / "memory" / ".codex-sync.json"
            sync_path.write_text(
                json.dumps(
                    {
                        "version": 1,
                        "sources": {
                            "host:extensions/ad_hoc/mynote.md": {
                                "target": "mynote.md",
                                "hash": "abc123",
                            }
                        },
                        "ignored": {},
                    }
                ),
                encoding="utf-8",
            )
            run_git(repo, "add", str(sync_path.relative_to(repo)))
            run_git(repo, "commit", "-m", "seed codex sync")

            result = run_promote(repo, "mynote.md")

            self.assertEqual(result.returncode, 0, result.stderr)
            base_sync = json.loads(sync_path.read_text(encoding="utf-8"))
            self.assertEqual(base_sync["sources"], {})
            root_sync = json.loads(
                (repo / "ai" / "memory" / ".codex-sync.json").read_text(encoding="utf-8")
            )
            self.assertEqual(
                root_sync["sources"]["host:extensions/ad_hoc/mynote.md"],
                {"target": "mynote.md", "hash": "abc123"},
            )

    def test_promote_refuses_when_destination_already_has_same_name(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp) / "base"
            init_repo(repo)
            seed_base_memory(repo, "mynote.md")
            root_dir = repo / "ai" / "memory"
            root_dir.mkdir(parents=True)
            (root_dir / "mynote.md").write_text("already here\n", encoding="utf-8")
            run_git(repo, "add", str((root_dir / "mynote.md").relative_to(repo)))
            run_git(repo, "commit", "-m", "seed collision")

            result = run_promote(repo, "mynote.md")

            self.assertEqual(result.returncode, 1)
            self.assertIn("refusing to overwrite", result.stderr)
            self.assertTrue((repo / "ai" / "°base" / "memory" / "mynote.md").exists())

    def test_promote_refuses_outside_base_repo(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp) / "some-project"
            repo.mkdir(parents=True)
            run_git(repo, "init")
            run_git(repo, "config", "user.email", "tester@example.com")
            run_git(repo, "config", "user.name", "Test User")
            (repo / "README.md").write_text("x\n", encoding="utf-8")
            run_git(repo, "add", "README.md")
            run_git(repo, "commit", "-m", "init")

            result = run_promote(repo, "mynote.md")

            self.assertEqual(result.returncode, 2)
            self.assertIn("only applies inside the base repo", result.stderr)


if __name__ == "__main__":
    unittest.main()
