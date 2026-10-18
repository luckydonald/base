# Todo loop for `base`

## Context

Work through the open todos of the `base` project one at a time, following the `todo-loop` skill and the `sync-todo-mcp` skill.
The todos live on CalDAV (calendar 7, "TODO: Today") and are mirrored into `ai/todo.md` by `/Users/user/Documents/programming/Python/DockerTgBot/scripts/sync_todos.py`.

## Parameters

- **Project**: `base` (tags `base`, `baseBase`), todo file `ai/todo.md`, calendar id `7`.
- **Commit style**: `commit-with-lplp-style` is active.
  The origin is `luckydonald/base`, so the opt-in question is skipped and assumed `yes`.
  Commit format is `[base] topic: ai: Run: Short summary.`, one commit per todo, messages via `ai/git/pending-commit.md`, never any trailer lines (`Co-Authored-By`, `Claude-Session`).
- **Code style**: `/code-style` applies, Markdown prose breaks only at sentence ends.
- **Tests**: `scripts/°base/.venv/bin/python3 -m unittest discover -s scripts/°base/tests -p <module>.py`, plus `python3 scripts/°base/ai/settings/sync.py --check` whenever settings or skills change.
  The full suite takes about 77 minutes, run it in the background only when needed.
- **Backup tags**: `base` has no `scripts/tag_backup.py`, so use `/Users/user/Documents/programming/Python/DockerTgBot/scripts/tag_backup.py` by absolute path.
- **Bugsink**: none configured for `base`, so the "all done" Bugsink check is skipped.
- **Untracked files** already in the tree (`ai/°base/errors/27.md`, `3_.md`, `output/agents/*`, `scripts/°base/tests/aaa.py`) are never committed.
- **No skill-creator evals** for now (they exhaust the usage limit), unless spread out over time.

## Workflow per todo

1. Reload with `cd /Users/user/Documents/programming/Python/DockerTgBot && uv run --script scripts/sync_todos.py --project base`, then read `ai/todo.md`.
2. Intel in normal mode, no project edits.
3. Plan mode for that one todo, wait for the user's accept.
4. Implement with tests, commit as plain new commits.
5. Close: tick the box, `complete_todo(7, uid, done=true)`, re-run the sync.
6. Rebase last: tag the prior HEAD, fold `ai:` auto-commits into the work commit, verify `git diff <bak-tag> HEAD` is empty.
7. Update **Current task**, repeat.

## Ordered list

1. `9adc5376` bugsink permissions: done.
2. `56f6ee1a` `checkout.sh` symlink guard: done.
3. `268ba6c5` code style for `/plan`: done (already fixed by the hook, evals skipped, ticked).
4. `5e80abad` Strip the "next message may contain a correction" note from plan decisions.
4. done (`7877487cc`).
5. `66f35747` `@file)` mention detection: done, already fixed by `0d86e4572`, ticked.
6. `b7a5299c` Referenced-file auto-commit for staged and previously committed files: done, same commit, ticked.
7. `be604b2a` Link `/skill` calls to their `SKILL.md`: done, same commit, ticked.
8. `e7df2be3` Skill for `download_ref.py` (at least `--no-ide`).
9. `51f4adc0` Proper diff in the settings sync script.
10. `7eb9a977` Plan-confirm hook syncs the plan once more.
11. `b8ae433f` Why `ai/memories/MEMORY.md` is skipped in commits.
12. `6f2b2450` Re-sync per-file subproject symlinks from git triggers.
13. `58a06dbd` `.run/.subprojectIgnore`.

## Current task

Items 1 to 3 are done, committed, folded and completed on CalDAV (`d9c9c0c4b`, `d1dbf09e0`, `c9d1085e2`).
Known pre-existing test failures, ignore: `test_ai_hooks_base_routing` (8), `test_get_base` (2), `test_tag_backup.test_remove_flag_deletes_tags_in_parent_history` (1).

### Plan for item 10 (`7eb9a977`): re-sync the plan file on plan confirm

Problem: `save-plan/hook.py` snapshots the plan into `ai/°base/plans/NNN_slug.md` on `Write`/`Edit` of the harness plan file (`~/.claude/plans/*.md`) and on `ExitPlanMode`.
When the agent edits the plan with `echo`, a Python script or another Bash command, no `Write`/`Edit` hook fires, and the path is often built (`CLAUDE_PLAN_DIR + NAME + '.md'`) so it never appears in one piece.
At `ExitPlanMode` the hook then takes `tool_input.plan` first and only then `tool_response.plan`, neither of which is guaranteed to be what is on disk now; it reads the file (`tool_response.filePath`) only when both are empty.
(The todo calls it "show-plan-confirm-action"; no hook has that name in `base`, the plan-confirm handling is `ExitPlanMode` in `save-plan/hook.py`, whose decision is recorded by `_record_claude_plan_acceptance`.)

