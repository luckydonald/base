# Claiming `2026-07-20-history-master-replay-guards.md` into `.codex-sync.json`

## Context

You wanted to make sure the memory `ai/°base/memory/2026-07-20-history-master-replay-guards.md` is "claimed" (tracked as owned by this repo) in `ai/°base/memory/.codex-sync.json`, and tried:

```
scripts/°base/ai/memory/import-codex.py ai/°base/memory/2026-07-20-history-master-replay-guards.md
```

which you suspected was wrong.

## Finding: it's already claimed — nothing to run

Checked directly:

- `ai/°base/memory/.codex-sync.json` already has the entry:
  ```json
  "fedora:extensions/ad_hoc/2026-07-20-history-master-replay-guards.md": {
    "hash": "755ce373a41cc7c9f5c96d3bb7f46bbf2077b07ac6378796aa0eb9ca86c64ff9",
    "target": "2026-07-20-history-master-replay-guards.md"
  }
  ```
- `ai/°base/memory/MEMORY.md` already has the index line for it.
- Both were committed together in `c0c2a14a` "[base] ai: sync codex memory" (2026-07-22).
- `git log`/`git status` on that memory file and `.codex-sync.json` show nothing pending.

This matches the design in `ai/°base/plans/051_scoped-two-way-codex-memory-sync.md:30-35`: a native Codex ad-hoc note gets auto-assigned to the owning project (linked in, added to `.codex-sync.json`, indexed in `MEMORY.md`) the first time a write-like `PostToolUse` event touches it in a repo — the `record-codex-memory` hook already did this automatically for this note. `import-codex.py` is only needed for the *unassigned* case (plan lines 37-41), which no longer applies here.

**No code/config change needed for this file.**

## Why your invocation was wrong (for future reference)

`scripts/°base/ai/memory/import-codex.py` imports Codex → repo. Its argument is the **bare filename as it lives under `$CODEX_HOME/memories/extensions/ad_hoc/`**, not a path into this repo (`hook.py` resolves `source = repository / "extensions/ad_hoc" / <arg>`). The correct shape, per the hook's own generated instructions (`hook.py:351` and plan line 38), is:

```
python3 scripts/°base/ai/memory/import-codex.py 2026-07-20-history-master-replay-guards.md
```

(bare note name, invoked via `python3`, from the affected unassigned-note case only — not needed here since it's already assigned).

## Unrelated stray change noticed along the way

`scripts/°base/ai/memory/import-codex.py` has an uncommitted mode-only diff (100644 → 100755), consistent with someone trying to execute it directly (`scripts/°base/ai/memory/import-codex.py ...` rather than `python3 scripts/...`). It's unrelated to the claiming question. No action planned here — mention it to you; revert with `chmod 644` if you'd like it back to how it's committed, or leave/commit the +x if you'd rather always invoke it directly going forward.

## Verification

Already done as part of this investigation (read-only):
- `cat "ai/°base/memory/.codex-sync.json"` — entry present.
- `grep "history-master-replay-guards" "ai/°base/memory/MEMORY.md"` — index line present.
- `git log --oneline -1 -- "ai/°base/memory/.codex-sync.json" "ai/°base/memory/2026-07-20-history-master-replay-guards.md"` → `c0c2a14a`.

No further action required unless you want the stray `import-codex.py` mode bit reverted.
