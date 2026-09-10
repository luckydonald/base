# Rename `ai/tool-settings/` → `ai/settings/`

## Context
The user asked to rename the `@ai/tool-settings/` folder to `ai/settings`. The folder move itself (`git mv ai/tool-settings ai/settings`) was already executed before plan mode engaged — `git status` confirms the 5 files show as renames. What remains is updating every functional reference to the old path so the repo keeps working, plus the couple of living docs/memory files that describe it. Historical/frozen records (past plan write-ups, agent output logs) are left untouched — they're records of what happened at the time, not living documentation, and rewriting them would falsify history.

Scope is the main worktree only. `.claude/worktrees/claude-split-impl` and `.claude/worktrees/claude-split-improvement` are separate git worktrees on other branches (confirmed via `git worktree list`) — out of scope, not touched.

## Already done
- `git mv ai/tool-settings ai/settings` (shows as 5 renames in `git status`)

## Files to update (functional — required for things to keep working)
- `scripts/°base/ai/settings/°settings_lib/paths.py` — `TRACKED_SHARED`/`LOCAL_SHARED` constants point at `ai/tool-settings/...`
- `scripts/°base/ai/settings/°settings_lib/cli.py` — docstring/help text reference
- `scripts/°base/ai/settings/°settings_lib/codex_toml.py` — comment reference
- `scripts/°base/ai/references/°dllink_lib/config.py` — two hardcoded paths to `settings.json`/`settings.local.json`
- `scripts/°base/git/hooks/commit/require_yarn_4.py` — `SHARED_SETTINGS`/`LOCAL_SETTINGS` constants + two message strings
- `scripts/°base/init/link-subproject-claude.sh` — symlink target `ai/tool-settings` (comment + `link_shared` call)
- `scripts/°base/tests/test_ai_settings_sync.py` — ~16 occurrences of `root / "ai" / "tool-settings" / ...`
- `scripts/°base/tests/test_yarn_4_hook.py` — path literals in fixtures
- `scripts/°base/tests/test_tool_settings_schema.py` — `SETTINGS_DIR` constant; **also rename this file itself** to `test_settings_schema.py` for consistency with the folder rename
- `.codex/config.toml` — reference to the old path (verify exact content before editing)

## Files to update (living docs/memory)
- `ai/°base/AGENTS.md` — codebase guidance doc, likely documents the settings folder location
- `ai/skills/bugsink-triage/enable.md`
- `ai/skills/code-style/references/yarn.md`
- `ai/memory/MEMORY.md` — index line for `repo_commit_hooks.md` mentions `ai/tool-settings/settings.json`
- `ai/memory/repo_commit_hooks.md` — two references to `ai/tool-settings/settings.json`
- `ai/°base/memory/MEMORY.md` — a second, distinct tracked memory-index file (not a hardlink of `ai/memory/MEMORY.md` — different inode, different/shorter content) whose one entry for "Repo commit hooks" also names `ai/tool-settings/settings.json`
- `.codex/config.toml` — one comment line: `# [plugins].*.enabled below is managed by scripts/°base/ai/settings/sync.py from ai/tool-settings/settings.json's enabledPlugins; ...`

## Explicitly out of scope (do not edit) — confirmed
- `ai/°base/plans/*.md` — historical plan write-ups documenting past work; frozen record
- `ai/°base/output/agents/**` and `ai/°base/output/compact/**` — frozen agent run logs
- `ai/output/agents/**` — frozen agent run logs
- `ai/°base/query.md` — confirmed to be a 302KB tracked transcript/query log of past conversations (contains dozens of `tool-settings` mentions verbatim as things were asked/said at the time); it's a historical record like the plans/output dirs, not living documentation — leave untouched

## Verification
1. `grep -rn "tool-settings\|tool_settings" --include="*" .` (excluding `.claude/worktrees/`, `ai/°base/plans/`, `ai/°base/output/`, `ai/output/`) returns nothing.
2. Run the settings-sync test suite: `cd scripts/°base && python -m pytest tests/test_ai_settings_sync.py tests/test_settings_schema.py tests/test_yarn_4_hook.py -q` (adjust invocation to however this repo normally runs its Python tests — check for a `pyproject.toml`/`poetry` or `uv` runner first).
3. Run `scripts/°base/init/link-subproject-claude.sh` sanity: not executed against real state, just review the diff for correctness (this script creates symlinks in consuming projects — don't actually invoke it).
4. `git status` shows the rename plus modified files; review the full diff before considering the task complete.
</content>
