"""Tests for the tag-backup helper."""

from __future__ import annotations

import importlib.util
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from _git_test_helpers import git, init_repo, make_commit

SCRIPT = Path(__file__).parents[1] / "git" / "tag-backup.py"


def load_module() -> object:
    spec = importlib.util.spec_from_file_location("tag_backup", SCRIPT)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module
# end def


class TagBackupTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.repo = Path(self.tempdir.name)
        init_repo(self.repo)
        self.parent = make_commit(self.repo, "parent.txt", "parent")
        make_commit(self.repo, "head.txt", "head")
        self.module = load_module()
    # end def

    def tearDown(self) -> None:
        self.tempdir.cleanup()
    # end def

    def run_script(self, *args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, str(SCRIPT), *args],
            cwd=self.repo,
            text=True,
            capture_output=True,
        )
    # end def

    def test_remove_flag_deletes_backup_tags_in_parent_history(self) -> None:
        git(["tag", f"bak/{self.parent}", self.parent], self.repo)

        result = self.run_script("--rm")

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertNotIn(f"bak/{self.parent}", git(["tag"], self.repo).splitlines())
    # end def

    def test_remove_flag_keeps_non_backup_tags_in_parent_history(self) -> None:
        git(["tag", "release-1", self.parent], self.repo)

        result = self.run_script("--rm")

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("release-1", git(["tag"], self.repo).splitlines())
    # end def

    def test_no_remove_flag_keeps_tags_in_parent_history(self) -> None:
        git(["tag", "old-backup", self.parent], self.repo)

        result = self.run_script("--no-rm")

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("old-backup", git(["tag"], self.repo).splitlines())
    # end def

    def test_remove_and_no_remove_flags_conflict(self) -> None:
        result = self.run_script("--rm", "--no-rm")

        self.assertEqual(result.returncode, 2)
        self.assertIn("not allowed with argument", result.stderr)
    # end def

    def test_interactive_removal_asks_for_each_parent_tag(self) -> None:
        with (
            patch.object(self.module, "parent_tags", return_value=["old-backup"]),
            patch("builtins.input", return_value="n") as input_mock,
        ):
            result = self.module.remove_parent_tags("bak/new", interactive=True)
        # end with

        self.assertEqual(result, 0)
        input_mock.assert_called_once_with("Remove old tag old-backup? (Y/n) ")
    # end def
# end class
