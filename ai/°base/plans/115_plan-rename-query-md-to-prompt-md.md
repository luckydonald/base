# Plan: Rename `query.md` to `prompt.md`

**Commit style:** Skill `/commit-with-lplp-style` is active — auto-commit following it for this implementation.

## Context

Todo `a224a3e0-f8ab-47c5-9382-437b225227de`: the prompt log file is called `query.md`, and it should be called `prompt.md`.
Projects using this base already have their own `ai/query.md` (their prompt log, with history), so the rename must migrate such files instead of leaving a stale `query.md` next to a fresh `prompt.md`.
The base repo itself has two such files: `ai/query.md` (the template shipped to other projects) and `ai/°base/query.md` (its own log).

## Findings

- All hooks get the path from `resolve_log_path("ai/query.md", "ai/°base/query.md")` in `scripts/°base/ai/hooks/_lib.py:679`, which also handles `by-issue/<KEY>/` routing.
  Callers: `_lib.py` (2×), `compact_result.py`, `save-command-decision/hook.py`, `save-compact-prompt/hook.py`, `save-decision/hook.py`, `save-plan/hook.py` (3×), `save-prompt/hook.py`.
- Other live usages:
  - `scripts/°base/init/link_subproject.py:744` seeds `ai/query.md` from `scripts/°base/init/templates/query.md`.
  - `.pre-commit-config.yaml:28-33` (`base-query-md-guard`, `files: ^ai/query\.md$`) and `scripts/°base/git/hooks/push/check_base_query_md.py` block pushing `ai/query.md` from the base repo.
  - Docs and skill text: `ai/°base/AGENTS.md:107-108`, `ai/skills/commit-with-lplp-style/SKILL.md` (lines 23, 134, 135, 159), docstrings in `sync_todos.py`.
  - Tests: `test_ai_hooks_base_routing.py` (many), `test_save_*`, `test_check_base_query_md.py`, `test_commit_style_lib.py`, `test_git_split_classify.py`, `test_git_split_push_checks.py`.
- Plan, errors and output files under `ai/°base/{plans,errors,output}` and `ai/plans` only mention `query.md` as history, so they stay untouched.
- Neither `ai/prompt.md` nor `ai/°base/prompt.md` exists yet, so there are no collisions in this repo.
- The `save-prompt` hook also names things like `000_online_query.md` (`save-prompt/hook.py:692`), which is a plan artifact and not the log, so it stays.
- Downstream merge: git's rename detection will usually carry a project's `ai/query.md` edits over to `ai/prompt.md` when it merges the renamed base file, but not reliably (a big log vs. a tiny template).
  So the migration has to live in code as well.

## Design

A single helper `migrate_query_to_prompt(query_path, prompt_path)` in `scripts/°base/ai/hooks/_lib.py`, called from `resolve_log_path` before it returns, so every hook migrates on first use.
It follows the todo's rules, working per directory (also the `by-issue/<KEY>/` ones):

1. `query.md` missing: nothing to do.
2. `prompt.md` missing, or identical to the `base/base` version (the shipped template, `scripts/°base/init/templates/prompt.md`): delete `prompt.md` if present, then `git mv query.md prompt.md`, as two separate commits (delete, rename), so git history follows the file.
3. Both exist with identical content: keep the one with the longer history in this repo.
   Compare `git log --oneline --follow` counts for each path, skipping commits that came from `base/base` (commits reachable from `base/base`, if that ref exists).
   Delete the other (1 commit), and if `query.md` is the one that remains, rename it (1 commit).
4. Both exist and differ: leave both alone, print a warning to stderr, and keep logging to `prompt.md`.
   Never overwrite.

The migration commits are plain commits with a message in the repo's `ai:` auto-commit style, made only with explicit paths (never `git add -A`), and are skipped (file operations only, no commit) when the repo is not clean for those paths.

## Steps

1. Pure rename first (so git shows moves, per the commit style):
   - `git mv ai/query.md ai/prompt.md`, `git mv "ai/°base/query.md" "ai/°base/prompt.md"`, `git mv scripts/°base/init/templates/query.md scripts/°base/init/templates/prompt.md`.
   - Commit as its own commit with content unchanged.
2. Point the code at the new name:
   - `resolve_log_path` call sites and docstrings: `ai/query.md` becomes `ai/prompt.md`, `ai/°base/query.md` becomes `ai/°base/prompt.md`.
   - `link_subproject.py` copies `prompt.md` and runs the same migration for the subproject.
   - Rename `check_base_query_md.py` to `check_base_prompt_md.py` (and its test), update the hook id, name and `files:` regex in `.pre-commit-config.yaml`.
   - Update `AGENTS.md`, `SKILL.md` (all four mentions) and the `sync_todos.py` docstrings.
   - Update the `ai/query.md` classification entries in tests and in the split classifier if it has a path list (`.ai-ignore` fallback), checking `scripts/°base/git/°split_lib/classify.py` for the literal.
3. Add the migration helper in `_lib.py` and call it from `resolve_log_path`.
4. Tests (`scripts/°base/tests/`):
   - New `test_migrate_query_to_prompt.py` covering the four cases above, plus a `by-issue` directory.
   - Sweep the existing tests from `query.md` to `prompt.md`.
5. Docs: note the rename and the migration in `ai/°base/AGENTS.md`.
6. Add the new i18n keys: none (no UI strings).

## Verification

- `uv run python -m unittest discover -s scripts/°base/tests` (or the repo's usual test command) is green, including the new migration tests.
- Run `pre-commit run --all-files` for the renamed guard hook.
- Manual check in a scratch git repo: an old `ai/query.md` log is renamed to `ai/prompt.md` by the next hook run, history intact (`git log --follow`).
- `git grep -n "query\.md"` outside `ai/°base/{plans,errors,output}`, `ai/plans` and `ai/output` returns nothing.

## Open question

Should the old `query.md` name keep working as a read fallback for other tools (Codex, IDE links in old logs)?
The plan assumes no, since old logs only contain relative links to other files and not to `query.md` itself.
