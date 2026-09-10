…
 
        result = self.run_script("--rm")
    
        self.assertEqual(result.returncode, 0, result.stderr)
>       self.assertNotIn("old-backup", git(["tag"], self.repo).splitlines())
E       AssertionError: 'old-backup' unexpectedly found in ['bak/525e97ff7599c35e9deefb4efc1b19abdaff9a0d', 'old-backup']

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
FAILED scripts/°base/tests/test_save_decision_pending.py::PendingDecisionTests::test_post_tool_use_deletes_marker_and_renders_answered
FAILED scripts/°base/tests/test_save_decision_pending.py::PendingDecisionTests::test_pre_tool_use_writes_marker_without_touching_query_md
FAILED scripts/°base/tests/test_save_decision_pending.py::PendingDecisionTests::test_stop_is_a_noop_when_nothing_pending
FAILED scripts/°base/tests/test_save_decision_pending.py::PendingDecisionTests::test_stop_sweeps_leftover_marker_as_canceled
FAILED scripts/°base/tests/test_save_decision_pending.py::ConcurrentSessionTests::test_distinct_sessions_get_distinct_markers
FAILED scripts/°base/tests/test_save_decision_pending.py::ConcurrentSessionTests::test_own_session_stop_does_not_sweep_other_sessions_fresh_marker
FAILED scripts/°base/tests/test_save_decision_pending.py::ConcurrentSessionTests::test_stale_marker_from_a_different_session_is_swept_as_orphan
FAILED scripts/°base/tests/test_tag_backup.py::TagBackupTests::test_remove_flag_deletes_tags_in_parent_history
18 failed, 585 passed, 15 skipped, 100 subtests passed in 641.70s (0:10:41)

[exited with code 0]
