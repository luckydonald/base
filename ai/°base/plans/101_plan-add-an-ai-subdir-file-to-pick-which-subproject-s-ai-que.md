# Plan: Add an `ai/.subDir` file to pick which subproject's `ai/query.md` etc. is used

**Commit style:** Skill `/commit-with-lplp-style` is active — auto-commit following it for this implementation.

Todo: `todo:6bc531bc-61bf-46b2-9bd1-2955685b80db` (project `base`, `ai/todo.md`).

## Context

The AI hooks write `query.md`, plans, decisions and commit templates under the `ai/` folder of the directory Claude was launched from (`_subproject_root()`: `CLAUDE_PROJECT_DIR`, else cwd).
When Claude is launched at the git root of a monorepo but the work belongs to one subproject, everything lands in the root's `ai/`.
An `ai/.subDir` file lets the user redirect those artifacts to a subproject's `ai/` folder, the same way `ai/.by-issue` already adds a `by-issue/<KEY>/` level.

Requested semantics:

- File not present: behaviour as before.
- File present: its content is the relative path from the git root to the subproject whose `ai/` folder is used. Trailing newlines and whitespace are stripped.
- The file is added to `.gitignore`.

## Findings

- `scripts/°base/ai/hooks/_lib.py`: `_ai_prefix_root()`, `resolve_log_path()` (builds `<subproject>/<ai_prefix>/…`, the central path generation), `append_and_commit()` (passes the root to `°reffiles_lib` for `@path` mentions).
- `scripts/°base/ai/hooks/°commit_style_lib/__init__.py`: `_read_by_issue()` (the precedent), `base_ai_commit_subject()`, `commit_message()` (looks up `ai/commit-templates/*` under the root). It deliberately duplicates `_subproject_root()` to avoid a circular import.
- `.by-issue` lives at `<root>/<ai_prefix>/.by-issue`, so `ai/°base/.by-issue` inside the base repo and `ai/.by-issue` elsewhere. `.subDir` follows the same location rule.
- `_subproject_root()` is also used for Claude's own per-project state (`_encoded_project_dir`, memory dirs in `record-memory/hook.py`, `memory/delete.py`, `memory/promote.py`). That must keep pointing at the launch directory, since Claude writes its transcripts there.

## Design

Keep `_subproject_root()` as "launch directory" and add a new `_ai_root()` for "where the `ai/` artifacts go":

1. `_read_sub_dir(launch: Path, ai_prefix: str) -> str` in `°commit_style_lib/__init__.py`, next to `_read_by_issue`. Returns the stripped content of `<launch>/<ai_prefix>/.subDir` or `""`.
2. `_ai_root()` (same module, re-exported by `_lib.py` like `_read_by_issue`): resolves the launch directory and git root, works out `ai_prefix` from them as `base_ai_commit_subject()` does, and returns `git_root / sub_dir` when the file is set, else the launch directory.
   - A path that escapes the git root (absolute, or `..`), or a directory that does not exist, falls back to the launch directory, since a hook must never fail a prompt. It logs one line to stderr.
3. Switch the artifact-path call sites from `_subproject_root()` to `_ai_root()`:
   - `resolve_log_path()`, `_ai_prefix_root()`, `append_and_commit()` (the `process_referenced_files` root), `base_ai_commit_subject()` and `commit_message()`.
   - `.by-issue` is then read from the redirected root's `ai/` folder, so each subproject keeps its own issue key.
4. Leave the memory and `_encoded_project_dir` call sites on `_subproject_root()`.

Files to change:

- `scripts/°base/ai/hooks/°commit_style_lib/__init__.py`, `scripts/°base/ai/hooks/_lib.py`
- `.gitignore` (add `ai/.subDir` and `ai/°base/.subDir`, in the section where `.by-issue` is handled if it is listed there)
- `ai/°base/AGENTS.md` (one line in the hooks section on `.subDir`)
- `scripts/°base/tests/test_ai_hooks_base_routing.py` (tests below)

## Tests

In `test_ai_hooks_base_routing.py`, next to the `.by-issue` cases:

- `.subDir` containing `sub/proj` (with trailing newline): the prompt hook writes `sub/proj/ai/query.md`, and nothing appears in `ai/query.md`.
- `.subDir` combined with `.by-issue` in the subproject's `ai/`: path is `sub/proj/ai/by-issue/<KEY>/query.md`, subject carries the key.
- Base repo variant: `ai/°base/.subDir` redirects `ai/°base/query.md`.
- Missing target directory and an escaping path (`../x`) fall back to the launch directory.
- No `.subDir`: unchanged (the existing tests cover it).

## Verification

- `uv run python -m unittest scripts/°base/tests/test_ai_hooks_base_routing.py`, then the whole `scripts/°base/tests` suite and the repo's lint (`pre-commit run --files …`).
- Manual: create `ai/°base/.subDir` in a scratch clone, run the save-prompt hook with a fake payload, check where `query.md` lands and the commit subject.
