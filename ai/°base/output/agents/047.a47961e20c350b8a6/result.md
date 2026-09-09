Good — this confirms `project_memory_dir()` (hook.py:61-66) has exactly one binary branch: `ai/°base/memory` if `_is_inside_base_repo(root)`, else `ai/memory`. Now I have everything for the report.

## Report

### 1. `import-codex.py` (73 lines, thin CLI wrapper)

It does no work itself — it dynamically loads `hook.py` (`load_hook`, lines 11-20) and delegates to its functions. All real logic lives in `hook.py`.

- `--ignore` (parsed at import-codex.py:36): sets `ignored=True` on `import_native_note()`. Inside `hook.py:254-255`, when `ignored=True` the resource's `source_id` is written into `metadata["ignored"][identity] = {"hash": digest(source)}` — the note is never copied/linked into the project, and it is popped from `ignored` again if later re-imported without `--ignore` (`hook.py:279`).
- "New" vs "already imported" vs "ignored" decision: `unassigned_notes()` (`hook.py:292-303`) lists every `*.md` under `extensions/ad_hoc/` in the Codex memory repo (excluding `instructions.md`) whose `source_id(path)` (device-hostname-prefixed identity, `hook.py:79-86`) is **not already a key** in either `metadata["sources"]` or `metadata["ignored"]`. So the classification is purely presence/absence of that identity string as a dict key in `.codex-sync.json` — content hash is stored but not used to decide new-vs-imported, only recorded for later comparisons/audit.
- Reading/writing `.codex-sync.json`: `read_metadata()` (`hook.py:94-109`) tolerates missing/corrupt files by returning `empty_metadata()` (`{"version":1,"sources":{},"ignored":{}}`). There are always **two copies** of this file — one in the project's memory dir, one in the Codex-side resource dir — and `merge_metadata()` (`hook.py:112-125`) unions both `sources` and `ignored` dicts (resource dict applied first, project dict values override) before `write_metadata()` (`hook.py:128-138`) rewrites both copies identically, sorted by key, skipping the write if content is byte-identical.

### 2. `record-codex-memory/hook.py` — firing and target directory

- `main()` (`hook.py:418-460`) is invoked with a CLI arg (`"claude"` or `"codex"`) and reads a JSON payload from stdin containing `hook_event_name`. It's wired to fire on **PostToolUse**, **SessionStart** (implicitly, any non-PostToolUse event goes to the `else` branch), and **Stop** (`test_ai_settings_sync.py:72,99` shows it's registered for the hook config generically; the branching logic in the hook itself only distinguishes `PostToolUse` from everything else).
- On `PostToolUse`, unassigned notes are **auto-imported** without asking (`hook.py:442-445`: `for note in notes: changed.extend(import_native_note(repository, root, note.name))` — no `ignored=True`, no `--as`). On any other event (e.g. `Stop`/`SessionStart`), it instead just emits advisory messages via `unassigned_messages()` (`hook.py:446-447`) telling the operator to run `import-codex.py <note> [--ignore]` manually.
- Target directory resolution: `project_memory_dir()` (`hook.py:61-66`):
```python
def project_memory_dir(root: Path) -> Path:
    if _is_inside_base_repo(root):
        return root / "ai" / "°base" / "memory"
    # end if
    return root / "ai" / "memory"
# end def
```
This is the **only** place the target directory is chosen, and it is a hardcoded binary branch — `ai/°base/memory` vs `ai/memory` — with no concept of "more than one target directory." There is no loop, no config list, no per-note directory selection. `resource_dir()` (`hook.py:74-76`) mirrors this 1:1 into a single per-project Codex-side folder keyed by `project_key(root)`. **The tool currently supports exactly one target memory directory per repo.**

### 3. Orphan-resource bug (`ai/°base/memory/project_codex_memory_orphan_resource_bug.md`)

