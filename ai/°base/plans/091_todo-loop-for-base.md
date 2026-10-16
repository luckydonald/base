# Todo loop for `base`

## Context

Work through the open todos of the `base` project one at a time, following the `todo-loop` skill and the `sync-todo-mcp` skill.
The todos live on CalDAV (calendar 7, "TODO: Today") and are mirrored into `ai/todo.md` by `/Users/user/Documents/programming/Python/DockerTgBot/scripts/sync_todos.py`.
The `sync_todo` and `bugsink` MCP servers failed to connect in this session (`CONNECTION_CLOSED`), so `complete_todo` / `create_todo` are not callable yet.
The sync script talks to the same MCP server over HTTP with its own token, so reloading the file does not depend on the stdio bridge.

## Parameters

- **Project**: `base` (tags `base`, `baseBase`), todo file `ai/todo.md`, calendar id `7`.
- **Commit style**: `commit-with-lplp-style` is active.
  The origin is `luckydonald/base`, so the opt-in question is skipped and assumed `yes`.
  Commit format is `[base] topic: ai: Run: Short summary.`, one commit per todo, messages via `ai/git/pending-commit.md`, never any `Co-Authored-By` or Claude footer lines other than the session trailer the pre-commit hook allows.
- **Code style**: `/code-style` applies, Markdown prose breaks only at sentence ends.
- **Tests**: `uv run --project scripts/°base python -m unittest discover -s scripts/°base/tests -v`, plus `python3 scripts/°base/ai/settings/sync.py --check` whenever settings or skills change.
- **Backup tags**: `base` has no `scripts/tag_backup.py`, so use `/Users/user/Documents/programming/Python/DockerTgBot/scripts/tag_backup.py` by absolute path.
- **Bugsink**: none configured for `base`, so the "all done" Bugsink check is skipped.
- **Untracked files** already in the tree (`ai/°base/errors/27.md`, `3_.md`, `output/agents/*`, `scripts/°base/tests/aaa.py`) are never committed.

## Workflow per todo

1. Reload with `uv run /Users/user/Documents/programming/Python/DockerTgBot/scripts/sync_todos.py --project base`, without `--purge-*`, then read `ai/todo.md`.
2. Intel in normal mode with throwaway scripts in the scratchpad, no project edits.
   A todo with several bugs becomes subtasks first.
3. Plan mode for that one todo, wait for the user's accept.
4. Implement with tests, commit as plain new commits, run the whole suite until green.
5. Close: tick the box, `complete_todo(7, uid)`, re-run the sync, re-read the file.
6. Rebase last: tag the prior HEAD, fold `ai:` auto-commits and fix commits into the work commit, verify `git diff <bak-tag> HEAD` is empty.
7. Update **Current task**, `/compact` if possible, repeat until all open todos are done, including ones added by later syncs.

## Ordered list

The five `[!]` items are open too (CalDAV "needs action"), so they are included.
Quick, well-specified items go first, the larger hook and symlink work last.

1. `9adc5376` Add the four missing `mcp__bugsink__*` permissions to `ai/settings/settings.json` (fix the curly quotes), then run `sync.py`.
2. `56f6ee1a` `checkout.sh`: add the `[ -L "$hook_file" ] && continue` guard in `repair_git_lfs_hooks_path()`, port `test_checkout_lfs_hooks.py` from docker-tg-bot.
3. `268ba6c5` Code style not loading for `/plan`: check `plan-style-context/hook.py` and the skill description, use the Anthropic skill-creator skill as the todo asks.
4. `5e80abad` Strip the "next message may contain a correction" note from plan decisions in `save-decision/hook.py`.
5. `66f35747` `@file)` mention detection: try the full match first, then without trailing punctuation, in the query-link hook.
6. `b7a5299c` Allow referenced-file auto-commit for staged and previously committed files while respecting `.gitignore`.
7. `be604b2a` Also link `/skill` calls to their existing `ai/skills/…/SKILL.md`, sharing the mention-detection code from item 5.
8. `e7df2be3` Add a skill for `download_ref.py` (at least with `--no-ide`).
9. `51f4adc0` Make the settings sync script print a proper diff for dry run and real run.
10. `7eb9a977` Plan-confirm hook syncs the plan once more, via the plan decision hook if simpler.
11. `b8ae433f` Investigate why `ai/memories/MEMORY.md` is skipped in commits, using backup tags and the commit hashes in the todo.
12. `6f2b2450` Re-sync per-file subproject symlinks from rebase/merge git triggers.
13. `58a06dbd` `.run/.subprojectIgnore` listing files not to link into subprojects, building on item 12.

## Current task

Item 1 of 13, `9adc5376` (bugsink permissions): intel done, awaiting plan accept.
Sync reload is done: `[base] up to date (13 todos)`.
Run the script from `/Users/user/Documents/programming/Python/DockerTgBot` with `uv run --script scripts/sync_todos.py --project base`, because run from `base` uv picks up DockerTgBot's `.python-version` (`docker-tg-bot-3.10.0`) and fails.

### Plan for item 1 (`9adc5376`)

Findings: `ai/settings/settings.json` already has `{"type": "mcp", "server": "bugsink", "tool": ...}` allow entries for `list_projects`, `list_issues` and `get_issue` at lines 362-364.
The todo's four tools are missing, and its curly quotes only matter if pasted literally, the structured form needs none.

Change: insert four entries after line 364, in the same compact one-line form.

```json
{"type": "mcp", "server": "bugsink", "tool": "list_events"},
{"type": "mcp", "server": "bugsink", "tool": "get_event"},
{"type": "mcp", "server": "bugsink", "tool": "get_stacktrace"},
{"type": "mcp", "server": "bugsink", "tool": "test_connection"},
```

Then run `python3 scripts/°base/ai/settings/sync.py` so `.claude/settings.json` (`mcp__bugsink__*` permission strings) follows, and check `sync.py --check` plus the unit tests.
No new unit test: this is pure data, covered by the existing sync round-trip tests and the `--check` pre-commit hook.
Commit: `[base] settings: ai: Run: Allow remaining read-only bugsink MCP tools.` with the message in `ai/git/pending-commit.md`.
Close: tick `9adc5376`, `complete_todo` (needs the `sync_todo` MCP, currently disconnected, so I'll report this to the user if it stays unavailable), re-run the sync, rebase.

## Verification

After each todo: the whole test command above is green, `sync.py --check` passes, `git diff <bak-tag> HEAD` is empty after the rebase, and the sync shows the todo ticked.
At the end, report what is done, what could not be verified without a live session (hooks only fire in a fresh Claude session), and anything left for the user.
