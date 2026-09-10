## Findings

**File paths and line numbers:**

1. `unlink_path` — `/home/user/git/luckydonald/base/scripts/°base/ai/hooks/°memory_lib/delete.py:28-30` (re-exported via `°memory_lib/__init__.py:2`, called in `hook.py` as `memory_lib.unlink_path`, e.g. `hook.py:563, 566`). `hook.py` resolves `memory_lib = importlib.import_module("°memory_lib")` at `hook.py:46`, so `hook.memory_lib` is this `°memory_lib` package, not a separate `memory_lib` file.

2. `project_memory_dirs` — `hook.py:88-90`; `project_memory_dir` — `hook.py:93-95`. Both delegate to `memory_lib.memory_dirs(root)` defined in `/home/user/git/luckydonald/base/scripts/°base/ai/hooks/°memory_lib/dirs.py:11-26`.

3. `METADATA_NAME` — `hook.py:50`; `read_codex_sync` — `hook.py:204-217`; `write_codex_sync` — `hook.py:236-238`.

**Behavior of `unlink_path`:**
```python
28  def unlink_path(path: Path) -> None:
29      if path.is_symlink() or path.exists():
30          path.unlink()
```
It is a plain, defensive single-file unlink — it only removes `path` itself (if it's a symlink or exists) and does **not** touch the parent directory. There is no walking upward to remove now-empty parent directories; no empty-dir pruning logic exists anywhere in `delete.py`.

**`project_memory_dir(root)` return value:**
It is not a fixed `"ai/memory"` string — it depends on whether `root` is inside the base repo itself, via `memory_dirs()`:
```python
11  def memory_dirs(subproject: Path) -> tuple[Path, Path]:
12      """(primary, secondary) memory dirs under `subproject`, primary first.
13  
14      Inside the base repo: primary=ai/°base/memory, secondary=ai/memory --
15      memories about developing the base tooling itself default there, but a
16      memory relevant to consuming repos too can live in the secondary,
17      subproject-facing `ai/memory/` instead (see `scripts/°base/ai/memory/promote.py`).
18      Elsewhere: primary=ai/memory, secondary=ai/°base/memory (unused/never
19      created outside the base repo, but always returned as a Path so callers
20      have a uniform two-dir shape to check).
21      """
22      base_dir = subproject / "ai" / "°base" / "memory"
23      root_dir = subproject / "ai" / "memory"
24      if _is_inside_base_repo(subproject):
25          return base_dir, root_dir
26      return root_dir, base_dir
```
So `project_memory_dir(root)` (= `memory_dirs(root)[0]`) returns `root/ai/°base/memory` when `root` is inside the base repo, and `root/ai/memory` otherwise.