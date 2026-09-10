# Consolidate memory-related directories under `scripts/°base/`

## Context

`scripts/°base/` has five directories with "memory"/"memories" in their name, which reads as possible duplication or leftover cruft. The user asked whether they can be merged, and specifically whether the link/unlink hardlinking mechanism is still used. An Explore agent audited all five directories, their git history, and every caller. Verdict: they are **not actually redundant** — four are distinct, live layers of one subsystem, and one is dead legacy code kept only as a citation. This plan documents that finding as a project memory and relocates the one genuinely dead piece.

## Findings (to become the memory note)

| Directory | Role | Status |
|---|---|---|
| `scripts/°base/ai/hooks/°memory_lib/` | Shared library: `dirs.py` (resolves primary/secondary memory dir pair), `links.py` (`link_file`/`same_inode` — the hardlink primitive), `delete.py` (`delete_memory`/`unlink_path` — the only place a memory deletion gets committed), `codex_hook.py` (dynamic loader for `record-codex-memory/hook.py`) | Active, core — imported by every other piece below |
| `scripts/°base/ai/hooks/record-codex-memory/` | Hook: two-way syncs Codex's native ad-hoc notes into the repo's memory tree via a registry (avoids the old hostname-keyed ownership bug) | Active, heavy `link_file`/`unlink_path` use |
| `scripts/°base/ai/hooks/record-memory/` | Hook: hardlinks Claude's per-project memory files into the repo, auto-commits them; also contains the legacy-cleanup detector for old whole-folder hardlinks/bind-mounts | Active, most-touched file in the subsystem |
| `scripts/°base/ai/memory/` | CLI maintenance scripts (`delete.py`, `promote.py`, `import-codex.py`, `codex-sync-audit.py`) — **code, not memory data**; the actual notes live at root `ai/memory/*.md` and `ai/°base/memory/*.md` | Active, tested |
| `scripts/°base/memories/` | `hardlink_memories.sh`/`unlink_memories.sh` — an earlier whole-folder hardlink/bind-mount/symlink approach, superseded by per-file hardlinking in `record-memory/hook.py` | **Dead** — no code path calls it; only cited in `record-memory/hook.py`'s docstring (line 27) and a runtime warning message (line 376) as the escape-hatch a user should run if the hook detects leftover directory-level links/mounts it can't safely auto-remove itself |

Link/unlink mechanism: `°memory_lib/links.py`'s `link_file`/`same_inode` (plus `delete.py`'s `unlink_path`) is the **current, actively used** per-file hardlinking tech — called by both hooks and all the `ai/memory/*.py` CLI scripts. The old whole-*folder* hardlink/bind-mount scripts in `scripts/°base/memories/` are not executed by anything anymore; they're legacy reference material the newer per-file approach was modeled on.

No merge is warranted: the split (shared lib vs. two sync hooks vs. CLI tools) is a clean layering, not duplication. The only actionable cleanup is relocating the dead `scripts/°base/memories/` pair.

## Actions

1. **Move the legacy scripts**: `git mv scripts/°base/memories/hardlink_memories.sh scripts/°base/ai/memory/legacy/hardlink_memories.sh` and the same for `unlink_memories.sh`, removing the now-empty `scripts/°base/memories/` directory.

2. **Update the two hardcoded references** in `scripts/°base/ai/hooks/record-memory/hook.py`:
   - Line 27 (module docstring): `` `scripts/°base/memories/hardlink_memories.sh` `` → `` `scripts/°base/ai/memory/legacy/hardlink_memories.sh` ``
   - Line 264 (comment): same path update
   - Line 376 (runtime warning message shown to the user): `` `scripts/°base/memories/unlink_memories.sh` `` → `` `scripts/°base/ai/memory/legacy/unlink_memories.sh` ``

   Leave `ai/°base/query.md` untouched — it's an append-only historical query log, not live documentation.

3. **Write a project memory** at `ai/°base/memory/memory_subsystem_directory_map.md`:
   ```markdown
   ---
   name: memory-subsystem-directory-map
   description: "Map of the 5 memory-related directories under scripts/°base/ — none are redundant; only scripts/°base/memories/ was dead code, now moved."
   metadata:
     type: project
   ---

   `scripts/°base/` has several similarly-named memory directories that look redundant but aren't: `ai/hooks/°memory_lib/` (shared hardlink/delete primitives), `ai/hooks/record-memory/` and `ai/hooks/record-codex-memory/` (the two active sync hooks, Claude-side and Codex-side), and `ai/memory/` (CLI maintenance scripts — `delete.py`/`promote.py`/`import-codex.py`/`codex-sync-audit.py` — not memory *data*, which lives at root `ai/memory/*.md` and `ai/°base/memory/*.md`).

   **Why it looked mergeable:** the layering is real but the names collide (`scripts/°base/ai/memory/` the code dir vs. `ai/memory/` the data dir; `memory` vs the now-moved `memories/`).

   **How to apply:** the only dead piece was `scripts/°base/memories/hardlink_memories.sh`/`unlink_memories.sh` — an earlier whole-folder hardlink/bind-mount approach with no live caller, kept only as the escape-hatch `record-memory/hook.py` points users to. Moved to `scripts/°base/ai/memory/legacy/` for discoverability alongside the other memory-tooling scripts. The current, actively-used link/unlink tech is `°memory_lib/links.py`'s `link_file`/`same_inode` (per-file hardlinking, called by both hooks and the `ai/memory/*.py` CLI scripts) — not the legacy folder-level scripts.
   ```

4. **Append its index entry** to `ai/°base/memory/MEMORY.md`:
   ```
   - [Memory subsystem directory map](memory_subsystem_directory_map.md) — the 5 memory-related dirs under scripts/°base/ aren't redundant; only scripts/°base/memories/ was dead, now moved to ai/memory/legacy/.
   ```

## Verification

- `grep -rn "scripts/°base/memories" scripts/°base ai/°base/AGENTS.md` returns nothing (only the untouched `ai/°base/query.md` historical log still mentions the old path).
- `python3 -c "import ast; ast.parse(open('scripts/°base/ai/hooks/record-memory/hook.py').read())"` to confirm the hook still parses after the string edits.
- Run the existing test suite: `uv run --project scripts/°base python -m unittest discover -s scripts/°base/tests -v` to confirm nothing depended on the old `scripts/°base/memories/` path.
- Manually eyeball `git mv` preserved file content unchanged (`git diff --stat` shows pure renames, no content diff).
