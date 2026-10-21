# Allow read-only `sync_todo` MCP tools

**Commit style:** Skill `/commit-with-lplp-style` is active — auto-commit following it for this implementation.

## Context

Todo `87dac3b4-331e-4043-8f5b-cc5e45c113ab` asks to add `mcp__sync_todo__list_calendars` to the allowed calls in `ai/settings/settings.json`.
None of the `sync_todo` tools is allowed yet, so every read prompts for permission, although they are read-only like the already allowed `bugsink` tools.
The user also asked to add the other read-only ones, and picked all of them.

## Changes

1. `ai/settings/settings.json`: add these entries to `permissions.allow`, right after the `bugsink` `test_connection` entry (line 368), in the same one-line object format:
   - `{"type": "mcp", "server": "sync_todo", "tool": "list_calendars"}`
   - `list_todos`, `list_tags`, `list_calendar_accounts`, `get_calendar_account`, `get_user_settings`
2. Deliberately not added: `get_calendar_password` (returns a secret) and every write tool (`create_*`, `update_*`, `delete_*`, `complete_todo`, `set_*`, `add_*`, `remove_*`, `rename_tag`).
3. Run `python3 scripts/°base/ai/settings/sync.py` so the generated `.claude/settings.json` gets the matching `mcp__sync_todo__*` entries (the pre-commit `sync.py --check` requires it).

No new tests: the change is pure config, covered by the existing sync check.

## Verification

- `python3 scripts/°base/ai/settings/sync.py --check` exits 0.
- `git diff` shows only the six new lines in `ai/settings/settings.json` and the matching lines in `.claude/settings.json`.
- Run the base test suite: `uv run --project scripts/°base python -m unittest discover -s scripts/°base/tests -v`.

## Close

Tick the todo in `ai/todos.md`, `complete_todo(calendar_id=7, uid="87dac3b4-331e-4043-8f5b-cc5e45c113ab")`, then `sync_todos.py --project base`, and fold the commits into one work commit.
