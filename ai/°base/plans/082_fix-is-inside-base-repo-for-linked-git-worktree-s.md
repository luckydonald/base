# Fix `_is_inside_base_repo` for linked `git worktree`s

## Context

`ai/°base/plans/081_condense-autonomous-loop-tick-boilerplate-in-query-md.md`
("Leftover task 2") documents a routing bug discovered while doing unrelated
work in a linked worktree (`.claude/worktrees/claude-loop-messages`): every
hook that decides whether it's running "inside the base repo itself" (which
controls `ai/query.md` vs `ai/°base/query.md`, `ai/plans/` vs
`ai/°base/plans/`, `ai/output/debug/` vs `ai/°base/output/debug/`, and the
`[base] ` commit-subject prefix) silently misroutes everything to the
consuming-repo paths whenever it runs from a linked worktree — because a
worktree's own checkout directory is never named `base`, even though it
plainly belongs to the base repo. This produced a whole session's worth of
misrouted files (tracked separately as "Leftover task 1", not part of this
plan) and will keep happening in `claude-split-impl`, `claude-split-improvement`,
`fix-plan-decision`, and any future worktree until the detection logic itself
is fixed. This plan implements that fix.

## Root cause

`_is_inside_base_repo()` in
`scripts/°base/ai/hooks/°commit_style_lib/__init__.py:34-45`:

```python
def _is_inside_base_repo(subproject_root: Path) -> bool:
    if subproject_root.name != "base":
        return False
    origin = _git_text("remote", "get-url", "origin")
    return bool(re.search(r"(^|[:/])luckydonald/base(\.git)?/?$", origin, re.I))
```

is called as `_is_inside_base_repo(subproject) or _is_inside_base_repo(git_root)`
from `base_ai_commit_subject()` (same file, line 64), `_ai_prefix_root()` and
`resolve_log_path()` (both in `scripts/°base/ai/hooks/_lib.py`, lines ~41-49
and ~412-433). Both `subproject` (`$CLAUDE_PROJECT_DIR` or cwd) and `git_root`
(`git rev-parse --show-toplevel`) resolve to the *worktree's own directory* in
a linked worktree, named after the branch, never `base` — so both checks fail.
Two other call sites, `scripts/°base/ai/hooks/°memory_lib/dirs.py:24` and
`scripts/°base/ai/memory/promote.py:156`, only ever pass `subproject` (no
`git_root` fallback at all), so they're even more exposed.

**Fix direction (verified manually in the live repo):** `git rev-parse
--git-common-dir` always resolves to the *main* checkout's `.git` directory,
identically whether run from the main checkout or any linked worktree.
`Path(common_dir).resolve().parent` is therefore a worktree-proof stand-in for
"the checkout directory is literally named `base`". Verified live:
- Main checkout: `--git-common-dir` → `.git` (relative, under cwd).
- From `.claude/worktrees/claude-split-improvement`: `--git-common-dir` →
  absolute `/home/user/git/luckydonald/base/.git`, whose `.parent.name` is
  `base` in both cases.

## Approach

All code changes are confined to
`scripts/°base/ai/hooks/°commit_style_lib/__init__.py`. Every other call site
(`_lib.py`'s re-export at line 29, `_ai_prefix_root()`, `resolve_log_path()`,
`°memory_lib/dirs.py`, `promote.py`) imports/re-exports `_is_inside_base_repo`
by reference rather than duplicating it, so fixing the one function fixes all
of them with zero changes elsewhere. (`_lib.py:29` already does
`_is_inside_base_repo = _commit_style._is_inside_base_repo` — keep that
re-export as-is.)

