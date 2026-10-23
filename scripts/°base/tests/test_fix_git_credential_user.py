from __future__ import annotations

import importlib.util
import tempfile
import unittest
from importlib.machinery import SourceFileLoader
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "fix_git_credential_user.py"


def load_script():
    loader = SourceFileLoader("fix_git_credential_user", str(SCRIPT))
    spec = importlib.util.spec_from_loader("fix_git_credential_user", loader)
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module
# end def


script = load_script()


class FixGitCredentialUserTest(unittest.TestCase):
    def test_url_with_username(self) -> None:
        cases = [
            ("https://github.com/luckydonald/repo.git", "https://luckydonald@github.com/luckydonald/repo.git"),
            ("http://example.com:8080/a.git", "http://luckydonald@example.com:8080/a.git"),
            ("https://other@github.com/luckydonald/repo.git", None),
            ("https://git::@github.com/tmux-plugins/tpm", None),
            ("git@github.com:luckydonald/repo.git", None),
        ]
        for url, expected in cases:
            with self.subTest(url=url):
                self.assertEqual(script.url_with_username(url, "luckydonald"), expected)
    # end def

    def test_url_with_username_quotes_special_characters(self) -> None:
        self.assertEqual(script.url_with_username("https://github.com/a/b.git", "me@work"), "https://me%40work@github.com/a/b.git")
    # end def

    def test_credential_helper_pattern_matches_only_helpers(self) -> None:
        self.assertTrue(script.CREDENTIAL_HELPER_RE.match("/usr/local/share/gcm-core/git-credential-manager get"))
        self.assertTrue(script.CREDENTIAL_HELPER_RE.match("git-credential-osxkeychain get"))
        self.assertFalse(script.CREDENTIAL_HELPER_RE.match("/usr/bin/grep git-credential-manager"))
        self.assertFalse(script.CREDENTIAL_HELPER_RE.match("/usr/bin/git -C /tmp push"))
    # end def

    def test_remote_helper_pattern_extracts_remote_and_url(self) -> None:
        match = script.REMOTE_HELPER_RE.search(
            "/Applications/Xcode.app/Contents/Developer/usr/libexec/git-core/git-remote-https origin https://github.com/a/b.git"
        )
        self.assertIsNotNone(match)
        self.assertEqual(match["remote"], "origin")
        self.assertEqual(match["url"], "https://github.com/a/b.git")
    # end def

    def test_git_working_dir_applies_dash_c(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            process = script.Process(pid=1, ppid=0, args=f"/usr/bin/git -C {tmp_path} push")
            self.assertEqual(script.git_working_dir(process), tmp_path)
    # end def

    def test_set_url_command_uses_push_flag_for_pushurl(self) -> None:
        tmp_path = Path("/tmp/repo")
        fetch = script.RemoteTarget(repo_dir=tmp_path, remote="origin", url_key="remote.origin.url", old_url="https://h/x")
        push = script.RemoteTarget(repo_dir=tmp_path, remote="origin", url_key="remote.origin.pushurl", old_url="https://h/x")
        self.assertEqual(
            script.set_url_command(fetch, "https://u@h/x"),
            ["git", "-C", str(tmp_path), "remote", "set-url", "origin", "https://u@h/x"],
        )
        self.assertEqual(
            script.set_url_command(push, "https://u@h/x"),
            ["git", "-C", str(tmp_path), "remote", "set-url", "--push", "origin", "https://u@h/x"],
        )
    # end def
# end class


if __name__ == "__main__":
    unittest.main()
