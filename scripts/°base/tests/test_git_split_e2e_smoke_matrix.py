"""End-to-end smoke matrix for split.py/get-base.py: every repo-preparation
variant (1.1-1.6 from the e2e test plan) combined with every branch-checkout
variant (2.1-2.9), run through the real "fake curl" get-base.py auto-mode
entry point, asserting the tool runs to completion without crashing and
without leaving an unresolved merge/cherry-pick/rebase behind.

This is deliberately shallow-but-wide -- it does not inspect commit content
in detail (see test_git_split_e2e_deep_flow.py for that). Branch-checkout
variants 5-8 all leave `ai/UNCLEAN/feature/batz` checked out; auto mode
always passes an explicit branch name to sync-splits (get-base.py's
auto_argv never uses the bare all-branches discovery form), so this matrix
does not exercise multi-branch discovery -- that's out of scope here.

Repo-variant 3 (README.md/.gitignore already committed on `mane` before
base/base is ever folded) combined with staying on `mane` (branch-checkout
1/2) is the smoke-level regression test for the history_master.py first-fold
auto-resolve fix: if that fix is missing or broken, this is where the matrix
first fails with a nonzero returncode (a real, unresolved MergeConflict).

Note: this suite fetches `base/base` from a small fixture base repo (see `fixtures.fixture_base_repo`), never GitHub
and not this repo's own thousands-of-commits-long `base` history. The fixture carries the current working tree's
°split_lib, so local, not-yet-committed fixes show up here, too. The combinations are independent and run concurrently
(`fixtures.E2E_WORKERS`).
"""

from __future__ import annotations

import sys
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _git_split_e2e_fixtures as fixtures  # noqa: E402


class SmokeMatrixTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls._tmp = tempfile.TemporaryDirectory()
        cls.this_repo_root = fixtures.resolve_this_repo_root()
        cls.empty_remote = fixtures.make_empty_init_remote(Path(cls._tmp.name))

    @classmethod
    def tearDownClass(cls) -> None:
        cls._tmp.cleanup()

    def run_combination(self, repo_name: str, repo_builder, branch_name: str, branch_applier) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = Path(tmp)
            manifest = repo_builder(repo_root, self.empty_remote)
            branch_applier(repo_root, manifest)

            fixtures.ensure_base_remote(repo_root)

            result = fixtures.run_fake_curl(repo_root, this_repo_root=self.this_repo_root)

            self.assertEqual(
                result.returncode,
                0,
                f"get-base.py failed for repo={repo_name} branch={branch_name}:\n"
                f"STDOUT:\n{result.stdout}\nSTDERR:\n{result.stderr}",
            )
            fixtures.assert_no_unresolved_merge_state(repo_root)

    def test_all_repo_and_branch_variant_combinations_run_cleanly(self) -> None:
        # The combinations only spawn `git`/`get-base.py` in their own temp repo, so they run concurrently.
        with ThreadPoolExecutor(max_workers=fixtures.E2E_WORKERS) as pool:
            futures = {
                (repo_name, branch_name): pool.submit(
                    self.run_combination, repo_name, repo_builder, branch_name, branch_applier
                )
                for repo_name, repo_builder in fixtures.REPO_VARIANTS
                for branch_name, branch_applier in fixtures.BRANCH_VARIANTS
            }
        for (repo_name, branch_name), future in futures.items():
            with self.subTest(repo=repo_name, branch=branch_name):
                future.result()


if __name__ == "__main__":
    unittest.main()
