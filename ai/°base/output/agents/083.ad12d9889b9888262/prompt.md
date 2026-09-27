We're designing a fix for a bug in the repo at /home/user/git/luckydonald/base (a "base" meta-repo consumed by other projects). This is PLANNING ONLY — do not write any code, just produce a detailed implementation plan as your response text.

## Bug

`_is_inside_base_repo(subproject_root)` in `scripts/°base/ai/hooks/°commit_style_lib/__init__.py:34-45`:

```python
def _is_inside_base_repo(subproject_root: Path) -> bool:
    """True iff we are inside the `base` meta-repo: subproject directory named
    `base`, with origin pointing at luckydonald/base.
    ...
    """
    if subproject_root.name != "base":
        return False
    origin = _git_text("remote", "get-url", "origin")
    return bool(re.search(r"(^|[:/])luckydonald/base(\.git)?/?$", origin, re.I))
```

`_git_text` (same file, lines 21-23) just does `subprocess.run(["git", *args], capture_output=True, text=True)` — no explicit cwd, relies on process cwd, no error handling (failed git command yields `""`).

This function is called from `base_ai_commit_subject()` (same file, lines 59-82) as:
```python
subproject = _subproject_root()
git_root_text = _git_text("rev-parse", "--show-toplevel")
git_root = Path(git_root_text) if git_root_text else subproject
is_base = _is_inside_base_repo(subproject) or _is_inside_base_repo(git_root)
```
and identically in `_ai_prefix_root()` in `scripts/°base/ai/hooks/_lib.py:41-49`, and again in `resolve_log_path()` in `_lib.py` (~lines 407-433, decides where hook logs land after `_chdir_to_git_root()`), and imported/used the same way in `scripts/°base/ai/hooks/°memory_lib/dirs.py:8,24` and `scripts/°base/ai/memory/promote.py:36,156`.

`_subproject_root()` (duplicated identically in both `_lib.py` and `°commit_style_lib/__init__.py`, lines 26-31) is:
```python
def _subproject_root() -> Path:
    raw = os.environ.get("CLAUDE_PROJECT_DIR") or os.getcwd()
    return Path(raw).resolve()
```

**Root cause**: for a linked `git worktree` of this repo (e.g. `/home/user/git/luckydonald/base/.claude/worktrees/claude-loop-messages`), both `subproject_root` (from `CLAUDE_PROJECT_DIR` or cwd) and `git_root` (`git rev-parse --show-toplevel`) resolve to the *worktree's own directory*, which is named after the worktree/branch (e.g. `claude-loop-messages`), never `base` — even though the worktree plainly belongs to the base repo. So `_is_inside_base_repo` always returns `False` inside any linked worktree, silently misrouting `ai/query.md` vs `ai/°base/query.md`, `ai/plans/` vs `ai/°base/plans/`, `ai/output/debug/` vs `ai/°base/output/debug/`, and the `[base]` commit-subject prefix.

**Confirmed fix direction** (verified manually in the live repo, not yet implemented): `git rev-parse --git-common-dir` always resolves to the *original* checkout's `.git` directory, identically whether run from the main checkout or from any of its linked worktrees. So `Path(git_common_dir).resolve().parent` gives the main checkout's root directory (name `base`) in both cases — this is a worktree-proof stand-in for "the checkout directory is literally named `base`".

Verified manually:
- From main checkout: `git rev-parse --git-common-dir` → `.git` (relative, resolves under cwd to `<main>/.git`)
- From worktree `.claude/worktrees/claude-split-improvement`: `git rev-parse --git-common-dir` → absolute path `/home/user/git/luckydonald/base/.git`
- So `Path(common_dir).resolve().parent.name == "base"` holds in both cases.

