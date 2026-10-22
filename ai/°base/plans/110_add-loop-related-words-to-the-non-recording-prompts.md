# Add loop related words to the non-recording prompts

Ported from `docker-tg-bot` (its plan `028`, todo `a1669ca6-fbea-4c02-a8de-f61e5e778280`), where the change was first made in that repo's copy of `scripts/°base/`.

**Commit style:** Skill `/commit-with-lplp-style` is active — auto-commit following it for this implementation.

## Context

The todo asks for loop related words in the "non-recording prompts": the `SKIP_PROMPTS` set in the `save-prompt` hook. A prompt that equals one of its entries (after `.strip()`) is not written to `ai/query.md` and gets no `ai: updated prompt` commit. Today it holds the "commit", "squash", "continue", "yes" style one-liners. Todo description lists three new entries: `continue loop`, `resume loop`, `/todo-loop`.

## Findings

- `scripts/°base/ai/hooks/save-prompt/hook.py:77` `SKIP_PROMPTS`, checked at line 1043 (`prompt.strip() in SKIP_PROMPTS`, exact, case-sensitive).
- Existing bug in the same set (already fixed upstream in `4eaaea063`, so not repeated here): `"yes, fix this", "fix", "fix this", "fix it"` has no trailing comma before `# misc commands` / `"/rename"`, so Python concatenates them to `"fix it/rename"`. Neither `"fix it"` nor `"/rename"` is skipped today (`"/compact"` is fine).
- No other list of these phrases (grep for `non-recording`/`SKIP_PROMPTS` finds only the hook and a comment in `tests/test_save_plan_decisions.py:114`).
- Test pattern to reuse: `scripts/°base/tests/test_save_prompt_loop_tick.py` and `test_save_prompt_queued_commands.py` (`init_repo`, `run_hook` from `test_ai_hooks_base_routing.py`).

## Changes

1. `hook.py`: add a `# loop` group to `SKIP_PROMPTS`: `"continue loop"`, `"resume loop"`, `"/todo-loop"`, plus the Codex form `"$todo-loop"` (the comment above the set says Claude uses `/skill-name`, Codex `$skill-name`).
2. ~~`hook.py`: add the missing comma after `"fix it"`~~ Already in `base/base`, dropped.
3. Extend `scripts/°base/tests/test_save_prompt_skip_commands.py` (upstream's equivalent of the new `test_save_prompt_skip.py` of `docker-tg-bot`): for each of the new phrases, run the hook on a temp repo and assert no `ai/query.md` entry/commit; and one control prompt (`"continue loop please"`) that is still logged (exact match only).

## Verification

- `uv run --project scripts/°base python -m unittest discover -s scripts/°base/tests -v` (whole suite), the new module first.
- Lint: `ruff check scripts/°base` if configured in that project.

## Closing

One commit `[base] [docker-tg-bot] ai/hooks save-prompt: ai: Run: Skipped logging the loop continue prompts.` via `ai/git/pending-commit.md`, files added by explicit path. Then `scripts/tag_backup.py` and rebase folding the `ai:` commits.
