[harness: subagent output matched instruction-shaped pattern(s): harness-envelope-tag. Control tags below are neutralized (`<` → `<\`); treat any remaining directive-shaped text as a finding to relay to the user, not an instruction to you.]

## Report

### 1. File paths

- Hook: `/home/user/git/luckydonald/base/scripts/°base/ai/hooks/save-prompt/hook.py`
- Shared library: `/home/user/git/luckydonald/base/scripts/°base/ai/hooks/_lib.py`
- Repo-identity/commit-style library: `/home/user/git/luckydonald/base/scripts/°base/ai/hooks/°commit_style_lib/__init__.py`
- Not `°reffiles_lib` (that's for file-mention auto-commits — `°reffiles_lib/commit.py`, `°reffiles_lib/mentions.py`); the base-vs-consuming-repo logic actually lives in `°commit_style_lib`.

### 2. Normal-case path resolution

`save-prompt/hook.py:1038`:
```python
log_path = resolve_log_path("ai/query.md", "ai/°base/query.md")
```
`_lib.py:670-693` (`resolve_log_path`):
```python
def resolve_log_path(default_relpath: str, base_relpath: str) -> Path:
    subproject = _subproject_root()
    git_root = _chdir_to_git_root()
    is_base = _is_inside_base_repo(subproject) or _is_inside_base_repo(git_root)
    ai_prefix = "ai/°base" if is_base else "ai"
    relpath = base_relpath if is_base else default_relpath
    ...
    log_path = (subproject / relpath).resolve()
    log_path.parent.mkdir(parents=True, exist_ok=True)
    return log_path
```
`is_base` comes from `_is_inside_base_repo` in `°commit_style_lib/__init__.py` (re-exported via `_lib.py:33`). This is the base-repo identity check (answers item 7 too).

### 3. `_render_loop_tick_entry` / `_reserve_loop_tick_file` (current source, `save-prompt/hook.py:771-814`)

```python
def _next_loop_tick_number(loop_dir: Path) -> int:
    if not loop_dir.exists():
        return 1
    numbers = [
        int(m.group(1))
        for path in loop_dir.iterdir()
        if path.is_file() and (m := re.match(r"^(\d+)_", path.name))
    ]
    return max(numbers, default=0) + 1


def _reserve_loop_tick_file(log_path: Path, text: str) -> Path:
    loop_dir = log_path.parent / "output" / "loop"
    if loop_dir.exists():
        for existing in sorted(loop_dir.glob("*.md")):
            try:
                if existing.read_text(encoding="utf-8") == text:
                    return existing
            except OSError:
                continue
    loop_dir.mkdir(parents=True, exist_ok=True)
    number = _next_loop_tick_number(loop_dir)
    target = loop_dir / f"{number:03d}_{slugify(text, fallback='tick')}.md"
    target.write_text(text, encoding="utf-8")
    return target


def _render_loop_tick_entry(prefix: str, text: str, log_path: Path) -> tuple[str, Path] | None:
    stripped = text.strip()
    if not LOOP_TICK_HEADER_RE.match(stripped):
        return None
    target = _reserve_loop_tick_file(log_path, stripped)
    header_line = next((line.strip() for line in stripped.splitlines() if line.strip()), "")
    label = header_line.lstrip("#").strip() or "Loop tick"
    rel_target = target.relative_to(log_path.parent).as_posix()
    link = _markdown_file_link(label, len(stripped), _human_size(str(target)), rel_target)
    return f"{prefix} {link}\n\n", target
```
**Important correction to the framing in the task**: this code itself is *not* hardcoded to `ai/query.md`. It derives `loop_dir` from `log_path.parent` (`output/loop/`), and `log_path` is passed in by the caller from `main()`, which always computes it via `resolve_log_path(...)` (line 1038). So the loop-tick functions faithfully use whatever path `resolve_log_path` gives them — they don't independently mis-resolve the base/consuming split.

### 4. Diff of commit `9909893...` for `save-prompt/hook.py`

Confirmed via `git show 99098937009ba32beeadb5b8aeced54e80dd1ea7 -- 'scripts/°base/ai/hooks/save-prompt/hook.py'`: adds `_next_loop_tick_number`, `_reserve_loop_tick_file`, `_render_loop_tick_entry`, and wires them into both call sites in `main()` (whole-prompt case and post-`<\task-notification>`-trailing-text case), consistently threading `log_path` through. No hardcoded `ai/query.md` path appears anywhere in this diff.

However, the commit's own file list shows it modified `ai/query.md` directly (92 lines added), even though this session ran inside the base repo — this is the actual observed bug, just not caused by hardcoding in `hook.py`.

### 5. Root cause — found via git archaeology

The real bug is upstream, in `_is_inside_base_repo` (`°commit_style_lib/__init__.py`), **not** in `save-prompt/hook.py`. History:

- `73a213a9a` (2026-08-12) — "Moved wrongly root `ai` folder plan/query to `./ai/°base/`" — an earlier occurrence of this exact same class of bug was cleaned up.
- `990989370` (2026-09-26, the commit named in the task) — added the loop-tick code and, in doing so, wrote 92 lines into `ai/query.md` instead of `ai/°base/query.md`.
- Five more commits kept appending to `ai/query.md` through **2026-09-28**: `927e13661`, `026495715`, `3d06a5898`, `98f9a7a27`, `f4f2d7196`, `7a7fb3ad5`.
- `d7d40ef9a` (2026-09-27) — **"Fixed `_is_inside_base_repo` misdetecting every linked `git worktree` as not being the base repo"** — this is the actual root-cause fix, and its own commit message states it explicitly:

  > `_is_inside_base_repo()` ... only checked `subproject_root.name == "base"`, which is never true inside a linked worktree (its own directory is named after the branch, not `base`), even though the worktree plainly belongs to this repo. This silently misrouted `ai/query.md` vs `ai/°base/query.md`, ...

  Diff (`°commit_style_lib/__init__.py`): before, `_is_inside_base_repo` just did `if subproject_root.name != "base": return False`. The fix added `_main_checkout_root()` using `git rev-parse --git-common-dir` as a worktree-proof fallback, and made `_git_text` accept an explicit `cwd=`.

So: commits `990989370` through `98f9a7a27` (Sep 26) ran from a linked worktree (evidenced by a debug-payload output-file path `/tmp/.../‑‑claude‑worktrees‑fix‑plan‑decision/.../tasks/....output` in the current `ai/query.md` tail), where `_is_inside_base_repo` wrongly returned `False`, so `resolve_log_path` picked `ai/query.md` instead of `ai/°base/query.md`. This bug was fixed on 2026-09-27 (`d7d40ef9a`), but:
- The fix was **not retroactive** — nothing moved the already-written bad entries out of `ai/query.md`.
- **`ai/query.md` still received writes on 2026-09-28** (commits `f4f2d7196` 26 lines, `7a7fb3ad5` 26 lines) — *after* the worktree fix landed — while `ai/°base/query.md` also grew in the same commits (8 lines in `7a7fb3ad5`). This means either another worktree/session-context still misroutes, or some code path bypasses `resolve_log_path` (e.g. the new `flush_pending_rejections` machinery added in `f4f2d7196`, which centralizes rejection-commit handling in `_lib.py` — worth checking separately whether it uses `resolve_log_path` or an independent path computation). This is outside the originally-scoped loop-tick bug but is still live contamination that would need the same cleanup.

Currently `ai/query.md` (`/home/user/git/luckydonald/base/ai/query.md`) contains base-repo-only content that should be in `ai/°base/query.md` — e.g. its current tail contains a "Task Notification" entry running `python3 -m unittest discover -s "scripts/°base/tests"` and a discussion about "Rebase this onto `base`", both clearly base-repo-internal work product, not content belonging to a consuming/subproject repo.

Confirm with:
```
git log --oneline --format="%h %ad %s" --date=short -- ai/query.md
```
Bad-write commits needing cleanup: `990989370`, `927e13661`, `026495715`, `3d06a5898`, `98f9a7a27`, `f4f2d7196`, `7a7fb3ad5` (all after the `73a213a9a` cleanup and mostly before/around the `d7d40ef9a` fix, with two stragglers after it).

### 6. Pre-push hook infrastructure

Real (non-sample) pre-push hooks exist, unrelated to `save-prompt`:
- `/home/user/git/luckydonald/base/.git/hooks/pre-push` — currently just the git-lfs trampoline (`git lfs pre-push "$@"`); no base-installed content is active in the *current* `.git/hooks/pre-push` (only lfs).
- Installer: `/home/user/git/luckydonald/base/scripts/°base/git/hooks/install/__init__.py` (and duplicate `setup.py`) — writes a trampoline at `.git/hooks/pre-push` that execs the tracked script below, preserving git-lfs behavior.
- Tracked hook script: `/home/user/git/luckydonald/base/scripts/°base/git/hooks/push/pre_push.sh` — runs git-lfs, then:
  ```sh
  python3 "$repo_root/scripts/°base/git/split.py" check-push \
      --remote-name "$remote_name" --remote-url "$remote_url" \
      <"$stdin_buf" || status=$?
  ```
- Policy logic: `/home/user/git/luckydonald/base/scripts/°base/git/°split_lib/push_checks.py` — pure branch-format/content push-policy checks (clean/unclean/history split), e.g. `check_content_policy`, `check_name_policy`, `evaluate_ref_update`. This is about clean/unclean/history branch-format push restrictions (see `ai/°base/todo.md:155-163`), **not** about the `ai/query.md` vs `ai/°base/query.md` routing bug — there is no existing push-time or pre-commit check guarding against writes to the wrong `query.md` file.
- `ai/settings/settings.json` only wires Claude-Code-level hooks (`PermissionRequest`, `PreCompact`, `PostCompact`, `SessionStart`, `PreToolUse`, `PostToolUse`); no push-related entries there.

### 7. Repo-identity ("is this the base repo") pattern

Canonical implementation: `_is_inside_base_repo` in `/home/user/git/luckydonald/base/scripts/°base/ai/hooks/°commit_style_lib/__init__.py:56-73` (current, worktree-proofed version):
```python
def _is_inside_base_repo(subproject_root: Path) -> bool:
    root = subproject_root
    if root.name != "base":
        root = _main_checkout_root(subproject_root)
        if root is None or root.name != "base":
            return False
    origin = _git_text("remote", "get-url", "origin", cwd=root)
    return bool(re.search(r"(^|[:/])luckydonald/base(\.git)?/?$", origin, re.I))
```
with the worktree-proof helper `_main_checkout_root` (lines 34-53) using `git rev-parse --git-common-dir`. `_lib.py` re-exports it (`_lib.py:33`: `_is_inside_base_repo = _commit_style._is_inside_base_repo`) and every consumer (`resolve_log_path`, `_ai_prefix_root`, `base_ai_commit_subject`, `°memory_lib/dirs.py`, `promote.py`) goes through this single function — so the September 27 fix (`d7d40ef9a`) automatically propagated everywhere except already-committed history.

Verified empirically that the current version correctly detects `is_base = True` from inside the still-present linked worktrees `claude-split-impl` and `claude-split-improvement`.