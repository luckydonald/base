AssertionError: True is not false

======================================================================
FAIL: test_remove_flag_deletes_tags_in_parent_history (test_tag_backup.TagBackupTests.test_remove_flag_deletes_tags_in_parent_history)
----------------------------------------------------------------------
Traceback (most recent call last):
  File "/home/user/git/luckydonald/base/.claude/worktrees/fix-plan-decision/scripts/°base/tests/test_tag_backup.py", line 58, in test_remove_flag_deletes_tags_in_parent_history
    self.assertNotIn("old-backup", git(["tag"], self.repo).splitlines())
    ~~~~~~~~~~~~~~~~^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
AssertionError: 'old-backup' unexpectedly found in ['bak/dff3d64ffabdefdcffdba11ef33934f6b01c61df', 'old-backup']

----------------------------------------------------------------------
Ran 686 tests in 554.463s

FAILED (failures=9, errors=2, skipped=15)
Rebasing onto merge-base abc123 with origin/mane, stripping AI attribution...
Rebasing onto merge-base abc123 with origin/mane, stripping AI attribution...
Checking for parent commits having older backup tags…
Found old backup tag: 'old-backup'
Tag cleanup done.

[exited with code 0]