Mechanism, restated from the code: each project's memory is mirrored bidirectionally with the Codex-side `resources/<project-key>/` folder via `link_file()` hardlinks in `synchronize_shared_memory()` (`hook.py:216-237`). Deletion only happens through `delete_scoped_memory()` (`hook.py:375-415`), which walks `metadata["sources"]`, and for every entry whose `entry.get("target") == name` unlinks both the native Codex ad-hoc note and the resource copy (`hook.py:388-397`). If a resource-dir copy of a file exists but has **no** corresponding `sources` entry (e.g., because it was created by the reverse project→resource sync path at `hook.py:224-237` without ever going through `import_native_note`, which is the only place that writes `sources[identity]`), then `delete_scoped_memory()`'s loop finds nothing matching `entry.get("target") == name` and never calls `unlink_path()` on that resource file. On the next sync (`synchronize_shared_memory`, `hook.py:224-233`), that orphaned resource file is still present and has no project-side counterpart, so the `for source in sorted(resource.glob("*.md"))` loop treats it as "new content coming from the resource side" and hardlinks it right back into the project's `ai/memory/` dir — resurrecting a file the user just deleted.

### 4. Tests

`scripts/°base/tests/test_ai_hooks_base_routing.py` covers `record-codex-memory/hook.py` (imported as `CODEX_MEMORY_HOOK`, line 23):
- `test_codex_memory_hook_commits_and_is_idempotent` (line 1257): asserts a `PostToolUse` run auto-imports an ad-hoc note into `project/ai/memory/note.md`, adds it to `MEMORY.md`, writes `scope.json` with `{"cwd": <project>}`, creates `.codex-sync.json` in the project, and commits exactly once to both the memory repo (`"ai: record codex memory"`) and the project (`"ai: sync codex memory"`); a second run (`Stop` event) is idempotent — no new commit, note still exists.
- `test_codex_memory_stop_reports_unassigned_note_as_json` (line 1314) and `test_claude_memory_stop_reports_unassigned_note_as_plain_text` (line 1344): assert that on `Stop`, an unassigned note produces an advisory message mentioning `import-codex.py later.md`, formatted as JSON `systemMessage` for `"codex"` vs plain stdout for `"claude"`, and that the note is *not* imported into the project.

No test file exercises `import-codex.py` directly by name, and no test exercises `--ignore`, `--as`, renames, or the orphan-resource scenario — that bug is documented only in the memory file, not covered by an automated test.

### Direct answers to your specific questions

- **`.codex-sync.json` schema**: `{"version": 1, "sources": {<source_id>: {"target": <filename>, "hash": <sha256>}}, "ignored": {<source_id>: {"hash": <sha256>}}}`, where `source_id` = `f"{device_id()}:{AD_HOC_DIR / source.name}"` (`hook.py:84-86`), e.g. `hostname:extensions/ad_hoc/foo.md`.
- **`git mv`/rename of a tracked memory file**: the tool has **no rename detection**. `synchronize_shared_memory()` only compares by filename existence/inode (`hook.py:216-237`) and `delete_scoped_memory()` only matches by `entry.get("target") == name` (`hook.py:389`). A `git mv old.md new.md` leaves the resource-side `old.md` still present with a `sources` entry pointing at `target: "old.md"` — the hook does not update that entry. The old resource file is not linked anywhere anymore since `old.md` no longer exists project-side, so on next sync nothing recreates the project-side `old.md` (good), but the stale `sources`/resource copy for `old.md` is never cleaned up automatically, and `new.md` is treated as a brand-new file with no `sources` entry — it will get pushed to the resource dir but won't gain a `sources` mapping back to any native Codex note unless separately imported. So: renames are **not detected**; the old path's metadata/resource file becomes dead weight, and the new path is treated as untracked/new content flowing from project to resource, not vice versa.
- **Hardcoded single target directory**: yes — `project_memory_dir()` at `/home/user/git/luckydonald/base/scripts/°base/ai/hooks/record-codex-memory/hook.py:61-66` is the sole and exclusive place the target directory is resolved, with a hardcoded two-way branch (`ai/°base/memory` vs `ai/memory`) and no support for additional/second memory locations. `resource_dir()` at `hook.py:74-76` and every call site (`import_native_note`, `synchronize_shared_memory`, `delete_scoped_memory`) call `project_memory_dir(root)` exactly once per invocation, assuming a single target dir.