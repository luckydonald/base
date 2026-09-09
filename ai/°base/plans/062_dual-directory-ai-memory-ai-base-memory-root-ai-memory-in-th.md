# Dual-directory AI memory: `ai/°base/memory/` + root `ai/memory/` in the base repo

## Context
The base repo's memory system currently forces every repo (base included) into exactly **one** memory
directory, chosen by `_is_inside_base_repo()`: base repo → `ai/°base/memory/`, everything else →
`ai/memory/`. This choice is duplicated three times (`record-memory/hook.py`, `record-codex-memory/hook.py`,
`scripts/°base/ai/memory/delete.py`), each hardcoding a single target dir.

The user manually promoted one memory (`repo_commit_hooks.md`, a note about the commit-trailer-rejection
hook — relevant to every consuming repo, not just base-tooling development) from `ai/°base/memory/` to a
new root `ai/memory/` (commit `726ab6a0a`), since `ai/memory/` is exactly the directory name consuming repos
already use for their own memory — putting it there makes it "available to subprojects" through base's
normal template-propagation. `ai/°base/memory/` stays for memories specifically about developing/maintaining
the base tooling itself. `ai/°base/memory/MEMORY.md` keeps a relative-link stub entry for the promoted file
(`- [Repo commit hooks](../../memory/repo_commit_hooks.md) — <same description>`) so base's own index stays a
superset view (own + promoted); the root `ai/memory/MEMORY.md` only lists promoted/shared ones.

Because none of the three routing helpers know a second valid directory can exist, the very next
`record-codex-memory` sync (commit `20223e6`) resurrected a duplicate `ai/°base/memory/repo_commit_hooks.md`
(byte-identical) plus a duplicate, placeholder (`TODO: summarize this file.`) `MEMORY.md` line — this
duplicate is **currently sitting in the repo's working tree right now** and needs cleaning up as part of
this fix, not just designing around.

Confirmed decisions (do not revisit):
1. New/incoming memories keep defaulting to `ai/°base/memory/` in the base repo (unchanged) — promoting to
   `ai/memory/` stays a deliberate, separate step.
2. Add a `promote`/`demote` script that does that step (git mv + both `MEMORY.md` updates), in both directions.
3. Keep the two `.codex-sync.json` files fully independent (one per directory, no schema merge) — the
   resurrection fix is a targeted "does this name already exist in the other dir" guard, not a metadata
   restructure.

## Implementation

### 1. Centralize directory resolution — `°memory_lib`
New `scripts/°base/ai/hooks/°memory_lib/dirs.py`:
```python
def memory_dirs(subproject: Path) -> tuple[Path, Path]:
    """(primary, secondary), primary first. Base repo: (ai/°base/memory, ai/memory).
    Elsewhere: (ai/memory, ai/°base/memory) — secondary is unused/never created there."""
```
Computes `_is_inside_base_repo(subproject)` itself (import from `_lib`, same as `°memory_lib/delete.py`
already does for `base_ai_commit_subject` — `°memory_lib` already depends on `_lib.py`, so this is
consistent, not a new dependency). Export via `°memory_lib/__init__.py` (`from .dirs import memory_dirs`,
add to `__all__`).

Replace all three duplicated helpers with calls to this:
- `record-memory/hook.py:58-61` (`_memory_dirs`) — delete; `main()` (~line 381) becomes
  `dst_dir, secondary_dir = memory_lib.memory_dirs(subproject)` (Claude-side `src_dir` computation is
  unrelated, stays as-is).
- `record-codex-memory/hook.py:61-66` (`project_memory_dir`) — delete; every call site
  (`synchronize_shared_memory` L202, `import_native_note` L261/282, `commit_project_memory` L333,
  `delete_scoped_memory` L377) switches to `memory_lib.memory_dirs(root)`, keeping a local one-line
  `_primary(root) -> Path: return memory_lib.memory_dirs(root)[0]` wrapper for the 3 call sites that only
  need primary (`import_native_note`, `commit_project_memory`) so they need no further edits beyond the
  rename.
- `scripts/°base/ai/memory/delete.py:23-26` (`_memory_dirs`) — delete; replaced by the dual-lookup in §3.

### 2. Resurrection-prevention guard (both hooks)

**`record-memory/hook.py::_sync_all`** (L142-175): new signature
`_sync_all(src_dir, dst_dir, secondary_dir, dst_dir_rel)`. In the `src_dir.glob("*.md")` loop, before the
existing `if not dst.exists():` resurrection branch, add:
```python
secondary = secondary_dir / src.name
if not dst.exists():
    if secondary.is_file():
        if not memory_lib.same_inode(secondary, src):
            memory_lib.link_file(secondary, src)
        continue
    # ...existing _is_marked_deleted / link_file(src, dst) logic unchanged
```
i.e. if the authoritative copy already lives in the *other* known dir (promoted/demoted), re-point the
Claude-side hardlink at that file instead of recreating a duplicate in `dst_dir`. No commit needed — only
the external Claude-side file changes here.