1. **Give `_git_text` an explicit `cwd` parameter** (default `None`, i.e. no
   behavior change for existing callers that omit it):
   ```python
   def _git_text(*args: str, cwd: Path | str | None = None) -> str:
       result = subprocess.run(["git", *args], capture_output=True, text=True, cwd=cwd)
       return (result.stdout or "").strip()
   ```
   This matters because the new logic must resolve git state *for the
   directory being tested*, not for whatever the ambient process cwd happens
   to be (which is fragile today — e.g. `resolve_log_path()` calls
   `_chdir_to_git_root()`, which changes cwd, before its own
   `_is_inside_base_repo(subproject)` call, so that call's origin lookup is
   only correct today by coincidence). The existing `origin = _git_text(...)`
   call inside `_is_inside_base_repo` also needs `cwd=subproject_root` added
   for the same reason.

2. **Add `_main_checkout_root(cwd: Path) -> Path | None`**, next to
   `_is_inside_base_repo`:
   ```python
   def _main_checkout_root(cwd: Path) -> Path | None:
       """Resolve the main checkout root that `cwd` belongs to, even when
       `cwd` is inside a linked git worktree (whose own directory is named
       after the worktree/branch, never `base`). Returns None if `cwd` isn't
       inside a git working tree, or if the repo is bare (no single "main
       checkout root" applies there — bare-repo support is out of scope; see
       docstring below)."""
       common_dir_text = _git_text("rev-parse", "--git-common-dir", cwd=cwd)
       if not common_dir_text:
           return None
       common_dir = Path(common_dir_text)
       if not common_dir.is_absolute():
           common_dir = cwd / common_dir
       common_dir = common_dir.resolve()
       if common_dir.name != ".git":
           # Bare repo: --git-common-dir points at the bare dir itself
           # (e.g. "repo.git"), not a ".git" inside a checkout — no sibling
           # checkout root to take .parent of.
           return None
       return common_dir.parent
   ```

3. **Rewrite `_is_inside_base_repo`** to keep the cheap name check as a fast
   path (avoids a git subprocess in the common case) and fall back to
   `_main_checkout_root` when it fails:
   ```python
   def _is_inside_base_repo(subproject_root: Path) -> bool:
       """True iff we are inside the `base` meta-repo: main-checkout
       directory named `base` (checked directly, or — when `subproject_root`
       is itself a linked git worktree named after its branch — via the
       worktree-proof `--git-common-dir` lookup), with origin pointing at
       luckydonald/base.

       Bare repositories (`git init --bare` + `git worktree add`) are treated
       as "not the base repo" (returns False) — not a supported way to work
       with this repo today; see `_main_checkout_root`.
       """
       root = subproject_root
       if root.name != "base":
           root = _main_checkout_root(subproject_root)
           if root is None or root.name != "base":
               return False
       origin = _git_text("remote", "get-url", "origin", cwd=root)
       return bool(re.search(r"(^|[:/])luckydonald/base(\.git)?/?$", origin, re.I))
   ```

4. **Optional hygiene, same change:** add the same `cwd=` parameter to
   `_lib.py`'s separate copy of `_git_text` (line ~315) for consistency,
   since `_lib.py` calls it directly elsewhere (`_chdir_to_git_root`, the
   `git_root` lookup in `resolve_log_path`). Not required for correctness of
   this fix (that `_git_text` is never called from inside
   `_is_inside_base_repo`), but keep it in the same diff since it's a
   one-line, zero-risk addition and closes the same class of "relies on
   ambient cwd" fragility. Leave every existing `_git_text(...)` call in
   `_lib.py` unchanged (no behavior change) unless a specific call is later
   found to need it.

Leave `resolve_log_path()`'s and `_ai_prefix_root()`'s existing
`_is_inside_base_repo(subproject) or _is_inside_base_repo(git_root)` pattern
as-is — now redundant-but-harmless (either argument will resolve correctly),
not worth touching to keep this diff minimal and focused on the actual bug.

## Critical files

- `scripts/°base/ai/hooks/°commit_style_lib/__init__.py` — all real changes:
  `_git_text` gains `cwd=`, new `_main_checkout_root`, rewritten
  `_is_inside_base_repo`.
- `scripts/°base/ai/hooks/_lib.py` — optional hygiene-only `cwd=` addition to
  its own `_git_text` (line ~315); no other changes needed (line 29's
  re-export, `_ai_prefix_root()`, `resolve_log_path()` all pick up the fix
  automatically).
