Investigation complete. Findings below.

## 1. `scripts/°base/git/hooks/push/pre_push.sh` (full, 38 lines)

```sh
#!/usr/bin/env sh
# Combined pre-push hook: preserves the existing git-lfs pre-push behavior,
# then enforces the base branch-split push-name/content policy (see
# scripts/°base/git/°split_lib/push_checks.py, ai/°base/todo.md lines 155-163).
#
# `.git/hooks/pre-push` is a tiny generated trampoline (written by
# scripts/°base/git/hooks/install) that execs this tracked script, so edits
# here take effect without re-running the installer.
#
# argv: <remote-name> <remote-url>
# stdin: 0+ lines of "<local ref> <local sha> <remote ref> <remote sha>"

set -u
export PATH="$HOME/.local/bin:$HOME/.cargo/bin:$HOME/.pyenv/shims:/opt/homebrew/bin:/opt/homebrew/sbin:/usr/local/bin:/usr/local/sbin:$PATH"

remote_name="${1:-}"
remote_url="${2:-}"
script_dir="$(cd "$(dirname "$0")" && pwd)"
repo_root="$(git -C "$script_dir" rev-parse --show-toplevel)"

stdin_buf="$(mktemp)"
trap 'rm -f "$stdin_buf"' EXIT
cat >"$stdin_buf"

status=0

if command -v git-lfs >/dev/null 2>&1; then
    git lfs pre-push "$remote_name" "$remote_url" <"$stdin_buf" || status=$?
else
    echo "git-lfs was not found on PATH for the pre-push hook." >&2
    status=2
fi

python3 "$repo_root/scripts/°base/git/split.py" check-push \
    --remote-name "$remote_name" --remote-url "$remote_url" \
    <"$stdin_buf" || status=$?

exit "$status"
```

Key point: it tees stdin to a tmpfile once, then feeds the same content to both git-lfs and `split.py check-push`, ORing exit codes so both checks always run and a failure of either fails the push.

## 2. `split.py check-push` dispatch (in `°split_lib/cli.py`)

`split.py` itself (12 lines) just adds itself to `sys.path` and calls `°split_lib.cli.main()`.

In `cli.py`, argparse setup (around line 456):
```python
check_push = subparsers.add_parser(
    "check-push", help="Enforce clean/unclean/history push name+content policy."
)
check_push.add_argument("--remote-name", required=True)
check_push.add_argument("--remote-url", required=True)
```
Dispatch (around line 527):
```python
if args.command == "check-push":
    stdin_text = sys.stdin.read()
    root = _resolve_repo_root(args)
    return _check_push(args.remote_name, args.remote_url, stdin_text, repo_root=root)
```

Stdin parsing, `cli.py:122-130`:
```python
def _parse_ref_lines(text: str) -> list[push_checks.RefUpdate]:
    updates: list[push_checks.RefUpdate] = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        local_ref, local_sha, remote_ref, remote_sha = line.split()
        updates.append(push_checks.RefUpdate(local_ref, local_sha, remote_ref, remote_sha))
    return updates
```

Orchestrator, `cli.py:133-166` (`_check_push`):
```python
def _check_push(remote_name: str, remote_url: str, stdin_text: str, *, repo_root: Path) -> int:
    ref_updates = _parse_ref_lines(stdin_text)
    main_branch = branches.detect_main_branch(repo_root)

    all_violations: list[str] = []
    for ref_update in ref_updates:
        if push_checks.is_zero_sha(ref_update.local_sha):
            continue  # deletion

        branch = branches.classify_branch(ref_update.local_ref, main_branch=main_branch)

        shas = git_ops.commits_new_to_remote(
            ref_update.local_sha, ref_update.remote_sha, remote_name, repo_root
        )
        commits = [
            classify.classify_commit(
                sha,
                git_ops.subject_for_commit(sha, repo_root),
                git_ops.changed_paths_for_commit(sha, repo_root),
                ignore_file=classify.resolve_ignore_file(repo_root),
            )
            for sha in shas
        ]

        violations = push_checks.evaluate_ref_update(ref_update, branch, remote_name, commits)
        all_violations.extend(violations)

    if all_violations:
        print("Push blocked by base branch-split policy:", file=sys.stderr)
        for violation in all_violations:
            print(f"  - {violation}", file=sys.stderr)
        return 1

    return 0
```
This is exactly the orchestrator for question 3's "top-level function" — it lives in `cli.py`, not `push_checks.py`. Nonzero-exit surfaces as `split.py`'s process exit code, which `pre_push.sh` captures into `status` and returns as the hook's own exit code, which git interprets as "reject the push."

