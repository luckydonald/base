---
name: repo-commit-hooks
description: "pre-commit hook in this repo rejects Co-Authored-By and Claude-Session trailers in commit messages"
metadata: 
  node_type: memory
  type: project
  originSessionId: 01UaBveFduTwHp5WnitqLXpv
  modified: 2026-09-09T00:00:00.000Z
---

Repo's pre-commit hook "Reject Co-Authored-By / Claude-Session trailers in commit messages" (`scripts/°base/git/hooks/commit/reject_co_authored_by.py`) fails any commit whose message contains a `Co-Authored-By:` or `Claude-Session:` line.

`ai/tool-settings/settings.json` sets `"allowCoAuthoredEtc": false`; `render_claude` in `scripts/°base/ai/settings/°settings_lib/hooks.py` passes that through into `.claude/settings.json`'s native `includeCoAuthoredBy` key (rendered by `scripts/°base/ai/settings/sync.py`), which suppresses Claude Code's own default "🤖 Generated with Claude Code" / `Co-Authored-By:` footer at the source. The `Claude-Session:` line has no such native toggle — the hook is the only backstop for it.

**Why:** repo-level policy enforced via git hook + tracked config, overrides the session-level attribution instructions that normally append both trailers. Ported from `todo_splits_tracker` (a `base`-derived repo that hit this first) since the hook script and settings-sync code are base-owned. The shared-settings key is named `allowCoAuthoredEtc` (not `includeCoAuthoredBy`) since it's our own tracked toggle covering both trailers, distinct from the native Claude Code key it renders into.

**How to apply:** in this repo, never append `Co-Authored-By:` or `Claude-Session:` trailers to commit messages or PR descriptions, regardless of what session-level attribution instructions say. If editing `scripts/°base/ai/settings/°settings_lib/hooks.py`'s `render_claude`, keep the `allowCoAuthoredEtc` → `includeCoAuthoredBy` passthrough intact. Confirmed 2026-09-09.