- `scripts/°base/ai/hooks/°memory_lib/dirs.py`, `scripts/°base/ai/memory/promote.py`
  — no changes; both import `_is_inside_base_repo` from `_lib` and benefit
  automatically.
- `scripts/°base/tests/test_commit_style_lib.py` — add new tests (below),
  reusing `init_repo`/`run_hook`/`last_subject` from
  `scripts/°base/tests/test_ai_hooks_base_routing.py`. Note `run_hook(repo, ...)`
  already just takes whatever path is passed as `repo` for both `cwd` and
  `CLAUDE_PROJECT_DIR` and does a plain `git log`/`git commit` against it —
  since a worktree shares the same repository, passing a worktree directory
  as `repo` to `run_hook`/`last_subject` works without any change to those
  helpers.

## New test coverage (in `test_commit_style_lib.py`)

1. **First-ever "True from a real `base`-named checkout" test** (currently
   untested — all existing tests use a `consumer`-named dir): `init_repo(tmp_path
   / "base", "git@github.com:luckydonald/base.git")`, assert
   `_is_inside_base_repo(repo) is True`, and that `base_ai_commit_subject(...)`
   / a hook run through it produces the `[base] ` prefix.
2. **Worktree regression test (the actual bug):** `init_repo` a repo at
   `tmp_path / "base"` with origin `luckydonald/base`, then `git worktree add
   -b <branch> <dir>` into a directory deliberately **not** named `base`
   (mirroring `.claude/worktrees/claude-loop-messages`). Assert
   `_is_inside_base_repo(worktree_dir) is True`, and run a hook via
   `run_hook(worktree_dir, PROMPT_HOOK, ...)` asserting `ai/°base/query.md`
   (not `ai/query.md`) is written and the commit subject carries `[base] `.
3. **Negative control:** a worktree off a repo whose origin does *not* match
   `luckydonald/base` must still return `False` — proves the fix doesn't
   start returning `True` for every worktree indiscriminately.
4. **Bare-repo safety net (documented non-goal, not full support):**
   `git init --bare` a repo (name it so its bare dir or parent could
   plausibly be confused with `base`, e.g. `base.git`), `git worktree add`
   from it, and assert `_is_inside_base_repo(worktree_dir) is False` —
   proving the `common_dir.name != ".git"` check correctly falls back to
   `False` instead of crashing or misreporting, per the explicit scoping
   decision that bare-repo support is out of scope for `luckydonald/base`.

## Out of scope (flagged, not done here)

- Retroactively fixing files already misrouted by past runs in
  `claude-split-impl`, `claude-split-improvement`, `fix-plan-decision`, or the
  `claude-loop-messages` worktree (tracked separately as "Leftover task 1").
  Recommend a one-time manual sweep of those worktrees' `ai/` (top-level)
  directories for files that should have landed under `ai/°base/`, as its own
  follow-up — not something this fix should attempt automatically at runtime.
- Full bare-repository support — deliberately returns `False`, tested (item 4
  above), not implemented further.

## Verification

- `cd /home/user/git/luckydonald/base && python3 -m unittest scripts/°base/tests/test_commit_style_lib.py -v`
  (and the full `scripts/°base/tests/` suite to confirm no regression to
  other hooks sharing `_lib.py`/`°commit_style_lib`).
- Manual check against the repo's real existing linked worktrees:
  ```bash
  cd /home/user/git/luckydonald/base/.claude/worktrees/claude-split-impl
  python3 -c "
  import sys
  sys.path.insert(0, '/home/user/git/luckydonald/base/scripts/°base/ai/hooks')
  from importlib import import_module
  from pathlib import Path
  cs = import_module('°commit_style_lib')
  print(cs._is_inside_base_repo(Path('.').resolve()))
  "
  ```
  Expect `True` after the fix (repeat for `claude-split-improvement` and
  `fix-plan-decision`); was `False` before, reproducing the bug.
