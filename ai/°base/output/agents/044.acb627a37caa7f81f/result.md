## Summary of findings

### (a) What `import-codex.py` actually does

`/Users/user/Documents/programming/Python/base/scripts/°base/ai/memory/import-codex.py` (76 lines) is a thin CLI wrapper around `import_native_note()` in `scripts/°base/ai/hooks/record-codex-memory/hook.py`. It imports **FROM** Codex's global ad-hoc notes **INTO** the current project's repo memory tree (the direction is Codex → repo, i.e. "claiming" is exactly what it's for).

**Usage** (line 49 of the script, and mirrored in `hook.py:351`):
```
Usage: import-codex.py <note.md> [--as <filename.md>] [--ignore]
```

Critical detail — `<note.md>` is **not a path into this repo**. It is resolved as (`hook.py:35-42,240-243`):
```python
source = repository / AD_HOC_DIR / note_name   # AD_HOC_DIR = Path("extensions/ad_hoc")
```
where `repository = $CODEX_HOME/memories` (default `~/.codex/memories`). So the argument must be the **bare filename as it exists in `~/.codex/memories/extensions/ad_hoc/`** (e.g. `2026-07-20-history-master-replay-guards.md`), not `ai/°base/memory/2026-07-20-history-master-replay-guards.md`.

Correct invocation (run from anywhere inside the git repo — it does `git rev-parse --show-toplevel` itself):
```
python3 scripts/°base/ai/memory/import-codex.py 2026-07-20-history-master-replay-guards.md
```
(Note: `hook.py:351` itself generates suggested commands with a `python3` prefix, not direct execution — see (e) on the executable bit.)

### (b)/(c) `.codex-sync.json` schema and claiming — and the key finding

Path: `ai/°base/memory/.codex-sync.json`. Schema:
```json
{"version": 1, "sources": {"<hostname>:extensions/ad_hoc/<note>.md": {"hash": "<sha256>", "target": "<repo-filename>.md"}}, "ignored": {}}
```
An entry in `sources` = "claimed". `import_native_note()` (hook.py:240-287) hard-links the Codex note into the resource dir and into `ai/°base/memory/<target_name>`, adds an index line to `ai/°base/memory/MEMORY.md`, and records the `sources` entry (keyed by `device_id():extensions/ad_hoc/<name>` — `device_id()` = `$CODEX_MEMORY_DEVICE_ID` or hostname).

**This specific memory is already fully claimed.** `.codex-sync.json` already contains:
```json
"fedora:extensions/ad_hoc/2026-07-20-history-master-replay-guards.md": {"hash": "755ce373...", "target": "2026-07-20-history-master-replay-guards.md"}
```
and this, plus the `.md` file itself and a `MEMORY.md` index line, were committed together in **`c0c2a14a` "[base] ai: sync codex memory"** (2026-07-22), evidently by the automated hook (its `PostToolUse` branch, `hook.py:440-443`, auto-imports any unassigned note without asking). `git status` on `ai/°base/memory/` is clean and `git log` shows only that one commit touching the file — there is nothing left to commit/claim. There is no correct invocation needed here because the goal state already exists; re-running `import-codex.py` for this file would be a no-op (content hashes already match) at best.

If the user's real concern is something else (e.g. verifying it survives the "orphan-resource" bug noted in memory `project_codex_memory_orphan_resource_bug.md`, where a deleted-but-still-source-mapped note can resurrect), that's a different, unrelated code path (`delete_scoped_memory`, hook.py:373-413) and doesn't apply here since nothing was deleted.

### (d) Why the user's invocation was wrong

They ran:
```
scripts/°base/ai/memory/import-codex.py ai/°base/memory/2026-07-20-history-master-replay-guards.md
```
Two problems:
1. **Wrong argument shape**: passing a repo-relative path instead of a bare Codex ad-hoc filename. Had the Codex repo been available, `source = repository/"extensions/ad_hoc"/"ai/°base/memory/2026-07-20-history-master-replay-guards.md"` would not exist, producing `import-codex-memory: native Codex memory note not found: extensions/ad_hoc/ai/°base/memory/2026-07-20-history-master-replay-guards.md` (hook.py:242-244).
2. In this sandbox, I actually got a different/earlier error first: `import-codex-memory: Codex memory repository is unavailable` (main.py:64-66 catching the `RuntimeError` from `codex_memory_repo()`), because here `~/.codex/memories/` exists but has no `.git` inside it (`codex_memory_repo()` checks `(repository / ".git").exists()`, hook.py:35-42). This is an environment artifact of this sandbox, not necessarily what the user's own machine produces — but it's worth flagging in case their real environment also lacks that git repo (e.g. wrong `$CODEX_HOME`, per the "Dual work/private Codex config dirs" memory).
3. Also moot in this case regardless, since the note is already claimed (see (c)).

### (e) Other relevant paths/notes
- `scripts/°base/ai/memory/delete.py` — the sibling script, but it's for **deleting** a claimed memory (and removing its Codex mirror), not claiming one.
- Uncommitted change on `scripts/°base/ai/memory/import-codex.py` is mode-only: committed as `100644` (`git ls-files -s` confirms), working tree now `100755`. This looks like someone `chmod +x`'d it trying to run it directly (`scripts/°base/ai/memory/import-codex.py ...`); it's unrelated to the actual bug and not needed — the documented/generated invocation (hook.py:351) always uses `python3 scripts/°base/ai/memory/import-codex.py <note.md>`. Sibling `delete.py` is likewise non-executable (100644), consistent with "always invoke via `python3`".
- `ai/°base/AGENTS.md` has no dedicated "claiming a memory" walkthrough — only a one-line hooks-table entry (line 108: `record-codex-memory/hook.py` syncs scoped Codex memory into the shared project memory tree).
- Relevant commits: `4cccee58` (added the two-way sync + `import-codex.py`), `cb30753f` (repaired hook output/bounded sync), `c0c2a14a` (the actual auto-claim of this exact memory file).