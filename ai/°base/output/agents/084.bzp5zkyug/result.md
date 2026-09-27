…
ost recent call last):
  File "/home/user/git/luckydonald/base/scripts/°base/tests/test_commit_style_lib.py", line 203, in test_record_memory_honors_override_and_keeps_dynamic_slug
    self.assertEqual(last_subject(repo), "🧠 ai: record memory note")
    ~~~~~~~~~~~~~~~~^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
AssertionError: 'init' != '🧠 ai: record memory note'
- init
+ 🧠 ai: record memory note


======================================================================
FAIL: test_delete_helper_removes_repo_and_source_and_formats_commit (test_memory_delete.MemoryDeleteTests.test_delete_helper_removes_repo_and_source_and_formats_commit)
----------------------------------------------------------------------
Traceback (most recent call last):
  File "/home/user/git/luckydonald/base/scripts/°base/tests/test_memory_delete.py", line 127, in test_delete_helper_removes_repo_and_source_and_formats_commit
    self.assertFalse(src.exists())
    ~~~~~~~~~~~~~~~~^^^^^^^^^^^^^^
AssertionError: True is not false

======================================================================
FAIL: test_remove_flag_deletes_tags_in_parent_history (test_tag_backup.TagBackupTests.test_remove_flag_deletes_tags_in_parent_history)
----------------------------------------------------------------------
Traceback (most recent call last):
  File "/home/user/git/luckydonald/base/scripts/°base/tests/test_tag_backup.py", line 58, in test_remove_flag_deletes_tags_in_parent_history
    self.assertNotIn("old-backup", git(["tag"], self.repo).splitlines())
    ~~~~~~~~~~~~~~~~^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
AssertionError: 'old-backup' unexpectedly found in ['bak/70e960c7c97febe492a82b7da38c5b3a5a6648c7', 'old-backup']

----------------------------------------------------------------------
Ran 737 tests in 578.530s

FAILED (failures=9, errors=2, skipped=15)
/tmp/tmph8sxc25p/repo/sub/ai/.env is already linked to /tmp/tmph8sxc25p/repo/ai/.env but not committed — committing.
committed /tmp/tmph8sxc25p/repo/sub/ai/.env as f1886dfeccf7f32294d9b63e9cec709501db80a8
touched /tmp/tmpwpvno4i8/repo/ai/.env
linked /tmp/tmpwpvno4i8/repo/sub/ai/.env -> ../../ai/.env
committed /tmp/tmpwpvno4i8/repo/sub/ai/.env as f1886dfeccf7f32294d9b63e9cec709501db80a8
touched /tmp/tmp7dqgvn0_/repo/ai/.env
linked /tmp/tmp7dqgvn0_/repo/sub/ai/.env -> ../../ai/.env
touched /tmp/tmpghjy5qio/repo/ai/.env
touched /tmp/tmpdo7lt6kv/repo/ai/.env
linked /tmp/tmpdo7lt6kv/repo/sub/ai/.env -> ../../ai/.env
committed /tmp/tmpdo7lt6kv/repo/sub/ai/.env as f1886dfeccf7f32294d9b63e9cec709501db80a8
/tmp/tmpdo7lt6kv/repo/sub/ai/.env already linked to /tmp/tmpdo7lt6kv/repo/ai/.env and committed.
touched /tmp/tmplbd2yvim/repo/ai/.env
Rebasing onto merge-base abc123 with origin/mane, stripping AI attribution...
Rebasing onto merge-base abc123 with origin/mane, stripping AI attribution...
Checking for parent commits having older backup tags…
Found old backup tag: 'old-backup'
Tag cleanup done.

[exited with code 0]
