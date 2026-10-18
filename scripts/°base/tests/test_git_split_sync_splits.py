from __future__ import annotations

import importlib
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _git_test_helpers import git, init_repo, make_commit  # noqa: E402

LIB_ROOT = Path(__file__).resolve().parents[1] / "git"
sys.path.insert(0, str(LIB_ROOT))

branches = importlib.import_module("°split_lib.branches")
classify = importlib.import_module("°split_lib.classify")
git_ops = importlib.import_module("°split_lib.git_ops")
trailers = importlib.import_module("°split_lib.trailers")
sync_splits = importlib.import_module("°split_lib.sync_splits")
sync_unclean = importlib.import_module("°split_lib.sync_unclean")
bootstrap = importlib.import_module("°split_lib.bootstrap")
cli = importlib.import_module("°split_lib.cli")


class SyncSplitsTestBase(unittest.TestCase):
    def setUp(self):
        self._tmpdir = tempfile.TemporaryDirectory()
        self.repo = Path(self._tmpdir.name)
        init_repo(self.repo, branch="master")
        make_commit(self.repo, "README.md", "initial commit")
        make_commit(
            self.repo,
            ".ai-ignore",
            (Path(__file__).resolve().parents[3] / ".ai-ignore").read_text(encoding="utf-8"),
        )
        # Seed ai/history/master so history branches have a base to fork from.
        git(["branch", "ai/history/master"], self.repo)

    def tearDown(self):
        self._tmpdir.cleanup()

    def make_unclean(self, base_branch: str) -> None:
        unclean_ref = branches.unclean_name(base_branch)
        git(["checkout", "-b", unclean_ref], self.repo)

    def message_for(self, sha: str) -> str:
        return git_ops.commit_message(sha, self.repo)


