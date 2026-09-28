…
----------------------------------------------
Traceback (most recent call last):
  File "/home/user/git/luckydonald/base/.claude/worktrees/fix-plan-decision/scripts/°base/tests/test_ai_hooks_base_routing.py", line 1223, in test_memory_session_start_does_not_resurrect_marked_deleted_memory
    self.assertFalse(src_file.exists())
    ~~~~~~~~~~~~~~~~^^^^^^^^^^^^^^^^^^^
AssertionError: True is not false

======================================================================
FAIL: test_record_memory_honors_override_and_keeps_dynamic_slug (test_commit_style_lib.CommitStyleLibOverrideTests.test_record_memory_honors_override_and_keeps_dynamic_slug)
----------------------------------------------------------------------
Traceback (most recent call last):
  File "/home/user/git/luckydonald/base/.claude/worktrees/fix-plan-decision/scripts/°base/tests/test_commit_style_lib.py", line 192, in test_record_memory_honors_override_and_keeps_dynamic_slug
    self.assertEqual(last_subject(repo), "🧠 ai: record memory note")
    ~~~~~~~~~~~~~~~~^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
AssertionError: 'init' != '🧠 ai: record memory note'
- init
+ 🧠 ai: record memory note


======================================================================
FAIL: test_delete_helper_removes_repo_and_source_and_formats_commit (test_memory_delete.MemoryDeleteTests.test_delete_helper_removes_repo_and_source_and_formats_commit)
----------------------------------------------------------------------
Traceback (most recent call last):
  File "/home/user/git/luckydonald/base/.claude/worktrees/fix-plan-decision/scripts/°base/tests/test_memory_delete.py", line 127, in test_delete_helper_removes_repo_and_source_and_formats_commit
    self.assertFalse(src.exists())
    ~~~~~~~~~~~~~~~~^^^^^^^^^^^^^^
AssertionError: True is not false

======================================================================
FAIL: test_remove_flag_deletes_tags_in_parent_history (test_tag_backup.TagBackupTests.test_remove_flag_deletes_tags_in_parent_history)
----------------------------------------------------------------------
Traceback (most recent call last):
  File "/home/user/git/luckydonald/base/.claude/worktrees/fix-plan-decision/scripts/°base/tests/test_tag_backup.py", line 58, in test_remove_flag_deletes_tags_in_parent_history
    self.assertNotIn("old-backup", git(["tag"], self.repo).splitlines())
    ~~~~~~~~~~~~~~~~^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
AssertionError: 'old-backup' unexpectedly found in ['bak/4e49bcf2786733d13d6ee65fbccca3aa60f4e586', 'old-backup']

----------------------------------------------------------------------
Ran 691 tests in 807.029s

FAILED (failures=9, errors=2, skipped=15)
Rebasing onto merge-base abc123 with origin/mane, stripping AI attribution...
Rebasing onto merge-base abc123 with origin/mane, stripping AI attribution...
Checking for parent commits having older backup tags…
Found old backup tag: 'old-backup'
Tag cleanup done.

[exited with code 0]
