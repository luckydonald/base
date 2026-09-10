Now I have everything needed for a thorough report.

## Directory-by-directory breakdown

### 1. `scripts/°base/ai/hooks/°memory_lib/` — shared code library (active, core)
Files: `__init__.py`, `dirs.py`, `delete.py`, `links.py`, `codex_hook.py` (+ `__pycache__`).

Purpose: the shared primitives used by every other memory piece, following the repo's `°name_lib` package convention (per `ai/°base/memory/feedback_lib_naming_convention.md`). Loaded via `importlib.import_module("°memory_lib")`.
- `dirs.py::memory_dirs(subproject)` — resolves the (primary, secondary) memory directory pair: inside base repo `(ai/°base/memory, ai/memory)`, elsewhere `(ai/memory, ai/°base/memory)` (secondary unused outside base).
- `links.py::link_file`/`same_inode` — the actual link/unlink filesystem primitive (see section below).
- `delete.py::delete_memory`/`is_tracked`/`unlink_path` — the "originate a marked deletion commit" logic (only place a memory deletion is ever committed, per `ai/°base/plans/007_prevent-accidental-memory-deletion.md`).
- `codex_hook.py::load_codex_hook_module` — dynamically loads `record-codex-memory/hook.py` as a module (workaround because parent dirs use non-ASCII/hyphenated names, so it can't be a normal package import).

Very actively used — imported by both hooks and all three `ai/memory/*.py` CLI scripts. Created relatively recently (commits `a9ec8a9`, `4cccee5`, `8f87b8c`).

### 2. `scripts/°base/ai/hooks/record-codex-memory/` — hook (active)
Files: `hook.py` (632 lines), `codex-sync.schema.json`, `registry.schema.json`.

Purpose: fires on Codex write tools / `SessionStart` / `Stop` to two-way-sync Codex's native ad-hoc memory notes into the shared project memory tree (`ai/memory` or `ai/°base/memory`), using a registry (`registry.schema.json`) to avoid the old hostname-keyed ownership bug (see user memory "Codex memory orphan-resource bug" and commit `a9efce8`, most recent touch to this dir). Uses `memory_lib.link_file`, `same_inode`, `unlink_path` heavily (lines 388-566) for hardlinking Codex's native resource files into the project tree and vice versa.

Documented in `ai/°base/AGENTS.md` line 108. Actively maintained (most recent commit is the top-of-branch registry rewrite).

### 3. `scripts/°base/ai/hooks/record-memory/` — hook (active)
Files: `hook.py` (447 lines).

Purpose: the Claude-side counterpart — fires on `PostToolUse(Write|Edit|Bash)` and `SessionStart` to hardlink Claude's per-project memory files (from `~/.claude/projects/<encoded-path>/memory/*.md`, or `$CLAUDE_CONFIG_DIR` equivalent) into the repo (`ai/memory/*.md` or `ai/°base/memory/*.md`), auto-committing them. Also contains the "DANGER ZONE" legacy-cleanup code (lines 260-380) that detects and removes an old whole-folder link left by `scripts/°base/memories/hardlink_memories.sh`, explicitly warning the user to run `unlink_memories.sh` when it finds something it can't safely auto-remove (a bind mount or directory hardlink).

Documented in `ai/°base/AGENTS.md` line 107. Actively maintained — most-touched file in the whole memory subsystem (12+ commits).

### 4. `scripts/°base/ai/memory/` — CODE, not memory data (active)
Files: `delete.py`, `promote.py`, `import-codex.py`, `codex-sync-audit.py`.

This is **not** memory content — it's a set of CLI maintenance scripts for the memory system, confusingly named `ai/memory` (mirroring the *target* directory name it operates on, `ai/memory/` and `ai/°base/memory/`, not containing memory notes itself):
- `delete.py` — CLI wrapper around `memory_lib.delete_memory` for deleting one memory + its Codex mirror.
- `promote.py` — moves a memory between `ai/°base/memory/` (base-tooling-only) and root `ai/memory/` (subproject-facing), rewriting `MEMORY.md` index stub links and relocating `.codex-sync.json` entries.
- `import-codex.py` — assigns one native Codex ad-hoc note to the current project.
- `codex-sync-audit.py` — reports/fixes ad-hoc Codex notes claimed by more than one project (cleanup tool for the pre-registry hostname-keyed bug).

All actively used, referenced in `AGENTS.md`, and covered by tests (`test_memory_delete.py`, `test_memory_promote.py`, `test_codex_memory_registry.py`, `test_codex_sync_audit.py`).

**Important distinction**: the actual memory *data* (markdown notes) lives at `ai/°base/memory/*.md` (base-tooling notes) and root `ai/memory/*.md` (subproject-facing notes) — these are sibling paths at the repo root, separate from `scripts/°base/ai/memory/` (which is pure code, nested under `scripts/`). The near-identical names (`ai/memory` vs `scripts/°base/ai/memory`) are a real naming collision risk for anyone skimming paths.

### 5. `scripts/°base/memories/` — DEAD/legacy code (only fossil of an earlier architecture)
Files: `hardlink_memories.sh`, `unlink_memories.sh`.

Purpose: an earlier, whole-folder-hardlink (or bind-mount, or symlink) approach — hardlink/mount/symlink the *entire* `~/.claude/projects/<encoded>/memory` directory into `.claude/memory` in the repo, with sudo/systemd/fstab plumbing for bind mounts. Superseded by the current per-file hardlink strategy in `record-memory/hook.py` (explicitly says in its own docstring: "Linking strategy mirrors `scripts/°base/memories/hardlink_memories.sh` but for single files").

Git history: only 2 commits ever — `a80466c` (2026-05-05, the bulk `ai/scripts/**` → `scripts/°base/**` move) and `9a8671b` (2026-05-14, an "AllMyStorage merge"). No commit has touched the *content* of these scripts since they were written; they predate `record-memory/hook.py` (whose earliest commit, `816bdb7`, says it hardlinks "Claude memories into the project tree", explicitly modeled on this pair).

**Still referenced today**, but only as a fallback/reference, not as an active code path:
- `record-memory/hook.py` names both scripts in its module docstring and in a runtime warning message (told to the user only if it finds a leftover bind-mount/dir-hardlink from the old approach that it can't safely auto-clean).
- `ai/°base/query.md` (a query log) references them once, from when they were being adapted into the new hook.

No other script imports, sources, or executes them. They are not called from any hook lifecycle, from `AGENTS.md`'s hook table, or from any test. This is a standalone bash tool a user would run manually (or has already run once) — currently vestigial except as the still-cited "if this legacy state exists, go run this" escape hatch.

## Link/unlink findings

- **Mechanism**: `scripts/°base/ai/hooks/°memory_lib/links.py` provides the *only* current link primitive: `link_file(source, destination)` — hardlinks `destination` to `source` (falls back to a symlink if `os.link` fails, e.g. cross-filesystem), and `same_inode()` to check if two paths already share a filesystem object. `delete.py::unlink_path` in the same package removes a path whether it's a symlink or regular file/dir entry.
- **Purpose today**: keeping the external Claude/Codex memory-note stores and the in-repo `ai/memory`/`ai/°base/memory` mirrors as durable hardlinked twins, so editing either side propagates and `git add`/`git commit` on the repo side "just works" without special-casing symlinks.
- **Active callers** (confirmed via grep of `memory_lib\.`):
  - `record-memory/hook.py` — `link_file`, `same_inode`, plus `memory_lib.delete_memory` (which itself calls `unlink_path`).
  - `record-codex-memory/hook.py` — heavy use of `link_file`/`same_inode` (lines 388-416, 447-453) and `unlink_path` (lines 563, 566).
  - `ai/memory/delete.py`, `promote.py`, `codex-sync-audit.py` — via `memory_lib.delete_memory`/`is_tracked`/`unlink_path`.
- **Vestigial counterpart**: the *old* whole-folder link/unlink mechanism is `scripts/°base/memories/hardlink_memories.sh` + `unlink_memories.sh` — these implement a much heavier hardlink→bind-mount→symlink cascade at directory granularity, including sudo/fstab/systemd persistence. This is **not called by any current code path** — it's dead as an executed mechanism, kept only as (a) design inspiration cited in `record-memory/hook.py`'s docstring, and (b) a manual escape-hatch script the hook tells users to run if it detects legacy directory-level links/mounts it can't safely remove itself. Verdict: **vestigial/legacy**, safe to consider archiving or folding into documentation, but not delete outright while any user might still have an old directory-hardlink/bind-mount installed (the hook's self-protection logic explicitly depends on `unlink_memories.sh` still existing at that path for its printed instructions to be correct).

## Documentation references

- `ai/°base/AGENTS.md`: lines 38 (table entry: `ai/°base/` holds "AI artifacts... memory"), 107-108 (hook table: `record-memory/hook.py` and `record-codex-memory/hook.py`), 113 (`require_memory_delete_marker.py` commit hook). No mention of `scripts/°base/memories/` or `°memory_lib` by path.
- `ai/°base/plans/`: `007_prevent-accidental-memory-deletion.md`, `012_fix-record-memory-hook-misses-paths-with-underscores.md`, `041_...memory-file-deletions-never-propagate-to-the-repo-mirror.md`, `051_scoped-two-way-codex-memory-sync.md`, `062_dual-directory-ai-memory-ai-base-memory-root-ai-memory-in-th.md` (the design doc explaining primary/secondary dir resolution — directly relevant), `063_redesign-codex-ad-hoc-memory-ownership-tracking.md`, `064_fix-codex-sync-audit-py-fix-crash-on-empty-memory-dir.md`.
- `ai/°base/memory/*.md`: `feedback_lib_naming_convention.md` (explains the `°name_lib` convention `°memory_lib` follows), `project_dual_codex_config_dirs.md`, `project_codex_memory_orphan_resource_bug.md`, `codex_sync_audit_fix_empty_memory_dir.md` — all describe pieces of this exact architecture and are directly relevant background for any consolidation plan.
- `ai/°base/query.md`: one historical reference to the two `memories/` shell scripts, from when `record-memory` was being designed off of them.

## Naming inconsistencies and hardcoded-path risk (impact assessment)

- **`memory` vs `memories`**: `scripts/°base/ai/memory/` (code) vs `scripts/°base/memories/` (legacy shell scripts) — different directories, easy to confuse by name alone; also collides in name (not path) with the actual memory-data directories `ai/memory/` and `ai/°base/memory/` at repo root.
- **`°memory_lib` vs `memory_lib`**: the package directory is `°memory_lib` (degree-sign prefixed, per convention) but always imported as the bare string `"°memory_lib"` via `importlib.import_module` — no separate unprefixed alias exists, so this isn't really an inconsistency, just the deliberate convention.
- **Hardcoded/literal path references** (impact surface for any rename):
  - `"°memory_lib"` import string appears in: `record-memory/hook.py`, `record-codex-memory/hook.py`, `ai/memory/delete.py`, `ai/memory/promote.py`, `ai/memory/codex-sync-audit.py` (via `codex_hook.load_codex_hook_module`, which also hardcodes the relative path to `record-codex-memory/hook.py`).
  - `"scripts/°base/memories/hardlink_memories.sh"` / `"unlink_memories.sh"` literal strings appear only in `record-memory/hook.py` (docstring + one runtime warning message) and `ai/°base/query.md`.
  - `"scripts/°base/ai/memory/delete.py"` is referenced as a literal string inside `record-memory/hook.py`'s `_check_memory_index_consistency` warning message (telling the user which script to run).
  - Test files with direct dependence: `test_memory_delete.py`, `test_memory_promote.py`, `test_codex_memory_registry.py`, `test_codex_sync_audit.py`, `test_ai_hooks_base_routing.py` (all under `scripts/°base/tests/`).
  - `scripts/°base/git/hooks/commit/require_memory_delete_marker.py` references "memory" concepts/paths as a commit-msg hook validating the `Deleted Memory: <name>` marker.

## Redundancy / merge candidates (observations, no plan proposed)

- `scripts/°base/memories/` (2 files) is the only directory of the five with **no live code path calling it** — it's cited only in comments/docstrings/warning text elsewhere. It's the clearest dead-weight candidate, but it can't be deleted without also either (a) updating `record-memory/hook.py`'s warning message and docstring to stop pointing users at it, or (b) deciding what replaces it as the "how do I clean up an old directory-hardlink/bind-mount" instructions.
- `scripts/°base/ai/memory/` and `scripts/°base/ai/hooks/°memory_lib/` have a natural boundary already (CLI scripts vs. shared library) but sit in different parent trees (`ai/memory/` vs `ai/hooks/°memory_lib/`) purely for historical reasons — `ai/memory/`'s CLI scripts already import from `°memory_lib` for everything nontrivial, so functionally they're one subsystem split across two directories that happen to share almost no code duplication (the split is clean, not redundant), but the name collision with the real memory-data dirs at `ai/memory/` (repo root) and `ai/°base/memory/` is a genuine confusion risk worth addressing by rename (e.g. `ai/memory-tools/` or similar) rather than merge.
- `record-memory/hook.py` and `record-codex-memory/hook.py` are not redundant with each other — they sync two different external sources (Claude-side files vs. Codex-side native notes) into the same target directories, sharing logic only through `°memory_lib`. No overlap to consolidate beyond what already lives in the shared lib.