class BasicClassificationSplitTests(SyncSplitsTestBase):
    def test_special_identity_config_sets_generated_commit_committer(self):
        git(["config", "base.split.name", "Configured Split Bot"], self.repo)
        git(["config", "base.split.email", "configured-split@example.com"], self.repo)
        self.make_unclean("feature/identity")
        make_commit(self.repo, "src/app.py", "add app code")

        sync_splits.sync_branch(
            "feature/identity", repo_root=self.repo, main_branch="master"
        )

        clean_tip = git_ops.rev_parse("feature/identity", self.repo)
        self.assertEqual(
            git(["log", "-1", "--format=%cn%x1f%ce", clean_tip], self.repo),
            "Configured Split Bot\x1fconfigured-split@example.com",
        )
    # end def

    def test_pure_code_commit_lands_on_clean_only(self):
        self.make_unclean("feature/x")
        code_sha = make_commit(self.repo, "src/app.py", "add app code")

        result = sync_splits.sync_branch(
            "feature/x", repo_root=self.repo, main_branch="master"
        )

        self.assertEqual(result.clean_commits_created, 1)
        self.assertEqual(result.clean_commits_skipped_ai_only, 0)
        self.assertEqual(result.history_commits_created, 1)

        clean_tip = git_ops.rev_parse("feature/x", self.repo)
        history_tip = git_ops.rev_parse(branches.history_name("feature/x"), self.repo)

        clean_paths = git(["ls-tree", "-r", "--name-only", clean_tip], self.repo).splitlines()
        history_paths = git(["ls-tree", "-r", "--name-only", history_tip], self.repo).splitlines()

        self.assertIn("src/app.py", clean_paths)
        self.assertNotIn("src/app.py", history_paths)

        clean_trailers = trailers.read_trailers(self.message_for(clean_tip), self.repo)
        self.assertFalse(any(key.startswith("X-Base-") for key in clean_trailers))

        history_trailers = trailers.read_trailers(self.message_for(history_tip), self.repo)
        self.assertEqual(history_trailers[sync_splits.SOURCE_TRAILER], [code_sha])
        self.assertEqual(history_trailers[sync_splits.KIND_TRAILER], ["code"])
        # code commit's clean counterpart tree should be recorded.
        self.assertIn(sync_splits.COUNTERPART_TREE_TRAILER, history_trailers)

    def test_pure_ai_commit_lands_on_history_only(self):
        self.make_unclean("feature/y")
        ai_sha = make_commit(self.repo, "ai/notes.md", "ai: jot down notes")

        result = sync_splits.sync_branch(
            "feature/y", repo_root=self.repo, main_branch="master"
        )

        self.assertEqual(result.clean_commits_created, 0)
        self.assertEqual(result.clean_commits_skipped_ai_only, 1)
        self.assertEqual(result.history_commits_created, 1)

        clean_tip = git_ops.rev_parse("feature/y", self.repo)
        main_tip = git_ops.rev_parse("master", self.repo)
        self.assertEqual(clean_tip, main_tip)

        history_tip = git_ops.rev_parse(branches.history_name("feature/y"), self.repo)
        history_paths = git(["ls-tree", "-r", "--name-only", history_tip], self.repo).splitlines()
        self.assertIn("ai/notes.md", history_paths)

        history_trailers = trailers.read_trailers(self.message_for(history_tip), self.repo)
        self.assertEqual(history_trailers[sync_splits.SOURCE_TRAILER], [ai_sha])
        self.assertEqual(history_trailers[sync_splits.KIND_TRAILER], ["history"])
        # No clean counterpart was created for a pure-ai commit.
        self.assertNotIn(sync_splits.COUNTERPART_TREE_TRAILER, history_trailers)

    def test_mixed_commit_splits_into_both_trees(self):
        self.make_unclean("feature/z")
        mixed_sha = self._make_mixed_commit()

        result = sync_splits.sync_branch(
            "feature/z", repo_root=self.repo, main_branch="master"
        )

        self.assertEqual(result.clean_commits_created, 1)
        self.assertEqual(result.history_commits_created, 1)

        clean_tip = git_ops.rev_parse("feature/z", self.repo)
        history_tip = git_ops.rev_parse(branches.history_name("feature/z"), self.repo)

        clean_paths = set(git(["ls-tree", "-r", "--name-only", clean_tip], self.repo).splitlines())
        history_paths = set(git(["ls-tree", "-r", "--name-only", history_tip], self.repo).splitlines())

        self.assertIn("src/mixed.py", clean_paths)
        self.assertNotIn("ai/mixed_notes.md", clean_paths)
        self.assertIn("ai/mixed_notes.md", history_paths)
        self.assertNotIn("src/mixed.py", history_paths)

        clean_trailers = trailers.read_trailers(self.message_for(clean_tip), self.repo)
        history_trailers = trailers.read_trailers(self.message_for(history_tip), self.repo)
        self.assertFalse(any(key.startswith("X-Base-") for key in clean_trailers))
        self.assertEqual(history_trailers[sync_splits.KIND_TRAILER], ["mixed"])
        self.assertEqual(history_trailers[sync_splits.SOURCE_TRAILER], [mixed_sha])
        self.assertIn(sync_splits.COUNTERPART_TREE_TRAILER, history_trailers)

        clean_tree = git_ops.tree_for_commit(clean_tip, self.repo)
        self.assertEqual(history_trailers[sync_splits.COUNTERPART_TREE_TRAILER], [clean_tree])

    def _make_mixed_commit(self) -> str:
        (self.repo / "src").mkdir(parents=True, exist_ok=True)
        (self.repo / "ai").mkdir(parents=True, exist_ok=True)
        (self.repo / "src" / "mixed.py").write_text("print('mixed')")
        (self.repo / "ai" / "mixed_notes.md").write_text("notes")
        git(["add", "src/mixed.py", "ai/mixed_notes.md"], self.repo)
        git(["commit", "-m", "ai: add mixed feature with notes"], self.repo)
        return git(["rev-parse", "HEAD"], self.repo)


class RenameBoundaryTests(SyncSplitsTestBase):
    def test_rename_crossing_boundary(self):
        self.make_unclean("feature/rename")
        make_commit(self.repo, "ai/scratch.md", "ai: scratch notes")

        (self.repo / "src").mkdir(parents=True, exist_ok=True)
        git(["mv", "ai/scratch.md", "src/scratch.py"], self.repo)
        git(["commit", "-m", "move scratch notes into code"], self.repo)

        result = sync_splits.sync_branch(
            "feature/rename", repo_root=self.repo, main_branch="master"
        )

        self.assertEqual(result.clean_commits_created, 1)
        self.assertEqual(result.history_commits_created, 2)

        clean_tip = git_ops.rev_parse("feature/rename", self.repo)
        history_tip = git_ops.rev_parse(branches.history_name("feature/rename"), self.repo)

        clean_paths = set(git(["ls-tree", "-r", "--name-only", clean_tip], self.repo).splitlines())
        history_paths = set(git(["ls-tree", "-r", "--name-only", history_tip], self.repo).splitlines())

        self.assertIn("src/scratch.py", clean_paths)
        self.assertNotIn("ai/scratch.md", clean_paths)
        self.assertNotIn("src/scratch.py", history_paths)
        self.assertNotIn("ai/scratch.md", history_paths)


