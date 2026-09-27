## Investigation Report

### 1. `scripts/°base/ai/hooks/°commit_style_lib/__init__.py` — full contents (141 lines)

Key pieces:

- **`_git_text`** (L21-23): `subprocess.run(["git", *args], capture_output=True, text=True)`, returns stripped stdout, no cwd argument (relies on process cwd), no error handling — a failed git command just yields `""` (stderr/returncode ignored).
- **`_subproject_root`** (L26-31): `Path(os.environ.get("CLAUDE_PROJECT_DIR") or os.getcwd()).resolve()`.
- **`_is_inside_base_repo`** (L34-45): the function under investigation — early-returns `False` unless `subproject_root.name == "base"`, then checks `git remote get-url origin` against `luckydonald/base` via regex. No caching (recomputes/re-shells-out every call).
- **`_read_by_issue`** (L48-56): reads `<subproject>/<ai_prefix>/.by-issue`, independent of the bug.
- **`base_ai_commit_subject`** (L59-82): calls `_is_inside_base_repo(subproject) or _is_inside_base_repo(git_root)` (L64) where `git_root = Path(git_text("rev-parse", "--show-toplevel"))`. This double-check exists precisely because `subproject_root` (from `CLAUDE_PROJECT_DIR`) and the git root can differ (monorepo case) — but note `--show-toplevel` itself returns the **current worktree's** toplevel, not the main checkout, so this fallback does *not* help the worktree case; both calls still test `.name == "base"` against directories that, in a worktree, are never named `base`.
- `_load_py_override` / `_load_md_override` / `commit_message` (L85-141): template override machinery, unrelated to the bug but call `_subproject_root()` / `base_ai_commit_subject()`.

### 2. Call sites of `_is_inside_base_repo` (main tree only; `.claude/worktrees/*` contain stale duplicated copies of the same files, not separate call sites)

- `scripts/°base/ai/hooks/_lib.py:29` — re-exported: `_is_inside_base_repo = _commit_style._is_inside_base_repo`.
- `scripts/°base/ai/hooks/_lib.py:47`, inside `_ai_prefix_root()` (L41-49): `is_base = _is_inside_base_repo(subproject) or _is_inside_base_repo(git_root)` → picks `ai_prefix = "ai/°base"` vs `"ai"`. Used for debug-dump path routing.
- `scripts/°base/ai/hooks/_lib.py:423`, inside `resolve_log_path()` (L~407-433): same `is_base` pattern, decides `ai_prefix`/`relpath` (`base_relpath` vs `default_relpath`) for where hook logs land, after `_chdir_to_git_root()`.
- `scripts/°base/ai/hooks/°commit_style_lib/__init__.py:64`, inside `base_ai_commit_subject()` — decides whether to prepend `[base] ` and use `ai/°base` for `_read_by_issue`.
- `scripts/°base/ai/hooks/°memory_lib/dirs.py:24` (`from _lib import _is_inside_base_repo` at L8) — decides a memory-dir path, same `ai/°base` vs `ai` branch pattern.
- `scripts/°base/ai/memory/promote.py:156` (`from ... import _is_inside_base_repo` at L36): `if not _is_inside_base_repo(subproject): ...` — likely restricts a memory-promotion feature to the base repo itself.

All call sites follow the same shape: boolean gates whether `ai/°base/...` or `ai/...` paths are used, and whether commit subjects get the `[base] ` prefix. Every one of them will silently take the "consuming repo" branch when run from a linked worktree of `luckydonald/base`, since neither `subproject_root.name` nor `git_root.name` (`--show-toplevel` of the worktree) will ever be `"base"`.

### 3. `_subproject_root()` in `_lib.py`

