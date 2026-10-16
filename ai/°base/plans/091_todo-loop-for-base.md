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

Item 1 of 13, `9adc5376` (bugsink permissions): done, committed (`d9c9c0c4b`), box ticked locally, folded by rebase.
`complete_todo` on CalDAV is still pending because the `sync_todo` MCP is disconnected, the user accepted that a later sync may overwrite the tick.
Item 2 of 13, `56f6ee1a` (`checkout.sh` symlink guard): done, committed (`86f60dd22`), box ticked locally, folded by rebase.
Known pre-existing test failures, ignore: `test_ai_hooks_base_routing` (8), `test_get_base` (2), `test_tag_backup.test_remove_flag_deletes_tags_in_parent_history` (1).
The full suite takes about 77 minutes, run it in the background.
Item 3 of 13, `268ba6c5` (code style not loading for `/plan`): intel done, awaiting plan accept.
Sync reload is done: `[base] up to date (13 todos)`.
Run the script from `/Users/user/Documents/programming/Python/DockerTgBot` with `uv run --script scripts/sync_todos.py --project base`, because run from `base` uv picks up DockerTgBot's `.python-version` (`docker-tg-bot-3.10.0`) and fails.

### Plan for item 3 (`268ba6c5`)

Findings: this todo is already implemented by commit `1152e0d72` ("Made the Markdown code style load reliably for `/plan`").
- The `code-style` skill description now leads with the plan trigger.
- `scripts/°base/ai/hooks/plan-style-context/hook.py` is a synchronous `UserPromptSubmit` hook that injects `additionalContext` when `permission_mode == "plan"` or the prompt starts with `/plan`, and it is registered in `ai/settings/settings.json:184` and `.claude/settings.json:176`.
- `test_plan_style_context.py` passes (3 tests, rerun just now).
- It works live: the injected "read `ai/skills/code-style/references/md.md`" context arrived with this session's first prompt, and every plan prompt since.
- That commit ticked the todo only in the old `ai/°base/todos.md`, not in `ai/todo.md`, which is why the box is still open.

Not done by that commit: the todo's hint to use the official skill-creator skill, i.e. its description-optimization loop (`scripts/run_loop.py`) to tune the new `code-style` description.
The user decided to run it (AskUserQuestion answer "Run skill-creator eval first").

Both MCP servers are reconnected (`/mcp`), so `complete_todo` works again.
First step after the accept: load the `mcp__sync_todo__complete_todo` schema and complete `9adc5376` and `56f6ee1a` (items 1 and 2, both committed and ticked), then re-run the sync.

Pitfalls found in `skill-creator/scripts/run_eval.py` and how the plan avoids them:
- It writes a temporary `.claude/commands/<name>.md` into the project root found by walking up from the cwd and then runs `claude -p` there.
  In this repo every one of those headless runs would fire the `UserPromptSubmit` hooks, i.e. `save-prompt` writing `ai/°base/query.md` and committing `ai: updated prompt`, hundreds of times.
- So the loop runs from an isolated scratch project in the scratchpad: `<scratchpad>/code-style-eval/.claude/skills/code-style/` holds a copy of `ai/skills/code-style/` (with `references/`), no hooks, no git repo.
  The repo itself is only touched at the end, when the winning description is applied by hand.
- The `claude -p` runs use the same model as this session, `claude-sonnet-5-5`, so triggering matches what the user experiences.
- Cost: 20 queries, 3 runs each, the train and test sets re-evaluated for up to 5 iterations, 10 parallel workers, roughly 300+ headless calls, so expect tens of minutes and noticeable token use.
  It runs in the background and I report the iteration scores as they come in.

Steps:
1. Write 20 realistic trigger-eval queries to `<scratchpad>/code-style-eval/trigger-eval.json`, 10 should-trigger and 10 should-not-trigger.
   - Should-trigger: asks to write or revise a `/plan`, a plan file or a `README.md`/`AGENTS.md`/skill doc (md), and to write, edit or review `py`, `ts` and `vue` code, in casual wording and with detail (file paths, context).
   - Should-not-trigger near-misses: Rust, Go, shell or SQL work, JSON/YAML config edits, answering a question about a codebase without writing code, git operations, ordinary prose that is not Markdown docs.
   - Note the skill is also applied by the plan hook, so the eval measures the description only.
2. Show the set to the user with `assets/eval_review.html` (placeholders filled, written to the scratchpad, opened with `open`), let them edit and export, then read `~/Downloads/eval_set.json`.
3. Copy `ai/skills/code-style/` into the scratch project and run, in the background, from the scratch project dir:
   `python -m scripts.run_loop --eval-set <exported set> --skill-path .claude/skills/code-style --model claude-sonnet-5-5 --max-iterations 5 --verbose --results-dir <scratchpad>/code-style-eval/results` (with `PYTHONPATH`/cwd set to the skill-creator directory for `scripts.*` imports, as the scripts require).
4. Take `best_description` (chosen by held-out test score), show before and after with the scores, and apply it to `ai/skills/code-style/SKILL.md` frontmatter only if it is not worse than the current description on the held-out set.
   The description must keep the `/plan` first wording, since `plan-style-context/hook.py`, `AGENTS.md` and the commit `1152e0d72` rely on it.
5. Run `python3 scripts/°base/ai/settings/sync.py` (regenerates `.claude/commands/code-style.md`), `sync.py --check`, and `test_plan_style_context.py`.
6. Commit `[base] code style skill: ai: Run: Tuned the `code-style` skill description with the skill-creator trigger evals.` with the scores in the body, staging only `ai/skills/code-style/SKILL.md` and the regenerated command file.
7. Tick `268ba6c5` in `ai/todo.md` as its own commit, tag with `tag_backup.py`, fold the tick and auto-commits into the work commit, verify `git diff <bak-tag> HEAD` is empty, `complete_todo` it, and re-run the sync.

If the loop finds no better description than the current one, nothing is changed in the skill, the result is stated in the tick commit's body, and the todo is still ticked since the original problem is already fixed by the hook.

## Verification

After each todo: the whole test command above is green, `sync.py --check` passes, `git diff <bak-tag> HEAD` is empty after the rebase, and the sync shows the todo ticked.
At the end, report what is done, what could not be verified without a live session (hooks only fire in a fresh Claude session), and anything left for the user.
