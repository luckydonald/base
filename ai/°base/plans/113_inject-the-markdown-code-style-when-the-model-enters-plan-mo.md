# Inject the Markdown code style when the model enters plan mode itself

**Commit style:** Skill `/commit-with-lplp-style` is active — auto-commit following it for this implementation.

Todo: `todo:360971fb-7080-4607-94bf-d13a523c30e9` — "Improve the Markdown (`md.md`) code style to actually automatically be loaded if `/plan` is executed."

## Context

Commit `1152e0d72` (2026-10-05) already added the `plan-style-context` hook (`scripts/°base/ai/hooks/plan-style-context/hook.py`), registered on `UserPromptSubmit`.
It injects "read `ai/skills/code-style/references/md.md`" as `additionalContext` when the prompt starts with `/plan` or `permission_mode == "plan"`.
The todo was filed on 2026-10-22, after that fix, so the style still goes missing in practice.

Cause: `UserPromptSubmit` only fires when the *user* sends a prompt.
When the model enters plan mode on its own via `EnterPlanMode` (e.g. in `/todo-loop` step 2, which starts from a `/todo-loop` prompt, not `/plan`), no prompt is submitted in plan mode, so nothing is injected before the plan is written.
The earlier commit's body lists exactly this as "not done: an `EnterPlanMode` `PostToolUse` hook".
Reproduced in this very session: the hook runs fine on `{"prompt": "/plan foo"}`, but entering plan mode through the tool produced no md-style reminder.

## Changes

1. `scripts/°base/ai/hooks/plan-style-context/hook.py`
   - Read `hook_event_name` from the payload and echo it back as `hookEventName`, so the one script serves both `UserPromptSubmit` and `PostToolUse`.
   - On `PostToolUse`, inject the same `CONTEXT` only when `tool_name == "EnterPlanMode"`; every other tool injects nothing.
   - Keep `UserPromptSubmit` behaviour unchanged, default to `UserPromptSubmit` when the field is missing so the existing tests stay valid.
   - Update the module docstring to name both entry points.
2. `ai/settings/settings.json`: add a synchronous (no `async`, since async output cannot reach the model) `PostToolUse` entry with `"matcher": "EnterPlanMode"` running the same hook command.
3. Run `scripts/°base/ai/settings/sync.py` to regenerate `.claude/settings.json`, `.codex/hooks.json` and `.github/hooks/generated.json` (the pre-commit `ai-settings-sync` hook requires it).
4. `scripts/°base/tests/test_plan_style_context.py`: add tests for a `PostToolUse`/`EnterPlanMode` payload (injects, `hookEventName` is `PostToolUse`), and for `PostToolUse` with another tool such as `Read` (injects nothing).
5. `ai/°base/AGENTS.md` "Plan mode": mention that the hook also fires after `EnterPlanMode`, so a model-initiated plan mode is covered too.
6. No new i18n keys (not a UI project).

## Verification

- `python3 -m unittest scripts/°base/tests/test_plan_style_context.py`, then the full base test suite (`ai/°base/AGENTS.md` names the command) and its lint/typing checks.
- Pipe `{"hook_event_name":"PostToolUse","tool_name":"EnterPlanMode"}` into the hook by hand and check the JSON.
- Needs a fresh Claude Code session to see it live: run `/todo-loop`, and the reminder should appear right after `EnterPlanMode`.

## Close

Tick the checkbox in `ai/°base/todos.md`, `complete_todo(7, 360971fb-…)`, sync with `--project base`, then fold everything into one work commit via the tag-backup and rebase procedure.
