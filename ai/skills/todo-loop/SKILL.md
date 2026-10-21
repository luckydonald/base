---
name: "todo-loop"
description: "Work through a project's open todos one by one (intel, plan, implement, commit, tick, complete on CalDAV, sync, rebase), for any project whose todos are synced from CalDAV into a todo file (calendar 7 by default). Use whenever the user asks to work through, burn down, or loop over the todos / `ai/todos.md` / the TODO list of a project, or to do the next todo, even if they only say 'go through the todos'."
---

# Todo loop

Processes the open todos of one project one at a time. Todos live on CalDAV (read and completed through the `sync_todo` MCP, see the `sync-todo-mcp` skill) and are mirrored into the project's todo file by `scripts/sync_todos.py`.

## Parameters (ask or derive; don't assume)

- **Project**: its tag / name (e.g. `SyncTodoBot`, `DockerTgBot`, `derpiscript2`), as mapped in the repo `CLAUDE.md` ("Todo-list identifiers") and `scripts/sync_todos.json`. Used for `--project` and the `#Tag` on new todos.
- **Todo file**: the project's file from that mapping (e.g. `sync_todo/ai/todos.md`).
- **Calendar id**: recommended `7` ("TODO: Today", iCloud account 1, the one with the real todos in the owner's setup); confirm with `list_calendars` if it fails or the user uses another.
- **Bugsink project ids**: from the "Issue-tracker identifiers" table, if the project has any.
- **Commit scope prefix** (`[sync_todo]`, `[root]`, …) and test/lint commands: from the project's `CLAUDE.md`.

## Setup (once)

1. Load `/commit-with-lplp-style` (one commit per todo, the project's scope prefix (`[sync_todo] [scope] …`), messages via `ai/git/pending-commit.md`) and `/code-style`.
2. Read the todo file. List the open `- [ ]` items (skip ones whose text says skip), put them in a sensible order (a blocker such as a crash first), and write that as a plan file: context, rules, the workflow below, an ordered list with a one-line approach each, and a **Current task** section.
3. Get the user's confirmation of the overall plan before starting.

## Per todo

1. **Intel** (normal mode, not plan mode): reproduce and understand with the MCPs (Bugsink, sync_todo, Coolify) and throwaway scripts and tests in the scratchpad dir. No project file edits yet. A todo with more than one bug becomes subtasks first (`create_todo` with `parent_uid`, tag it with the project tag).
2. **Plan**: re-enter plan mode, write the detailed plan for this one todo (findings, files, tests, new i18n keys), and wait for the user's accept. Take their corrections as decisions.
3. **Implement**: code plus tests as it makes sense. Commit as plain new commits following `/commit-with-lplp-style`, but do **not** rebase yet (that is the last step, 6). Run the project's whole test suite (and lint/build where it has them, e.g. backend `pytest`, frontend `npm run test` / `npm run build`); if everything is green, go straight to 4. If red, fix code or tests, commit the fix, run the tests again, and repeat until green. Add the guidance to the project's `CLAUDE.md` when behaviour worth knowing changed.
4. **Close**: tick the checkbox in the todo file, `complete_todo(calendar_id, uid)`, then run `uv run scripts/sync_todos.py --project <project>` (from the repo root) **without** `--purge-missing`/`--purge-complete` (completed todos stay in the file).
5. **Re-read** the todo file: the sync may have rewritten it, and new todos can be integrated right away. The file replaces the `list_todos(calendar_id=...)` MCP call, which is not needed in the loop.
6. **Rebase** (the very last step of a task's loop, nothing after it but step 7): tag the prior HEAD with `../scripts/tag_backup.py`, then an interactive rebase that folds the `ai:` auto-commits and the fix commits into the one work commit, with the message from `ai/git/pending-commit.md`. Squash rules:
   - If the run commit contains no plan and there is a plan commit right before it, squash the plan into the run commit (LPLP commit style); don't keep it as `ai: Plan:`.
   - If the `sync_todos.py` commit (`ai: synced todos …`) only ticked the checkbox of the todo just finished, squash it into the work commit too. If it also added, changed or removed other todos, keep it as its own commit.
   Verify the tree equals the backup tag (`git diff <bak-tag> HEAD`).
7. **Next**: update **Current task** once (number, uid, done, next), `/compact` if possible (ignore if there is no way to), repeat at 1, until ALL remaining open todos are done, including the ones added later by a sync. Todos whose text says to skip are skipped.

## Rules that bit before

- One commit per todo, never bundled; unrelated files (stray edits, other people's stashes) are never committed.
- Follow the project's own rules from its `CLAUDE.md` (e.g. sync_todo: every new UI string goes into all six `frontend/src/i18n/locales/*.json`, bot strings into `i18n/langs/*.py`; tap/click/type stay distinct, no iCloud).
- Don't delete or "clean up" data on the user's behalf (duplicate todos, files); report it as a follow-up instead. Never reset or push without being asked.
- Report faithfully at the end: what is done, what you could not verify without a deploy, and anything left for the user.

## When all todos are done (once)

Check Bugsink (the project's ids from the repo `CLAUDE.md`, see `bugsink-triage`; skip if it has none) for new unresolved issues, create a todo for each via `create_todo`, then loop again from step 1 for those. Otherwise finish with a summary.
