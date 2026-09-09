from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
AUDIT = ROOT / "scripts" / "°base" / "ai" / "memory" / "codex-sync-audit.py"


def run_git(repo: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["git", *args], cwd=repo, capture_output=True, text=True, check=True)


def init_repo(repo: Path) -> None:
    repo.mkdir(parents=True, exist_ok=True)
    run_git(repo, "init")
    run_git(repo, "config", "user.email", "tester@example.com")
    run_git(repo, "config", "user.name", "Test User")
    (repo / "README.md").write_text("test repo\n", encoding="utf-8")
    run_git(repo, "add", "README.md")
    run_git(repo, "commit", "-m", "init")


def seed_claim(base_synced: Path, project_key: str, root: Path) -> None:
    resource = base_synced / "resources" / project_key
    resource.mkdir(parents=True)
    (resource / "scope.json").write_text(json.dumps({"cwd": str(root)}), encoding="utf-8")
    (resource / "note.md").write_text("# Note\n", encoding="utf-8")
    (resource / ".codex-sync.json").write_text(json.dumps({
        "version": 2,
        "notes": {
            "extensions/ad_hoc/note.md": {"status": "assigned", "target": "ai/memory/note.md", "hash": "abc"},
        },
    }), encoding="utf-8")
    memory_file = root / "ai" / "memory" / "note.md"
    memory_file.parent.mkdir(parents=True, exist_ok=True)
    memory_file.write_text("# Note\n", encoding="utf-8")
    index = root / "ai" / "memory" / "MEMORY.md"
    index.write_text("# Memory\n- [Note](note.md) — TODO: summarize this file.\n", encoding="utf-8")
    (root / "ai" / "memory" / ".codex-sync.json").write_text(json.dumps({
        "version": 2,
        "notes": {
            "extensions/ad_hoc/note.md": {"status": "assigned", "target": "ai/memory/note.md", "hash": "abc"},
        },
    }), encoding="utf-8")
    run_git(root, "add", "ai")
    run_git(root, "commit", "-m", "seed claim")


def run_audit(codex_home: Path, *args: str) -> subprocess.CompletedProcess[str]:
    import os

    env = os.environ.copy()
    env["CODEX_HOME"] = str(codex_home)
    return subprocess.run(
        [sys.executable, str(AUDIT), *args], env=env, capture_output=True, text=True
    )


class CodexSyncAuditTests(unittest.TestCase):
    def test_report_lists_duplicate_claim(self) -> None:
        with tempfile.TemporaryDirectory(dir="/tmp") as tmp:
            codex_home = Path(tmp) / "codex"
            base_synced = codex_home / "memories" / "extensions" / "base_synced"
            project_a = Path(tmp) / "project-a"
            project_b = Path(tmp) / "project-b"
            init_repo(project_a)
            init_repo(project_b)
            seed_claim(base_synced, "project-a", project_a)
            seed_claim(base_synced, "project-b", project_b)

            result = run_audit(codex_home)

            self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
            self.assertIn("extensions/ad_hoc/note.md", result.stdout)
            self.assertIn("project-a", result.stdout)
            self.assertIn("project-b", result.stdout)

    def test_fix_keeps_chosen_owner_and_removes_others(self) -> None:
        with tempfile.TemporaryDirectory(dir="/tmp") as tmp:
            codex_home = Path(tmp) / "codex"
            base_synced = codex_home / "memories" / "extensions" / "base_synced"
            project_a = Path(tmp) / "project-a"
            project_b = Path(tmp) / "project-b"
            init_repo(project_a)
            init_repo(project_b)
            seed_claim(base_synced, "project-a", project_a)
            seed_claim(base_synced, "project-b", project_b)

            result = run_audit(codex_home, "--fix", "note.md", "--owner", "project-a")

            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertTrue((project_a / "ai" / "memory" / "note.md").exists())
            self.assertFalse((project_b / "ai" / "memory" / "note.md").exists())
            b_sync = json.loads((project_b / "ai" / "memory" / ".codex-sync.json").read_text())
            self.assertEqual(b_sync["notes"], {})
            registry = json.loads((base_synced / "registry.json").read_text())
            self.assertEqual(registry["notes"]["extensions/ad_hoc/note.md"]["project"], "project-a")

            rerun = run_audit(codex_home)
            self.assertEqual(rerun.returncode, 0, rerun.stdout + rerun.stderr)
            self.assertIn("No note is claimed", rerun.stdout)


if __name__ == "__main__":
    unittest.main()
