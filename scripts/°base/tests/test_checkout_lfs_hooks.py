from __future__ import annotations

import os
import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
CHECKOUT = ROOT / "scripts" / "°base" / "init" / "checkout.sh"
LFS_TEXT = '#!/bin/sh\ncommand -v git-lfs >/dev/null 2>&1 || exit 2\ngit lfs {name} "$@"\n'


def run_git(repo: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=repo, capture_output=True, text=True, check=True)


class CheckoutLfsHooksTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.repo = Path(self._tmp.name)
        run_git(self.repo, "init", "-q", ".")
        self.hooks = self.repo / ".git" / "hooks"

    def run_checkout(self) -> None:
        env = {**os.environ, "HOME": self._tmp.name}  # no real ~/.local/bin tools needed, nothing outside the throwaway repo is touched
        subprocess.run(["bash", str(CHECKOUT)], cwd=self.repo, env=env, capture_output=True, text=True, check=True)

    def test_symlinked_hook_is_not_rewritten_through_the_link(self) -> None:
        tracked = self.repo / ".hooks" / "pre-push.bash"
        tracked.parent.mkdir()
        original = '#!/usr/bin/env bash\n# tracked hook, also calls git lfs / git-lfs\ngit lfs pre-push "$@"\n./tag_on_push.py\n'
        tracked.write_text(original)
        tracked.chmod(0o755)
        (self.hooks / "pre-push").symlink_to("../../.hooks/pre-push.bash")

        self.run_checkout()

        self.assertTrue((self.hooks / "pre-push").is_symlink())
        self.assertEqual(tracked.read_text(), original)

    def test_plain_lfs_stub_is_still_repaired(self) -> None:
        stub = self.hooks / "post-commit"
        stub.write_text(LFS_TEXT.format(name="post-commit"))
        stub.chmod(0o755)

        self.run_checkout()

        text = stub.read_text()
        self.assertIn("AllMyStorage hook PATH", text)
        self.assertIn('git lfs post-commit "$@"', text)


if __name__ == "__main__":
    unittest.main()