Apply the same one-line guard in the `PostToolUse(Write/Edit)` branch (~L406-417): if `secondary_dir / rel`
exists and `dst_dir / rel` doesn't, link into `secondary_dir` instead of `dst_dir`, and pass that dir's
relpath to `_commit`.

**`record-codex-memory/hook.py::synchronize_shared_memory`** (L201-238): in the resource→project loop
(L224-237), same guard before `if not target.exists():`'s creation branch:
```python
secondary_target = secondary_dir / source.name
if not target.exists():
    if secondary_target.is_file():
        if not memory_lib.same_inode(secondary_target, source):
            memory_lib.link_file(secondary_target, source)
        continue
    # ...existing link_file(source, target) / add_index_entry logic unchanged
```
The `.codex-sync.json` split stays independent (per decision #3) — the sync hook only ever guards against
*duplicating*; it never infers a metadata relocation from a bare filename match. Relocating a `sources`/
`ignored` entry between the two files, when one exists, is `promote.py`'s job (see §4), not this hook's.

**`delete_scoped_memory`** (L375-415): also extend to clean up a promoted memory's *stub* line. Currently
it only edits `memory_dir / "MEMORY.md"` (the single primary dir). Change to check **both**
`memory_dirs(root)` dirs' `MEMORY.md` for a line referencing `name` (matching `]({name})` same as today) and
strip it from whichever has it — since a promoted memory's stub line lives in the non-owning dir's index,
not just the owning one.

### 3. `delete.py` — find/delete a memory regardless of which dir holds it
Replace the single-dir lookup (L60-68) with a loop over `memory_lib.memory_dirs(subproject)` (primary then
secondary), picking the first dir where `memory_lib.is_tracked(f"{dir_rel}/{name}")` is true; error only if
neither has it. The rest of `main()` (the `delete_memory(...)` call, the Codex-mirror cleanup) is unchanged —
`delete_scoped_memory` already resolves both dirs per §2's extension.

### 4. New `scripts/°base/ai/memory/promote.py` (with `--demote`)
CLI: `python3 scripts/°base/ai/memory/promote.py <name.md> [--demote]`. Only valid inside the base repo
(`_is_inside_base_repo`) — exit 2 otherwise, since a consuming repo has no `ai/°base/memory` to promote
from/to.

Algorithm (promote direction; `--demote` swaps src/dst and the stub-link relative path):
1. Validate `name` (plain `.md` filename, same check as `delete.py`), source file exists and is tracked,
   destination doesn't already have a same-named file (collision → error, mirroring `import_native_note`'s
   collision check).
