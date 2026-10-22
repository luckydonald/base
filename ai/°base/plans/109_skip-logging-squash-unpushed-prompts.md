# Skip logging `squash unpushed` prompts

**Commit style:** Skill `/commit-with-lplp-style` is active — auto-commit following it for this implementation.

**Code style:** Load `/code-style` for `py` and `md` before editing (`references/py.md`, `references/md.md`).

## Context

Todo `823f4001-2f8c-4a77-a2dd-f9d1d86a75d9` (`ai/°base/todos.md`): add `squash unpushed` to the ignored queries.
The `save-prompt` hook logs every user prompt to `ai/°base/query.md` and auto-commits it, except for the reminder-style prompts in `SKIP_PROMPTS`.
`squash unpushed` is such a reminder (it already shows up once in `query.md`), so it should not be logged either.

## Changes

1. `scripts/°base/ai/hooks/save-prompt/hook.py`: add `"squash unpushed"` to the `# squashing/cleanup` group of `SKIP_PROMPTS` (next to `"squash"`, `"squash ai"`).
2. `scripts/°base/tests/test_save_prompt_skip_commands.py`: add a test `test_squash_unpushed_is_skipped`, mirroring `test_commit_is_skipped`, asserting `squash unpushed` does not appear in the logged query.
3. Mark the todo done: tick the checkbox in `ai/°base/todos.md`, `complete_todo(calendar_id=7, uid=823f4001-2f8c-4a77-a2dd-f9d1d86a75d9)`, then `uv run scripts/°base/ai/todos/sync_todos.py --project base` (no `--purge-*`).

Only exact matches are skipped (`is_skipped_prompt`), so longer prompts that merely start with `squash unpushed` stay logged.

## Verification

- `uv run --project scripts/°base python -m unittest discover -s scripts/°base/tests -v` stays green, including the new test.

## Git

- One work commit via `ai/git/pending-commit.md`, message like `[base] ai/hooks save-prompt: ai: Run: Skipped logging `squash unpushed` prompts.` (component wording reused from the file's history).
- Then `scripts/tag_backup.py`, fold the `ai:` auto-commits and the `[TODOs] synced todos` commit into it, and check that `git diff <bak-tag> HEAD` is empty.
- No push.
