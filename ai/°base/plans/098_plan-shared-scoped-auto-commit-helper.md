# Plan: shared scoped auto-commit helper

**Commit style:** Skill `/commit-with-lplp-style` is active — auto-commit following it for this implementation. Code follows `/code-style` (py: no `_` prefix on new identifiers, `# end if`-style block endings, full type annotations; md: no mid-sentence wrapping).

Todo: `todo:163fb511-e999-42c1-b288-818da77d2e40` (calendar 7).

## Context

`link_subproject.py` already has a safe auto-commit (`commit_blocker` + `commit_resync`): it commits only the given paths through plumbing (temporary index, `commit-tree`, `update-ref`), runs no hooks, refuses during merge/rebase/cherry-pick/revert/bisect/`index.lock`/detached HEAD, and leaves the paths staged on any failure.
Every other auto-committing site re-implements a weaker version of this by shelling out to `git commit --no-verify --only <paths>`, with no state checks (only `reffiles` has a partial one, `operation_in_progress`, and it ignores detached HEAD).
The todo asks for one shared Python function that all of them use.

Sites found (all in `scripts/°base/`):

- `init/link_subproject.py`: `commit_blocker`, `commit_resync` (the reference implementation, keep behaviour).
- `ai/hooks/_lib.py`: `append_and_commit` (prompt/decision/plan logs, called by most hooks).
- `ai/hooks/°reffiles_lib/commit.py`: `stage_and_commit_mentions`, `operation_in_progress`.
- `ai/hooks/record-memory/hook.py`: `_commit`.
- `ai/hooks/save-plan/hook.py`: `_commit`.
- `ai/hooks/record-codex-memory/hook.py`: `commit_project_memory` (raises on failure today).
- `ai/hooks/save-prompt/hook.py` (autoloads) and `ai/hooks/save-compact-prompt/hook.py` (compacted prompt): inline `git add` + `git commit`.
- Left alone on purpose: `°memory_lib/delete.py` (must run the pre-commit delete-marker hook), `link_subproject.commit_env_symlink` (own post-commit verify/purge dance), `ai/memory/codex-sync-audit.py` and `ai/memory/promote.py` (re-checked during implementation; migrated only if they have the same shape).

## Design

New package `scripts/°base/git/°scoped_commit_lib/__init__.py` (the `°*_lib` naming the repo already uses), imported the way `_lib.py` imports `°commit_style_lib`: a `sys.path.insert` of its parent, then `import_module`.
Public API, all fully typed, never raising:

- `commit_blocker(event: str | None = None, cwd: Path | None = None) -> str | None`: moved verbatim from `link_subproject.py`, `event` stays `"merge"` / `"rebase"` / `None`.
- `commit_staged_paths(paths: list[str], message: str, *, event: str | None = None, cwd: Path | None = None) -> str | None`: moved from `commit_resync`, message becomes a parameter. Returns the new sha, or `None` when nothing to commit, blocked, or failed (paths stay staged, reason on stderr).
- `stage_and_commit(paths: list[str], message: str, *, event: str | None = None, cwd: Path | None = None) -> str | None`: `git add -- <paths>` (skipping non-existent paths that are already staged as deletions), then `commit_staged_paths`. This is what the hooks call.

Decisions:

- Plumbing instead of `git commit --only`: it also works while `MERGE_HEAD` exists (post-merge) and never runs hooks, which matches today's `--no-verify`.
- Detached HEAD now skips the commit for the AI hooks too (staged only). That is a behaviour change from today and is what the todo asks for.
- `sites that need hooks` (`delete.py`) stay on `git commit`, so the memory delete marker check keeps working.
- Unrelated staged files never enter the commit, because the temporary index starts from `HEAD` and only takes the staged entries of `paths`.

## Steps (one commit each, per the lplp style)

1. Pure move: relocate `commit_blocker` and `commit_resync` into the new lib unchanged, `link_subproject.py` imports them. No behaviour change.
2. Generalise: message and `cwd` parameters, add `stage_and_commit`, tests for the lib (below).
3. Migrate hook sites (`_lib.py`, `reffiles`, `record-memory`, `save-plan`, `record-codex-memory`, `save-prompt`, `save-compact-prompt`) and delete `operation_in_progress` once unused. Keep existing function names (renaming `_`-prefixed ones is the separate todo `fded287a`).
4. Update `CLAUDE.md` / `ai/°base/AGENTS.md` ("AI artifact routing" or a short new paragraph) with the shared helper and the detached-HEAD behaviour.

## Tests

New `tests/test_scoped_commit_lib.py` using the existing `_git_test_helpers.py` repos:

- commits only the given paths and leaves other staged and unstaged files untouched;
- deleted path is committed as a deletion;
- unchanged tree returns `None` and creates no commit;
- `commit_blocker` for each state: `MERGE_HEAD`, `rebase-merge`/`rebase-apply`, `CHERRY_PICK_HEAD`, `REVERT_HEAD`, `BISECT_LOG`, `index.lock`, detached HEAD, with the `merge` / `rebase` event exemptions;
- failure inside the plumbing (e.g. unreadable index via a bad `GIT_INDEX_FILE`) returns `None` and keeps paths staged;
- no hooks run (a failing `pre-commit` hook does not block).

Existing `test_link_subproject.py` commit tests keep passing against the import; hook tests (`test_save_*`, `test_record_memory_hook.py`, codex memory tests) get a case where the hook runs mid-merge or on a detached HEAD and leaves the file staged.

## Verification

- `uv run --project scripts/°base python -m unittest discover -s scripts/°base/tests -v` is green.
- `python3 scripts/°base/ai/settings/sync.py --check` is clean.
- Manual: in a scratch clone, `git checkout --detach`, send a prompt through the hook, confirm `ai/°base/query.md` is staged and not committed; back on a branch it commits normally.
