# Redesign Codex ad-hoc memory ownership tracking

## Context

`scripts/°base/ai/hooks/record-codex-memory/hook.py` mirrors Codex's global
`extensions/ad_hoc/*.md` notes into whichever project repo happens to fire a
`PostToolUse` hook next, tracking "is this note already handled" in a
per-project `.codex-sync.json` (`ai/memory/.codex-sync.json` /
`ai/°base/memory/.codex-sync.json`), which is also mirrored into
`$CODEX_HOME/memories/extensions/base_synced/resources/<project-key>/.codex-sync.json`.

Two compounding bugs were confirmed live in this environment:

1. **Hostname-keyed identity is brittle.** `source_id()` builds each note's
   metadata key as `f"{device_id()}:{AD_HOC_DIR / name}"`, and `device_id()`
   falls back to `socket.gethostname()`. On this machine the hostname
   changes across sessions/containers (`fedora`, `fedora.fritz.box`,
   `fedora-2.fritz.box`, `fedora-3.fritz.box` all appear in the data). Every
   new hostname makes an already-handled note look brand new again.
2. **No cross-project ownership check.** `main()`'s `PostToolUse` branch
   loops over *every* currently-"unassigned" note and auto-imports it into
   whatever project's tool call happened to trigger the hook — with no check
   for whether another project already owns it. Combined with bug 1, the
   same note gets re-imported into unrelated repos every time the hostname
   changes.

   Confirmed evidence: `2026-07-20-history-master-replay-guards.md` (which is
   about this `base` repo's own `history-master` git tooling — clearly
   `base`-only content) is recorded as a `sources` entry in **14** unrelated
   project resource dirs under `~/.codex/memories/extensions/base_synced/resources/`
   (`times-uploader`, `DockerTgBot`, `game-collections`, `ai-usage`,
   `CrushCrushEventTracker`, etc.), several with duplicate hostname-keyed
   entries for the same note.

Per discussion, this is a redesign, not a patch: replace the current
peer-to-peer, hostname-keyed, per-project merge scheme with a single
authoritative ownership registry, drop hostname from the identity entirely,
and gate the existing auto-import loop on that registry. Auto-migration of
existing data ships disabled until the new logic has test coverage, then
gets enabled; a manual audit/cleanup script handles the already-corrupted
data in the 13 wrongly-owning projects.

**Cross-device note:** `$CODEX_HOME/memories` is a local git repo with no
configured remote today — nothing currently syncs it across machines. The
registry is just another tracked file in that same repo, so it travels
exactly the way `extensions/ad_hoc/*.md` notes already do, if/when the user
sets up a remote and starts pushing/pulling it. A real ownership conflict
(two devices independently assigning the *same* note to two *different*
projects before syncing) becomes a normal single-file git merge conflict —
correct to surface, versus today's silent hostname-keyed duplication.

## New data model

Replace the per-project `sources`/`ignored` merge with:

- **`$CODEX_HOME/memories/extensions/base_synced/registry.json`** — the one
  authoritative file, tracking every ad-hoc note's fate:
  ```json
  {
    "version": 1,
    "notes": {
      "extensions/ad_hoc/2026-07-20-history-master-replay-guards.md": {
        "status": "assigned",           // "assigned" | "ignored"
        "project": "-home-user-git-luckydonald-base",
        "target": "2026-07-20-history-master-replay-guards.md",
        "hash": "dd6c17d6..."
      }
    }
  }
  ```
  Key is the note's stable path under `extensions/ad_hoc/` — **no device/host
  prefix**. `device_id()`/`CODEX_MEMORY_DEVICE_ID` stay only as an optional
  informational field on the entry (e.g. `"recorded_by": "fedora"`) for
  provenance, never part of the key or the ownership decision.

- **Per-project `.codex-sync.json`** (both the committed
  `ai[/°base]/memory/.codex-sync.json` and the mirrored resource-dir copy)
  becomes a **derived, project-scoped view**: just the subset of
  `registry.json` entries where `project` equals this project's key. It is
  written *from* the registry, never merged back into it — there is exactly
  one writer of ownership state (the registry), so `merge_metadata()` and
  its pairwise-merge logic go away entirely.

- **`unassigned_notes()`** becomes a registry lookup: a note is eligible for
  auto-import into the *current* project only if it has no entry in
  `registry.json` at all. If it's already `assigned` (to this project or any
  other) or `ignored`, skip it — no writes happen outside the owning
  project, ever.

