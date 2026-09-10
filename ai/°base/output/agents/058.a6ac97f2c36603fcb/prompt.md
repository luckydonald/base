In the repo /home/user/git/luckydonald/base, find the implementation of:
1. `unlink_path` in whatever module is imported as `hook.memory_lib` (likely under scripts/°base/ai/hooks/record-codex-memory/hook.py or a shared memory_lib module it imports)
2. `project_memory_dir` and `project_memory_dirs` functions used in scripts/°base/ai/memory/codex-sync-audit.py and referenced via `hook.project_memory_dir(...)` / `hook.project_memory_dirs(...)` — these come from scripts/°base/ai/hooks/record-codex-memory/hook.py
3. `METADATA_NAME`, `read_codex_sync`, `write_codex_sync` in the same hook.py

Report back:
- The exact file paths and line numbers for each
- What `unlink_path` does when it removes the last file in a directory (does it remove the now-empty parent directory too, walking upward?)
- What `project_memory_dir(root)` returns (the relative path under `root`, e.g. is it always "ai/memory" or does it depend on config)
- Full source of `unlink_path` and `project_memory_dir`/`project_memory_dirs`

Keep the report factual and include code snippets with line numbers. Under 400 words plus code snippets.