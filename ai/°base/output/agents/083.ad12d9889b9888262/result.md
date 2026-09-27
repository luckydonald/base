Confirmed everything manually. Now producing the full implementation plan.

## Implementation Plan: Fix `_is_inside_base_repo` for linked worktrees

### 1. Confirmed facts from re-reading the actual files

- `_git_text` is defined identically in both `°commit_style_lib/__init__.py:21-23` and `_lib.py:315-317`: `subprocess.run(["git", *args], capture_output=True, text=True)` — no `cwd=`. It relies entirely on the *process* cwd.
- All call sites that matter run either from a hook process whose cwd Claude Code sets to the project dir, or after `_chdir_to_git_root()` (which itself calls `_git_text("rev-parse", "--show-toplevel")` before any chdir happens, so at that specific call the cwd is whatever it was on process start). There is no code path that calls `_is_inside_base_repo` after cwd has been changed to something unrelated to `subproject_root`/`git_root`. So today's callers are "safe" only because they don't cd away first — but a new implementation that shells out from inside `_is_inside_base_repo` must not assume this implicitly; it should pass `cwd=` explicitly rather than depend on ambient state, both for correctness and for testability (tests will want to call the function against an arbitrary path without chdir'ing the whole test process).
- Verified live in this repo: from `.claude/worktrees/claude-split-impl`, `git rev-parse --git-common-dir` → `/home/user/git/luckydonald/base/.git`, and `Path(...).resolve().parent.name == "base"`. Matches the bug report exactly.
- All 7 call sites are confirmed present and unchanged from the report:
  1. `°commit_style_lib/__init__.py:34-45` (`_is_inside_base_repo` itself)
  2. `°commit_style_lib/__init__.py:64` (`base_ai_commit_subject`)
  3. `_lib.py:29` — `_is_inside_base_repo = _commit_style._is_inside_base_repo` re-export
  4. `_lib.py:41-49` (`_ai_prefix_root`)
  5. `_lib.py:404-433` (`_chdir_to_git_root` at 404-408, `resolve_log_path` at 412-433) — confirmed: `resolve_log_path` calls `_chdir_to_git_root()` (which itself calls `_git_text("rev-parse", "--show-toplevel")`, then `os.chdir(root)`), then evaluates `_is_inside_base_repo(subproject) or _is_inside_base_repo(git_root)` — same broken pattern, and by this point cwd has *already* changed to the git root, so any git subprocess called without explicit `cwd=` from inside `_is_inside_base_repo` at this call site would actually be running with cwd = git root already (fine for this case, but inconsistent with the other call sites where cwd is still the original launch dir) — this asymmetry is exactly why the new implementation must not rely on ambient cwd at all.
  6. `°memory_lib/dirs.py:8,24` — imports `_is_inside_base_repo` from `_lib` and calls `_is_inside_base_repo(subproject)` (no git_root fallback used here at all — only checks `subproject`, meaning `memory_dirs()` today is *even more* broken in a worktree than the commit-subject path, since it never tries `git_root` as a second guess).
  7. `promote.py:36,156` — imports from `_lib`, calls `_is_inside_base_repo(subproject)` at line 156 as a hard gate (`if not _is_inside_base_repo(subproject): print error; return 2`) — also no git_root fallback.

  Because sites 6 and 7 only ever pass `subproject_root` (never `git_root`), fixing `_is_inside_base_repo` itself is the only way to fix them — you cannot rely on "try git_root too" as a workaround for these two.

### 2. The fix itself

**Decision: replace the body of `_is_inside_base_repo`, keep the cheap name check as a fast-path short-circuit, add the worktree-proof fallback.** Do not rename the function — it's imported/re-exported by name in 4 files; renaming multiplies the diff for no benefit. Signature stays `_is_inside_base_repo(subproject_root: Path) -> bool`.

New logic (to live in `°commit_style_lib/__init__.py`, duplicated into `_lib.py` — see section 3 for why):

```python
def _main_checkout_root(cwd: Path) -> Path | None:
    """Resolve the root of the *main* checkout that `cwd` belongs to, even
    when `cwd` is inside a linked `git worktree` (whose own directory is
    named after the worktree/branch, never `base`). Returns None if `cwd`
    isn't inside a git working tree at all, or if the repo is bare (no
    single "main checkout root" concept applies there -- see docstring
    below).
    """
    common_dir_text = _git_text("rev-parse", "--git-common-dir", cwd=cwd)
    if not common_dir_text:
        return None
    common_dir = Path(common_dir_text)
    if not common_dir.is_absolute():
        common_dir = cwd / common_dir
    common_dir = common_dir.resolve()
    # Bare repos: --git-common-dir points at the bare dir itself (typically
    # named "<name>.git"), not at a ".git" inside a checkout, so there is no
    # sibling worktree-checkout root to take `.parent` of in the way this
    # repo cares about. Treat as "not a match" rather than guessing.
    if common_dir.name != ".git":
        return None
    return common_dir.parent


def _is_inside_base_repo(subproject_root: Path) -> bool:
    """True iff we are inside the `base` meta-repo: main-checkout directory
    named `base` (checked directly, or via the worktree-proof
    `--git-common-dir` lookup when `subproject_root` is itself a linked
    `git worktree` whose own directory is named after the branch, not
    `base`), with origin pointing at luckydonald/base.

    Bare repositories (`git init --bare` + `git worktree add`) are treated
    as "not the base repo" (returns False) -- not a supported/expected way
    to work with luckydonald/base today; see NOTES.md / commit message for
    the explicit scoping decision.
    """
    if subproject_root.name != "base":
        root = _main_checkout_root(subproject_root)
        if root is None or root.name != "base":
            return False
        subproject_root = root  # for the origin check below
    origin = _git_text("remote", "get-url", "origin", cwd=subproject_root)
    return bool(re.search(r"(^|[:/])luckydonald/base(\.git)?/?$", origin, re.I))
```

And `_git_text` gains an explicit `cwd` parameter (default `None`, i.e. current behavior unchanged for every other caller):

```python
def _git_text(*args: str, cwd: Path | str | None = None) -> str:
    result = subprocess.run(["git", *args], capture_output=True, text=True, cwd=cwd)
    return (result.stdout or "").strip()
```

Rationale for each decision point raised in the task:

- **Keep the cheap `.name == "base"` check as a fast path**: yes — it avoids a git subprocess call in the overwhelmingly common case (non-worktree consuming repos, and the base repo's own main checkout), and it's already proven correct for those cases. Only fall through to the `--git-common-dir` computation when the cheap check fails, since that's the only case that needs disambiguating (worktree vs. genuinely-not-base).
- **`_git_text` needs an explicit `cwd=`**: yes, this is a real gap, not just theoretical. `_main_checkout_root` needs to run `git rev-parse --git-common-dir` *for the worktree in question*, not for whatever the ambient process cwd happens to be — the whole point is testability (calling `_is_inside_base_repo(some_arbitrary_path)` from a test without chdir'ing the test process) and correctness at call site 5 (`resolve_log_path`), where cwd has already been changed by `_chdir_to_git_root()` before the second `_is_inside_base_repo(subproject)` call — that second call's implicit-cwd behavior would silently use the *new* cwd (already the git root) rather than `subproject`, which happens to still work today only by coincidence of the two being equivalint for git-common-dir purposes, but is fragile. Making cwd explicit closes this off. The existing `origin = _git_text("remote", "get-url", "origin")` call (with no `cwd=`) must also become `cwd=subproject_root` for the same reason — right now it too relies on ambient cwd, which is only "by luck" correct at every existing call site.
- **Bare repo**: explicitly **out of scope** for `luckydonald/base` as a *supported* configuration — there is no evidence anyone bare-clones this specific repo, and the task description confirms no test fixture or code path handles it today. The plan makes this a **deliberate, tested** `False`-fallback (see test plan below) rather than a silent gap: `_main_checkout_root` explicitly checks `common_dir.name != ".git"` and returns `None` in that case (a bare repo's common-dir *is* the bare dir, e.g. `repo.git`, not a `.git` inside a checkout), so `_is_inside_base_repo` cleanly falls through to `False` instead of crashing or misreporting. Document this as a known non-goal in the docstring and in the commit message, so a future maintainer who *does* need bare-repo support sees why it wasn't handled and where to extend it.

### 3. Duplication vs. shared import — decision

**Duplicate `_main_checkout_root` and the updated `_is_inside_base_repo` body into both `°commit_style_lib/__init__.py` and `_lib.py`, exactly following the existing established pattern** (the module docstring in `°commit_style_lib/__init__.py` already explains why `_git_text`/`_subproject_root` are duplicated rather than shared: `_lib.py` imports `base_ai_commit_subject`/`commit_message` from `°commit_style_lib`, so the reverse import would be circular).

However, `_lib.py:29` currently does `_is_inside_base_repo = _commit_style._is_inside_base_repo` — i.e. **it already re-exports rather than duplicates** for this specific function. Two options:

- **Option A (recommended): keep it a re-export.** Only implement `_main_checkout_root` + the new `_is_inside_base_repo` body once, in `°commit_style_lib/__init__.py` (which needs `_git_text`/`_subproject_root` anyway per its existing duplication), and leave `_lib.py:29`'s `_is_inside_base_repo = _commit_style._is_inside_base_repo` untouched — it will automatically pick up the fix with zero changes to `_lib.py` beyond the `_git_text(cwd=...)` signature update (see below). This is the minimal-diff, least-duplication option and matches what `_lib.py` already does for this exact symbol.
- Option B (duplicate the whole function into `_lib.py` too) is unnecessary extra surface with no circular-import constraint forcing it — `_lib.py` importing `_is_inside_base_repo` from `°commit_style_lib` already works today (that's literally what line 29 does), so there's no reason to duplicate the new, more complex logic.

**Decision: Option A.** Only `°commit_style_lib/__init__.py` gets the real implementation (`_main_checkout_root` + rewritten `_is_inside_base_repo` + `_git_text` gaining `cwd=`). `_lib.py`'s own separate `_git_text` (line 315) also needs `cwd=` added — but only because `_lib.py` calls `_git_text` directly for other purposes (`_chdir_to_git_root`, `resolve_log_path`'s `git_root` lookup, etc.) where we want the same discipline of not relying on ambient cwd; it does **not** need `_main_checkout_root` duplicated since it only ever calls `_is_inside_base_repo` (already re-exported).

This means the concrete file-by-file diff is:

- `°commit_style_lib/__init__.py`: add `cwd=` param to `_git_text`; add `_main_checkout_root`; rewrite `_is_inside_base_repo` body as above.
- `_lib.py`: no change needed to `_is_inside_base_repo` (still just re-exports at line 29) — verify this remains true after the change. Optionally add `cwd=` to its own `_git_text` (line 315) for consistency/hygiene, but this is **not required** for correctness of the bug fix itself since `_lib.py`'s `_git_text` is never called from inside `_is_inside_base_repo` (that lives entirely in `°commit_style_lib`). Recommend doing it anyway in the same change for consistency, but call it out as a separate, lower-risk hunk in the diff review.
- `°memory_lib/dirs.py`: **no code change** — it imports `_is_inside_base_repo` from `_lib`, which re-exports from `°commit_style_lib`; fixing the one function fixes this call site automatically.
- `promote.py`: **no code change** — same reasoning, imports `_is_inside_base_repo` from `_lib`.
- `resolve_log_path` in `_lib.py`: **no code change needed for correctness** since it also just calls the (now-fixed) `_is_inside_base_repo`; the existing double-call pattern (`_is_inside_base_repo(subproject) or _is_inside_base_repo(git_root)`) still works fine and is now doubly redundant-but-harmless once the core function handles worktrees itself (either `subproject` or `git_root` will resolve to `.../base` and pass). Leave the `or` pattern in place everywhere it exists rather than simplifying it in this change, to keep the diff minimal and focused on the actual bug.

So the total code-touch surface for the fix is essentially **one file**: `°commit_style_lib/__init__.py`, plus an optional hygiene-only `cwd=` addition to `_lib.py`'s own `_git_text`.

### 4. New test coverage

Location: extend `scripts/°base/tests/test_commit_style_lib.py` (it already imports `init_repo`/`run_hook` from `test_ai_hooks_base_routing.py` and is the natural home for `_is_inside_base_repo`/`base_ai_commit_subject` behavior tests).

Needed test helpers/fixtures:

1. **First-ever "returns True from a real `base`-named checkout" test.** Currently `init_repo(repo, origin)` is called with a `consumer`-named dir in all existing tests. Add a test that calls `init_repo(tmp_path / "base", "git@github.com:luckydonald/base.git")` (i.e. literally name the temp dir `base`) and asserts `_is_inside_base_repo(repo) is True`, plus a `base_ai_commit_subject(...)` test asserting the `[base]`-prefixed / `ai/°base` routing behavior actually triggers. This closes the "no test currently exercises the `True` branch at all" gap called out in the task.
2. **Real worktree fixture.** Add a new helper, e.g. `add_worktree(repo: Path, worktree_dir: Path, branch: str) -> None` that shells out to `git worktree add -b <branch> <worktree_dir>` against a repo created via `init_repo`. Then:
   - Create `repo = tmp_path / "base"` via `init_repo(repo, "git@github.com:luckydonald/base.git")`.
   - Create a worktree at `tmp_path / "some-feature-branch"` (deliberately **not** named `base`, mirroring the real bug: `.claude/worktrees/claude-loop-messages`).
   - Assert `_is_inside_base_repo(worktree_dir) is True` — this is the core regression test for the bug.
   - Also run `base_ai_commit_subject(...)` (via `run_hook` or directly) with `CLAUDE_PROJECT_DIR`/cwd pointed at the worktree dir, asserting the `[base]` prefix and `ai/°base` path are used, matching the real-world symptom described in the bug report (misrouted `ai/query.md` vs `ai/°base/query.md` etc.).
   - Add a negative-control worktree case too: a worktree off a *non-base* repo (origin not matching `luckydonald/base`) should still return `False`, proving the fix doesn't just start returning `True` for every worktree indiscriminately.
3. **Bare-repo scope decision test.** Since bare-repo support is explicitly declared out of scope with a documented `False` fallback, add **one small regression test** proving the fallback is safe rather than crashing: `git init --bare` a repo, add a worktree from it, and assert `_is_inside_base_repo(worktree_dir) is False` (even if you contrive the bare dir's parent or the bare dir itself to be named `base` — e.g. `base.git` — to prove it's the `.git`-vs-bare-dir distinction being tested, not just an incidental name mismatch). This directly satisfies the task's requirement that the known gap be "a deliberate, tested decision" rather than silently ignored. Do **not** attempt full bare-repo *support* — just the negative-safety test. Name this fixture clearly, e.g. `_init_real_bare_repo()`, to avoid repeating the existing misleading-naming trap in `_git_split_e2e_fixtures.py:_init_bare()` (which the task confirms is unrelated and doesn't actually create a bare repo).
4. Keep all new tests self-contained using `tmp_path`, matching existing test style (no reliance on the live worktrees under `.claude/worktrees/` in this actual repo — those are for manual verification only, see below).

### 5. Migration/cleanup considerations

- This session's own misrouted files: explicitly **not in scope here** (already tracked as a separate "Leftover Task 2" per the parent plan) — do not touch them as part of this change.
- **Recommendation on existing linked worktrees** (`claude-split-impl`, `claude-split-improvement`, `fix-plan-decision`, `splitter`): once this fix lands, any of those worktrees that have *already* accumulated misrouted `ai/query.md`, `ai/plans/`, `ai/output/debug/`, or commit-subject history (created while the bug was live) will **not** be automatically retro-corrected by the code fix — the fix only affects *future* writes made from within those worktrees. Recommend a **one-time manual sweep**, scoped as a separate leftover-task item (not part of this fix's implementation), that:
  1. Greps each of the 4 listed worktree dirs for `ai/query.md`, `ai/plans/`, `ai/output/debug/*.json` files that exist at the *top level* `ai/` (i.e. were misrouted there instead of under `ai/°base/`), created/modified since each worktree was added.
  2. `git mv`s them into `ai/°base/...` in the corresponding worktree, with a manual commit describing it as a routing-bug cleanup (referencing this fix's commit).
  3. This is explicitly a follow-up/manual task, not something the code fix itself should attempt automatically (no code should move files at runtime as a "repair" side effect — too risky/surprising for a hook).
- Recommend this sweep be tracked as its own leftover-task item in whatever tracking mechanism the parent plan uses, distinct from "Leftover Task 2" (this session's misrouted files) — i.e., a **new**, third cleanup item: "sweep pre-existing linked worktrees for base-repo-routing-bug misrouted files."

### 6. Verification plan

**Manual verification in the live repo** (read-only / additive only, no destructive worktree operations):

```bash
cd /home/user/git/luckydonald/base/.claude/worktrees/claude-split-impl
python3 -c "
import sys
sys.path.insert(0, '/home/user/git/luckydonald/base/scripts/°base/ai/hooks')
from importlib import import_module
cs = import_module('°commit_style_lib')
from pathlib import Path
print(cs._is_inside_base_repo(Path('.').resolve()))
"
# expect: True (after fix); False (before fix, reproducing the bug)
```

Repeat against `claude-split-improvement` and `fix-plan-decision` worktrees for confidence across all three real linked worktrees already present in this repo. Also spot-check `base_ai_commit_subject("some message")` and `resolve_log_path(...)`-driven behavior (e.g. by invoking `save-prompt`'s hook script with `CLAUDE_PROJECT_DIR` set to a worktree path) to confirm `ai/°base/query.md` is chosen over `ai/query.md` from inside a worktree.

**Automated test command:**

```bash
cd /home/user/git/luckydonald/base
python3 -m unittest "scripts/°base/tests/test_commit_style_lib.py" -v
```

(and the full suite once done, e.g. whatever the repo's standard `run tests` entry point is — check for a `Makefile`/`pytest.ini`/CI config if one exists, but `unittest` direct invocation matches the existing test file's style.)

---

### Critical Files for Implementation

- /home/user/git/luckydonald/base/scripts/°base/ai/hooks/°commit_style_lib/__init__.py
- /home/user/git/luckydonald/base/scripts/°base/ai/hooks/_lib.py
- /home/user/git/luckydonald/base/scripts/°base/tests/test_commit_style_lib.py
- /home/user/git/luckydonald/base/scripts/°base/tests/test_ai_hooks_base_routing.py
- /home/user/git/luckydonald/base/scripts/°base/ai/memory/promote.py
- /home/user/git/luckydonald/base/scripts/°base/ai/hooks/°memory_lib/dirs.py