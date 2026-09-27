I'm planning a fix for a bug in this repo (luckydonald/base). Read-only exploration only, no edits.

Context: `_is_inside_base_repo(subproject_root)` in `scripts/°base/ai/hooks/°commit_style_lib/__init__.py` (around lines 34-45) currently does:

```python
def _is_inside_base_repo(subproject_root: Path) -> bool:
    if subproject_root.name != "base":
        return False
    origin = _git_text("remote", "get-url", "origin")
    return bool(re.search(r"(^|[:/])luckydonald/base(\.git)?/?$", origin, re.I))
```

This breaks for linked `git worktree`s of this repo, since a worktree's own checkout directory is never named "base" (it's named after the worktree/branch), even though `git rev-parse --git-common-dir` resolves to the same `.git` as the main checkout in that case.

I need a full picture before designing a fix. Please investigate and report back (be thorough, include file paths and line numbers):

1. Full contents of `scripts/°base/ai/hooks/°commit_style_lib/__init__.py` — especially `_is_inside_base_repo`, `_git_text`, and any other helper it depends on (e.g. how git commands are run, cwd handling, error handling/caching).

2. Every call site of `_is_inside_base_repo` repo-wide (grep for it). For each, show the surrounding function and how the boolean result is used (e.g. `_ai_prefix_root()`, `base_ai_commit_subject()` in `scripts/°base/ai/hooks/_lib.py` and `°commit_style_lib/__init__.py`). Include line numbers.

3. How `_subproject_root()` is implemented in `_lib.py` (what it returns, how `$CLAUDE_PROJECT_DIR` vs cwd is chosen).

4. Any existing usage of `git rev-parse --git-common-dir`, `--absolute-git-dir`, or similar git-worktree-detection logic anywhere else in the repo (to see if there's already a pattern to reuse).

5. Existing tests for this logic: `scripts/°base/tests/test_commit_style_lib.py` — full contents, and how it sets up git fixtures (e.g. does it use temp git repos, does it already have any worktree-related fixture helpers elsewhere in the test suite that could be reused, like a `tmp_path` git init helper).

6. Check whether a bare repository's "main checkout" concept could break the `git rev-parse --git-common-dir` parent-basename approach — i.e., find out what `--git-common-dir` returns for a repo initialized with `git init --bare` plus `git worktree add`, if there's any existing test or code that already handles bare repos in this codebase (grep for "bare").

7. List all current linked worktrees mentioned in code/tests if any (not `git worktree list` on the live system — I already know that from context — just check if tests reference multiple worktree names).

Report concisely but completely with file:line references. Don't propose the fix yourself — just gather facts.