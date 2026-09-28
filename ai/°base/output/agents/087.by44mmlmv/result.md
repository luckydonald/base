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
AssertionError: 'old-backup' unexpectedly found in ['bak/69ce0c03517dca64177b3824463a7b01179c27bc', 'old-backup']

----------------------------------------------------------------------
Ran 744 tests in 695.657s

FAILED (failures=9, errors=2, skipped=15)
/tmp/tmpdunnmf00/repo/sub/ai/.env is already linked to /tmp/tmpdunnmf00/repo/ai/.env but not committed — committing.
committed /tmp/tmpdunnmf00/repo/sub/ai/.env as 0261e97ddd0c3a7f9a35fbacf4e0de98936345a0
touched /tmp/tmpt_14biw5/repo/ai/.env
linked /tmp/tmpt_14biw5/repo/sub/ai/.env -> ../../ai/.env
committed /tmp/tmpt_14biw5/repo/sub/ai/.env as 5723a457de3eb97f96ed7077a58b3ae150dfd4ac
touched /tmp/tmp7nv_6z0g/repo/ai/.env
linked /tmp/tmp7nv_6z0g/repo/sub/ai/.env -> ../../ai/.env
touched /tmp/tmpw50s8fof/repo/ai/.env
touched /tmp/tmps6wro379/repo/ai/.env
linked /tmp/tmps6wro379/repo/sub/ai/.env -> ../../ai/.env
committed /tmp/tmps6wro379/repo/sub/ai/.env as 5723a457de3eb97f96ed7077a58b3ae150dfd4ac
/tmp/tmps6wro379/repo/sub/ai/.env already linked to /tmp/tmps6wro379/repo/ai/.env and committed.
touched /tmp/tmpkgo_5tsm/repo/ai/.env
Rebasing onto merge-base abc123 with origin/mane, stripping AI attribution...
Rebasing onto merge-base abc123 with origin/mane, stripping AI attribution...
Checking for parent commits having older backup tags…
Found old backup tag: 'old-backup'
Tag cleanup done.

[exited with code 0]
