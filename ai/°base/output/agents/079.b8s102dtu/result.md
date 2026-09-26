FAIL: test_remove_flag_deletes_tags_in_parent_history (test_tag_backup.TagBackupTests.test_remove_flag_deletes_tags_in_parent_history)
----------------------------------------------------------------------
Traceback (most recent call last):
  File "/home/user/git/luckydonald/base/scripts/°base/tests/test_tag_backup.py", line 58, in test_remove_flag_deletes_tags_in_parent_history
    self.assertNotIn("old-backup", git(["tag"], self.repo).splitlines())
    ~~~~~~~~~~~~~~~~^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
AssertionError: 'old-backup' unexpectedly found in ['bak/74e9eef0557b46dd8108d353e057ec74c95d4947', 'old-backup']

----------------------------------------------------------------------
Ran 708 tests in 527.309s

FAILED (failures=9, errors=2, skipped=2)
/tmp/tmpkri96uay/repo/sub/ai/.env is already linked to /tmp/tmpkri96uay/repo/ai/.env but not committed — committing.
committed /tmp/tmpkri96uay/repo/sub/ai/.env as b67e3dde9801d1412effdb6555df829fb4f4c17a
touched /tmp/tmpjh23icey/repo/ai/.env
linked /tmp/tmpjh23icey/repo/sub/ai/.env -> ../../ai/.env
committed /tmp/tmpjh23icey/repo/sub/ai/.env as b67e3dde9801d1412effdb6555df829fb4f4c17a
touched /tmp/tmpid5sd41x/repo/ai/.env
linked /tmp/tmpid5sd41x/repo/sub/ai/.env -> ../../ai/.env
touched /tmp/tmp_mb40gos/repo/ai/.env
touched /tmp/tmpsfpq6r9x/repo/ai/.env
linked /tmp/tmpsfpq6r9x/repo/sub/ai/.env -> ../../ai/.env
committed /tmp/tmpsfpq6r9x/repo/sub/ai/.env as b67e3dde9801d1412effdb6555df829fb4f4c17a
/tmp/tmpsfpq6r9x/repo/sub/ai/.env already linked to /tmp/tmpsfpq6r9x/repo/ai/.env and committed.
touched /tmp/tmparoj75iu/repo/ai/.env
Rebasing onto merge-base abc123 with origin/mane, stripping AI attribution...
Rebasing onto merge-base abc123 with origin/mane, stripping AI attribution...
Checking for parent commits having older backup tags…
Found old backup tag: 'old-backup'
Tag cleanup done.

[exited with code 0]
