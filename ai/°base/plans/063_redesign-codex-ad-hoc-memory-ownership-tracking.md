# Redesign Codex ad-hoc memory ownership tracking

## Context

`scripts/°base/ai/hooks/record-codex-memory/hook.py` mirrors Codex's global `extensions/ad_hoc/*.md` notes into whichever project repo happens to fire a `PostToolUse` hook next, tracking "is this note already handled" in a per-project `.codex-sync.json` (`ai/memory/.codex-sync.json` / `ai/°base/memory/.codex-sync.json`), which is also mirrored into `$CODEX_HOME/memories/extensions/base_synced/resources/<project-key>/.codex-sync.json`.

Two compounding bugs were confirmed live in this environment:

1. **Hostname-keyed identity is brittle.** `source_id()` builds each note's metadata key as `f"{device_id()}:{AD_HOC_DIR / name}"`, and `device_id()` falls back to `socket.gethostname()`. On this machine the hostname changes across sessions/containers (`fedora`, `fedora.fritz.box`, `fedora-2.fritz.box`, `fedora-3.fritz.box` all appear in the data). Every new hostname makes an already-handled note look brand new again.
2. **No cross-project ownership check.** `main()`'s `PostToolUse` branch loops over *every* currently-"unassigned" note and auto-imports it into whatever project's tool call happened to trigger the hook, with no check for whether another project already owns it. Combined with bug 1, the same note gets re-imported into unrelated repos every time the hostname changes.

Confirmed evidence: `2026-07-20-history-master-replay-guards.md` (which is about this `base` repo's own `history-master` git tooling, clearly `base`-only content) is recorded as a `sources` entry in **14** unrelated project resource dirs under `~/.codex/memories/extensions/base_synced/resources/` (`times-uploader`, `DockerTgBot`, `game-collections`, `ai-usage`, `CrushCrushEventTracker`, etc.), several with duplicate hostname-keyed entries for the same note.

Per discussion, this is a redesign, not a patch: replace the current peer-to-peer, hostname-keyed, per-project merge scheme with a single local ownership index, drop hostname from the identity key entirely, and gate the existing auto-import loop on that index. Auto-migration of existing data ships disabled until the new logic has test coverage, then gets enabled; a manual audit/cleanup script handles the already-corrupted data in the 13 wrongly-owning projects.

**Correction on `$CODEX_HOME/memories` being a git repo:** it only has a `.git` because one was run there ad hoc during earlier exploration — that is not a supported setup. Treat `$CODEX_HOME/memories` as a **plain folder**, not a git repository. All the sync logic must work purely off local files in `$CODEX_HOME` and the current project's own repo; nothing under `$CODEX_HOME/memories` should be `git add`/`git commit`ed by this hook. The only git commits this hook makes are inside the current project's own repo (`root`), via the existing `commit_project_memory()` — that part is unchanged and correct.

**Correction on the `device` key's purpose:** it isn't for disambiguating multiple physical machines pulling the same git history — it's for telling apart "our Codex on this machine just authored this ad_hoc note" (we are the source) from "this note was already seen/handled before" (we are not the source, it's already accounted for). With ownership tracked directly by a `status: assigned/ignored` entry in the new local index, that distinction is captured by the index entry's presence, not by a device string in the key. The device field survives only as an informational, non-key value on each entry (e.g. `"recorded_by": "fedora"`), useful for debugging, never part of the identity or the ownership decision.

## New data model

Replace the per-project `sources`/`ignored` merge with:

- **`$CODEX_HOME/memories/extensions/base_synced/registry.json`** — a local index tracking every ad-hoc note's fate on this machine. It is a plain file in a plain folder (no git involved), and it is a **rebuildable cache**: the durable, authoritative record for a given project's notes remains that project's own committed `.codex-sync.json` (see below). If `registry.json` is ever missing or lost, it can be reconstructed by scanning the existing `resources/*/.codex-sync.json` files already present under `$CODEX_HOME`.

  ```json
  {
    "$schema": "../../../../../scripts/°base/ai/hooks/record-codex-memory/registry.schema.json",
    "version": 2,
    "notes": {
      "extensions/ad_hoc/2026-07-20-history-master-replay-guards.md": {
        "status": "assigned",
        "project": "-home-user-git-luckydonald-base",
        "target": "ai/°base/memory/2026-07-20-history-master-replay-guards.md",
        "hash": "dd6c17d6...",
        "recorded_by": "fedora"
      }
    }
  }
  ```

  Key is the note's stable path under `extensions/ad_hoc/`, with no device/host prefix. `target` is the exact path of the mirrored file *relative to the owning project's repo root* — e.g. `ai/°base/memory/<name>.md` inside the `base` repo itself, or `ai/memory/<name>.md` inside a consuming project — resolved once via `project_memory_dir(root)` (which already picks the right one of the two, see `memory_lib.memory_dirs`) and stored verbatim, so any reader can resolve the file directly as `root / target` without re-deriving which of the two memory dirs applies.

  This is a breaking format change from the current `sources`/`ignored`, hostname-keyed, bare-filename-`target` shape, so `version` bumps from `1` to `2`. Both `read_registry` and `read_metadata` branch on `version`: `1` is the old shape (read-only, tolerant, never written back unless the migration flag is on), `2` is this shape. This reuses the field that already exists in every current file instead of inventing a parallel migration marker.

