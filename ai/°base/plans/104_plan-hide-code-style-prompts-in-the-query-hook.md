# Plan: hide `/code-style` prompts in the query hook

**Commit style:** Skill `/commit-with-lplp-style` is active — auto-commit following it for this implementation.

Todo `2eaeb8ce-67be-4878-a8df-3fb3311a4be8`.

## Context

`save-prompt/hook.py` (`scripts/°base/ai/hooks/save-prompt/hook.py`) skips prompts that exactly match an entry of the `SKIP_PROMPTS` set, so `/commit-with-lplp-style` never lands in `ai/query.md`.
`/code-style` is invoked with optional arguments (`/code-style .md .py`, `/code-style md`), so exact matching cannot cover it and those prompts get logged and auto-committed as `ai: updated prompt`.

## Findings

- The check is `if prompt.strip() in SKIP_PROMPTS: return 0` at about line 1038 of the hook.
- Pre-existing bug in the same set: `"fix it"` has no trailing comma, so Python concatenates it with the next entry into `"fix it/rename"`, and neither `"fix it"` nor `"/rename"` is skipped. It sits on the exact lines being touched, so it gets fixed as a separate commit first.

## Changes

1. Separate preceding commit: add the missing comma after `"fix it"` in `SKIP_PROMPTS`, plus a test that `"fix it"` and `"/rename"` are skipped.
2. Add `SKIP_PROMPT_COMMANDS = {"/code-style", "$code-style"}`, next to `SKIP_PROMPTS` so it is the array to fill, with the same Claude `/` and Codex `$` convention.
3. Add a small helper `is_skipped_prompt(prompt)` in the hook:
   - `stripped = prompt.strip()`
   - returns true if `stripped in SKIP_PROMPTS`
   - or if `stripped.split(maxsplit=1)[0] in SKIP_PROMPT_COMMANDS`, which covers the bare command and any suffix (`.md .py`, `md`).
   - Matching on the first whitespace-delimited token avoids skipping `/code-style-foo` or prose that merely mentions the command.
4. Replace the inline `in SKIP_PROMPTS` check in `main()` with the helper.

## Tests

New `scripts/°base/tests/test_save_prompt_skip_commands.py`, modelled on `test_save_prompt_loop_tick.py` (`init_repo` and `run_hook` from `test_ai_hooks_base_routing`):

- `/code-style`, `/code-style md`, `/code-style .md .py` and `$code-style md` write no `ai/query.md` entry.
- `/code-style-other` and `please run /code-style` are still logged.
- Existing `commit` skip still works.

## Verification

Run the new test file and the other `test_save_prompt_*.py` and `test_save_plan_decisions.py` tests with `uv run python -m unittest`, then the project's full test suite in `scripts/°base/tests`.