**Known gap / edge case to resolve in the plan**: bare repositories. No code or test in this repo currently handles `git init --bare` + `git worktree add`. Conceptually, for a bare repo `repo.git` with a worktree added, `--git-common-dir` from the worktree returns the bare dir itself (e.g. `/path/repo.git`), whose parent is just whatever directory contains the bare repo — not a checkout named `base`, and the bare dir itself is typically named `something.git`, not `base`. There is no existing bare-repo test fixture in this codebase (the misleadingly-named `_init_bare()` in `scripts/°base/tests/_git_split_e2e_fixtures.py:87-90` does NOT actually pass `--bare`, it's a plain `git init`, unrelated). The plan must explicitly decide: is bare-repo support in scope at all for the actual `luckydonald/base` repo (does anyone realistically bare-clone+worktree this specific repo)? If not clearly in scope, the plan should say so explicitly rather than silently ignoring it, and should ensure the fix doesn't misbehave (e.g. crash, or falsely claim `True`) in that case — a safe `False` fallback is acceptable but should be a deliberate, tested decision.

## Call sites needing the fix (repo-wide, confirmed via grep — all in `scripts/°base/ai/hooks/` and `scripts/°base/ai/memory/`, NOT under any `.claude/worktrees/*` stale copies)

1. `scripts/°base/ai/hooks/°commit_style_lib/__init__.py:34-45` — the function itself.
2. `scripts/°base/ai/hooks/°commit_style_lib/__init__.py:64`, inside `base_ai_commit_subject()`.
3. `scripts/°base/ai/hooks/_lib.py:29` — re-export `_is_inside_base_repo = _commit_style._is_inside_base_repo`.
4. `scripts/°base/ai/hooks/_lib.py:41-49`, inside `_ai_prefix_root()`.
5. `scripts/°base/ai/hooks/_lib.py` (~407-433), inside `resolve_log_path()`, after `_chdir_to_git_root()` — need to actually read this function's current implementation to confirm.
6. `scripts/°base/ai/hooks/°memory_lib/dirs.py:8,24`.
7. `scripts/°base/ai/memory/promote.py:36,156` — `if not _is_inside_base_repo(subproject): ...` gate, need to read this to see what it restricts.

Note: `°commit_style_lib/__init__.py`'s own docstring says it intentionally duplicates `_git_text`/`_subproject_root` from `_lib.py` rather than importing them, to avoid a circular import (`_lib.py` imports `base_ai_commit_subject`/`commit_message` from `°commit_style_lib`). Any new shared helper (e.g. a `_main_checkout_root()` or an updated `_is_inside_base_repo`) needs to either live in `°commit_style_lib/__init__.py` and be re-exported from `_lib.py` (following the existing pattern for `_is_inside_base_repo` itself at `_lib.py:29`), or be duplicated in both files consistent with the existing duplication pattern — decide and justify which.

## Existing test infrastructure

- `scripts/°base/tests/test_commit_style_lib.py` (199 lines) — exercises `commit_message()`/override-template behavior via shared fixtures `init_repo(repo, origin_url)` and `run_hook(...)` imported from `scripts/°base/tests/test_ai_hooks_base_routing.py:35-42`. `init_repo()` is: plain `git init` + git config + one commit + `git remote add origin <url>`. **No existing test exercises `_is_inside_base_repo` returning `True`** (i.e., no test simulates actually being inside a real `.../base` checkout with matching origin) — all existing tests use a `consumer` dir name, only covering the `is_base == False` branch. **No worktree fixture exists anywhere in the test suite.**
- `scripts/°base/tests/_git_split_e2e_fixtures.py:87-90` has a misleadingly-named `_init_bare()` that does NOT create a real bare repo (just plain `git init`) — unrelated subsystem (`°split_lib` history-master), not reusable as-is for a real bare-repo fixture, but shows the naming collision to be aware of if adding a *real* bare-repo fixture.

## What the plan must cover

1. **The actual code fix** for `_is_inside_base_repo` (or a new/renamed helper) using `git rev-parse --git-common-dir`, resolving where it should live (per the duplication-vs-shared-import question above) and exact logic:
   - Fast path: keep `subproject_root.name == "base"` as a cheap check (avoids a git subprocess call in the common consuming-repo case), OR replace it outright — decide and justify.
   - Fallback/addition: compute main checkout root via `git rev-parse --git-common-dir`, resolve it, take `.parent`, check `.name == "base"`, then verify origin matches `luckydonald/base` (existing regex) run against the correct directory (need `_git_text` invocations to work correctly regardless of cwd — check whether `_git_text` needs a `cwd=` argument added, since it currently relies on process cwd; confirm whether `_subproject_root()`/other cwd-dependent assumptions elsewhere already ensure cwd is the worktree dir when hooks run, so this is safe, or whether it's actually a real problem needing an explicit `cwd=subproject_root` argument added to `_git_text` calls in this function).
   - Explicit deliberate handling (or explicit documented non-goal) for the bare-repo case.
2. **Where the fix needs to be duplicated/re-exported** to reach all 7 call sites above without missing one — confirm by re-reading `_lib.py`'s `resolve_log_path` and `°memory_lib/dirs.py` and `promote.py` call sites first (the details above are from a prior exploration pass and may need double-checking against current file contents).
3. **New test coverage**: a real worktree fixture (using actual `git worktree add`, not a differently-named plain directory) added to the test suite (likely in `test_commit_style_lib.py` or a new file), verifying `_is_inside_base_repo`/`base_ai_commit_subject` returns the base-repo behavior from inside a linked worktree whose directory is NOT named `base`. Also a first-ever test that `_is_inside_base_repo` returns `True` from an actual `base`-named non-worktree checkout (currently untested). Explicitly decide whether a bare-repo test is in scope given the scoping decision from point 1.
4. **Migration/cleanup considerations**: this session's own misrouted files (already flagged in the parent plan as a separate leftover task, NOT in scope here — just don't duplicate that work) and whether other existing linked worktrees (`claude-split-impl`, `claude-split-improvement`, `fix-plan-decision`) need any one-time sweep-up — the parent plan explicitly says this decision belongs to whoever implements Leftover Task 2, i.e. you should make a recommendation here.
5. **Verification plan**: how to manually confirm the fix in the live repo's actual linked worktrees, plus the automated test command.

Please read the actual current contents of `scripts/°base/ai/hooks/_lib.py` (specifically `resolve_log_path`, roughly lines 380-440, and `_chdir_to_git_root`), `scripts/°base/ai/hooks/°memory_lib/dirs.py`, and `scripts/°base/ai/memory/promote.py` (lines around 30-40 and 150-160) yourself to verify/correct the above before finalizing the plan, since some of these details come from an earlier exploration pass. Produce a complete, concrete implementation plan as your response.