- **Per-project `.codex-sync.json`** (both the committed `ai[/°base]/memory/.codex-sync.json` and the mirrored resource-dir copy under `$CODEX_HOME`) becomes a **derived, project-scoped view**: just the subset of `registry.json` entries where `project` equals this project's key, with `target` already given as the in-repo path, also stamped `"version": 2` and its own `$schema`. It is written *from* the registry, never merged back into it, so there is exactly one writer of ownership state per note, and `merge_metadata()` and its pairwise-merge logic go away entirely.

- **`unassigned_notes()`** becomes an index lookup: a note is eligible for auto-import into the *current* project only if it has no entry in `registry.json` at all. If it's already `assigned` (to this project or any other) or `ignored`, skip it — no writes happen outside the owning project, ever.

- **`import_native_note()`** writes the assignment into `registry.json` first (`status: assigned`, `project: <current project key>`, `target: <in-repo path>`), then mirrors into the current project's resource dir and committed memory dir exactly as today (reusing `memory_lib.link_file`).

- **`delete_scoped_memory()`** removes the entry from `registry.json` instead of parsing a `device:path` identity out of the metadata key — the `identity.split(":", 1)[-1]` logic goes away, since the note path is already the key.

## Bootstrapping a fresh machine / fresh clone

Since `registry.json` is local-machine state under `$CODEX_HOME`, a freshly cloned checkout of a project on a machine that has never run Codex against it (empty or unrelated `$CODEX_HOME`) needs a way to reconstruct the local index — otherwise the hook would treat every note the project already owns as unowned again on that machine.

The project's own committed `ai[/°base]/memory/.codex-sync.json` is the durable, git-tracked record of what that project already owns — it travels with the clone for free, no extra step. What's missing locally is just the `$CODEX_HOME`-side mirror (`resources/<project-key>/*.md` + the corresponding `registry.json` entries). Steps, all automatic, no manual action beyond having the hook wired up (already a prerequisite today):

