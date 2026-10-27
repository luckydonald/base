# Plan: Amend the previous commit in `sync_todos.py` if it already is a clean todo sync commit

**Commit style:** Skill `/commit-with-lplp-style` is active — auto-commit following it for this implementation.

Todo: `f6e1cc84-5df5-4eb3-bc87-4c0b8e302134` — "if the last commit already is a clean todo commit, `--amend` the new commit."

## Context

Every run of `scripts/°base/ai/todos/sync_todos.py` that changes a todo file makes a commit `{prefix}[TODOs] synced todos for {projects}.`.
Run twice in a row (e.g. `/todo-loop` setup, then a manual sync), this piles up several identical todo commits that later have to be squashed by hand.
When `HEAD` is already such a todo-only sync commit, the new changes should go into it instead of a new commit.

## Findings

- The commit is made in `commit_written()` in `scripts/°base/ai/todos/sync_todos.py:877`, one commit per `(git root, prefix)` group, with `git commit -m subject -m body -- files`.
- The body (`describe_changes()`, capped by `MAX_DETAIL_LINES`) lists what changed; an amended commit must keep the old lines and add the new ones.
- Purges, resets and header upgrades call the same function with another `action`; those are meant to stay their own commits.
- Tests are pytest style in `scripts/°base/ai/todos/tests/test_sync_todos.py` (`_repo()` helper, `st.sync(...)`).

## Design

`commit_written()` amends instead of creating a new commit when **all** of these hold for the group's `HEAD`:

1. `action == "synced todos"`, and `HEAD`'s subject is exactly the subject that would be written now (same prefix, same project names), so nothing is renamed by the amend.
2. `HEAD` touches only files of this group (`git show --name-only --format= HEAD` is a subset of `files`), so it is a clean todo commit.
3. `HEAD` is not pushed: `git branch -r --contains HEAD` is empty. A pushed commit is never rewritten.
4. Not in the middle of a merge, rebase, cherry-pick or revert (`git rev-parse -q --verify MERGE_HEAD` etc. plus the `rebase-merge`/`rebase-apply` dirs), and `--no-amend` was not passed.

The amend is `git commit --amend -m subject -m body -- files`, with the body being the old body lines followed by the new ones (the old body is read with `git log -1 --format=%b`), capped like before.
Anything else falls through to the existing new-commit path.
The printed line says `amended <hash>` instead of `committed <hash>`.

New flag `--no-amend` to force a new commit; documented in the module docstring (`sync_todos.py:23`), the `--help` text, and the `todo-loop` skill needs no change since its rebase step already folds syncs.

## Files

- `scripts/°base/ai/todos/sync_todos.py`: helper `amendable(top, subject, files)`, the amend branch in `commit_written()`, the `--no-amend` flag threaded through `sync()`, docstring.
- `scripts/°base/ai/todos/tests/test_sync_todos.py`: new tests.
- Check `ai/°base/AGENTS.md` and the repo `CLAUDE.md` for a description of the todo sync commits and update it if it says "one commit per sync".

## Tests

- Two syncs in a row with a changed todo between: one commit only, body holds both changes.
- `HEAD` is a normal work commit: new commit.
- `HEAD` is a sync commit that also touched another file: new commit.
- `HEAD` is a sync commit already on a remote branch (local bare remote): new commit.
- `HEAD` is a sync of other projects (different subject): new commit.
- A purge commit on top of a sync commit: purge stays its own commit (action differs).
- `--no-amend`: new commit.

## Verification

- `uv run --project scripts/°base python -m pytest scripts/°base/ai/todos/tests -q` and the repo's full unittest command from `ai/°base/AGENTS.md`.
- Manual: run `sync_todos.py --project base` twice against a changed todo, check `git log -3`.