class FreshBranchCreationTests(SyncSplitsTestBase):
    def test_fresh_branch_parents(self):
        main_tip = git_ops.rev_parse("master", self.repo)
        history_master_tip = git_ops.rev_parse(branches.history_name("master"), self.repo)

        self.make_unclean("feature/fresh")
        make_commit(self.repo, "src/one.py", "add one")

        sync_splits.sync_branch("feature/fresh", repo_root=self.repo, main_branch="master")

        clean_first = git(
            ["log", "--reverse", "--format=%H", "master..feature/fresh"], self.repo
        ).splitlines()[0]
        clean_first_parent = git(["rev-parse", f"{clean_first}^"], self.repo)
        self.assertEqual(clean_first_parent, main_tip)

        history_ref = branches.history_name("feature/fresh")
        history_first = git(
            [
                "log",
                "--reverse",
                "--format=%H",
                f"{branches.history_name('master')}..{history_ref}",
            ],
            self.repo,
        ).splitlines()[0]
        history_first_parent = git(["rev-parse", f"{history_first}^"], self.repo)
        self.assertEqual(history_first_parent, history_master_tip)

    def test_fresh_history_branch_writes_fork_point_ref(self):
        history_master_tip = git_ops.rev_parse(branches.history_name("master"), self.repo)

        self.make_unclean("feature/fresh")
        make_commit(self.repo, "src/one.py", "add one")

        sync_splits.sync_branch("feature/fresh", repo_root=self.repo, main_branch="master")

        fork_point = git_ops.rev_parse(branches.history_fork_point_ref("feature/fresh"), self.repo)
        self.assertEqual(fork_point, history_master_tip)

    def test_fork_point_ref_not_rewritten_when_history_already_exists(self):
        self.make_unclean("feature/fresh")
        make_commit(self.repo, "src/one.py", "add one")
        sync_splits.sync_branch("feature/fresh", repo_root=self.repo, main_branch="master")

        fork_point_ref = branches.history_fork_point_ref("feature/fresh")
        original_fork_point = git_ops.rev_parse(fork_point_ref, self.repo)

        git(["checkout", branches.unclean_name("feature/fresh")], self.repo)
        make_commit(self.repo, "src/two.py", "add two")
        sync_splits.sync_branch("feature/fresh", repo_root=self.repo, main_branch="master")

        self.assertEqual(git_ops.rev_parse(fork_point_ref, self.repo), original_fork_point)


class IdempotentReRunTests(SyncSplitsTestBase):
    def test_second_run_only_adds_new_commit(self):
        self.make_unclean("feature/incr")
        make_commit(self.repo, "src/one.py", "add one")

        first = sync_splits.sync_branch(
            "feature/incr", repo_root=self.repo, main_branch="master"
        )
        self.assertEqual(first.clean_commits_created, 1)
        self.assertEqual(first.history_commits_created, 1)

        clean_tip_after_first = git_ops.rev_parse("feature/incr", self.repo)

        second_noop = sync_splits.sync_branch(
            "feature/incr", repo_root=self.repo, main_branch="master"
        )
        self.assertEqual(second_noop.clean_commits_created, 0)
        self.assertEqual(second_noop.history_commits_created, 0)
        self.assertEqual(git_ops.rev_parse("feature/incr", self.repo), clean_tip_after_first)

        git(["checkout", branches.unclean_name("feature/incr")], self.repo)
        make_commit(self.repo, "src/two.py", "add two")
        git(["checkout", "master"], self.repo)

        third = sync_splits.sync_branch(
            "feature/incr", repo_root=self.repo, main_branch="master"
        )
        self.assertEqual(third.clean_commits_created, 1)
        self.assertEqual(third.history_commits_created, 1)

        clean_log = git(["log", "--format=%H", "master..feature/incr"], self.repo).splitlines()
        self.assertEqual(len(clean_log), 2)


