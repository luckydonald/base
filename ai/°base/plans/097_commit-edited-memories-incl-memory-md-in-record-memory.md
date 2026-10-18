# Commit edited memories (incl. `MEMORY.md`) in `record-memory`

## Context

Todo `b8ae433f`: `ai/memories/MEMORY.md` gets written but is then left as a dirty file instead of being committed by the `record-memory` hook.
The `DockerTgBot` example (`3927b1d4c`, later folded into `b6bab629b`) had the file added by hand.

Root cause, found by reading `scripts/°base/ai/hooks/record-memory/hook.py` and `°memory_lib/links.py`:
- On `PostToolUse` of a `Write`/`Edit` in the Claude memory dir, `main()` only calls `_commit(...)` when `memory_lib.link_file(src_file, target_dir / rel)` returns `True`.
- `link_file` returns `True` only when the hardlink was created or replaced.
  For a memory that is already hardlinked (same inode), an edit changes the content through the shared inode, `link_file` returns `False`, and nothing is committed.
- So only brand-new memory files are ever committed, and every edit of an existing one (`MEMORY.md` is edited on almost every new memory) stays dirty.
- The `SessionStart` catch-up has the same hole: `_sync_all` only reports newly linked files, so earlier dirty edits are never picked up.

Not verified: the todo's "Claude running from the `sync_todo` subdirectory" hint.
The `_memory_src_dirs` / `rel` resolution looks correct for that case, so I treat it as a side observation, not a second cause.

## Change (`scripts/°base/ai/hooks/record-memory/hook.py`)

1. New `_dirty_names(dst_dir_rel, names=None)`: returns the `*.md` names in the memory dir that `git status --porcelain -- <dir>` reports as modified or untracked (optionally limited to `names`).
2. `PostToolUse` branch: after `link_file`, commit when the link changed **or** `rel` is dirty: `if linked or _dirty_names(rel_dir, [str(rel)]): _commit(...)`.
3. `SessionStart` branch: `changed += _dirty_names(dst_dir_rel)` (deduplicated), so edits made while the hook did not run get committed at the next start.
4. `_commit` stays as is (`git add -- <dir>`, `commit --no-verify --only <dir>`); it already skips when `names` is empty.
   The commit message wording `record memory <stem>` fits edits too, so no change.
5. Not changed: the delete path, the `secondary_dir` promote logic, Codex and Copilot handling.

## Tests

New `scripts/°base/tests/test_record_memory_hook.py`, in the style of `test_memory_delete.py` (temporary git repo with a `luckydonald/base` origin, hook run as a subprocess with `CLAUDE_CONFIG_DIR` pointing into the temp dir):
- A new memory is committed (regression for the existing behavior).
- An already hardlinked memory edited in place is committed by the `PostToolUse` run (fails before the fix).
- `MEMORY.md` edited in place is committed.
- An unchanged, clean memory creates no commit.
- A dirty memory left over from before is committed by a `SessionStart` run.

## Verification

- `scripts/°base/.venv/bin/python3 -m unittest discover -s scripts/°base/tests -p test_record_memory_hook.py`, then `test_memory_delete.py` and `test_memory_promote.py` for neighbouring behavior.
- `python3 scripts/°base/ai/settings/sync.py --check` (no settings change expected).
- The hook only fires for real in a fresh Claude session, so the live behavior cannot be confirmed here.

Commit: `[base] ai/hooks record-memory: ai: Run: Committed edited memories, including MEMORY.md, not only newly linked ones.` (check topic wording with `git log --oneline -5 -- scripts/°base/ai/hooks/record-memory`), then tick, tag, fold, `complete_todo`, sync.