2. `git mv <src_dir_rel>/<name> <dst_dir_rel>/<name>`.
3. Append the source's exact existing `MEMORY.md` entry line (title + description, unchanged) to the
   destination `MEMORY.md` (bootstrap with `# Memory\n` header if the file doesn't exist yet — root
   `ai/memory/MEMORY.md` won't always pre-exist).
4. Rewrite the *source* `MEMORY.md`'s line for `name` in place: replace `](name)` with the relative-link
   stub — `](../../memory/{name})` for promote, `](../°base/memory/{name})` for demote — keeping the rest of
   the line byte-for-byte. Do not delete the line.
5. If the source dir's `.codex-sync.json` has a `sources`/`ignored` entry whose `target == name`, pop it and
   insert the identical entry (same identity key, same `hash`) into the destination `.codex-sync.json`
   (creating it via the hook's `empty_metadata()` shape if absent). Reuse `record-codex-memory/hook.py`'s
   `read_metadata`/`write_metadata` — load the hook module the same way `delete.py::_codex_hook()` already
   does (consider factoring that loader into `°memory_lib` so `delete.py` and `promote.py` share one
   implementation instead of a third copy).
6. `git add` both `MEMORY.md` files and any touched `.codex-sync.json`; commit via
   `base_ai_commit_subject(f"ai: promote memory {Path(name).stem}")` (or `"demote"`).
   **No `Deleted Memory:` marker needed** — a pure `git mv` is detected as a rename (`R`, not `D`) by
   `git diff --cached --diff-filter=D`, so `require_memory_delete_marker.py` doesn't fire on it, and the
   source `MEMORY.md` stub-rewrite is a content edit to an existing tracked file, not a deletion. (Verify
   this empirically in a test — see §5 — since the whole design leans on it.)
7. Print `Promoted memory {name} in {commit}` (mirroring `delete.py`'s final print).

### 5. Tests
Existing tests that stay valid unmodified (no secondary dir ever created in their scenarios):
`test_memory_in_base_repo_routes_and_prefixes`, `test_memory_session_start_restores_missing_claude_source_from_repo`,
`test_memory_session_start_does_not_resurrect_marked_deleted_memory`,
`test_memory_posttooluse_write_with_underscore_in_project_path`, all of `test_memory_delete.py`, and the
existing `record-codex-memory` idempotency/unassigned-note tests in `test_ai_hooks_base_routing.py` (none
import the renamed internal helpers directly — only exercised via hook `main()`/CLI).

New tests (in `scripts/°base/tests/test_ai_hooks_base_routing.py` unless noted):
- `test_memory_session_start_does_not_resurrect_across_promoted_directory` — seed `ai/memory/<name>.md`
  (tracked) plus a stale differently-content Claude-source copy; run `SessionStart`; assert
  `ai/°base/memory/<name>.md` is never created and the Claude source ends up hardlinked with `ai/memory/`.
- `test_codex_memory_sync_does_not_resurrect_across_promoted_directory` — same idea for
  `record-codex-memory/hook.py`: seed the resource dir + `ai/memory/<name>.md`; run the hook; assert
  `ai/°base/memory/<name>.md` is not created.
- `test_delete_helper_deletes_promoted_memory_from_root_dir` — seed a tracked memory under `ai/memory/` in a
  base repo, run `delete.py`, assert it's found/removed there (not just the primary dir).
- New `scripts/°base/tests/test_memory_promote.py`:
  - `test_promote_moves_file_and_rewrites_both_memory_md` — full round trip: file only at `ai/memory/<name>`
    afterward (confirm via `git ls-files`), destination `MEMORY.md` has the verbatim entry, source
    `MEMORY.md`'s line rewritten to the stub form with description preserved, and the commit passes the real
    `require_memory_delete_marker.py` pre-commit hook with **no** marker present.
  - `test_demote_reverses_promote` — round-trip, stub direction flips to `](../°base/memory/<name>)`.
  - `test_promote_relocates_codex_sync_entry_when_present` — seed a `sources[identity]` entry in the source
    `.codex-sync.json`, run promote, assert it now lives (same identity/hash) in the destination file.
  - `test_promote_refuses_when_destination_already_has_same_name` — collision guard.

### 6. One-off cleanup of the live duplicate (separate commit, landed *after* §2's fix)
Target state: `repo_commit_hooks.md` exists only at `ai/memory/repo_commit_hooks.md` (already correct);
`ai/°base/memory/MEMORY.md` has just its original 3 lines (line 3 is the already-correct stub).
1. `git rm "ai/°base/memory/repo_commit_hooks.md"` (byte-identical duplicate, confirmed via `diff`).
2. Remove the spurious 4th line (`- [repo commit hooks](repo_commit_hooks.md) — TODO: summarize this
   file.`) from `ai/°base/memory/MEMORY.md`.
3. `ai/°base/memory/.codex-sync.json` needs no edit (it has no entry for `repo_commit_hooks.md` at all — the
   duplicate was created without ever going through `import_native_note`).
4. Also remove the stray Codex-side resource-dir copy on this machine (under
   `~/.codex/memories/extensions/base_synced/resources/<base-project-key>/repo_commit_hooks.md`) — otherwise
   the very next sync recreates the duplicate again. Do this only after §2's hook fix has landed, or it
   recurs a third time.
5. This is a real `git rm` of a tracked file (not a rename — the survivor at `ai/memory/` is a different,
   pre-existing tracked file from git's perspective), so `require_memory_delete_marker.py` *will* require the
   marker: include `Deleted Memory: repo_commit_hooks.md` in this commit's message. Land it as its own
   commit, separate from the §1-§4 code fix.

## Verification
- `uv run --project scripts/°base python -m unittest discover -s scripts/°base/tests -v` — full suite green
  (allow for the pre-existing unrelated 7 failures/2 errors already known from prior work this session).
- Manually exercise `promote.py`/`demote.py` round-trip in a scratch repo and confirm
  `git diff --cached --diff-filter=D` is empty for a pure `git mv` (validates §4 step 6's no-marker claim)
  before relying on it in the implementation.
- `python3 scripts/°base/ai/settings/sync.py --check` (unaffected by this change, but part of repo hygiene).
- After landing, run the real `record-codex-memory` hook once more (SessionStart) and confirm
  `ai/°base/memory/repo_commit_hooks.md` does not reappear.
