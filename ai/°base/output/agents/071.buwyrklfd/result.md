            text=True,
        )
        if result.returncode != 0:
>           raise AssertionError(
                f"hook failed with {result.returncode}\nstdout:\n{result.stdout}\nstderr:\n{result.stderr}"
            )
E           AssertionError: hook failed with 1
E           stdout:
E           
E           stderr:
E           Traceback (most recent call last):
E             File "/home/user/git/luckydonald/base/scripts/°base/ai/hooks/save-decision/hook.py", line 16, in <module>
E               from pydantic import BaseModel, StrictBool, StrictInt, computed_field
E           ModuleNotFoundError: No module named 'pydantic'

scripts/°base/tests/test_ai_hooks_base_routing.py:77: AssertionError
________ TagBackupTests.test_remove_flag_deletes_tags_in_parent_history ________

self = <tests.test_tag_backup.TagBackupTests testMethod=test_remove_flag_deletes_tags_in_parent_history>

    def test_remove_flag_deletes_tags_in_parent_history(self) -> None:
        git(["tag", "old-backup", self.parent], self.repo)
    
        result = self.run_script("--rm")
    
        self.assertEqual(result.returncode, 0, result.stderr)
>       self.assertNotIn("old-backup", git(["tag"], self.repo).splitlines())
E       AssertionError: 'old-backup' unexpectedly found in ['bak/f2cfe1e59c7480b20cef71d836574677760ca98c', 'old-backup']

scripts/°base/tests/test_tag_backup.py:58: AssertionError
=========================== short test summary info ============================
FAILED scripts/°base/tests/test_save_decision_pending.py::PendingDecisionTests::test_post_tool_use_deletes_marker_and_renders_answered
FAILED scripts/°base/tests/test_save_decision_pending.py::PendingDecisionTests::test_pre_tool_use_writes_marker_without_touching_query_md
FAILED scripts/°base/tests/test_save_decision_pending.py::PendingDecisionTests::test_stop_is_a_noop_when_nothing_pending
FAILED scripts/°base/tests/test_save_decision_pending.py::PendingDecisionTests::test_stop_sweeps_leftover_marker_as_canceled
FAILED scripts/°base/tests/test_save_decision_pending.py::ConcurrentSessionTests::test_distinct_sessions_get_distinct_markers
FAILED scripts/°base/tests/test_save_decision_pending.py::ConcurrentSessionTests::test_own_session_stop_does_not_sweep_other_sessions_fresh_marker
FAILED scripts/°base/tests/test_save_decision_pending.py::ConcurrentSessionTests::test_stale_marker_from_a_different_session_is_swept_as_orphan
FAILED scripts/°base/tests/test_tag_backup.py::TagBackupTests::test_remove_flag_deletes_tags_in_parent_history
8 failed, 628 passed, 15 skipped, 100 subtests passed in 689.23s (0:11:29)

[exited with code 0]
