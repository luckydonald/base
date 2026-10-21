# Allow `mcp__sync_todo__list_calendars`

**Commit style:** Skill `/commit-with-lplp-style` is active — auto-commit following it for this implementation.

## Context

Todo `87dac3b4-331e-4043-8f5b-cc5e45c113ab` asks to add `mcp__sync_todo__list_calendars` to the allowed calls in `ai/settings/settings.json`.
Today the call prompts for permission each time, although it is read-only like the already allowed `bugsink` list/get tools.

## Changes

1. `ai/settings/settings.json`: add `{"type": "mcp", "server": "sync_todo", "tool": "list_calendars"}` to `permissions.allow`, right after the `bugsink` `test_connection` entry (line 368), using the same one-line object format.
2. Run `python3 scripts/°base/ai/settings/sync.py` so the generated `.claude/settings.json` gets `mcp__sync_todo__list_calendars` (and the Codex files stay in sync, as the pre-commit `sync.py --check` requires).

No new tests: the change is pure config, covered by the existing sync check.

## Verification

- `python3 scripts/°base/ai/settings/sync.py --check` exits 0.
- `git diff` shows only the one new line in `ai/settings/settings.json` and the matching line in `.claude/settings.json`.
- Run the base test suite: `uv run --project scripts/°base python -m unittest discover -s scripts/°base/tests -v`.

## Close

Tick the todo in `ai/todos.md`, `complete_todo(calendar_id=7, uid="87dac3b4-331e-4043-8f5b-cc5e45c113ab")`, then `sync_todos.py --project base`, and fold the commits into one work commit.
