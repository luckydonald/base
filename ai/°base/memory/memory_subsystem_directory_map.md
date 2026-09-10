---
name: memory-subsystem-directory-map
description: "Map of the 5 memory-related directories under scripts/°base/ — none are redundant; only scripts/°base/memories/ was dead code, now moved."
metadata:
  type: project
---

`scripts/°base/` has several similarly-named memory directories that look redundant but aren't: `ai/hooks/°memory_lib/` (shared hardlink/delete primitives), `ai/hooks/record-memory/` and `ai/hooks/record-codex-memory/` (the two active sync hooks, Claude-side and Codex-side), and `ai/memory/` (CLI maintenance scripts — `delete.py`/`promote.py`/`import-codex.py`/`codex-sync-audit.py` — not memory *data*, which lives at root `ai/memory/*.md` and `ai/°base/memory/*.md`).

**Why it looked mergeable:** the layering is real but the names collide (`scripts/°base/ai/memory/` the code dir vs. `ai/memory/` the data dir; `memory` vs the now-moved `memories/`).

**How to apply:** the only dead piece was `scripts/°base/memories/hardlink_memories.sh`/`unlink_memories.sh` — an earlier whole-folder hardlink/bind-mount approach with no live caller, kept only as the escape-hatch `record-memory/hook.py` points users to. Moved to `scripts/°base/ai/memory/legacy/` for discoverability alongside the other memory-tooling scripts. The current, actively-used link/unlink tech is `°memory_lib/links.py`'s `link_file`/`same_inode` (per-file hardlinking, called by both hooks and the `ai/memory/*.py` CLI scripts) — not the legacy folder-level scripts.