class AllAiOnlyBranchTests(SyncSplitsTestBase):
    def test_all_ai_only_branch_clean_created_but_empty(self):
        main_tip = git_ops.rev_parse("master", self.repo)

        self.make_unclean("feature/ai-only")
        make_commit(self.repo, "ai/one.md", "ai: one")
        make_commit(self.repo, "ai/two.md", "ai: two")

        result = sync_splits.sync_branch(
            "feature/ai-only", repo_root=self.repo, main_branch="master"
        )

        self.assertEqual(result.clean_commits_created, 0)
        self.assertEqual(result.clean_commits_skipped_ai_only, 2)
        self.assertEqual(result.history_commits_created, 2)

        clean_tip = git_ops.rev_parse("feature/ai-only", self.repo)
        self.assertIsNotNone(clean_tip)
        self.assertEqual(clean_tip, main_tip)


class EmptyUncleanCommitTests(SyncSplitsTestBase):
    def test_empty_unclean_commits_do_not_create_clean_commits(self):
        self.make_unclean("feature/empty-provenance")
        git(["commit", "--allow-empty", "-m", "ai: actually call apis instead of the mock."], self.repo)
        git(
            [
                "commit",
                "--allow-empty",
                "-m",
                'Revert "ai: Attempt to fix the expander being in both rows somehow."',
            ],
            self.repo,
        )
        code_sha = make_commit(self.repo, "src/widget.py", "add widget refresh")

        result = sync_splits.sync_branch(
            "feature/empty-provenance", repo_root=self.repo, main_branch="master"
        )

        self.assertEqual(result.clean_commits_created, 1)
        self.assertEqual(result.clean_commits_skipped_noop, 2)
        self.assertEqual(result.history_commits_created, 3)
        clean_shas = git(
            ["log", "--reverse", "--format=%H", "master..feature/empty-provenance"], self.repo
        ).splitlines()
        self.assertEqual(len(clean_shas), 1)
        clean_message = self.message_for(clean_shas[0])
        self.assertFalse(any(key.startswith("X-Base-") for key in trailers.read_trailers(clean_message, self.repo)))

        history_shas = git(
            ["log", "--reverse", "--format=%H", "ai/history/master..ai/history/feature/empty-provenance"],
            self.repo,
        ).splitlines()
        self.assertEqual(len(history_shas), 3)
        self.assertEqual(
            trailers.read_trailer_value(self.message_for(history_shas[-1]), sync_splits.SOURCE_TRAILER, self.repo),
            code_sha,
        )

        rerun = sync_splits.sync_branch(
            "feature/empty-provenance", repo_root=self.repo, main_branch="master"
        )
        self.assertEqual(rerun.clean_commits_created, 0)
        self.assertEqual(rerun.history_commits_created, 0)
    # end def
# end class


class DryRunTests(SyncSplitsTestBase):
    def test_dry_run_makes_no_ref_changes(self):
        self.make_unclean("feature/dry")
        make_commit(self.repo, "src/one.py", "add one")
        make_commit(self.repo, "ai/notes.md", "ai: notes")

        before_refs = set(
            git(["for-each-ref", "--format=%(refname)"], self.repo).splitlines()
        )

        result = sync_splits.sync_branch(
            "feature/dry", repo_root=self.repo, main_branch="master", dry_run=True
        )

        after_refs = set(
            git(["for-each-ref", "--format=%(refname)"], self.repo).splitlines()
        )

        self.assertEqual(before_refs, after_refs)
        self.assertEqual(result.clean_commits_created, 1)
        self.assertEqual(result.history_commits_created, 2)
        self.assertEqual(result.clean_commits_skipped_ai_only, 1)


