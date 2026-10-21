---
name: "todo-loop"
description: "Work through a project's open todos one by one (intel, plan, implement, commit, tick, complete on CalDAV, sync, rebase), the way sync_todo's `ai/todos.md` is processed. Use whenever the user asks to work through, burn down, or loop over the todos / `ai/todos.md` / the TODO list of a project, or to do the next todo, even if they only say 'go through the todos'."
---

# Todo loop

Processes the open todos of one project (here `SyncTodoBot`, file `sync_todo/ai/todos.md`, CalDAV calendar `7`) one at a time. Todo ids and MCP details: the repo `CLAUDE.md` ("Todo-list identifiers", "Ids for the MCP servers") and the `sync-todo-mcp` skill.

## Setup (once)

1. Load `/commit-with-lplp-style` (one commit per todo, prefix `[sync_todo] [scope] …`, messages via `ai/git/pending-commit.md`) and `/code-style`.
2. Read `ai/todos.md`. List the open `- [ ]` items (skip ones whose text says skip), put them in a sensible order (a blocker such as a crash first), and write that as a plan file: context, rules, the workflow below, an ordered list with a one-line approach each, and a **Current task** section.
3. Get the user's confirmation of the overall plan before starting.

## Per todo

1. **Intel** (normal mode, not plan mode): reproduce and understand with the MCPs (Bugsink, sync_todo, Coolify) and throwaway scripts and tests in the scratchpad dir. No project file edits yet. A todo with more than one bug becomes subtasks first (`create_todo` with `parent_uid`, tag `#SyncTodoBot`).
2. **Plan**: re-enter plan mode, write the detailed plan for this one todo (findings, files, tests, new i18n keys), and wait for the user's accept. Take their corrections as decisions.
3. **Implement**: code plus tests. Commit as plain new commits (no rebase yet). Run the whole backend (`uv run pytest code/tests`) and, if touched, frontend (`npm run test`, `npm run build`) suites; if red, fix, commit the fix, repeat until green. Add the guidance to `CLAUDE.md` when behaviour worth knowing changed.
4. **Close**: tick the checkbox in `ai/todos.md`, `complete_todo(calendar_id=7, uid)`, then run `uv run ../scripts/sync_todos.py --project SyncTodoBot` **without** `--purge-missing`/`--purge-complete` (completed todos stay in the file).
5. **Rebase**: tag the prior HEAD with `../scripts/tag_backup.py`, then an interactive rebase that folds the `ai:` auto-commits (saved plans and decisions included: the plan commit right before the run commit is squashed into it) and the fix commits into the one work commit, with the message from `ai/git/pending-commit.md`. Verify the tree equals the backup tag (`git diff <bak-tag> HEAD`).
6. **Next**: re-read `ai/todos.md` (the sync may have added todos), update **Current task** once (number, uid, done, next), `/compact` if possible, repeat at 1.

## Rules that bit before

- One commit per todo, never bundled; unrelated files (stray edits, other people's stashes) are never committed.
- Every new UI string goes into all six `frontend/src/i18n/locales/*.json`, bot strings into `i18n/langs/*.py`. tap/click/type stay distinct, no iCloud.
- Don't delete or "clean up" data on the user's behalf (duplicate todos, files); report it as a follow-up instead. Never reset or push without being asked.
- Report faithfully at the end: what is done, what you could not verify without a deploy, and anything left for the user.

## When all todos are done (once)

Check Bugsink (project `17` backend, `19` frontend, see `bugsink-triage`) for new unresolved issues, create a todo for each via `create_todo`, then loop again from step 1 for those. Otherwise finish with a summary.
