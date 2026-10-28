# Plan: Show the todo priority in the synced todo file

**Commit style:** Skill `/commit-with-lplp-style` is active — auto-commit following it for this implementation.

Todo `a4424413-2c35-4623-95ef-2927a5a03281`: "todos.md script should include the priority if set. In a way that the numbers make sense. I'm always confused if one or nine is the high priority."
The `# end if` plugin todo (`7f19ba8b-…`) was skipped, since nothing says the plugin is released.

## Context

`scripts/°base/ai/todos/sync_todos.py` already receives `priority` from the CalDAV todos (iCal semantics: `1` is highest, `9` is lowest, `0`/`null` is unset), but `render()` and `update_line()` never write it into the todo file.
The numbers alone are ambiguous, so the marker carries the scale (`₍₉₎`) and a band word next to the number.
Current CalDAV data: 477 todos with `0`, 6 with `9`, 4 with `5`, 1 with `1`, so the unset case must stay silent.

## Format

The priority joins the existing status bracket, separated by `; `, and stands alone in its own bracket when there is no status:

| Priority | Band word | Example |
|---|---|---|
| `1` | `highest` | `_(prio 1₍₉₎ highest)_` |
| `2`–`4` | `high` | `_(prio 2₍₉₎ high)_` |
| `5` | `medium` | `_(prio 5₍₉₎ medium)_` |
| `6`–`8` | `low` | `_(prio 7₍₉₎ low)_` |
| `9` | `lowest` | `_(prio 9₍₉₎ lowest)_` |
| `0` / unset | nothing | no marker |

With a status: `_(in process, 40%; prio 1₍₉₎ highest)_`, `_(done; prio 9₍₉₎ lowest)_`.
The minimum and maximum spell out `highest`/`lowest`; the bands in between use `high`/`medium`/`low` (RFC 5545 bands).

## Findings

- The state marker (`_(done)_`, `_(in process, 40%)_`, …) is produced by `checkbox_and_state()` and stripped again by `STATE` in `update_line()`, so an existing line is refreshed on every sync without touching hand-written text after the uid.
- `STATE_TEXT` in `managed_todos()` / `describe_changes()` reads the same marker for the commit body (`state: … (a -> b)`).
- `render()` builds new lines, `update_line()` refreshes existing ones, and both go through `checkbox_and_state()`.

## Changes

1. In `sync_todos.py`, add `priority_text(todo) -> str` (returns `""` for unset, else `prio N₍₉₎ word`) next to `checkbox_and_state()`.
   `checkbox_and_state()` keeps returning the box and now the merged bracket: it joins the status text and the priority text with `; ` inside one `_(…)_`, or emits the priority alone.
   The existing parametrized test keeps passing, since the priority is unset there.
2. Widen the `STATE` regex (used by `update_line()`) and `STATE_TEXT` (used by `managed_todos()`) to accept the optional `; prio N₍₉₎ word` part and the priority-only bracket, so a changed or removed priority is refreshed and a hand note after the uid stays.
3. Report a priority change in `describe_changes()` as `priority: <shown> (a -> b)`, with a separate `priority` entry in `managed_todos()`, so the commit body names it and a priority change is not misreported as a state change.
4. Explain the scale once in `todos.template.md` ("`prio 1₍₉₎` is the highest, `9₍₉₎` the lowest"), so a file made from the template says it too.
   The `upgrade` logic for existing files is untouched; the markers appear on the next sync.

## Tests (`scripts/°base/ai/todos/tests/test_sync_todos.py`)

- Parametrized `priority_text`: `None`, `0`, `1`, `2`, `4`, `5`, `6`, `8`, `9`, and a bad value.
- `checkbox_and_state` with a priority: merged with a status, alone without one.
- `render` shows the merged bracket, and nothing for an unset priority.
- `merge` is idempotent with a priority, refreshes a changed one, drops a removed one, and keeps a hand note after the uid.
- `describe_changes` reports a priority change.

## Verification

- `uv run --project scripts/°base python -m pytest scripts/°base/ai/todos/tests`, then the full suite from `ai/°base/AGENTS.md`.
- `uv run scripts/°base/ai/todos/sync_todos.py --project base --dry-run` shows `prio 9₍₉₎ lowest` on the `7f19ba8b-…` line.
- The real sync afterwards writes markers only for the few todos with a priority and leaves the 477 others alone.