class ReconstructionCursorFallbackTests(SyncSplitsTestBase):
    def test_find_reconstruction_correlated_cursor_finds_newest_match(self):
        git(["checkout", "-b", "feature/clean-only"], self.repo)
        make_commit(self.repo, "src/one.py", "add one")
        clean_tip = git(["rev-parse", "HEAD"], self.repo)
        git(["checkout", "master"], self.repo)

        git(["checkout", "-b", branches.unclean_name("feature/clean-only")], self.repo)
        message = trailers.write_trailers(
            "reconstructed commit\n", {sync_unclean.RECON_TRAILER: clean_tip}, self.repo
        )
        msg_file = self.repo / ".commitmsg-tmp"
        msg_file.write_text(message)
        try:
            git(["commit", "--allow-empty", "-F", str(msg_file)], self.repo)
        finally:
            msg_file.unlink(missing_ok=True)
        unclean_sha = git(["rev-parse", "HEAD"], self.repo)
        git(["checkout", "master"], self.repo)

        cursor = sync_splits.find_reconstruction_correlated_cursor(
            branches.unclean_name("feature/clean-only"), "feature/clean-only", self.repo
        )
        self.assertEqual(cursor, unclean_sha)

    def test_find_reconstruction_correlated_cursor_returns_none_when_no_match(self):
        self.make_unclean("feature/fresh2")
        make_commit(self.repo, "src/one.py", "add one")

        cursor = sync_splits.find_reconstruction_correlated_cursor(
            branches.unclean_name("feature/fresh2"), "master", self.repo
        )
        self.assertIsNone(cursor)


class BootstrapThenForwardSyncTests(SyncSplitsTestBase):
    def test_forward_sync_after_bootstrap_reconstruction_does_not_duplicate(self):
        git(["checkout", "-b", "feature/clean-only"], self.repo)
        make_commit(self.repo, "src/one.py", "add one")
        make_commit(self.repo, "src/two.py", "add two")
        git(["checkout", "master"], self.repo)

        clean_commit_count_before = int(
            git(["rev-list", "--count", "master..feature/clean-only"], self.repo)
        )

        result = bootstrap.bootstrap_branch(
            "feature/clean-only", repo_root=self.repo, main_branch="master"
        )
        self.assertTrue(result["ok"])

        sync_splits.sync_branch("feature/clean-only", repo_root=self.repo, main_branch="master")

        clean_commit_count_after = int(
            git(["rev-list", "--count", "master..feature/clean-only"], self.repo)
        )
        self.assertEqual(clean_commit_count_after, clean_commit_count_before)


class DiscoverUncleanBranchesTests(SyncSplitsTestBase):
    def test_discover_unclean_branches(self):
        self.make_unclean("feature/one")
        make_commit(self.repo, "src/a.py", "a")
        git(["checkout", "master"], self.repo)
        git(["checkout", "-b", branches.unclean_name("feature/two")], self.repo)
        make_commit(self.repo, "src/b.py", "b")
        git(["checkout", "master"], self.repo)

        found = sorted(sync_splits.discover_unclean_branches(self.repo))
        self.assertEqual(found, ["feature/one", "feature/two"])


