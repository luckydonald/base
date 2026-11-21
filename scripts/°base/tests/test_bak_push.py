"""Tests for bak-push: layered `backup_tags` settings, pushing and deleting tags."""

from __future__ import annotations

import importlib
import io
import json
import sys
import tempfile
import unittest
from unittest.mock import patch
from contextlib import redirect_stdout
from pathlib import Path

from _git_test_helpers import git, init_repo, make_commit

sys.path.insert(0, str(Path(__file__).parents[1] / "git"))

push = importlib.import_module("°bak_lib.push")
settings = importlib.import_module("°bak_lib.settings")
normalize_url, process = push.normalize_url, push.process
DEFAULT_REPO, BackupTags, load_backup_tags = settings.DEFAULT_REPO, settings.BackupTags, settings.load_backup_tags


def write_settings(root: Path, name: str, section: object) -> None:
    path = root / "ai" / "settings" / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"backup_tags": section}))
# end def


class SettingsTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
    # end def

    def tearDown(self) -> None:
        self.tmp.cleanup()
    # end def

    def test_defaults_without_files(self) -> None:
        self.assertEqual(load_backup_tags(self.root, {}), BackupTags(DEFAULT_REPO, False, False))
    # end def

    def test_layers_override_only_set_keys(self) -> None:
        write_settings(self.root, "settings.json", {"repo": "https://a/x.git", "delete_tags": {"local": True, "origin": True}})
        write_settings(self.root, "settings.local.json", {"delete_tags": {"origin": False}})
        self.assertEqual(load_backup_tags(self.root, {}), BackupTags("https://a/x.git", True, False))
        write_settings(self.root, "settings.repo.json", {"repo": "https://b/y.git"})
        self.assertEqual(load_backup_tags(self.root, {}).repo, "https://b/y.git")
    # end def

    def test_env_beats_files_and_parses_bools(self) -> None:
        write_settings(self.root, "settings.local.json", {"repo": "https://a/x.git", "delete_tags": {"local": True}})
        env = {"BACKUP_TAGS_REPO": "https://env/z.git", "BACKUP_TAGS_DELETE_TAGS_LOCAL": "No", "BACKUP_TAGS_DELETE_TAGS_ORIGIN": " TRUE "}
        self.assertEqual(load_backup_tags(self.root, env), BackupTags("https://env/z.git", False, True))
        self.assertEqual(load_backup_tags(self.root, {"BACKUP_TAGS_DELETE_TAGS_LOCAL": ""}).delete_local, True)
    # end def

    def test_invalid_values_exit(self) -> None:
        with self.assertRaises(SystemExit):
            load_backup_tags(self.root, {"BACKUP_TAGS_DELETE_TAGS_LOCAL": "maybe"})
        # end with
        write_settings(self.root, "settings.json", {"delete_tags": {"local": "yes"}})
        with self.assertRaises(SystemExit):
            load_backup_tags(self.root, {})
        # end with
    # end def


class PushTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        base = Path(self.tmp.name)
        self.bak, self.origin, self.repo = base / "bak.git", base / "origin.git", base / "repo"
        for bare in (self.bak, self.origin):
            git(["init", "--bare", "-b", "master", str(bare)], base)
        # end for
        self.repo.mkdir()
        init_repo(self.repo)
        self.sha = make_commit(self.repo, "a.txt", "a")
        git(["remote", "add", "origin", self.origin.as_uri()], self.repo)
        git(["tag", f"bak/{self.sha}"], self.repo)
        self.name = f"bak/{self.sha}"
        patcher = patch.object(push, "has_empty", return_value=False)  # no network, no `-rebased-` variant
        patcher.start()
        self.addCleanup(patcher.stop)
    # end def

    def tearDown(self) -> None:
        self.tmp.cleanup()
    # end def

    def run_process(self, *, local: bool = False, origin: bool = False, dry: bool = False, bak: Path | None = None) -> None:
        with redirect_stdout(io.StringIO()):
            process(self.repo, [], BackupTags((bak or self.bak).as_uri(), local, origin), dry)
        # end with
    # end def

    def tags(self, repo: Path) -> list[str]:
        return git(["tag", "--list", "bak/*"], repo).split()
    # end def

    def test_push_is_namespaced_and_leaves_config_alone(self) -> None:
        config = (self.repo / ".git" / "config").read_text()
        self.run_process()
        remote = self.tags(self.bak)
        self.assertEqual(len(remote), 1)
        self.assertRegex(remote[0], rf"^bak/\+/.+/\+/tag/(on-empty|no-empty)/\+/{self.name}$")
        self.assertEqual(config, (self.repo / ".git" / "config").read_text())
        self.assertEqual(self.tags(self.repo), [self.name])
    # end def

    def test_dry_run_changes_nothing(self) -> None:
        git(["push", "origin", f"refs/tags/{self.name}"], self.repo)
        self.run_process(local=True, origin=True, dry=True)
        self.assertEqual(self.tags(self.bak), [])
        self.assertEqual(self.tags(self.origin), [self.name])
        self.assertEqual(self.tags(self.repo), [self.name])
    # end def

    def test_delete_local_only(self) -> None:
        git(["push", "origin", f"refs/tags/{self.name}"], self.repo)
        self.run_process(local=True)
        self.assertEqual(self.tags(self.repo), [])
        self.assertEqual(self.tags(self.origin), [self.name])
        self.assertEqual(len(self.tags(self.bak)), 1)
    # end def

    def test_delete_origin_when_same_commit(self) -> None:
        git(["push", "origin", f"refs/tags/{self.name}"], self.repo)
        self.run_process(origin=True)
        self.assertEqual(self.tags(self.origin), [])
        self.assertEqual(self.tags(self.repo), [self.name])
    # end def

    def test_keep_origin_when_other_commit_or_absent(self) -> None:
        self.run_process(origin=True)  # absent on origin
        other = make_commit(self.repo, "b.txt", "b")
        git(["push", "origin", f"{other}:refs/tags/{self.name}"], self.repo)
        self.run_process(origin=True)
        self.assertEqual(self.tags(self.origin), [self.name])
    # end def

    def test_keep_origin_when_it_is_the_backup_repo(self) -> None:
        git(["remote", "set-url", "origin", self.bak.as_uri()], self.repo)
        git(["push", "origin", f"refs/tags/{self.name}"], self.repo)
        self.run_process(origin=True)
        self.assertIn(self.name, self.tags(self.bak))
    # end def

    def test_nothing_deleted_when_push_fails(self) -> None:
        self.run_process(local=True, origin=True, bak=self.bak.parent / "missing.git")
        self.assertEqual(self.tags(self.repo), [self.name])
    # end def


class NormalizeTests(unittest.TestCase):
    def test_equivalent_forms(self) -> None:
        expected = normalize_url("https://github.com/o/r")
        for url in ("https://user@github.com/o/r.git", "git@GitHub.com:o/r.git", "ssh://git@github.com:22/o/r/"):
            self.assertEqual(normalize_url(url), expected, url)
        # end for
    # end def
# end class


if __name__ == "__main__":
    unittest.main()