`--remote-url` is accepted/parsed but currently unused inside `_check_push` (parameter present, not referenced in the body) — relevant since your new check needs to detect "is this repo `luckydonald/base`", which today is done via local git state (`origin` remote URL from `_is_inside_base_repo`), not via the push's own `--remote-url` arg.

## 3. `°split_lib/push_checks.py` (full — 76 lines, already shown above in full)

Pure-logic module, no subprocess calls. All four functions in full:

- `is_zero_sha` — deletion detection.
- `check_content_policy(branch, commits) -> list[str]` — per-commit violation messages based on `BranchFormat.CLEAN` (no `is_ai_tainted_commit`) / `HISTORY` (no `is_code_containing_commit`) / `UNCLEAN` (unrestricted).
- `check_name_policy(branch, remote_name) -> str | None` — blocks `UNCLEAN`/`HISTORY` format branches from being pushed when `remote_name == "origin"`.
- `evaluate_ref_update(ref_update, branch, remote_name, commits) -> list[str]` — the actual "top-level" combinator inside this module: short-circuits to `[]` on a deletion (zero sha), otherwise concatenates a name-policy violation (if any) with all content-policy violations and returns the flat list.

None of these functions raise or return exit codes directly — they return `list[str]` of violation strings. It's `cli._check_push` (see #2) that turns a non-empty aggregate list into `return 1` and prints to stderr, which is the actual failure signal `pre_push.sh` uses.

## 4. Commit-range enumeration (`git_ops.py:35-53`, `commits_new_to_remote`)