class UncleanMergeDetectionTests(SyncSplitsTestBase):
    """A merge commit landing directly on ai/UNCLEAN/* (e.g. someone merges
    base/base straight into it, which is allowed there) must never be
    silently unrolled into its second parent's whole ancestry -- it must be
    detected and handed to the caller to decide how to resolve.
    """

    def _make_merge_commit_on_unclean(self, base_branch: str, *, side_files: dict[str, str]) -> tuple[str, str]:
        self.make_unclean(base_branch)
        make_commit(self.repo, "src/app.py", "add app code")

        git(["checkout", "master"], self.repo)
        git(["checkout", "-b", "side-branch"], self.repo)
        for filename, content in side_files.items():
            make_commit(self.repo, filename, f"side: add {filename}", content=content)
        second_parent_sha = git(["rev-parse", "HEAD"], self.repo)

        git(["checkout", branches.unclean_name(base_branch)], self.repo)
        git(["merge", "--no-ff", "--no-edit", "side-branch"], self.repo)
        merge_sha = git(["rev-parse", "HEAD"], self.repo)
        return merge_sha, second_parent_sha

    def test_merge_commit_raises_instead_of_unrolling_ancestry(self):
        merge_sha, second_parent_sha = self._make_merge_commit_on_unclean(
            "feature/x", side_files={"docs/extra.txt": "hi\n"}
        )

        with self.assertRaises(sync_splits.UncleanMergeDetected) as ctx:
            sync_splits.sync_branch("feature/x", repo_root=self.repo, main_branch="master")

        self.assertEqual(ctx.exception.sha, merge_sha)
        self.assertEqual(ctx.exception.target, "clean")
        self.assertIn(second_parent_sha, ctx.exception.parents)

        # The one ordinary code commit before the merge should have landed
        # (partial progress preserved), but nothing from the merge itself --
        # in particular, none of second_parent_sha's own ancestry should
        # have been unrolled/treated as standalone commits.
        clean_tip = git_ops.rev_parse("feature/x", self.repo)
        clean_trailers = trailers.read_trailers(self.message_for(clean_tip), self.repo)
        self.assertFalse(any(key.startswith("X-Base-") for key in clean_trailers))

    def test_fake_merges_flattens_merge_into_a_single_parent_commit(self):
        merge_sha, second_parent_sha = self._make_merge_commit_on_unclean(
            "feature/x", side_files={"docs/extra.txt": "hi\n"}
        )

        result = sync_splits.sync_branch(
            "feature/x", repo_root=self.repo, main_branch="master", fake_merges=True
        )
        self.assertGreater(result.clean_commits_created, 0)

        clean_tip = git_ops.rev_parse("feature/x", self.repo)
        parents = git_ops.parents_of(clean_tip, self.repo)
        self.assertEqual(len(parents), 1, "fake-merge commit must be single-parent, not a real merge")

        clean_trailers = trailers.read_trailers(self.message_for(clean_tip), self.repo)
        self.assertFalse(any(key.startswith("X-Base-") for key in clean_trailers))

        clean_paths = git(["ls-tree", "-r", "--name-only", clean_tip], self.repo).splitlines()
        self.assertIn("docs/extra.txt", clean_paths)


class BuildFilteredMergeCommitTests(SyncSplitsTestBase):
    def test_real_merge_auto_resolves_readme_conflict(self):
        shared_sha = git(["rev-parse", "master"], self.repo)

        # clean_onto: consumer's own change to README.md, diverging from
        # shared_sha.
        git(["checkout", "-b", "feature/x"], self.repo)
        make_commit(self.repo, "README.md", "consumer readme change", content="consumer readme\n")
        clean_onto = git(["rev-parse", "HEAD"], self.repo)

        # side-branch: an independent change to the SAME path, also
        # diverging from shared_sha -- guarantees a real README.md conflict.
        git(["checkout", shared_sha], self.repo)
        git(["checkout", "-b", "side-branch"], self.repo)
        make_commit(self.repo, "README.md", "side readme change", content="side readme\n")
        make_commit(self.repo, "src/feature.py", "side: add feature code")
        second_parent_tip = git(["rev-parse", "HEAD"], self.repo)

        new_sha = sync_splits.build_filtered_merge_commit(
            clean_onto,
            second_parent_tip,
            second_parent_tip,
            "mixed",
            keep=lambda p: not classify.is_ai_base_path(p),
            cwd=self.repo,
        )

        self.assertIsNotNone(new_sha)
        parents = git_ops.parents_of(new_sha, self.repo)
        self.assertEqual(set(parents), {clean_onto, second_parent_tip})

        readme = git_ops.show_path_at(new_sha, "README.md", self.repo).decode()
        self.assertEqual(readme, "side readme\n")

        # The checkout must be restored to whatever was checked out before.
        self.assertEqual(git(["branch", "--show-current"], self.repo), "side-branch")

    def test_real_merge_returns_none_on_genuine_conflict(self):
        shared_sha = git(["rev-parse", "master"], self.repo)

        git(["checkout", "-b", "feature/x"], self.repo)
        make_commit(self.repo, "shared.txt", "consumer shared", content="consumer version\n")
        clean_onto = git(["rev-parse", "HEAD"], self.repo)

        git(["checkout", shared_sha], self.repo)
        git(["checkout", "-b", "side-branch"], self.repo)
        make_commit(self.repo, "shared.txt", "side shared", content="side version\n")
        second_parent_sha = git(["rev-parse", "HEAD"], self.repo)

        new_sha = sync_splits.build_filtered_merge_commit(
            clean_onto,
            second_parent_sha,
            second_parent_sha,
            "mixed",
            keep=lambda p: not classify.is_ai_base_path(p),
            cwd=self.repo,
        )

        self.assertIsNone(new_sha)
        # No merge should be left in progress, and the checkout restored.
        status = git(["status", "--porcelain"], self.repo)
        self.assertEqual(status, "")
        self.assertEqual(git(["branch", "--show-current"], self.repo), "side-branch")

    def test_real_merge_never_adopts_gitattributes_when_clean_side_has_matching_binaries(self):
        # Regression: .gitattributes must never come from the incoming
        # (second_parent) side if `onto`'s own history already has non-LFS
        # blobs for an extension it would newly filter -- even when the
        # merge is otherwise perfectly clean (no textual conflict at all,
        # since onto has no .gitattributes yet).
        shared_sha = git(["rev-parse", "master"], self.repo)

        git(["checkout", "-b", "feature/x"], self.repo)
        (self.repo / "logo.png").write_bytes(b"\x89PNG fake binary content")
        git(["add", "logo.png"], self.repo)
        git(["commit", "-m", "add logo"], self.repo)
        clean_onto = git(["rev-parse", "HEAD"], self.repo)

        git(["checkout", shared_sha], self.repo)
        git(["checkout", "-b", "side-branch"], self.repo)
        make_commit(
            self.repo,
            ".gitattributes",
            "side gitattributes",
            content="*.png filter=lfs diff=lfs merge=lfs -text\n",
        )
        second_parent_sha = git(["rev-parse", "HEAD"], self.repo)

        new_sha = sync_splits.build_filtered_merge_commit(
            clean_onto,
            second_parent_sha,
            second_parent_sha,
            "mixed",
            keep=lambda p: not classify.is_ai_base_path(p),
            cwd=self.repo,
        )

        self.assertIsNotNone(new_sha)
        entry = git_ops.ls_tree_entry(new_sha, ".gitattributes", self.repo)
        self.assertIsNone(entry, "clean_onto never had .gitattributes and has a matching binary -- must stay absent")


