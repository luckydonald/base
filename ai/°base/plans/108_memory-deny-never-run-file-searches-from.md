# Memory + deny: never run file searches from `/`

**Commit style:** Skill `/commit-with-lplp-style` is active, auto-commit following it for this implementation.

Todo `d23bc543-c583-4dc1-a8ed-1141c92f6822` (calendar 7, `ai/todos.md`, base repo).

## Context

Searching the whole filesystem (`find / …`, `grep -r … /`) is slow, noisy and can hit protected or huge trees.
Record it as a memory and block `find /` in the shared settings.

## Findings

- Base-repo memory lives in `ai/°base/memory/` (format: `feedback_fix_preexisting_errors_separate_commit.md`), indexed in `ai/°base/memory/MEMORY.md`.
- Shared permissions are in `ai/settings/settings.json`, `permissions.deny` (~line 379), entries look like `{"type": "bash", "command": "ls:*"}` (`:*` = prefix match).
- No existing memory or deny rule covers this.

## Changes

1. New `ai/°base/memory/feedback_never_search_from_filesystem_root.md`
   - `name: feedback-never-search-from-filesystem-root`, `metadata.type: feedback`.
   - Body: never run file searches (find, grep -r, fd, rg, Glob/Grep with path `/`) rooted at `/`. Search within the project dir or a specific subdirectory instead.
   - **Why:** whole-disk scans are slow, flood output and touch unrelated or protected data.
   - **How to apply:** scope every search to the repo or a known directory; if the location is unknown, ask or check likely dirs.
2. `ai/°base/memory/MEMORY.md`: one index line.
3. `ai/settings/settings.json` `permissions.deny`: add `{"type": "bash", "command": "find /:*"}` and `{"type": "bash", "command": "find / :*"}`-style variants, so `find / …` is blocked (`find /:*` also matches `find /Users/...`, so use `find / :*` plus exact `find /`).
   Risk: `find /:*` prefix would block `find /Users/user/project`, so only the space-terminated form `find / :*` and the exact `find /` are added.
4. Run the settings sync that renders `.claude/settings*.json` if the repo requires it (see `ai/settings/README.md`), and check the rendered deny list.

## Verification

- JSON validity: `python -m json.tool ai/settings/settings.json`.
- Settings sync output shows the new deny entries; settings tests if any (`scripts/°base/tests`).
