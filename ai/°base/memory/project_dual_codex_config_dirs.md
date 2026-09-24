---
name: project-dual-codex-config-dirs
description: "User runs separate work and private Claude/Codex logins via different CLAUDE_CONFIG_DIR paths; base repo hooks must resolve paths through that env var, not hardcode ~/.claude."
metadata: 
  node_type: memory
  type: project
  originSessionId: a25e02e3-6045-40dc-b481-2ed444335951
  modified: 2026-09-24T11:40:29.811Z
---

The user has two separate Claude/Codex accounts (work and private), configured with different config directories so both logins work independently, e.g. `CLAUDE_CONFIG_DIR=/home/user/.confuig/claude/accounts/private/`. Sometimes they end up on the "wrong" one for a given terminal/session.

**Why:** Discovered 2026-08-18 while testing whether memory management was "broken" — the `record-memory` hook (`scripts/°base/ai/hooks/record-memory/hook.py`) hardcoded `~/.claude/projects/<encoded>/memory/` as the memory source dir, so it silently never saw memory files written under a relocated `CLAUDE_CONFIG_DIR`. Fixed in commit `b402a60` by adding `_claude_config_dir()`, mirroring the pattern `save-plan/hook.py` already used (see `_is_plan_file_path` there, which reads `os.environ.get("CLAUDE_CONFIG_DIR")`).

**How to apply:** Any base-repo hook or script that locates per-project Claude state under `~/.claude/...` (plans, memory, sessions, etc.) needs to check `$CLAUDE_CONFIG_DIR` first and fall back to `~/.claude`, or it will silently misbehave for this user under one of the two accounts. Correction (2026-09-24): `scripts/°base/ai/memory/delete.py` does NOT duplicate the hardcoded logic — it imports `_encoded_project_dir`/`_claude_config_dir` directly from `_lib.py` (`delete.py:12-16`), so it already gets any fix made there for free. See [[project-codex-memory-orphan-resource-bug]] for a separate, unrelated sync issue found in the same session, and [[fix-subproject-memory-project-dir-name-override]] for a related fix to `_encoded_project_dir()` (adding `CLAUDE_CODE_PROJECT_DIR_NAME` support for linked monorepo subprojects).