Change, all in `scripts/°base/ai/hooks/save-plan/hook.py`:
1. New `_plan_from_disk(payload, session)`: for Claude, the current text of the plan file, from `tool_response["filePath"]` when `_is_plan_file_path()` accepts it, else the session's recorded `source` filename looked up in `<CLAUDE_CONFIG_DIR or ~/.claude>/plans/`.
   Returns `""` when the file is missing or unreadable.
2. In `main()`, the `ExitPlanMode` branch tries `_plan_from_disk` first (Claude only), then falls back to the existing `tool_input.plan`, `tool_response.plan`, Copilot session order.
   The existing dedup (identical content skips, changed content commits `ai: save plan NNN_slug` under the same prefix, renaming if the slug changed) then does the "write and commit it once more".
3. Not changed: Codex and Copilot paths, the `Write`/`Edit` handling, the `done` marker logic.

Tests in `scripts/°base/tests/test_save_plan_decisions.py` (hook run through `run_hook` with a plan file inside a temporary `.claude/plans/` dir):
- A `Write` snapshot, then the file edited on disk without a hook, then `ExitPlanMode` whose `tool_response.plan` is the stale text: the second commit contains the on-disk text.
- `ExitPlanMode` with unchanged file content creates no extra plan commit (dedup).
- `filePath` outside any plans dir (like the existing fixture's `/tmp/plan.md`) is ignored and the old fallback order applies.

Verify: `test_save_plan_decisions.py`, plus `test_ai_hooks_base_routing.py -k Plan` to check nothing in the routing broke (the known `/private/var` failures aside).
Commit `[base] ai/hooks save-plan: ai: Run: Re-read the plan file from disk when a plan is confirmed.` (topic wording from `git log --oneline -5 -- scripts/°base/ai/hooks/save-plan`), then tick, tag, fold, `complete_todo`, sync.

### Done: plan for item 9 (`51f4adc0`): proper diff in the settings sync

Problem: `sync.py` (`scripts/°base/ai/settings/°settings_lib/cli.py`) only prints file names (`Would write: …` / `Wrote: …` / the `--check` list).
When the wrong file is detected as newest (`_load_layer` merges native sources sorted by `st_mtime`), an older file can overwrite fresh edits, and nothing shows it.
The todo wants a real diff for both the dry run and the actual run so the agent or user can spot that.

Design:
1. `json_io.py`: add a module-level `CHANGE_DIFFS: dict[str, str]` plus `_record_change(path, old_text, new_text)` which stores a `difflib.unified_diff` (`a/<path>` and `b/<path>` labels, 3 lines of context, empty `old_text` for a new file).
   Add `_json_text(data)` (`_dump_json(data) + "\n"`, already what `_write_json` writes) so the JSON and the diff use the same text.
2. Record the diff exactly where a change is detected, before it is applied:
   - `cli._apply_or_check`, in the render loop after `_same_json(...)` is false: old text is the file's current text (or empty), new text `_json_text(data)`; same for the `claude_mcp_path` write.
   - `json_io._write_text_if_changed`, which covers `codex_rules`, `codex config.toml`, the skill files and the command shims.
   - Symlink changes in `skills.py` (`_write_symlink_if_changed`, `_write_dir_symlink_if_changed`) have no text, so record a one-line `symlink <link> -> <target>` entry instead.
3. `cli.main`: clear `CHANGE_DIFFS` at the start and add `_print_changes(changed)`, replacing the three separate loops (`Wrote:`, the `--check` list, `Would write:`).
   For each path it prints the existing line, followed by its diff (if any), and a one-line summary `N files, +A -R lines`.
   A diff with removed lines in the shared source `ai/settings/settings.json` gets a `WARNING: removes lines from the shared source, check the newest-file detection` line, since that is the case the todo is about.
   `--check` still exits 1, and the diff makes the pre-commit failure self-explanatory.
   The merge auto-sync branch prints the diffs too.
4. Tests in `scripts/°base/tests/test_ai_settings_sync.py` next to `test_apply_or_check_writes_and_is_idempotent`:
   - A change in dry mode (`apply=False`) records a diff containing the `-` and `+` lines and writes nothing.
   - The same with `apply=True` records the diff and writes the file; an idempotent second pass records nothing.
   - A new file gets an all-`+` diff.
   - `_print_changes` output contains the diff and the warning when the shared source loses lines.

No change to the return type of `_apply_or_check` (`list[str]`), so existing callers and tests are unaffected.
Verify: `test_ai_settings_sync.py`, then `sync.py --dry-run` and `--check` for real on the repo (clean, so "already in sync"), plus a manual dry run with a temporary edit of `.claude/settings.json` that is reverted.
Commit `[base] ai/settings sync: ai: Run: Showed a unified diff of every file the settings sync would write or wrote.` (check the topic wording with `git log --oneline -5 -- scripts/°base/ai/settings`), then tick, tag, fold, `complete_todo`, sync.

### Done: plan for item 8 (`e7df2be3`): skill for `download_ref.py`

Context: `scripts/download_ref.py` (symlink to `scripts/°base/download_ref.py`, a `uv run --script` entry point into `scripts/°base/ai/references/°dllink_lib/cli.py`) downloads documentation pages into `ai/references/<host>/…` as Markdown.
There is no skill telling an agent when and how to use it, and the default behavior opens the downloaded file in an IDE (`--open-ide`, setting `ide`), which hangs or pops windows during agent runs, hence the todo's "at least `--no-ide`".

Facts from `cli.py`:
- Usage `scripts/download_ref.py [URL] [flags]`, URL may also be piped on stdin.
- Flags: `--output-root` (default `ai/references`), `--open-ide/--open/--ide COMMAND`, `--no-ide` (`--no-open-ide`, `--no-ide-open`), `--no-git-add`, `--no-git-commit`, `--no-git` (both).
- By default it does `git add` and `git commit --no-verify --only <file>` with the message ``ai/references: Downloaded `<path>`.``, then opens the IDE.
- Providers: `providers/github.py` and `providers/generic.py`, with a Markdown variant tried first and the web archive as a fallback (prints `archive fallback: snapshot from …` to stderr).
- Output is printed as `download:`, `wrote:`, `git add:`, `git commit:`, `open:` lines, errors exit 1 as `download-link: …`.

Change:
1. New `ai/skills/download-ref/SKILL.md` (frontmatter `name`, `description` that says when to use: user shares a docs URL to keep as a reference, asks to "download/save this doc", or an `@ai/references/…` path is missing).
   Body: how to run it, always pass `--no-ide` as an agent, when to add `--no-git`/`--no-git-commit` (the commit is made on its own and bypasses hooks via `--no-verify`, so mention it in the lplp-style flow), where the file lands, how to cite it with `@ai/references/<host>/…`, and how to check a failure (exit 1, archive fallback note).
   Keep it short and in the style of `ai/skills/sanitize-error-logs/SKILL.md`.
2. Run `python3 scripts/°base/ai/settings/sync.py` to generate the `.claude`/`.codex` skill copies and command file, then `--check`.
3. No script changes, and no live download (would hit the network and commit); verify the flags with `scripts/download_ref.py --help`.

Commit `[base] ai/skills: ai: Run: Added a `download-ref` skill for `scripts/download_ref.py`, using `--no-ide` as an agent.`, staging the skill plus the sync-generated files.
Then tick, tag, fold, `complete_todo`, sync.

### Done: plan for item 4 (`5e80abad`)

Problem: when the user denies a plan or a command with typed text, Claude Code appends a boilerplate sentence to the deny message:
`Note: The user's next message may contain a correction or preference. Pay close attention — if they explain what went wrong or how they'd prefer you to work, consider saving that to memory for future sessions.`
It lands in `ai/°base/query.md` inside the `❯ Plan denied:` blocks (and `Command denied:` ones), e.g. around lines 5989 to 6010.

Where it comes from: `rejection_reason()` in `scripts/°base/ai/hooks/_lib.py:381` extracts everything after `user said:\n` via `_REJECTION_REASON_RE` (`_lib.py:165`).
The text goes through `_render_plan_rejection` and `_render_command_rejection` into `render_decision_block`.
(The todo names `save-decision/hook.py`, but that hook only handles `AskUserQuestion`, the plan denials are recorded via `_lib.py` and `save-plan/hook.py`.)

Change:
1. In `_lib.py`, add a compiled regex for the trailing note (anchored at the end, preceded by optional blank lines, tolerant of the dash variant and trailing whitespace) and apply it in `rejection_reason()` after the match.
   - If nothing is left after stripping, return `None`, so the block becomes the plain `Plan denied.`
   - Fixing it in `rejection_reason()` covers both plan and command denials, as both go through it.
2. Tests in `scripts/°base/tests/test_save_plan_decisions.py`, next to `test_deny_with_reason_records_reason`:
   - A deny with reason plus the note records only the reason (`assertNotIn("next message may contain", content)`).
   - A deny where the message is only the note records plain `Plan denied.`
   - Reuse `_write_rejection_transcript`, extending it if needed to take the full message text.
3. Do not rewrite the existing historic entries in `ai/°base/query.md`, only new ones are affected.

Verify: run `test_save_plan_decisions.py` and `test_ai_hooks_base_routing.py`'s unaffected parts are not needed; run `python3 scripts/°base/ai/settings/sync.py --check`.
Commit `[base] hooks: ai: Run: Stripped the correction note from recorded plan and command denials.` (check `git log --oneline -5 -- scripts/°base/ai/hooks/_lib.py` for the established topic wording first), then tick, tag, fold, `complete_todo`, sync.

## Verification

After each todo: the relevant unit tests are green, `sync.py --check` passes when settings or skills changed, `git diff <bak-tag> HEAD` is empty after the rebase, and the sync shows the todo ticked.
At the end, report what is done, what could not be verified without a live session (hooks only fire in a fresh Claude session), and anything left for the user.
