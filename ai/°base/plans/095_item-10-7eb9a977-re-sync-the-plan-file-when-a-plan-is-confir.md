# Item 10 (`7eb9a977`): re-sync the plan file when a plan is confirmed

## Context

`save-plan/hook.py` snapshots the plan into `ai/°base/plans/NNN_slug.md` on `Write`/`Edit` of the harness plan file and on `ExitPlanMode`.
When the plan is edited via Bash (`echo`, a Python script), no `Write`/`Edit` hook fires.
At `ExitPlanMode` the hook prefers `tool_input.plan`, then `tool_response.plan`, neither guaranteed to match the file on disk. It reads the file only when both are empty.

## Change (`scripts/°base/ai/hooks/save-plan/hook.py`)

1. New `_plan_from_disk(payload, session)` (Claude only): current text of the plan file, from `tool_response["filePath"]` when `_is_plan_file_path()` accepts it, else the session's recorded `source` filename in `<CLAUDE_CONFIG_DIR or ~/.claude>/plans/`. Returns `""` if missing or unreadable.
2. In `main()`'s `ExitPlanMode` branch, try `_plan_from_disk` first, then fall back to the existing `tool_input.plan`, `tool_response.plan`, Copilot order.
   The existing dedup (identical skips, changed commits `ai: save plan NNN_slug`, renames on slug change) does the re-sync.
3. Unchanged: Codex and Copilot paths, `Write`/`Edit` handling, `done` marker.

## Tests (`scripts/°base/tests/test_save_plan_decisions.py`)

- `Write` snapshot, file edited on disk without a hook, then `ExitPlanMode` with stale `tool_response.plan`: second commit holds the on-disk text.
- `ExitPlanMode` with unchanged file: no extra plan commit.
- `filePath` outside a plans dir is ignored; old fallback order applies.

## Verify

`test_save_plan_decisions.py`, `test_ai_hooks_base_routing.py -k Plan` (known `/private/var` failures aside), `sync.py --check`.
Commit `[base] ai/hooks save-plan: ai: Run: Re-read the plan file from disk when a plan is confirmed.`, then tick, tag, fold, `complete_todo(7, uid)`, sync.