```python
def commits_new_to_remote(local_sha: str, remote_sha: str, remote_name: str, cwd: Path) -> list[str]:
    """Commits reachable from local_sha not already reachable from remote_sha.

    Oldest first. Handles branch deletion (empty result) and brand-new
    branches (remote_sha unknown locally, or all-zero) via the same
    ``--not --remotes=`` fallback pre-commit itself uses.
    """
    is_deletion = set(local_sha) == {"0"}
    if is_deletion:
        return []

    is_new_remote_ref = set(remote_sha) == {"0"} or not rev_exists(remote_sha, cwd)
    if is_new_remote_ref:
        args = ["git", "rev-list", "--reverse", local_sha, "--not", f"--remotes={remote_name}"]
    else:
        args = ["git", "rev-list", "--reverse", f"{remote_sha}..{local_sha}"]
    ...
```
So the plumbing is `git rev-list --reverse <remote_sha>..<local_sha>` normally, falling back to `git rev-list --reverse <local_sha> --not --remotes=<remote_name>` when the remote ref is brand new/unknown. This is exactly the list a new check would reuse (it's already produced once per ref-update in `cli._check_push` and handed to `classify.classify_commit`; a new check could take the same `shas`/`commits` list rather than recomputing).

## 5. Per-commit changed-path pattern

`git_ops.py:56-64`:
```python
def changed_paths_for_commit(sha: str, cwd: Path) -> list[str]:
    result = subprocess.run(
        ["git", "diff-tree", "--no-commit-id", "--name-only", "-r", sha],
        cwd=cwd, capture_output=True, text=True, check=True,
    )
    return [line for line in result.stdout.splitlines() if line]
```
And `classify.py`'s `CommitClassification` dataclass already carries `paths: tuple[str, ...]` per commit (`classify.py:161-192`, `classify_commit`), populated from exactly this. So `commits` (the `list[CommitClassification]` built in `cli._check_push`) already has each commit's changed paths available as `commit.paths` — a new "does this commit touch `ai/query.md`" check can just do `"ai/query.md" in commit.paths` per commit, no new git plumbing needed, reusing the same `commits` list already computed for `evaluate_ref_update`.

`.ai-ignore` glob matching itself (`classify.is_ai_base_path` / `path_matches_glob`, `classify.py:129-158`) is a separate, more general glob-based classifier — not needed for an exact-path check like `ai/query.md`, but shows the file's general pattern-matching idiom if you want glob semantics instead of exact-string comparison.

## 6. `_is_inside_base_repo` — location and importability

- Only defined in `scripts/°base/ai/hooks/°commit_style_lib/__init__.py:56-73` (full body shown above). It calls two other local helpers in the same file: `_main_checkout_root` (`°commit_style_lib/__init__.py:34-53`) and `_git_text`.
- `push_checks.py` / `cli.py` / any file under `°split_lib/` do **not** import or use `_is_inside_base_repo` or any equivalent today — grep confirms it's only referenced in `ai/hooks/_lib.py`, `ai/hooks/°memory_lib/dirs.py`, `ai/hooks/°commit_style_lib/__init__.py`, and `ai/memory/promote.py` — all inside the `ai/hooks` tree, never `°split_lib`.
- Directory layout: `scripts/°base/ai/hooks/` and `scripts/°base/git/°split_lib/` are siblings under `scripts/°base/` (one under `ai/hooks`, the other under `git/°split_lib`), not nested. There's no existing import path between them, but nothing prevents one — Python-wise, `°commit_style_lib` is a normal package (has `__init__.py`) reachable if its parent dir is put on `sys.path`, exactly the pattern `test_git_split_push_checks.py` already uses (`sys.path.insert(0, str(LIB_ROOT)); importlib.import_module("°split_lib.branches")`, etc.) — so `°split_lib` code could do `sys.path.insert(0, str(repo_root/"scripts/°base/ai/hooks")); importlib.import_module("°commit_style_lib")._is_inside_base_repo(...)`, or more simply just copy the ~15-line self-contained function (it already only depends on `_git_text`/`_main_checkout_root`, both small and self-contained, and the module's own docstring notes it's deliberately self-contained to avoid circular imports from `_lib.py`). No true import cycle risk either way since `°split_lib` currently has zero dependency edges to/from `ai/hooks`; it would be a brand-new one-directional edge (or a duplicate) — a design decision (import vs duplicate) rather than a hard technical blocker, consistent with the existing codebase's precedent of intentionally duplicating tiny helpers to avoid new cross-tree coupling (see `°commit_style_lib`'s own docstring, and `classify.py:18-20`'s comment about duplicating `BASE_REMOTE_NAME` etc. from `get-base.py` rather than importing it).

## 7. Existing tests for `push_checks.py`

Path: `scripts/°base/tests/test_git_split_push_checks.py`. Module setup imports via `sys.path.insert` + `importlib.import_module` exactly as described in #6:
```python
LIB_ROOT = Path(__file__).resolve().parents[1] / "git"
sys.path.insert(0, str(LIB_ROOT))
branches = importlib.import_module("°split_lib.branches")
classify = importlib.import_module("°split_lib.classify")
push_checks = importlib.import_module("°split_lib.push_checks")
cli = importlib.import_module("°split_lib.cli")
```
Two representative styles present:

- Unit-level (`PolicyMatrixTests`, `NamePolicyTests`) — construct `BranchClassification`/`CommitClassification` dataclasses directly and call `push_checks.check_content_policy` / `check_name_policy` in isolation, e.g.:
```python
def test_unclean_blocked_on_origin(self):
    self.assertIsNotNone(
        push_checks.check_name_policy(self._branch(branches.BranchFormat.UNCLEAN), "origin")
    )
```
- End-to-end (`EndToEndCheckPushTests`) — builds a real temp git repo (`git init`, commits, including copying the real `.ai-ignore` from the repo root), then drives the whole pipeline through `cli._check_push` with synthetic stdin lines, e.g.:
```python
def test_clean_to_non_origin_with_ai_tainted_blocked(self):
    sha = make_commit(self.repo, "ai/query.md", "ai: log prompt")
    code, output = self._run_check("backup", "refs/heads/feature-x", sha)
    self.assertEqual(code, 1)
    self.assertIn("clean-format", output)
```
Notably this file already uses `ai/query.md` as its example ai-tainted path in multiple tests (`test_unclean_to_non_origin_with_mixed_commit_allowed`, `test_clean_to_non_origin_with_ai_tainted_blocked`, `test_history_to_origin_with_ai_only_blocked_by_name_and_content_would_pass_content`) — a new query.md-on-push test would slot in naturally alongside these, likely in `EndToEndCheckPushTests` since the new check needs a real repo root (`_is_inside_base_repo` reads `origin`'s remote URL via git) rather than the pure dataclass-level tests.

## 8. `ai/°base/todo.md` lines ~140-163 — existing policy notes

The referenced section (`ai/°base/todo.md:155-163`, shown with surrounding context above) documents exactly the two checks already implemented (name policy + content policy) but has **no mention of an `ai/query.md`-specific check** at all:
```
Additionally, we need:

1. branch push name check
   1. do not allow **unclean** or **history** format-named branches to be pushed to a remote called `origin`.
2. branch push content check
   1. block ai or ai-containing commits to be pushed if the branch name is not **unclean** format.
   2. block code or code-containing commits to be pushed if the branch name is not **history** format.

- [x] Probably Done? At least low prio…
```
So there's no existing TODO/spec note for the specific "reject push if a commit touches root `ai/query.md` when this is the base/base repo" concern you're planning — it would be a genuinely new addition, not something partially specified already. Worth noting `push_checks.py`'s own module docstring (line 1-5) points back at these exact todo.md lines as its design doc, so if you add the new check, updating/extending that todo.md pointer (or adding a new note) would match the existing self-documentation convention.