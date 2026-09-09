…
wip dual memory dirs
ERROR: test_codex_memory_stop_reports_unassigned_note_as_json (test_ai_hooks_base_routing.AiHooksBaseRoutingTests.test_codex_memory_stop_reports_unassigned_note_as_json)
ERROR: test_memory_in_base_repo_routes_and_prefixes (test_ai_hooks_base_routing.AiHooksBaseRoutingTests.test_memory_in_base_repo_routes_and_prefixes)
ERROR: test_memory_session_start_restores_missing_claude_source_from_repo (test_ai_hooks_base_routing.AiHooksBaseRoutingTests.test_memory_session_start_restores_missing_claude_source_from_repo)
FAILED (failures=8, errors=3, skipped=2)
FAIL: test_delete_helper_removes_repo_and_source_and_formats_commit (test_memory_delete.MemoryDeleteTests.test_delete_helper_removes_repo_and_source_and_formats_commit)
FAIL: test_memory_bash_rm_chained_command_still_detected (test_ai_hooks_base_routing.AiHooksBaseRoutingTests.test_memory_bash_rm_chained_command_still_detected)
FAIL: test_memory_bash_rm_of_source_file_deletes_repo_mirror (test_ai_hooks_base_routing.AiHooksBaseRoutingTests.test_memory_bash_rm_of_source_file_deletes_repo_mirror)
FAIL: test_memory_posttooluse_write_with_underscore_in_project_path (test_ai_hooks_base_routing.AiHooksBaseRoutingTests.test_memory_posttooluse_write_with_underscore_in_project_path)
FAIL: test_memory_session_start_content_mismatch_repo_wins (test_ai_hooks_base_routing.AiHooksBaseRoutingTests.test_memory_session_start_content_mismatch_repo_wins)
FAIL: test_memory_session_start_does_not_resurrect_marked_deleted_memory (test_ai_hooks_base_routing.AiHooksBaseRoutingTests.test_memory_session_start_does_not_resurrect_marked_deleted_memory)
FAIL: test_record_memory_honors_override_and_keeps_dynamic_slug (test_commit_style_lib.CommitStyleLibOverrideTests.test_record_memory_honors_override_and_keeps_dynamic_slug)
FAIL: test_remove_flag_deletes_tags_in_parent_history (test_tag_backup.TagBackupTests.test_remove_flag_deletes_tags_in_parent_history)
On branch base
Your branch is ahead of 'base/base' by 12 commits.
  (use "git push" to publish your local commits)

Changes not staged for commit:
  (use "git add <file>..." to update what will be committed)
  (use "git restore <file>..." to discard changes in working directory)
	modified:   "scripts/\302\260base/ai/hooks/record-codex-memory/hook.py"
	modified:   "scripts/\302\260base/ai/hooks/record-memory/hook.py"
	modified:   "scripts/\302\260base/ai/hooks/\302\260memory_lib/__init__.py"
	modified:   "scripts/\302\260base/ai/memory/delete.py"

Untracked files:
  (use "git add <file>..." to include in what will be committed)
	ai/references/https/github.com/bazelbuild/
	ai/references/https/learn.chatgpt.com/
	ai/skills/coolify-compose-deploy-workspace/
	"ai/\302\260base/by-feature/.debug"
	"ai/\302\260base/decisions/"
	poetry.lock
	pyproject.toml
	"scripts/\302\260base/ai/hooks/\302\260memory_lib/dirs.py"

no changes added to commit (use "git add" and/or "git commit -a")
Dropped refs/stash@{0} (9162a27bbdf319118787c9ae31dfb7a8b40a7741)

[exited with code 0]
