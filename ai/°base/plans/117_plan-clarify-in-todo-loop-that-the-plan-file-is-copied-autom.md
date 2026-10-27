# Plan: Clarify in `/todo-loop` that the plan file is copied automatically

## Context

Todo `c2227a34-850b-488f-a9b3-9837f7f8f3d8` asks to change the wording of the `/todo-loop` skill.
Step 2 ("Plan") currently says to write the plan "into the project's plan file".
Agents read that as a task to copy the plan into `ai/plans/` by hand, but a hook already does that when the plan is saved.

## Change

Only one file: `ai/skills/todo-loop/SKILL.md` (`.claude/skills/todo-loop` is a symlink to it), step 2 of "The todo".

Old:
> 2. **Plan**: enter plan mode, write the plan (findings, files, tests, new i18n keys) into the project's plan file, wait for the user's accept. Corrections are decisions.

New:
> 2. **Plan**: enter plan mode, write the plan (findings, files, tests, new i18n keys) into the plan file that plan mode gives you, wait for the user's accept. Corrections are decisions.
> The hook copies that plan file into the project's `ai/plans/` automatically, so never copy or move it yourself.

No other file mentions this wording, so nothing else changes.

## Verification

- `git diff` shows only that one step changed.
- Re-read the step to check it still fits the rest of the list, e.g. step 5 ("squash a directly preceding plan commit") which already assumes the hook commits the plan.
- No tests apply, as this is skill prose only.

## Commit

One commit, `[todos] todo-loop skill: ai: Run: Clarified that the plan file is copied automatically by the hook.`, with the todo ticked and the CalDAV todo completed per step 4 of the skill.