class UncleanMergeCliFlagTests(SyncSplitsTestBase):
    """End-to-end coverage of the non-interactive `--unclean-merge` flag
    (the interactive a/b/c menu itself needs a simulated tty/input() and is
    covered at the sync_splits.py unit level above instead)."""

    def _make_merge_commit_on_unclean(self, base_branch: str, *, side_files: dict[str, str]) -> str:
        self.make_unclean(base_branch)
        make_commit(self.repo, "src/app.py", "add app code")

        git(["checkout", "master"], self.repo)
        git(["checkout", "-b", "side-branch"], self.repo)
        for filename, content in side_files.items():
            make_commit(self.repo, filename, f"side: add {filename}", content=content)

        git(["checkout", branches.unclean_name(base_branch)], self.repo)
        git(["merge", "--no-ff", "--no-edit", "side-branch"], self.repo)
        return git(["rev-parse", "HEAD"], self.repo)

    def test_unclean_merge_fake_flag_completes_the_sync(self):
        self._make_merge_commit_on_unclean("feature/x", side_files={"docs/extra.txt": "hi\n"})

        code = cli.main([
            "--repo-root", str(self.repo),
            "sync-splits", "feature/x", "--direction=to-clean-history", "--unclean-merge=fake",
        ])
        self.assertEqual(code, 0)

        clean_tip = git_ops.rev_parse("feature/x", self.repo)
        self.assertEqual(len(git_ops.parents_of(clean_tip, self.repo)), 1)
        clean_paths = git(["ls-tree", "-r", "--name-only", clean_tip], self.repo).splitlines()
        self.assertIn("docs/extra.txt", clean_paths)

    def test_unclean_merge_abort_flag_leaves_partial_progress_and_fails(self):
        self._make_merge_commit_on_unclean("feature/x", side_files={"docs/extra.txt": "hi\n"})

        code = cli.main([
            "--repo-root", str(self.repo),
            "sync-splits", "feature/x", "--direction=to-clean-history", "--unclean-merge=abort",
        ])
        self.assertEqual(code, 1)

        # The code commit before the merge should still have landed.
        clean_tip = git_ops.rev_parse("feature/x", self.repo)
        clean_paths = git(["ls-tree", "-r", "--name-only", clean_tip], self.repo).splitlines()
        self.assertIn("src/app.py", clean_paths)
        self.assertNotIn("docs/extra.txt", clean_paths)


if __name__ == "__main__":
    unittest.main()
