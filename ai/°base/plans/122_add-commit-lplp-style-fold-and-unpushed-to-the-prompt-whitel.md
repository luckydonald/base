# Add `/commit-lplp-style`, `fold` and `unpushed` to the prompt whitelist

**Commit style:** Skill `/commit-with-lplp-style` is active — auto-commit following it for this implementation.

## Context

Todo `7a963fde-75b7-493a-8861-f6c44f291157`.
The `save-prompt` hook skips bare reminder prompts so they do not land in `ai/prompt.md`.
The skip list is `SKIP_PROMPTS` in `scripts/°base/ai/hooks/save-prompt/hook.py`.
It already holds `/commit-with-lplp-style`, `squash unpushed` and similar, but not the short alias `/commit-lplp-style`, nor the bare words `fold` and `unpushed`.

## Changes

1. `scripts/°base/ai/hooks/save-prompt/hook.py`, `SKIP_PROMPTS`:
   - In the skills block add `/commit-lplp-style` and `$commit-lplp-style` (Claude uses `/`, Codex `$`).
   - In the squashing/cleanup block add `fold`, `fold it`, `unpushed`, `fold unpushed` and `clean unpushed`.
     Only exact whole-prompt matches are skipped, so longer prompts containing these words are still logged.
2. `scripts/°base/tests/test_save_prompt_skip_commands.py`:
   - Add `test_lplp_alias_and_fold_commands_are_skipped`, looping over the new entries with `subTest` and asserting the logged query is empty (same shape as `test_loop_continuations_are_skipped`).
   - Add one lookalike to the logging test, e.g. `fold the laundry` stays logged.

## Verification

- `uv run scripts/°base/tests/test_save_prompt_skip_commands.py`, then the full `scripts/°base/tests/` suite.
- Run the project's lint/typing check if one exists for the hooks.
- Close the todo: tick the checkbox, `complete_todo`, sync, rebase into one work commit.
