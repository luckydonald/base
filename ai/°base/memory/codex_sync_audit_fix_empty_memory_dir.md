---
name: codex-sync-audit-fix-empty-memory-dir
description: "codex-sync-audit.py --fix crashed with a git add pathspec error when removing a note emptied a project's memory dir entirely."
metadata:
  type: project
---

`codex-sync-audit.py --fix` resolves ad-hoc Codex notes claimed by more than one project by deleting the losing project's copy (`_remove_from_project()`). It used to always run `git add --all -- <memory-dir>` unconditionally afterward.

**Why:** `hook.memory_lib.unlink_path()` only unlinks the single note file — it never prunes the now-possibly-empty parent directory. When the removed note was the only untracked thing under a project's memory dir, `git add --all -- <dir>` had nothing to match (nothing tracked, nothing untracked) and git exits 128 with "did not match any files," which `check=True` turned into a crash (`ai/°base/errors/25.txt`).

**How to apply:** Any script that deletes files under a memory/notes dir and then unconditionally `git add`s that dir is exposed to this same crash once the dir empties out. Guard with `git status --porcelain -- <dir>` first and skip add/commit when there's nothing to stage — see the fix in `scripts/°base/ai/memory/codex-sync-audit.py`'s `_remove_from_project()`.

Separately, running `--fix` afterward surfaced a related pre-existing gap: `report()`/`collect_claims()` still flags a note as claimed by projects whose resource-mirror `.codex-sync.json` is still in the legacy v1 (hostname-keyed `sources`) shape — `fix()` only clears the v2 `notes` map, so a project stuck on v1 keeps reporting as a claimant even after its actual repo file and project-side sync data were correctly removed. Not fixed here; worth a proper v1-migration-on-fix pass if it keeps surfacing.