- **`import_native_note()`** writes the assignment into `registry.json`
  first (`status: assigned`, `project: <current project key>`), then
  mirrors into the current project's resource dir and committed memory dir
  exactly as today (reusing `memory_lib.link_file`).

- **`delete_scoped_memory()`** removes the entry from `registry.json`
  instead of parsing a `device:path` identity out of the metadata key
  (the `identity.split(":", 1)[-1]` logic goes away — the note path is
  already the key).

## Implementation

- `scripts/°base/ai/hooks/record-codex-memory/hook.py`:
  - Add `registry_path(repository)` → `repository / BASE_SYNCED_DIR / "registry.json"`.
  - Add `read_registry`/`write_registry` (same tolerant-parse / stable-sort /
    no-op-if-unchanged style as the existing `read_metadata`/`write_metadata`).
  - Rewrite `source_id()` to just return the stable relative path (drop
    `device_id()` from the key); keep `device_id()` itself for the
    informational field.
  - Rewrite `unassigned_notes()`, `import_native_note()`,
    `synchronize_shared_memory()`, and `delete_scoped_memory()` around the
    registry as described above; drop `merge_metadata()`.
  - Keep the existing hardlink-mirroring behavior (`memory_lib.link_file`,
    `same_inode`) and the `MEMORY.md` index-entry logic (`add_index_entry`,
    `note_title`) unchanged — only the ownership bookkeeping changes.
  - **Feature-gate auto-migration**: reading an old-format per-project
    `.codex-sync.json` (hostname-prefixed keys, no `registry.json` yet) must
    not crash or silently duplicate — but must not auto-migrate into
    `registry.json` yet either. Gate the migration path behind an explicit
    opt-in (e.g. `CODEX_MEMORY_MIGRATE_REGISTRY=1` env var, removed once
    confirmed working), so shipping the code change alone is inert against
    the corrupted live data. Document this switch at the top of the file.

- `scripts/°base/ai/memory/import-codex.py`: no interface change expected
  (still calls `import_native_note`), verify it still works against the new
  registry-backed implementation.

- **New cleanup/audit script** — `scripts/°base/ai/memory/codex-sync-audit.py`:
  - Scans every `~/.codex/memories/extensions/base_synced/resources/*/.codex-sync.json`
    plus the note content itself, groups entries by note identity, and
    reports every note with more than one distinct owning project (with each
    project's path and the note's title/first line for context).
  - Run in report-only mode by default; an explicit `--fix <note> --owner <project-key>`
    (or similar) applies one decision at a time: keep the entry in the
    chosen owner's resource dir + committed project memory, remove it from
    every other project's `.codex-sync.json`/resource `.md`/`MEMORY.md`
    index entry, and seed `registry.json` with the resolved owner. Never
    guess or bulk-apply — every fix is a reviewed, explicit call, since it
    touches git state in unrelated repos outside this one.
  - This is the tool used to resolve the 13-projects-deep
    `2026-07-20-history-master-replay-guards.md` case once the new code is
    trusted.

## Verification

- Add focused unit tests (temp `CODEX_HOME` + temp project git repos under
  `/tmp`, never touching the real `~/.codex`), covering:
  - stable identity survives a changed `CODEX_MEMORY_DEVICE_ID`/hostname
    between two hook invocations (no duplicate/re-import).
  - a note already assigned to project A is never touched when the hook
    runs inside project B (`unassigned_notes()` returns empty for B).
  - explicit `import-codex.py` assignment still works end-to-end
    (registry entry, resource mirror, project mirror, `MEMORY.md` index).
  - `--ignore` still records via the registry and is respected across
    projects.
  - `delete_scoped_memory()` removes the registry entry, both mirrors, and
    the index line, and stays idempotent on a repeat call.
  - old-format data is read without crashing when the migration flag is
    off, and migrates correctly when it's on.
- Run the audit script's report mode against a synthetic multi-project temp
  tree with an intentionally duplicated note, confirm it lists all owners.
- Run the existing focused hook/settings tests plus the full `scripts/°base`
  suite (`pytest scripts/°base/tests` or the project's usual test command)
  to confirm no regressions in the adjacent `°memory_lib` / promote / delete
  flows.
- Only after tests pass: flip the migration flag on for real usage, then run
  `codex-sync-audit.py` in report mode against the live `~/.codex` tree to
  size the actual cleanup, and resolve the known
  `2026-07-20-history-master-replay-guards.md` case (and anything else it
  finds) via `--fix`, one project at a time, reviewing each.