1. On its first run inside that project (any hook event, since `synchronize_shared_memory()` already runs unconditionally at the top of `main()`), the hook reads the project's own `ai[/°base]/memory/.codex-sync.json`.
2. For every entry there whose note identity is **not yet present** in the local `registry.json`, the hook backfills it: inserts the registry entry (`status`, `project` = this project's key, `target`, `hash`) straight from the project's file, and links the project's `.md` file into `resources/<project-key>/` — this is the same `memory_lib.link_file` mirroring `synchronize_shared_memory()` already does for plain memory files, just extended to also seed the registry, not only the file mirror.
3. If the local registry **already has a conflicting entry** for that note identity (assigned to a *different* project) — a sign of pre-existing corrupted data — the backfill leaves the existing registry entry alone and does not overwrite it; this surfaces as exactly the kind of case `codex-sync-audit.py` is for, so it's out of scope for silent auto-resolution here.
4. The original `extensions/ad_hoc/<name>.md` scratch file itself is never reconstructed on the new machine — it doesn't need to be. It was ephemeral, per-device Codex scratch input; the durable content already lives in the project's committed memory file, and that's what gets mirrored back into `resources/<project-key>/`.

This makes `registry.json` self-healing per project: it costs nothing extra if it's already populated (no-op), and catches up automatically the first time the hook runs against a project it hasn't locally indexed yet.

## Implementation

- `scripts/°base/ai/hooks/record-codex-memory/hook.py`:
  - `codex_memory_repo()` (naming aside, this returns the Codex memories *folder*, not a git repo — consider renaming to `codex_memory_dir()`) drops its `(repository / ".git").exists()` check; it should just resolve `$CODEX_HOME/memories`, creating it if missing, with no git requirement.
  - Drop `commit_pending()` and every `git(repository, ...)` call — there is no git repo at `$CODEX_HOME/memories` to commit into. The advisory lock currently taken at `repository / ".git" / "codex-memory-hook.lock"` moves to a plain lock file directly under that folder (e.g. `repository / ".record-codex-memory.lock"`).
  - Add `registry_path(repository)` → `repository / BASE_SYNCED_DIR / "registry.json"`, plus `read_registry`/`write_registry` in the same tolerant-parse, stable-sort, no-op-if-unchanged style as the existing `read_metadata`/`write_metadata`.
  - Rewrite `source_id()` to just return the stable relative path, dropping `device_id()` from the key; keep `device_id()` itself to populate the informational `recorded_by` field only.
  - Rewrite `unassigned_notes()`, `import_native_note()`, `synchronize_shared_memory()`, and `delete_scoped_memory()` around the registry as described above; drop `merge_metadata()`.
  - Keep the existing hardlink-mirroring behavior (`memory_lib.link_file`, `same_inode`) and the `MEMORY.md` index-entry logic (`add_index_entry`, `note_title`) unchanged — only the ownership bookkeeping and the (now git-free) storage location change.
  - **Feature-gate auto-migration**: reading an old-format per-project `.codex-sync.json` (hostname-prefixed keys, bare `target` filenames, no `registry.json` yet) must not crash or silently duplicate, but must not auto-migrate into `registry.json` yet either. Gate the migration path behind an explicit opt-in (e.g. `CODEX_MEMORY_MIGRATE_REGISTRY=1` env var, removed once confirmed working), so shipping the code change alone is inert against the corrupted live data. Document this switch at the top of the file.

- **JSON Schemas**, following the existing convention in `ai/tool-settings/*.schema.json` (draft 2020-12, a `$id` GitHub URL, `$schema`/`version` pinned via `const`):
  - `scripts/°base/ai/hooks/record-codex-memory/registry.schema.json` for `registry.json` — `version` (`const: 2`), `notes` (object keyed by the `extensions/ad_hoc/...` path pattern, each value requiring `status` (`enum: [assigned, ignored]`), and for `status: assigned`: `project`, `target`, `hash`; `recorded_by` optional throughout).
  - `scripts/°base/ai/hooks/record-codex-memory/codex-sync.schema.json` for the per-project `.codex-sync.json`, same entry shape minus the `project` field (implicit — it's always this project).
  - Both `registry.json` and `.codex-sync.json` get a `"$schema"` field pointing at the relevant file (relative path), matching how `ai/tool-settings/settings-local.json` points at its schema, so editors validate them and the format is self-documenting; `write_registry`/`write_metadata` always emit that field.
  - Add a focused test asserting a freshly written `registry.json`/`.codex-sync.json` validates against its schema, following the same pattern as `scripts/°base/tests/test_tool_settings_schema.py`; `jsonschema>=4,<5` is already a declared dependency (`scripts/°base/pyproject.toml`), so no new dependency is needed.

- `scripts/°base/ai/memory/import-codex.py`: no interface change expected, since it still calls `import_native_note`; verify it still works against the new registry-backed implementation and no longer references `module.commit_pending(repository, ...)` for the (now non-git) Codex memories folder.

- **New cleanup/audit script** — `scripts/°base/ai/memory/codex-sync-audit.py`:
  - Scans every `~/.codex/memories/extensions/base_synced/resources/*/.codex-sync.json` plus the note content itself, groups entries by note identity, and reports every note with more than one distinct owning project (with each project's path and the note's title/first line for context).
  - Runs in report-only mode by default; an explicit `--fix <note> --owner <project-key>` (or similar) applies one decision at a time: keep the entry in the chosen owner's resource dir plus committed project memory, remove it from every other project's `.codex-sync.json`/resource `.md`/`MEMORY.md` index entry, and seed `registry.json` with the resolved owner (using the in-repo `target` path, not a bare filename). Never guess or bulk-apply — every fix is a reviewed, explicit call, since it touches git state in unrelated repos outside this one.
  - This is the tool used to resolve the 13-projects-deep `2026-07-20-history-master-replay-guards.md` case once the new code is trusted.

## Verification

- Add focused unit tests (temp `CODEX_HOME` + temp project git repos under `/tmp`, never touching the real `~/.codex`), covering: stable identity survives a changed `CODEX_MEMORY_DEVICE_ID`/hostname between two hook invocations (no duplicate/re-import); a note already assigned to project A is never touched when the hook runs inside project B (`unassigned_notes()` returns empty for B); explicit `import-codex.py` assignment still works end-to-end (registry entry with correct in-repo `target`, resource mirror, project mirror, `MEMORY.md` index); `--ignore` still records via the registry and is respected across projects; `delete_scoped_memory()` removes the registry entry, both mirrors, and the index line, and stays idempotent on a repeat call; old-format data (hostname-prefixed keys, bare-filename `target`) is read without crashing when the migration flag is off, and migrates correctly when it's on; no git commands are ever invoked against `$CODEX_HOME/memories`; a project whose committed `.codex-sync.json` already owns a note, run against a fresh/empty local `registry.json`, backfills that entry (and the resource mirror) on first run without re-prompting or reassigning; a backfill that would conflict with an existing differently-owned registry entry leaves the registry untouched.
- Run the audit script's report mode against a synthetic multi-project temp tree with an intentionally duplicated note, and confirm it lists all owners.
- Run the existing focused hook/settings tests plus the full `scripts/°base` suite (`pytest scripts/°base/tests` or the project's usual test command) to confirm no regressions in the adjacent `°memory_lib` / promote / delete flows.
- Only after tests pass: flip the migration flag on for real usage, then run `codex-sync-audit.py` in report mode against the live `~/.codex` tree to size the actual cleanup, and resolve the known `2026-07-20-history-master-replay-guards.md` case (and anything else it finds) via `--fix`, one project at a time, reviewing each.
