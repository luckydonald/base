EXIT:1
FAIL: test_remove_flag_deletes_tags_in_parent_history (test_tag_backup.TagBackupTests.test_remove_flag_deletes_tags_in_parent_history)
----------------------------------------------------------------------
Traceback (most recent call last):
  File "/home/user/git/luckydonald/base/scripts/°base/tests/test_tag_backup.py", line 58, in test_remove_flag_deletes_tags_in_parent_history
    self.assertNotIn("old-backup", git(["tag"], self.repo).splitlines())
    ~~~~~~~~~~~~~~~~^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
AssertionError: 'old-backup' unexpectedly found in ['bak/cd3b6cd9262c170251a5e32daaeadceb8b4c5671', 'old-backup']

----------------------------------------------------------------------
Ran 737 tests in 574.265s

FAILED (failures=9, errors=2, skipped=15)
/tmp/tmpgslc064k/repo/sub/ai/.env is already linked to /tmp/tmpgslc064k/repo/ai/.env but not committed — committing.
committed /tmp/tmpgslc064k/repo/sub/ai/.env as 5943c5f041d3d422f0f57406570c9bc502633489
touched /tmp/tmp4tlykesq/repo/ai/.env
linked /tmp/tmp4tlykesq/repo/sub/ai/.env -> ../../ai/.env
committed /tmp/tmp4tlykesq/repo/sub/ai/.env as c2384c309a6124bfdd08fc573514488cd8db36ce
touched /tmp/tmp66s2f5wx/repo/ai/.env
linked /tmp/tmp66s2f5wx/repo/sub/ai/.env -> ../../ai/.env
touched /tmp/tmpebqix2g_/repo/ai/.env
touched /tmp/tmp6insh57c/repo/ai/.env
linked /tmp/tmp6insh57c/repo/sub/ai/.env -> ../../ai/.env
committed /tmp/tmp6insh57c/repo/sub/ai/.env as fed114480d5b56a3c4022cc44a984a282fc0e9a5
/tmp/tmp6insh57c/repo/sub/ai/.env already linked to /tmp/tmp6insh57c/repo/ai/.env and committed.
touched /tmp/tmprbgsl_c5/repo/ai/.env
Rebasing onto merge-base abc123 with origin/mane, stripping AI attribution...
Rebasing onto merge-base abc123 with origin/mane, stripping AI attribution...
Checking for parent commits having older backup tags…
Found old backup tag: 'old-backup'
Tag cleanup done.

[exited with code 0]
