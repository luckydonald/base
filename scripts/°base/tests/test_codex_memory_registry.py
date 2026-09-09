"""Focused tests for `record-codex-memory/hook.py`'s registry-backed
ownership tracking: stable (hostname-free) identity, cross-project
no-touch, `--ignore`, deletion, v1-format tolerance, and fresh-machine
backfill. Broader hook-invocation coverage (PostToolUse/Stop wiring,
message formatting) lives in `test_ai_hooks_base_routing.py`.
"""
from __future__ import annotations

import importlib.util
import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator
from referencing import Registry, Resource


ROOT = Path(__file__).resolve().parents[3]
HOOK_DIR = ROOT / "scripts" / "°base" / "ai" / "hooks" / "record-codex-memory"


def load_hook():
    spec = importlib.util.spec_from_file_location("record_codex_memory", HOOK_DIR / "hook.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


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


class RegistrySchemaTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        def load(name: str) -> dict[str, Any]:
            return json.loads((HOOK_DIR / name).read_text(encoding="utf-8"))

        cls.registry_schema = load("registry.schema.json")
        cls.codex_sync_schema = load("codex-sync.schema.json")
        registry = Registry().with_resources(
            [
                (cls.registry_schema["$id"], Resource.from_contents(cls.registry_schema)),
                (cls.codex_sync_schema["$id"], Resource.from_contents(cls.codex_sync_schema)),
            ]
        )
        cls.registry_validator = Draft202012Validator(cls.registry_schema, registry=registry)
        cls.codex_sync_validator = Draft202012Validator(cls.codex_sync_schema, registry=registry)

    def assertValid(self, validator: Draft202012Validator, value: dict[str, Any]) -> None:
        errors = sorted(validator.iter_errors(value), key=lambda error: list(error.path))
        self.assertEqual(errors, [], "\n".join(error.message for error in errors))

    def assertInvalid(self, validator: Draft202012Validator, value: dict[str, Any]) -> None:
        self.assertTrue(list(validator.iter_errors(value)))

    def test_freshly_written_registry_validates(self) -> None:
        hook = load_hook()
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "registry.json"
            hook.write_registry(path, {"notes": {
                "extensions/ad_hoc/a.md": {
                    "status": "assigned", "project": "proj", "target": "ai/memory/a.md",
                    "hash": "abc", "recorded_by": "fedora",
                },
                "extensions/ad_hoc/b.md": {"status": "ignored", "hash": "def", "recorded_by": None},
            }})
            self.assertValid(self.registry_validator, json.loads(path.read_text(encoding="utf-8")))

    def test_freshly_written_codex_sync_validates(self) -> None:
        hook = load_hook()
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / ".codex-sync.json"
            hook.write_codex_sync(path, {"notes": {
                "extensions/ad_hoc/a.md": {"status": "assigned", "target": "ai/memory/a.md", "hash": "abc"},
            }})
            self.assertValid(self.codex_sync_validator, json.loads(path.read_text(encoding="utf-8")))

    def test_codex_sync_rejects_project_field(self) -> None:
        # The per-project view never carries `project` -- it's implicit.
        self.assertInvalid(self.codex_sync_validator, {
            "version": 2,
            "notes": {"extensions/ad_hoc/a.md": {"status": "assigned", "project": "x", "target": "ai/memory/a.md"}},
        })

    def test_registry_rejects_unknown_status(self) -> None:
        self.assertInvalid(self.registry_validator, {
            "version": 2,
            "notes": {"extensions/ad_hoc/a.md": {"status": "pending"}},
        })


class RegistryOwnershipTests(unittest.TestCase):
    def test_identity_is_stable_across_a_changed_device_id(self) -> None:
        hook = load_hook()
        source = Path(tempfile.mkdtemp()) / "ad_hoc" / "note.md"
        source.parent.mkdir(parents=True)
        source.write_text("hi\n", encoding="utf-8")
        identity_a = hook.note_identity(source)
        identity_b = hook.note_identity(source)
        self.assertEqual(identity_a, identity_b)
        self.assertNotIn(":", identity_a)

    def test_unassigned_notes_excludes_notes_owned_by_another_project(self) -> None:
        hook = load_hook()
        with tempfile.TemporaryDirectory() as tmp:
            repository = Path(tmp) / "codex" / "memories"
            (repository / "extensions" / "ad_hoc").mkdir(parents=True)
            note = repository / "extensions" / "ad_hoc" / "shared.md"
            note.write_text("# Shared\n", encoding="utf-8")
            registry = hook.empty_registry()
            registry["notes"]["extensions/ad_hoc/shared.md"] = {
                "status": "assigned", "project": "some-other-project",
                "target": "ai/memory/shared.md", "hash": "x",
            }
            self.assertEqual(hook.unassigned_notes(repository, registry), [])

    def test_delete_scoped_memory_is_idempotent(self) -> None:
        hook = load_hook()
        with tempfile.TemporaryDirectory(dir="/tmp") as tmp:
            root = Path(tmp) / "project"
            init_repo(root)
            repository = Path(tmp) / "codex" / "memories"
            (repository / "extensions" / "ad_hoc").mkdir(parents=True)
            note = repository / "extensions" / "ad_hoc" / "note.md"
            note.write_text("# Note\n", encoding="utf-8")

            hook.import_native_note(repository, root, "note.md")
            self.assertTrue((root / "ai" / "memory" / "note.md").exists())

            first = hook.delete_scoped_memory(repository, root, "note.md")
            self.assertFalse((root / "ai" / "memory" / "note.md").exists() and note.exists())
            self.assertFalse(note.exists())
            registry = hook.read_registry(repository / "extensions" / "base_synced" / "registry.json")
            self.assertNotIn("extensions/ad_hoc/note.md", registry["notes"])

            second = hook.delete_scoped_memory(repository, root, "note.md")
            self.assertEqual(second, [])
            self.assertNotEqual(first, None)

    def test_ignore_records_via_registry_and_is_respected(self) -> None:
        hook = load_hook()
        with tempfile.TemporaryDirectory(dir="/tmp") as tmp:
            root = Path(tmp) / "project"
            init_repo(root)
            repository = Path(tmp) / "codex" / "memories"
            (repository / "extensions" / "ad_hoc").mkdir(parents=True)
            note = repository / "extensions" / "ad_hoc" / "note.md"
            note.write_text("# Note\n", encoding="utf-8")

            hook.import_native_note(repository, root, "note.md", ignored=True)
            registry, _ = hook.synchronize_shared_memory(repository, root)
            self.assertEqual(registry["notes"]["extensions/ad_hoc/note.md"]["status"], "ignored")
            self.assertEqual(hook.unassigned_notes(repository, registry), [])
            self.assertFalse((root / "ai" / "memory" / "note.md").exists())

    def test_v1_project_file_is_read_only_without_migration_flag(self) -> None:
        hook = load_hook()
        with tempfile.TemporaryDirectory(dir="/tmp") as tmp:
            root = Path(tmp) / "project"
            init_repo(root)
            path = root / "ai" / "memory" / ".codex-sync.json"
            path.parent.mkdir(parents=True)
            path.write_text(json.dumps({
                "version": 1,
                "sources": {"host:extensions/ad_hoc/old.md": {"target": "old.md", "hash": "abc"}},
                "ignored": {},
            }), encoding="utf-8")
            before = path.read_text(encoding="utf-8")

            data = hook.read_codex_sync(path, root)

            self.assertEqual(data["notes"], {})
            self.assertEqual(path.read_text(encoding="utf-8"), before)

    def test_sync_never_blanks_out_an_unmigrated_v1_project_file(self) -> None:
        """Regression: `synchronize_shared_memory()` must never overwrite a
        live v1 `.codex-sync.json` with an empty v2 shell just because
        migration is disabled -- it must leave the file untouched."""
        hook = load_hook()
        with tempfile.TemporaryDirectory(dir="/tmp") as tmp:
            root = Path(tmp) / "project"
            init_repo(root)
            path = root / "ai" / "memory" / ".codex-sync.json"
            path.parent.mkdir(parents=True)
            v1_content = json.dumps({
                "version": 1,
                "sources": {"host:extensions/ad_hoc/old.md": {"target": "old.md", "hash": "abc"}},
                "ignored": {},
            })
            path.write_text(v1_content, encoding="utf-8")
            run_git(root, "add", "ai")
            run_git(root, "commit", "-m", "seed v1 sync file")

            repository = Path(tmp) / "codex" / "memories"
            repository.mkdir(parents=True)

            hook.synchronize_shared_memory(repository, root)

            self.assertEqual(path.read_text(encoding="utf-8"), v1_content)

    def test_backfill_seeds_registry_from_projects_committed_file_on_a_fresh_machine(self) -> None:
        hook = load_hook()
        with tempfile.TemporaryDirectory(dir="/tmp") as tmp:
            root = Path(tmp) / "project"
            init_repo(root)
            memory_file = root / "ai" / "memory" / "note.md"
            memory_file.parent.mkdir(parents=True)
            memory_file.write_text("# Note\n", encoding="utf-8")
            sync_path = root / "ai" / "memory" / ".codex-sync.json"
            hook.write_codex_sync(sync_path, {"notes": {
                "extensions/ad_hoc/note.md": {"status": "assigned", "target": "ai/memory/note.md", "hash": "abc"},
            }})
            run_git(root, "add", "ai")
            run_git(root, "commit", "-m", "seed")

            # Simulate a machine that has never run Codex against this project.
            repository = Path(tmp) / "codex" / "memories"
            repository.mkdir(parents=True)

            registry, _ = hook.synchronize_shared_memory(repository, root)

            key = hook.project_key(root)
            self.assertEqual(
                registry["notes"]["extensions/ad_hoc/note.md"],
                {"status": "assigned", "project": key, "target": "ai/memory/note.md", "hash": "abc"},
            )

    def test_backfill_does_not_overwrite_entry_owned_by_a_different_project(self) -> None:
        hook = load_hook()
        with tempfile.TemporaryDirectory(dir="/tmp") as tmp:
            root = Path(tmp) / "project"
            init_repo(root)
            memory_file = root / "ai" / "memory" / "note.md"
            memory_file.parent.mkdir(parents=True)
            memory_file.write_text("# Note\n", encoding="utf-8")
            sync_path = root / "ai" / "memory" / ".codex-sync.json"
            hook.write_codex_sync(sync_path, {"notes": {
                "extensions/ad_hoc/note.md": {"status": "assigned", "target": "ai/memory/note.md", "hash": "abc"},
            }})
            run_git(root, "add", "ai")
            run_git(root, "commit", "-m", "seed")

            repository = Path(tmp) / "codex" / "memories"
            (repository / "extensions" / "base_synced").mkdir(parents=True)
            hook.write_registry(repository / "extensions" / "base_synced" / "registry.json", {"notes": {
                "extensions/ad_hoc/note.md": {
                    "status": "assigned", "project": "someone-elses-project",
                    "target": "ai/memory/note.md", "hash": "abc",
                },
            }})

            registry, _ = hook.synchronize_shared_memory(repository, root)

            self.assertEqual(registry["notes"]["extensions/ad_hoc/note.md"]["project"], "someone-elses-project")


if __name__ == "__main__":
    unittest.main()
