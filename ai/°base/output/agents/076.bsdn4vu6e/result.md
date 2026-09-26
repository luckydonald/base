E           AssertionError: True is not false

scripts/°base/tests/test_memory_delete.py:127: AssertionError
________ TagBackupTests.test_remove_flag_deletes_tags_in_parent_history ________

self = <tests.test_tag_backup.TagBackupTests testMethod=test_remove_flag_deletes_tags_in_parent_history>

    def test_remove_flag_deletes_tags_in_parent_history(self) -> None:
        git(["tag", "old-backup", self.parent], self.repo)
    
        result = self.run_script("--rm")
    
        self.assertEqual(result.returncode, 0, result.stderr)
>       self.assertNotIn("old-backup", git(["tag"], self.repo).splitlines())
E       AssertionError: 'old-backup' unexpectedly found in ['bak/fa9f4c85a655a5600e71c8e48aa97ed11653950f', 'old-backup']

scripts/°base/tests/test_tag_backup.py:58: AssertionError
=========================== short test summary info ============================
FAILED scripts/°base/tests/test_ai_hooks_base_routing.py::AiHooksBaseRoutingTests::test_memory_bash_rm_chained_command_still_detected
FAILED scripts/°base/tests/test_ai_hooks_base_routing.py::AiHooksBaseRoutingTests::test_memory_bash_rm_of_source_file_deletes_repo_mirror
FAILED scripts/°base/tests/test_ai_hooks_base_routing.py::AiHooksBaseRoutingTests::test_memory_in_base_repo_routes_and_prefixes
FAILED scripts/°base/tests/test_ai_hooks_base_routing.py::AiHooksBaseRoutingTests::test_memory_posttooluse_write_with_underscore_in_project_path
FAILED scripts/°base/tests/test_ai_hooks_base_routing.py::AiHooksBaseRoutingTests::test_memory_session_start_content_mismatch_repo_wins
FAILED scripts/°base/tests/test_ai_hooks_base_routing.py::AiHooksBaseRoutingTests::test_memory_session_start_does_not_resurrect_across_promoted_directory
FAILED scripts/°base/tests/test_ai_hooks_base_routing.py::AiHooksBaseRoutingTests::test_memory_session_start_does_not_resurrect_marked_deleted_memory
FAILED scripts/°base/tests/test_ai_hooks_base_routing.py::AiHooksBaseRoutingTests::test_memory_session_start_restores_missing_claude_source_from_repo
FAILED scripts/°base/tests/test_commit_style_lib.py::CommitStyleLibOverrideTests::test_record_memory_honors_override_and_keeps_dynamic_slug
FAILED scripts/°base/tests/test_memory_delete.py::MemoryDeleteTests::test_delete_helper_removes_repo_and_source_and_formats_commit
FAILED scripts/°base/tests/test_tag_backup.py::TagBackupTests::test_remove_flag_deletes_tags_in_parent_history
11 failed, 669 passed, 15 skipped, 102 subtests passed in 455.61s (0:07:35)

[exited with code 0]
