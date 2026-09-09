I don't have file-writing tools available (only Bash/Read/Skill/ToolSearch), and my role here is strictly read-only exploration and planning — so I'm returning the full plan as text below rather than writing a plan file.

# Implementation Plan: Dual Memory-Directory Support (`ai/°base/memory` + `ai/memory`)

## 0. Live-mess diagnosis (confirms the bug is exactly as suspected)

Commit `20223e62d98719c7506831a6414841a60eaf8864` ("ai: sync codex memory") is the smoking gun: after commit `726ab6a` promoted `repo_commit_hooks.md` from `ai/°base/memory/` to `ai/memory/` (removing it from the base dir, rewriting `ai/°base/memory/MEMORY.md`'s entry to the `../../memory/repo_commit_hooks.md` stub link), the very next `record-codex-memory` run's `synchronize_shared_memory()` (hook.py:224-237) walked the **base-side** Codex resource dir (`~/.codex/memories/extensions/base_synced/resources/<base-project-key>/`), found `repo_commit_hooks.md` still sitting there (nothing ever deleted the resource-side copy — promote.py doesn't exist yet), saw `target = project_memory_dir(root) / "repo_commit_hooks.md"` did not exist in `ai/°base/memory/` anymore, and dutifully re-hardlinked it back in, then `add_index_entry()` (hook.py:156-175) appended a second, TODO-stubbed `MEMORY.md` line since the existing stub-link line's `]({note.name})` text (`](../../memory/repo_commit_hooks.md)`) didn't match its naive `]({note.name})` substring check (`](repo_commit_hooks.md)`).

Current disk state confirmed: `ai/°base/memory/repo_commit_hooks.md` is byte-identical to `ai/memory/repo_commit_hooks.md` (`diff` exit 0); `ai/°base/memory/MEMORY.md` has 4 lines — the 3 pre-existing ones (including the correct stub-link line 3) plus a spurious line 4: `- [repo commit hooks](repo_commit_hooks.md) — TODO: summarize this file.`. `ai/°base/memory/.codex-sync.json` has a `sources` entry keyed `fedora:extensions/ad_hoc/2026-07-20-history-master-replay-guards.md` (unrelated file, not part of this bug) — **no `sources`/`ignored` entry exists for `repo_commit_hooks.md` in either `.codex-sync.json`**, because it was never imported via `import_native_note`; it only ever existed as a plain resource-mirror file with no metadata identity, which is exactly why `delete_scoped_memory`'s identity-matching loop (hook.py:388-396) can't find/remove it — same root cause class as the already-documented orphan-resource bug, just triggered by `git mv` instead of a metadata gap.

The `2026-07-20-history-master-replay-guards.md` duplication across both dirs (also link-count-4 in `ai/°base/memory`, present with divergent content in both, both `ignored`) is a **separate, pre-existing, intentional** state — not part of this bug, do not touch it during cleanup.

## 1. Centralizing directory resolution

**Decision: put it in `°memory_lib`, not `_lib.py`.** Rationale: `_lib.py` is prompt/decision-log-hook-scoped (imports `merge_staged`, handles `.by-issue`, `append_and_commit`, etc.) and is already imported by `record-memory/hook.py`; `record-codex-memory/hook.py` deliberately imports only `_is_inside_base_repo` + `read_payload` from `_lib.py` and otherwise stays independent, and `°memory_lib` is already the shared, dependency-light package all three call sites import (`memory_lib = importlib.import_module("°memory_lib")`). Directory-list resolution is conceptually a memory-filesystem primitive, same category as `link_file`/`same_inode`/`delete_memory`, so it belongs beside them. This also avoids giving `°memory_lib` a new dependency on `_lib.py` (it currently doesn't import it) or forcing `record-codex-memory` to start importing more of `_lib.py`.

New module: `scripts/°base/ai/hooks/°memory_lib/dirs.py`

```python
def memory_dirs(subproject: Path, *, is_inside_base_repo) -> tuple[Path, Path]:
    """Return (primary, secondary) memory dirs for `subproject`, primary first.
    primary = ai/°base/memory when subproject is the base repo, else ai/memory.
    secondary = the other one (ai/memory inside base; ai/°base/memory outside — always exists as a Path even if unused/never created outside base)."""
```

Exact proposed signature (avoid a hard dependency on `_commit_style_lib` from within `°memory_lib` — pass the predicate in, since `°memory_lib` currently has zero imports from `_lib`/`°commit_style_lib` and should stay that way per its existing self-contained-primitives style):

```python
# scripts/°base/ai/hooks/°memory_lib/dirs.py
from __future__ import annotations
from pathlib import Path

def memory_dirs(subproject: Path, is_base: bool) -> tuple[Path, Path]:
    """(primary, secondary) memory dirs under `subproject`, primary first.
    Inside the base repo: primary=ai/°base/memory, secondary=ai/memory.
    Elsewhere:            primary=ai/memory,       secondary=ai/°base/memory."""
    base_dir = subproject / "ai" / "°base" / "memory"
    root_dir = subproject / "ai" / "memory"
    return (base_dir, root_dir) if is_base else (root_dir, base_dir)
```

Export it from `°memory_lib/__init__.py`: add `from .dirs import memory_dirs` and append `"memory_dirs"` to `__all__`.

Each of the three call sites keeps computing `is_base` itself via its own already-imported `_is_inside_base_repo` (no behavior change to that predicate) and calls `memory_lib.memory_dirs(subproject, is_base)`.

### Call-site diffs

**`scripts/°base/ai/hooks/record-memory/hook.py`** (lines 58-61): delete `_memory_dirs` entirely. At line 381-382 in `main()`:
```python
subproject = _subproject_root()
is_base = _is_inside_base_repo(subproject)
src_dir = _encoded_project_dir(subproject) / "memory"
dst_dir, secondary_dir = memory_lib.memory_dirs(subproject, is_base)
```
(`src_dir` — the Claude-side source — stays computed locally exactly as before, since `memory_dirs` only knows about the two *repo-side* dirs, not the Claude config dir.) Every other reference to `dst_dir` in this file (lines 384, 401-402, 409-417, 422-426) is unchanged; `_sync_all` and `_commit` gain a `secondary_dir` parameter (see §2).

**`scripts/°base/ai/hooks/record-codex-memory/hook.py`** (lines 61-66): delete `project_memory_dir`. Replace every call site (lines 202, 261, 282, 333, 377) with a local pattern:
```python
def _memory_dirs(root: Path) -> tuple[Path, Path]:
    return memory_lib.memory_dirs(root, _is_inside_base_repo(root))
```
placed near the top (right after `project_key`), and change `memory_dir = project_memory_dir(root)` → `memory_dir, secondary_dir = _memory_dirs(root)` at each of the 5 call sites, threading `secondary_dir` into `synchronize_shared_memory` and `delete_scoped_memory` (see §2/§3 — `import_native_note` and `commit_project_memory` don't need `secondary_dir`, only `memory_dir`, so for those two keep calling `_memory_dirs(root)[0]` or just keep a `project_memory_dir(root) -> Path` thin wrapper for callers that only need primary. Recommend keeping a **local** one-line wrapper `project_memory_dir(root) -> Path: return _memory_dirs(root)[0]` so the 3 call sites that don't care about secondary (`import_native_note` line 261/282, `commit_project_memory` line 333) don't need edits beyond the top-level rename).

**`scripts/°base/ai/memory/delete.py`** (lines 23-26): delete `_memory_dirs`, replace `src_dir, dst_dir = _memory_dirs(subproject)` (line 61) with:
```python
is_base = _is_inside_base_repo(subproject)
src_dir = _encoded_project_dir(subproject) / "memory"
dst_dir, secondary_dir = memory_lib.memory_dirs(subproject, is_base)
```
then use `secondary_dir` in the new dual-directory lookup (§3).

## 2. Resurrection-prevention fix

### 2a. `record-memory/hook.py::_sync_all` (lines 142-175)

New signature: `_sync_all(src_dir: Path, dst_dir: Path, secondary_dir: Path, dst_dir_rel: str) -> list[str]`.

In the `src_dir.glob("*.md")` loop (lines 157-168), before the `if not dst.exists():` resurrection branch, insert a secondary-dir check:
```python
for src in sorted(src_dir.glob("*.md")):
    src_names.add(src.name)
    dst = dst_dir / src.name
    secondary = secondary_dir / src.name
    if not dst.exists():
        if secondary.is_file():
            # Authoritative copy lives in the OTHER valid repo dir (promoted/
            # demoted, or a pre-existing legacy split) -- do not resurrect a
            # second copy in dst_dir. Re-point the Claude-side hardlink at
            # the file's real current location instead, so future edits still
            # flow correctly and _sync_all doesn't churn every SessionStart.
            if not memory_lib.same_inode(secondary, src):
                memory_lib.link_file(secondary, src)
            continue
        if _is_marked_deleted(dst_dir_rel, src.name):
            _unlink_file(src)
            continue
        if memory_lib.link_file(src, dst):
            changed.append(src.name)
        continue
    if not memory_lib.same_inode(dst, src):
        memory_lib.link_file(dst, src)
```
Reasoning for hardlink direction: `secondary` is the authoritative on-disk copy (git-tracked, possibly promoted deliberately); `src` (Claude's per-project memory file) should mirror whichever repo copy is real, exactly the same policy `_sync_all`'s docstring already states for `dst`↔`src` — just generalized to "whichever of the two known repo dirs currently holds the file." No commit is needed here since `secondary_dir` content isn't being modified, only the external Claude-side file, which this hook never commits directly (only `dst_dir_rel` is committed via `_commit`).

Also handle the reverse direction (dst_dir → src orphan-relink loop, lines 170-174: "any dst not in src_names gets linked src_dir/dst.name"): this loop only touches `dst_dir` (the primary), so it's unaffected by secondary_dir — leave unchanged, it already only fires for genuinely-primary-only files.

`_check_memory_index_consistency` (lines 181-206) currently only inspects `dst_dir`. **Extend it to also accept an optional `secondary_dir`** and, when checking "on_disk - referenced" orphans, treat a file present in `dst_dir` whose *name* also appears as a `](../../memory/<name>)`-shaped (or `](../°base/memory/<name>)`-shaped, from the other direction) relative-link inside `secondary_dir`'s own `MEMORY.md` as NOT orphaned even if `dst_dir`'s own `MEMORY.md` has no entry for it — not strictly required for the resurrection fix itself, but avoids new false-positive stderr warnings once dual dirs are common. This is a nice-to-have; can be deferred to a follow-up if scope needs trimming.

Call-site update in `main()` (line 423): `changed = _sync_all(src_dir, dst_dir, secondary_dir, dst_dir_rel)`.

The `PostToolUse`(Write/Edit) branch (lines 406-417) also deserves the same guard in principle (a `Write`/`Edit` to the Claude-side source file for a name that already lives in `secondary_dir`), but per the confirmed decision "default write target stays `ai/°base/memory/`", a live edit event should still land in `dst_dir` (primary) per existing behavior *unless* the name already exists in `secondary_dir`, in which case it should update the file wherever it actually lives instead of creating a second copy. Add the same one-line secondary-check right before line 414's `memory_lib.link_file(src_file, dst_dir / rel)`:
```python
target_dir = secondary_dir if (secondary_dir / rel).is_file() and not (dst_dir / rel).is_file() else dst_dir
if memory_lib.link_file(src_file, target_dir / rel):
    _commit(str(target_dir.relative_to(Path.cwd())), [str(rel)])
```
(requires `_commit`'s first arg naming to stay generic — it already takes `dst_dir_rel: str`, no signature change needed, just pass the right relpath.)

### 2b. `record-codex-memory/hook.py::synchronize_shared_memory` (lines 201-238)

New signature: `synchronize_shared_memory(repository: Path, root: Path, memory_dir: Path, secondary_dir: Path, resource: Path) -> ...` — or keep `synchronize_shared_memory(repository, root)` and internally call `_memory_dirs(root)` for both dirs (simpler; only this function and `delete_scoped_memory` need `secondary_dir`, and both already take `root`).

Apply the same guard to the resource→project reverse-sync loop (lines 224-237):
```python
for source in sorted(resource.glob("*.md")) if resource.is_dir() else []:
    target = memory_dir / source.name
    secondary_target = secondary_dir / source.name
    if not target.exists():
        if secondary_target.is_file():
            # Authoritative copy already lives in the other valid memory dir
            # (e.g. promoted since this resource snapshot was taken) -- keep
            # the resource mirror pointed at the real file, don't resurrect
            # a duplicate in memory_dir.
            if not memory_lib.same_inode(secondary_target, source):
                memory_lib.link_file(secondary_target, source)
            continue
        if memory_lib.link_file(source, target):
            changed.append(str(target.relative_to(root)))
            if add_index_entry(memory_dir, target):
                changed.append(str((memory_dir / "MEMORY.md").relative_to(root)))
                memory_lib.link_file(memory_dir / "MEMORY.md", resource / "MEMORY.md")
        continue
    elif not memory_lib.same_inode(target, source):
        memory_lib.link_file(target, source)
```

**On whether `sources`/`ignored` entries need to move between the two `.codex-sync.json` files when the underlying file moves**: per the confirmed decision to keep the two files fully independent (no schema change), and since promote.py performs an *explicit, deliberate* move, **the answer is: `promote.py`/`demote.py` itself is responsible**, not the sync hook. The sync hook's job is only the resurrection guard above (a passive "don't duplicate" check); it must never infer identity relocation from a bare filename match, since that's exactly the kind of implicit inference `require_memory_delete_marker.py`/the whole "repo is authoritative, no inference" design principle (see `_sync_all`'s docstring and `record-memory/hook.py`'s module docstring) exists to avoid. Concretely: after `synchronize_shared_memory` runs post-promote (fresh resource dirs, no matching `sources` entry for the moved file in the *new* location's `.codex-sync.json`), the file will just be treated as an untracked-but-present resource file with no metadata entry at all — harmless, matches the pre-existing "plain files can live in the resource dir with zero metadata" pattern already used for e.g. `repo_commit_hooks.md` today. `promote.py` should still opportunistically relocate a `sources`/`ignored` entry if one exists (see §4) so metadata isn't silently orphaned, but the sync hook does not need to do this on its own.

## 3. `delete.py` dual-directory lookup

Current logic (lines 60-68) only checks `dst_dir` from the single-purpose `_memory_dirs`. New logic:
```python
subproject = _subproject_root()
is_base = _is_inside_base_repo(subproject)
src_dir = _encoded_project_dir(subproject) / "memory"
primary_dir, secondary_dir = memory_lib.memory_dirs(subproject, is_base)
_chdir_to_git_root()

for candidate_dir in (primary_dir, secondary_dir):
    candidate_rel = str(candidate_dir.relative_to(Path.cwd()))
    if memory_lib.is_tracked(f"{candidate_rel}/{name}"):
        dst_dir, dst_dir_rel = candidate_dir, candidate_rel
        break
else:
    print(f"Memory is not tracked in {primary_dir} or {secondary_dir}: {name}", file=sys.stderr)
    return 1
```
Then the existing `memory_lib.delete_memory(name, src_dir=src_dir, dst_dir=dst_dir, dst_dir_rel=dst_dir_rel)` call (line 70) is unchanged — it already takes an explicit `dst_dir`/`dst_dir_rel`, so no change needed inside `°memory_lib/delete.py::delete_memory`. The Codex-mirror cleanup call (`hook.delete_scoped_memory(repository, subproject, name)`, line 78) already resolves its own dirs via `project_memory_dir`/`_memory_dirs(root)` internally, so once `record-codex-memory/hook.py::delete_scoped_memory` is updated to also check *both* dirs for the `MEMORY.md`-line removal and the `sources`-identity removal (mirroring the same primary/secondary loop), it'll find the right one regardless of which dir actually held the file. Concretely, `delete_scoped_memory` (hook.py:375-415) needs: `memory_dir, secondary_dir = _memory_dirs(root)`, and the "remove from MEMORY.md" block (lines 398-407) run against **both** `memory_dir / "MEMORY.md"` and `secondary_dir / "MEMORY.md"` (whichever actually references `name`), since a promoted memory's *stub* line lives in the non-owning dir's MEMORY.md, not just the owning one, and a straight deletion of a promoted memory should also clean up the stub line in the demoted-from dir. This is a meaningful extra behavior worth calling out explicitly in the plan doc.

## 4. `promote.py` (with `--demote`)

Location: `scripts/°base/ai/memory/promote.py` (sibling to `delete.py`, `import-codex.py`).

CLI: `python3 scripts/°base/ai/memory/promote.py <name.md> [--demote]`
- Default (no flag): promote `ai/°base/memory/<name>` → `ai/memory/<name>` (°base→root).
- `--demote`: reverse direction, `ai/memory/<name>` → `ai/°base/memory/<name>` (root→°base).
- Only meaningful/allowed when `_is_inside_base_repo(subproject)` is true (promote/demote is a base-repo-specific concept — a consuming repo has no `ai/°base/memory` at all). Exit 2 with a clear message otherwise.

Algorithm (promote direction; demote is the mirror, swapping "base"/"root" roles and stub-link direction `../°base/memory/<name>.md` instead of `../../memory/<name>.md` — note relative depth: from `ai/memory/MEMORY.md` up to `ai/°base/memory/<name>.md` is `../°base/memory/<name>.md`, confirmed against the existing example's inverse: from `ai/°base/memory/MEMORY.md` up to `ai/memory/<name>.md` is `../../memory/<name>.md`, i.e. up two levels then down into `memory/`; for the reverse, up one level from `ai/memory/` to `ai/`, then down into `°base/memory/`, so `../°base/memory/<name>.md`):

1. Resolve `subproject`, confirm `_is_inside_base_repo`.
2. `src_dir, dst_dir = (base_dir, root_dir)` for promote, swapped for demote (reuse `memory_lib.memory_dirs`).
3. Validate: `name` is a plain `.md` filename (same validation as `delete.py` line 55-58); `(src_dir / name).is_file()`; `(dst_dir / name)` does NOT already exist (refuse silently-overwriting collisions — print + exit 1, mirroring `import_native_note`'s collision check at hook.py:265-269); `memory_lib.is_tracked(f"{src_dir_rel}/{name}")` (must be a real tracked memory, not a stray untracked file).
4. `git mv <src_dir_rel>/<name> <dst_dir_rel>/<name>` (`subprocess.run(["git", "mv", ...], check=True)`).
5. Update destination `MEMORY.md` (`dst_dir/MEMORY.md`): extract the existing entry line for `name` from `src_dir/MEMORY.md` (regex match on the `]({name})` link target, same pattern `_MEMORY_LINK_RE` in `record-memory/hook.py` uses, or simpler: match the exact `- [<title>](name) — <desc>` line), append the *same* line verbatim (same title/description text) to `dst_dir/MEMORY.md`, creating the file with a `# Memory\n` header first if it doesn't exist yet (matching `add_index_entry`'s bootstrap behavior, hook.py:162-163).
6. Rewrite the **source** `MEMORY.md` entry (`src_dir/MEMORY.md`) in place: replace `]({name})` with the relative-link stub path — `](../../memory/{name})` for promote, `](../°base/memory/{name})` for demote — keeping the rest of the line (title + em-dash + description) byte-for-byte unchanged. Do NOT delete the line.
7. If `(src_dir / ".codex-sync.json")` exists and has a `sources[identity]` (or `ignored[identity]`) entry whose `target == name`: pop it from the source file's metadata dict and insert it (same `identity` key, same `hash`, `target` updated only if the filename itself changed — it doesn't here) into the destination `.codex-sync.json`'s corresponding dict, creating that file via `empty_metadata()`-shaped JSON if it doesn't exist. Write both files back (reuse `record-codex-memory`'s `read_metadata`/`write_metadata` by importing the hook module the same way `delete.py::_codex_hook()` already does — add a matching `_codex_hook()` helper in `promote.py`, or better, factor `_codex_hook()` out of `delete.py` into a tiny shared helper, e.g. add it to `°memory_lib/__init__.py` as `load_codex_hook_module()` so both `delete.py` and `promote.py` reuse one implementation instead of duplicating the `importlib.util.spec_from_file_location` dance a 3rd time).
8. `git add -- <src_dir_rel>/MEMORY.md <dst_dir_rel>/MEMORY.md` (git mv already staged the moved file itself) plus the two `.codex-sync.json` paths if touched.
9. Commit: subject via `base_ai_commit_subject(f"ai: promote memory {Path(name).stem}")` (or `"demote"`) — reuse `_commit_style_lib.base_ai_commit_subject` the same way `°memory_lib/delete.py::delete_memory` does. **No `Deleted Memory: <name>` marker is needed** (see empirical rename-detection check below) since the memory file's own content doesn't change — only `git mv` (100% similarity, default `diff.renames` is on in this repo's git 2.55, confirmed by a scratch-repo test: `git diff --cached --name-only --diff-filter=D` on a pure `git mv` reports nothing, `git status --porcelain` shows `R`, not `D`+`A`). The stub-rewrite in the source `MEMORY.md` is a content edit to an *existing tracked file*, not a deletion, so `require_memory_delete_marker.py`'s `--diff-filter=D` scan is untouched by it either.
10. Print the new commit hash/summary, mirroring `delete.py`'s final `print(f"Deleted memory {name} in {commit}")` (line 87) style — e.g. `Promoted memory {name} in {commit}` / `Demoted memory {name} in {commit}`.

Edge case to flag explicitly in the plan doc: step 5's "extract exact same line" must handle the destination `MEMORY.md` not existing yet (root `ai/memory/MEMORY.md` is a *new* file per the confirmed target shape — `726ab6a` shows it going from absent to created) — use the same bootstrap-header logic as `add_index_entry` (`"# Memory\n"` if missing) for consistency, even though the real historical commit's resulting root `MEMORY.md` in this repo happens to already have that header from a separate prior commit; don't assume it pre-exists.

## 5. Test plan

**Stay valid as-is:**
- `test_memory_in_base_repo_routes_and_prefixes` (routing test, lines 1143-1165) — no promotion occurs, `assertFalse(ai/memory exists)` still holds; the new secondary-dir check only activates when the secondary dir + matching filename exist, which this test never creates.
- `test_memory_session_start_restores_missing_claude_source_from_repo` (1167-1188) — single-dir repo state, secondary dir absent → `secondary.is_file()` is `False` → falls through to existing behavior unchanged.
- `test_memory_session_start_does_not_resurrect_marked_deleted_memory` (1190-1223) — unaffected, same reasoning.
- `test_memory_posttooluse_write_with_underscore_in_project_path` (1225-1255) — no secondary dir present, behaves as before (need to double check: with the `target_dir` logic added in §2a's PostToolUse branch, confirm `(secondary_dir / rel).is_file()` is `False` here since `ai/°base/memory` doesn't exist in this non-base repo — fine).
- All `test_memory_delete.py` marker-hook tests (unaffected — no code path touched).
- `test_delete_helper_removes_repo_and_source_and_formats_commit` — still passes: single-dir scenario, the new dual-dir loop in `delete.py` finds it on the first (only) candidate.

**Need updating:** none of the existing bodies require literal edits, but recommend reviewing `test_memory_bash_rm_*` tests (1387-1502) and `test_codex_memory_hook_commits_and_is_idempotent`/`test_codex_memory_stop_reports_unassigned_note_as_json`/`test_claude_memory_stop_reports_unassigned_note_as_plain_text` (1257-1387) since `record-codex-memory/hook.py`'s internal helper renames (`project_memory_dir` → `_memory_dirs`) and `synchronize_shared_memory`/`delete_scoped_memory` signature changes are implementation details these tests exercise only through the public `main()`/CLI surface — confirm no test imports `project_memory_dir` directly (grep confirms: no test file references `project_memory_dir` or `_memory_dirs` by name, only `MEMORY_HOOK`/`CODEX_MEMORY_HOOK` subprocess paths), so these should keep passing unmodified.

**New tests to add** (both in `test_ai_hooks_base_routing.py`, near the existing memory tests, and possibly a new `test_memory_promote.py` for §4):

1. `test_memory_session_start_does_not_resurrect_across_promoted_directory` — seed `ai/memory/<name>.md` (tracked) in a base repo, put a *stale* copy of the same name in the Claude source dir with different content, run `SessionStart`; assert `ai/°base/memory/<name>.md` is NOT created, and the Claude source file's content becomes byte-identical to (hardlinked with) `ai/memory/<name>.md`, not `ai/°base/memory/`.
2. `test_codex_memory_sync_does_not_resurrect_across_promoted_directory` — analogous, but for `record-codex-memory/hook.py`: seed the resource dir with `<name>.md`, seed `ai/memory/<name>.md` (secondary-from-resource's-perspective is `ai/°base/memory`), run the hook; assert `ai/°base/memory/<name>.md` is not created.
3. `test_delete_helper_deletes_promoted_memory_from_root_dir` — seed a tracked memory directly under `ai/memory/` in a base repo (bypassing the default-writes-to-°base convention, simulating a promoted file), run `delete.py`; assert it's found/removed from `ai/memory/` (not just `ai/°base/memory/`) and the commit's marker/subject match.
4. `test_promote_moves_file_and_rewrites_both_memory_md` — full round trip: seed `ai/°base/memory/<name>.md` + a matching `ai/°base/memory/MEMORY.md` entry, run `promote.py <name>.md`; assert (a) file now only at `ai/memory/<name>.md` (git-tracked, old path gone from `git ls-files`), (b) `ai/memory/MEMORY.md` has the same entry line verbatim, (c) `ai/°base/memory/MEMORY.md`'s line for `<name>.md` is rewritten to the `](../../memory/<name>.md)` stub form with description preserved, (d) the commit passes `require_memory_delete_marker.py` with no marker present (i.e. running the real pre-commit hook against the staged diff exits 0) — reuse the `run_marker_hook`/`init_repo` helpers from `test_memory_delete.py`.
5. `test_demote_reverses_promote` — round-trip promote then demote (or demote directly from a pre-seeded `ai/memory/` file), assert file lands back in `ai/°base/memory/`, stub direction flips to `](../°base/memory/<name>.md)` in `ai/memory/MEMORY.md`.
6. `test_promote_relocates_codex_sync_entry_when_present` — seed a `sources[identity] = {"target": name, "hash": ...}` entry in `ai/°base/memory/.codex-sync.json`, run promote, assert the entry is now present (same identity/hash) in `ai/memory/.codex-sync.json` and absent from the source file.
7. `test_promote_refuses_when_destination_already_has_same_name` — collision guard (§4 step 3).

## 6. One-off cleanup of the live mess (manual, not via promote.py)

Exact target state: `repo_commit_hooks.md` exists ONLY at `ai/memory/repo_commit_hooks.md` (already correct, untouched); `ai/°base/memory/MEMORY.md` has exactly 3 lines (the original pre-`726ab6a` set, with line 3 being the correct stub `- [Repo commit hooks](../../memory/repo_commit_hooks.md) — ...`).

Steps (to hand off as a literal one-off, not code):
1. `git rm "ai/°base/memory/repo_commit_hooks.md"` — removes the resurrected duplicate file (byte-identical to the real one at `ai/memory/repo_commit_hooks.md`, confirmed via `diff` exit code 0 above).
2. Edit `ai/°base/memory/MEMORY.md`: delete line 4 (`- [repo commit hooks](repo_commit_hooks.md) — TODO: summarize this file.`), leaving lines 1-3 exactly as they are now (line 3's stub-link is already correct, untouched by this cleanup).
3. `ai/°base/memory/.codex-sync.json` needs **no edit** — it has no entry keyed to `repo_commit_hooks.md` at all (confirmed above; its only entry is the unrelated `2026-07-20-history-master-replay-guards.md` one), so there's nothing to remove there. However, the underlying Codex resource-side mirror (`~/.codex/memories/extensions/base_synced/resources/<base-project-key>/repo_commit_hooks.md`, wherever `CODEX_HOME` points on the machine doing the cleanup) should also be deleted by hand, otherwise the very next `record-codex-memory` run will resurrect the duplicate file into `ai/°base/memory/` again immediately — **this manual resource-dir cleanup must happen before or in the same sitting as steps 1-2**, and ideally happen only after §2b's fix lands (otherwise, absent the fix, this exact resurrection will simply recur on the next Codex sync even after manual cleanup).
4. Since this is a `git rm` of a tracked memory file under `ai/°base/memory/`, `require_memory_delete_marker.py` WILL flag it (this is a real, path-level deletion under `MEMORY_DIRS`, not a rename — the surviving copy at `ai/memory/repo_commit_hooks.md` is a *different, pre-existing* tracked file from git's perspective, so no rename pairing applies). The cleanup commit must include a `Deleted Memory: repo_commit_hooks.md` marker line, exactly as `_has_memory_delete_marker`/`require_memory_delete_marker.py` expect — even though semantically this is "removing an accidental duplicate," not a real memory loss, the marker's own purpose (audit trail + explicit acknowledgment) is satisfied by including it deliberately here too.
5. Recommend doing steps 1-2 as their own standalone commit (not folded into the code-fix commit), titled e.g. `[base] ai/°base/memory: Remove Codex-resurrected duplicate of repo_commit_hooks.md.` with body `Deleted Memory: repo_commit_hooks.md`, landed strictly *after* the §2b hook fix is committed (otherwise, if a Codex `SessionStart`/`PostToolUse` sync fires between the cleanup commit and the fix commit, it recurs a third time).

### Critical Files for Implementation
- /home/user/git/luckydonald/base/scripts/°base/ai/hooks/°memory_lib/__init__.py
- /home/user/git/luckydonald/base/scripts/°base/ai/hooks/record-memory/hook.py
- /home/user/git/luckydonald/base/scripts/°base/ai/hooks/record-codex-memory/hook.py
- /home/user/git/luckydonald/base/scripts/°base/ai/memory/delete.py
- /home/user/git/luckydonald/base/scripts/°base/ai/memory/promote.py (new)
- /home/user/git/luckydonald/base/scripts/°base/tests/test_ai_hooks_base_routing.py
- /home/user/git/luckydonald/base/scripts/°base/tests/test_memory_delete.py