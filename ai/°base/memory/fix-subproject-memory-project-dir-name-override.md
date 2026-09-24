---
name: fix-subproject-memory-project-dir-name-override
description: "Linked monorepo subprojects silently lost Claude memories because .claude is a symlink; fixed via CLAUDE_CODE_PROJECT_DIR_NAME, not by de-symlinking."
metadata:
  node_type: memory
  type: project
  originSessionId: 1583e1ae-de2c-4b45-94d3-81b7f5c7daa9
  modified: 2026-09-24T11:40:43.159Z
---

`scripts/°base/init/link-subproject-claude.sh` symlinks a subfolder's `.claude` to the monorepo root's `.claude` wholesale. This made Claude Code's own native auto-memory feature attach memories saved from inside the subfolder to the **parent repo's** project bucket instead of the subfolder's — confirmed via `ai/.debug` hook dumps showing the `Write` tool's `file_path` missing the subfolder suffix that the same payload's `transcript_path` had correctly.

**Why:** discovered 2026-09-24 while investigating why a freshly linked subproject "can't save memories." Root cause is Claude Code's project-identity resolution, not this repo's `record-memory` hook (which already correctly reads the literal `CLAUDE_PROJECT_DIR`). The user rejected restructuring `.claude` away from a whole-directory symlink ("not symlinking kinda sucks"). Verified against the installed CLI binary (`/home/user/.local/share/claude/versions/*`, string-searched, not just docs) that `CLAUDE_CODE_PROJECT_DIR_NAME` is a real env var that pins the project directory name — but only when `CLAUDE_CONFIG_DIR` is *also* set in the environment, and only when it matches `^[A-Za-z0-9_-]{1,64}$`.

**How to apply:** the fix (implemented same session) has two parts — `link-subproject-claude.sh` now seeds a `.claude-project.env` per subfolder (source it before launching Claude there) exporting both vars with a deterministic slug, and `scripts/°base/ai/hooks/_lib.py`'s `_encoded_project_dir()` now checks for the same override (mirroring Claude's own gating) so this repo's `record-memory` hook and `°base/ai/memory/delete.py` (which imports the same helper) look in the same directory Claude actually wrote to. See [[project_dual_codex_config_dirs]] for the related `$CLAUDE_CONFIG_DIR` env-var-resolution history this builds on.

Side note from the same session: a `claude-code-guide` subagent researching this autonomously downloaded and staged several `code.claude.com` doc pages into `ai/references/https/code.claude.com/docs/en/` via `scripts/download_ref.py` without an explicit approval prompt reaching the user — matches this repo's existing doc-caching convention (a `hooks.md` was already there), so likely fine, but worth watching for.
