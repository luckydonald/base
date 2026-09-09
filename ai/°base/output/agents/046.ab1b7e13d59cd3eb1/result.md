## Report: How the AI-memory system decides base repo vs. subproject memory path

### 1. `scripts/°base/ai/hooks/_lib.py`

- `_is_inside_base_repo` is actually **defined in** `scripts/°base/ai/hooks/°commit_style_lib/__init__.py:34-45` and re-exported by `_lib.py:29`. Logic:
```python
def _is_inside_base_repo(subproject_root: Path) -> bool:
    if subproject_root.name != "base":
        return False
    origin = _git_text("remote", "get-url", "origin")
    return bool(re.search(r"(^|[:/])luckydonald/base(\.git)?/?$", origin, re.I))
```
  i.e. true only when the project dir is literally named `base` *and* `origin` points at `luckydonald/base`.

- `resolve_log_path()` (`_lib.py:247-270`) — the general AI-artifact path resolver (used for `query.md` etc., not memory specifically):
```python
is_base = _is_inside_base_repo(subproject) or _is_inside_base_repo(git_root)
ai_prefix = "ai/°base" if is_base else "ai"
relpath = base_relpath if is_base else default_relpath
```
  Same pattern repeats in `_ai_prefix_root()` (`_lib.py:41-49`) and `base_ai_commit_subject()` (`°commit_style_lib/__init__.py:60-64`). There is **no dedicated "memory dir" function in `_lib.py` itself** — each memory-touching module implements its own tiny `_memory_dirs`/`project_memory_dir` using the same `ai/°base/memory` vs `ai/memory` ternary (three separate copies, listed below).

### 2. `scripts/°base/ai/hooks/record-memory/hook.py`

- `_memory_dirs()` (line 58-61):
```python
def _memory_dirs(subproject: Path) -> tuple[Path, Path]:
    src = _encoded_project_dir(subproject) / "memory"
    rel = "ai/°base/memory" if _is_inside_base_repo(subproject) else "ai/memory"
    return src, subproject / rel
```
- Source discovery: `_encoded_project_dir()` (`_lib.py:222-228`) resolves `$CLAUDE_CONFIG_DIR` or `~/.claude` (`_claude_config_dir()`, `_lib.py:212-219`), then `<config-dir>/projects/<encoded-subproject-path>/memory/`.
- Same base/non-base branch is duplicated verbatim in `scripts/°base/ai/memory/delete.py:25` and in `record-codex-memory/hook.py`'s `project_memory_dir()` (`scripts/°base/ai/hooks/record-codex-memory/hook.py:61-66`).

### 3. `°memory_lib` package

- `__init__.py` just re-exports `delete_memory`, `is_tracked`, `link_file`, `same_inode`, `unlink_path` — no path-decision logic.
- `links.py`: `link_file(source, destination)` and `same_inode` are pure filesystem primitives (hardlink-then-symlink-fallback); they take already-resolved paths and have no knowledge of base-vs-subproject routing.
- `delete.py`: `delete_memory(name, *, src_dir, dst_dir, dst_dir_rel)` unlinks both copies and commits with a `Deleted Memory: <name>` marker; it also takes already-resolved dirs — the caller (`record-memory/hook.py`) is responsible for computing `dst_dir`/`dst_dir_rel` via `_memory_dirs()`.

So the actual slug→path mapping is **not** centralized in `°memory_lib`; it lives in each caller's local `_memory_dirs`/`project_memory_dir` helper, duplicated 3x (`record-memory/hook.py:58-61`, `record-codex-memory/hook.py:61-66`, `scripts/°base/ai/memory/delete.py:23-26`).

### 4. Tests

`scripts/°base/tests/test_ai_hooks_base_routing.py` — `test_memory_in_base_repo_routes_and_prefixes` (line 1143) asserts that inside the base repo, memory lands in `ai/°base/memory/note.md` and **`ai/memory` must not exist** (`self.assertFalse((repo / "ai" / "memory").exists())`, line 1164). `test_memory_posttooluse_write_with_underscore_in_project_path` (line 1225) asserts a non-base repo writes to `ai/memory/tip.md`. Codex-memory tests (`test_codex_memory_hook_commits_and_is_idempotent`, etc.) mirror the same split. `test_memory_delete.py` covers the marker-commit requirement, not path routing.

### Key finding: precedent already exists

There is **currently no code path** that makes the base repo write memory into a root-level `ai/memory/` of its own — `_is_inside_base_repo` + all three duplicated helpers always force base-repo memory into `ai/°base/memory/`, and the test above explicitly pins that.

However, `ai/memory/` **does already exist on disk right now** (`ls` confirms: `ai/memory/MEMORY.md`, `repo_commit_hooks.md`, `2026-07-20-history-master-replay-guards.md`, `.codex-sync.json`), created manually via commit `726ab6a "[base] repo hook memory: Moved to non-base memory folder."` (2026-09-09). That commit moved `repo_commit_hooks.md` out of `ai/°base/memory/` into a hand-created `ai/memory/`, with `ai/°base/memory/MEMORY.md` updated to cross-link it via `../../memory/repo_commit_hooks.md`. This is a manual, hook-unsupported precedent for exactly the split you're planning: `ai/°base/memory/` = memory about the base-tooling project itself, `ai/memory/` = memory about *this checkout as a repo* (its own commit hooks etc.). No hook currently maintains or knows about that second folder — it was built by hand, and any future `record-memory`/`record-codex-memory` SessionStart sync would still only look at `ai/°base/memory/` and ignore/orphan `ai/memory/` since the three duplicated `_memory_dirs` helpers are strictly base-repo → `ai/°base/memory`, no in-between case.