`scripts/°base/ai/hooks/_lib.py` (same implementation duplicated in `°commit_style_lib/__init__.py:26-31`, per that file's own docstring about intentional duplication): `Path(os.environ.get("CLAUDE_PROJECT_DIR") or os.getcwd()).resolve()`. `CLAUDE_PROJECT_DIR` is set by Claude Code hook invocations; falls back to cwd for manual/test runs. Nothing here is worktree-aware — it just returns whatever directory Claude/tests say is the project root, which for a worktree checkout is the worktree's own directory (named after the branch/worktree, not `base`).

### 4. Existing `git rev-parse --git-common-dir` / `--absolute-git-dir` usage

None found anywhere in the live codebase (`scripts/°base/**`, excluding the stale `.claude/worktrees/*` copies of the same files). Grep for `git-common-dir|--absolute-git-dir|common-dir|worktree` only turns up:
- `scripts/°base/git/get-base.py` — its *own* worktree bootstrap mechanism (`worktree_path`, `ensure_worktree`, `_is_valid_worktree`, `_split_command`, L103-300ish) which creates a worktree at `.git/luckydonald/base#get-base.py` (name literally `base#get-base.py`, never plain `base`) to run `°split_lib` tooling from an unmerged `base` remote — this is a *different* feature (a self-managed internal worktree for bootstrapping), not related to detecting whether the *user's own* checkout is a worktree of this repo.
- `scripts/°base/git/°split_lib/git_ops.py:172`, `°split_lib/cli.py:452`, `°split_lib/history_master.py:185`, various test files — mentions of "worktree" in comments/docstrings about dirty working trees, not git-common-dir detection.
- No existing helper computes "main checkout root" via `--git-common-dir`'s parent. I manually verified the mechanism works in this live repo: from the main checkout, `git rev-parse --git-common-dir` → `.git` (relative); from `.claude/worktrees/claude-split-improvement`, it returns the absolute path `/home/user/git/luckydonald/base/.git`, and `.git-dir` for that worktree resolves to `/home/user/git/luckydonald/base/.git/worktrees/claude-split-improvement` — so `Path(git_common_dir).resolve().parent` reliably gives the main checkout root (`/home/user/git/luckydonald/base`, `.name == "base"`) in both cases. No existing code pattern reuses this; a fix would introduce it fresh.

### 5. `scripts/°base/tests/test_commit_style_lib.py` — full contents

199 lines, reproduced/summarized above (Read tool output). It has **no direct fixture** for `_is_inside_base_repo` or worktrees — all 6 tests exercise `commit_message`/override-template behavior via `init_repo(repo, origin_url)` + `run_hook(...)`, importing shared fixtures from `test_ai_hooks_base_routing.py` (`init_repo`, `run_hook`, `last_subject`, hook path constants, `_encode_project_path`). None of these tests set `subproject_root.name == "base"` or exercise the "we are inside base itself" branch at all — they all use `repo = Path(tmp) / "consumer"`, i.e. only the "consuming repo" (`is_base == False`) path is covered by this file. I did not find a separate test file that specifically exercises `_is_inside_base_repo` returning `True` (i.e., simulates being inside an actual `.../base` checkout with the real origin) — worth confirming with a repo-wide search for `"luckydonald/base"` in tests if the fix needs such coverage; I did not do that broader grep since it's outside the questions asked, but flagging it as a gap for the test-design step.

`init_repo()` itself (`test_ai_hooks_base_routing.py:35-42`) is a plain `git init` + config + one commit + `remote add origin <url>` — no worktree setup, no bare-repo option, no `base`-named directory option.

### 6. Bare-repo / `--git-common-dir` interaction

- No code in the live tree handles bare repositories in the context of this bug. The only `bare`-named test helper is `_init_bare()` in `scripts/°base/tests/_git_split_e2e_fixtures.py:87-90`, but despite its name it does **not** actually create a bare repo — it just runs plain `git init` + user config (no `--bare` flag). This helper is unrelated to the `_is_inside_base_repo` bug; it's part of the `°split_lib` history-master e2e fixtures.
- I did not find any test or code path that initializes with `git init --bare` and then `git worktree add`. So there's no existing precedent in this codebase for how `--git-common-dir` behaves for a bare-repo-plus-worktree setup, and no safety net if a common-dir-based fix needs to special-case it. (For reference, conceptually: for `git init --bare repo.git` + `git worktree add ../w1`, `--git-common-dir` run from `w1` returns the bare dir itself, e.g. `/path/repo.git`, whose parent is whatever directory contains the bare repo — not a checkout named `base` at all, so a naive "parent-of-common-dir" approach would need explicit handling for the bare case, which nothing in this repo currently provides or tests.)

### 7. Worktree names referenced in code/tests

- No test file references multiple named worktrees for `_is_inside_base_repo`/commit-style purposes.
- The only worktree-name convention present anywhere in code is `get-base.py`'s own fixed relative path `WORKTREE_RELATIVE_PATH = Path(".git") / "luckydonald" / "base#get-base.py"` (`scripts/°base/git/get-base.py:44`), and `test_get_base.py` (throughout) which drives that bootstrap worktree in tests — again, a different feature, not the user-facing linked-worktree case this bug is about.
- On the live filesystem (from git status context, not tests): `.claude/worktrees/claude-split-improvement`, `.claude/worktrees/claude-split-impl`, `.claude/worktrees/fix-plan-decision` — these are real linked worktrees under `.claude/worktrees/`, each containing a full stale copy of `scripts/°base/...` (source of the duplicate grep hits above), confirming the real-world layout: worktree dirs live under `<main-checkout>/.claude/worktrees/<branch-name>/`, never named `base`.

### Summary of relevant files/lines for the fix design
- `scripts/°base/ai/hooks/°commit_style_lib/__init__.py:21-45` (`_git_text`, `_subproject_root`, `_is_inside_base_repo`)
- `scripts/°base/ai/hooks/_lib.py:26-31` (duplicate `_subproject_root`/`_chdir_to_git_root`), `:29`, `:41-49` (`_ai_prefix_root`), `:407-433`ish (`resolve_log_path`)
- `scripts/°base/ai/hooks/°memory_lib/dirs.py:8,24`
- `scripts/°base/ai/memory/promote.py:36,156`
- `scripts/°base/tests/test_commit_style_lib.py` (whole file) + `scripts/°base/tests/test_ai_hooks_base_routing.py:1-60` (shared `init_repo`/`run_hook` fixtures) — no worktree or bare-repo fixture exists yet for this specific bug; both would need to be added for the fix's tests.
- `scripts/°base/tests/_git_split_e2e_fixtures.py:87-90` (`_init_bare`, misleadingly named — not actually bare, unrelated subsystem).
- `scripts/°base/git/get-base.py:44,103-146` — repo's only other worktree-creation logic, unrelated feature, no reusable common-dir helper.