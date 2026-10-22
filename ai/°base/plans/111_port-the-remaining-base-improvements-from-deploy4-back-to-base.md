# Port the remaining `°base` improvements from `deploy4` back to `base/base`

**Commit style:** Skill `/commit-with-lplp-style` is active — auto-commit following it for this implementation.

## Context

Merging `base/base` into `deploy4` conflicts in `scripts/°base/**` and in a few shared files (`ai/skills/*`, `ai/settings/*`, `.claude/settings.json`).
The `[base]` fixes were made inside `deploy4` (the consumer copy) instead of upstream, so both sides evolved.
A dry run (`git merge-tree --write-tree HEAD base/base`, merge-base `601dd3145`) shows most of the `°base` conflicts are the same fix written twice with different comment wording.
`base/base` (local checkout `../base`, branch `base`, same tip `d83a11f88`) already has these, so only a merge resolution is needed for them:

- `get-base.py` `_is_valid_worktree` resolve, `°reffiles_lib/commit.py` `link_target` resolve, `record-memory` `target.parent.resolve()`.
- `checkout.sh` symlinked-hook skip (`d4015887c`) and `test_checkout_lfs_hooks.py`.
- The test fixes (`FETCH_HEAD`, `bak/old-backup`, resolved toplevels) in `c177045fa`.
- The skill changes (`todo-loop`, `commit-with-lplp-style` squash rule, `sync-todo-mcp`) in `7cf701ced`, `d665f86d3`, `52f321c1f`.

So there are only a few `deploy4`-only improvements that have to go upstream.
The user also wants the prompts and plans that led to them recorded under `ai/°base/` in the base repo.

## What is missing upstream

1. `save-prompt/hook.py` `SKIP_PROMPTS`: `continue loop`, `resume loop`, `/todo-loop`, `$todo-loop` (deploy4 commit `b39557907`, plan `ai/plans/028_add-loop-related-words-to-the-non-recording-prompts-todo-a16.md`).
   Upstream already fixed the missing comma after `"fix it"`.
2. Ruff cleanup in the same hook (`a972e8618`): drop the unused `noqa: E402` on `import compact_result` / `from _lib import (`, parenthesize the `Trigger:` f-string pair in `_online_query_artifact_text`, and pass `check=False` to the two `subprocess.run` calls in `_handle_compact_prompt`.
3. Tests for item 1.
   Upstream has `tests/test_save_prompt_skip_commands.py` (a different class), so extend it with the loop phrases and the longer-prompt-still-logged case from deploy4's `tests/test_save_prompt_skip.py`, instead of adding a second file.

Before editing, re-verify each item against `../base` (e.g. `grep SKIP_PROMPTS`), because upstream keeps moving.
Anything found already present is dropped from the list.

## Steps

### A. Commit in `../base` (branch `base`, lplp style, `[base]` format from `ai/°base/AGENTS.md`)

The checkout has unrelated untracked files (`ai/°base/errors/*`, `output/agents/*`, `scripts/.DS_Store`, `scripts/°base/tests/aaa.py`).
Stage by explicit path only and leave those alone.
Read `../base/CLAUDE.md` first and use its pending-commit file, `tag_backup.py` and fold procedure.

1. Commit `[base] [docker-tg-bot] ai/hooks save-prompt: ai: Run: Skipped logging the loop continue prompts.` with the `hook.py` change and the extended test.
   The `[docker-tg-bot]` source-repo bracket is allowed because this session names `DockerTgBot` as the origin.
2. Commit `[base] [docker-tg-bot] ai/hooks save-prompt: ai: Run: Fixed the ruff findings in the \`save-prompt\` hook.` for the cleanup (item 2).
   Check `git log -5 -- <file>` first for the established `component-or-topic` wording.
3. Run the affected tests from `../base`: `uv run python -m unittest scripts/°base/tests/test_save_prompt_skip_commands.py` (or the repo's runner) plus `ruff check` on the hook.
4. No `Co-Authored-By` or `Claude-Session` trailers (the pre-commit hook rejects them), so ignore the attribution reminder.

### B. Record the prompt and plan history in `../base/ai/°base/`

- Append the relevant `ai/query.md` entries from `deploy4` (the prompts around `b39557907` and `a972e8618`, plus this request) to `../base/ai/°base/query.md`, in the same `❯ …` format.
  The hooks that normally write it route by repo, so write it directly and do not trigger them.
- Copy plan `028_add-loop-related-words-…` to `../base/ai/°base/plans/110_add-loop-related-words-to-the-non-recording-prompts.md` (next free number after `109`; re-check with `ls`).
  Keep its text, only drop the `deploy4`-specific path references.
  Add the ruff-cleanup and this port as `111_…` if a plan existed for them; otherwise only a prompt entry.
- Fold these as `ai:` auto-commits into the matching work commit per the skill (the final plan revision folds into the run commit, earlier revisions stay `ai: Plan:` / `ai: Plan update:`).
- Do not push.
  Leave that to the user.

### C. Resolve the merge in `deploy4` (only after A, on the user's go-ahead)

Once `../base` has the commits, fetch `base` and merge `base/base`.
Take the upstream side for every `°base` conflict, since upstream is now a superset.
Leave the other conflicts (`.claude/settings.json`, `ai/settings/settings.json`, `ai/settings/sync_todos.json`, the three skills) for a separate look, because they may hold `deploy4`-specific settings.
This step is not part of the commit-back itself.

## Critical files

- `../base/scripts/°base/ai/hooks/save-prompt/hook.py` (SKIP_PROMPTS, ruff fixes)
- `../base/scripts/°base/tests/test_save_prompt_skip_commands.py`
- `../base/ai/°base/query.md`, `../base/ai/°base/plans/`
- Source of truth in this repo: commits `b39557907`, `a972e8618`, `ai/plans/028_*`, `scripts/°base/tests/test_save_prompt_skip.py`

## Verification

- `git -C ../base log --oneline -6` shows the new commits with `[base]` prefix and no trailers.
- `git -C ../base status --short` shows only the pre-existing untracked files.
- Tests above pass, `ruff check` on the hook is clean.
- `git merge-tree --write-tree HEAD base/base` in `deploy4` (after fetching) no longer lists `scripts/°base/**` conflicts for the ported files.
