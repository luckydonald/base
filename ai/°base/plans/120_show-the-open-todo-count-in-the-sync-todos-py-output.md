# Show the open todo count in the `sync_todos.py` output

**Commit style:** Skill `/commit-with-lplp-style` is active — auto-commit following it for this implementation.

## Context

Todo `ed8607fe-9744-4eff-946d-a43b77c7764b`: the sync prints `[base] up to date (33 todos)`, which says nothing about how much is left to do.
Wanted: `[base] up to date (33 todos, 2 open)`.
A todo is not open when it is done or when it is waiting or deferred.
So "open" excludes the statuses `COMPLETED`, `CANCELLED` (deferred) and `DELEGATED` (waiting on someone else).
`NEEDS-ACTION` stays open: eM Client wrongly uses it for "waiting", but the todo itself says to rely on `DELEGATED`, so we do not guess from it.

## Findings

- The message is printed in `sync()` in `scripts/°base/ai/todos/sync_todos.py` (the `up to date` print, near line 1425), counting `assigned[project.name]`.
- Statuses are read with `todo.get("status")`, see `checkbox_and_state()` (line 683) and `done_uids` in `sync()`.
- `checkbox_and_state()` has no `DELEGATED` branch, so a delegated todo renders with an empty checkbox, which counts as open in the file.
  The count follows CalDAV, so it will not match the unticked boxes in the file for delegated todos, which is the point of the todo.
- Tests live in `scripts/°base/ai/todos/tests/test_sync_todos.py` (pytest style, `capsys` is already used, e.g. `test_project_without_path_is_skipped_but_still_claims_its_tags`).

## Changes

1. `scripts/°base/ai/todos/sync_todos.py`:
   - Add a module constant `NOT_OPEN_STATUSES = frozenset({"COMPLETED", "CANCELLED", "DELEGATED"})`.
   - Add `count_open(todos: list[dict[str, Any]]) -> int` next to `checkbox_and_state()`, counting todos whose `status` is not in that set (a missing status counts as open).
   - Change the print to `up to date ({len(...)} todos, {count_open(...)} open)`.
   - Only the `up to date` line changes; the `wrote … (action)` lines stay as they are, since other tooling may read them.
   - Update the module docstring if it describes the output.
2. `scripts/°base/ai/todos/tests/test_sync_todos.py`:
   - `test_count_open_skips_done_cancelled_and_delegated`: parametrized over each status, including `NEEDS-ACTION`, `IN-PROCESS` and no status as open.
   - `test_up_to_date_line_shows_the_open_count`: run `sync()` twice on a temporary repo (helpers `_repo` / `_reset_cfg`-style), the second run is a no-op, assert the captured line contains `, 2 open)`.

## Verification

- `uv run --project scripts/°base python -m pytest scripts/°base/ai/todos/tests -q`, then the full base suite from `AGENTS.md`.
- `uv run scripts/°base/ai/todos/sync_todos.py --dry-run --project base` and check the printed `up to date (N todos, M open)` against the todo file.

## Close

Tick the box in `ai/°base/todos.md`, `complete_todo(7, ed8607fe-…)`, run the project sync, then squash into one work commit (`[base] todos: ai: Run: …`).
