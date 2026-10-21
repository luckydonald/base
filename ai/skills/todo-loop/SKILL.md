---
name: "todo-loop"
description: "Work on exactly ONE open todo of a project, the next unchecked `- [ ]` item of its todo file (intel, plan, implement, commit, tick, complete on CalDAV, sync, rebase), then stop so the user can /clear and run it again for the next one. Todos are synced from CalDAV into the todo file (calendar 7 by default). Use whenever the user asks to do the next todo, work on the todos / `ai/todos.md` / the TODO list of a project, or says 'go through the todos'."
---

# Todo loop (one todo per run)

Does the **next open todo** of one project, then stops, so the user can `/clear` and invoke it again. Todos live on CalDAV (read and completed through the `sync_todo` MCP, see the `sync-todo-mcp` skill) and are mirrored into the project's todo file by `scripts/sync_todos.py`. Never continue with a second todo in the same run.

## Parameters (ask or derive; don't assume)

- **Project**: its tag / name (e.g. `SyncTodoBot`, `DockerTgBot`, `derpiscript2`), as mapped in the repo `CLAUDE.md` ("Todo-list identifiers") and `scripts/sync_todos.json`. Used for `--project` and the `#Tag` on new todos. If the user names a file (e.g. `@sync_todo/ai/todos.md`), the project follows from it.
- **Todo file**: the project's file from that mapping (e.g. `sync_todo/ai/todos.md`).
- **Calendar id**: recommended `7` ("TODO: Today", iCloud account 1, the one with the real todos in the owner's setup); confirm with `list_calendars` if it fails or the user uses another.
- **Bugsink project ids**: from the "Issue-tracker identifiers" table, if the project has any.
- **Commit scope prefix** (`[sync_todo]`, `[root]`, …) and test/lint commands: from the project's `CLAUDE.md`.

## Setup

1. Load `/commit-with-lplp-style` (one commit per todo, the project's scope prefix (`[sync_todo] [scope] …`), messages via `ai/git/pending-commit.md`) and `/code-style`.
2. Read the todo file and pick the open `- [ ]` item to do next. That is the first one in file order, unless another is clearly more urgent (a crash, or a blocker for the others): then take that one, without asking. Skip ones whose text says skip; a subtask comes before its parent (a parent stays open while a child is). Tell the user which todo (uid and summary) you take and, if it is not the first in the file, why.

## The todo

1. **Intel** (normal mode, not plan mode): reproduce and understand with the MCPs (Bugsink, sync_todo, Coolify) and throwaway scripts and tests in the scratchpad dir. No project file edits yet. A todo with more than one bug becomes subtasks first (`create_todo` with `parent_uid`, tag it with the project tag); then work on the first subtask only.
2. **Plan**: enter plan mode, write the detailed plan for this one todo (findings, files, tests, new i18n keys) into the project's plan file, and wait for the user's accept. Take their corrections as decisions.
3. **Implement**: code plus tests as it makes sense. Commit as plain new commits following `/commit-with-lplp-style`, but do **not** rebase yet (that is step 6). Run the project's whole test suite (and lint/build where it has them, e.g. backend `pytest`, frontend `npm run test` / `npm run build`); if everything is green, go straight to 4. If red, fix code or tests, commit the fix, run the tests again, and repeat until green. Add the guidance to the project's `CLAUDE.md` when behaviour worth knowing changed.
4. **Close**: tick the checkbox in the todo file, `complete_todo(calendar_id, uid)`, then run `uv run scripts/sync_todos.py --project <project>` (from the repo root) **without** `--purge-missing`/`--purge-complete` (completed todos stay in the file).
5. **Re-read** the todo file: the sync may have rewritten it. The file replaces the `list_todos(calendar_id=...)` MCP call, which is not needed.
6. **Rebase** (the last step of the work): tag the prior HEAD with `scripts/tag_backup.py`, then an interactive rebase that folds the `ai:` auto-commits and the fix commits into the one work commit, with the message from `ai/git/pending-commit.md`. Squash rules:
   - If the run commit contains no plan and there is a plan commit right before it, squash the plan into the run commit (LPLP commit style); don't keep it as `ai: Plan:`.
   - If the `sync_todos.py` commit (`ai: synced todos …`) only ticked the checkbox of the todo just finished, squash it into the work commit too. If it also added, changed or removed other todos, keep it as its own commit.
   Verify the tree equals the backup tag (`git diff <bak-tag> HEAD`).
7. **Stop**: report faithfully in a few lines (todo done, commit hash, tests run, what could not be verified without a deploy, anything left for the user) and name the next open todo from the file as a hint. Then end the turn, with nothing else started: the user runs `/clear` and invokes the skill again.

## Rules that bit before

- One commit per todo, never bundled; unrelated files (stray edits, other people's stashes) are never committed.
- Follow the project's own rules from its `CLAUDE.md` (e.g. sync_todo: every new UI string goes into all six `frontend/src/i18n/locales/*.json`, bot strings into `i18n/langs/*.py`; tap/click/type stay distinct, no iCloud).
- Don't delete or "clean up" data on the user's behalf (duplicate todos, files); report it as a follow-up instead. Never reset or push without being asked.
- Report faithfully at the end: what is done, what you could not verify without a deploy, and anything left for the user.

## When no open todo is left

Check Bugsink (the project's ids from the repo `CLAUDE.md`, see `bugsink-triage`; skip if it has none) for new unresolved issues and create a todo for each via `create_todo`, then stop and say so (the next run picks them up after a sync). Otherwise just report that everything is done.
