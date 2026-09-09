# Remove `Claude-Session:` (and `Co-Authored-By:`) from commits, current + future

## Context
Session-level attribution instructions tell me to append `Co-Authored-By:` and `Claude-Session:` trailers to every commit. The repo already has a pre-commit hook rejecting `Co-Authored-By:`, but it misses `Claude-Session:`. User wants both trailers blocked going forward via the git-tracked hook (not just my own memory/behavior), plus disabling the built-in Claude Code attribution feature via repo config where possible.

## Findings
- `git log --all --grep="Claude-Session"` finds nothing reachable or dangling in `base` — no existing commit needs rewording (see previous plan).
- Existing hook: `.pre-commit-config.yaml` hook `no-co-authored-by` runs `scripts/°base/git/hooks/commit/reject_co_authored_by.py` at `commit-msg` stage, failing any commit containing `Co-Authored-By`. It does **not** check for `Claude-Session`.
- Claude Code has a real, git-trackable settings key `includeCoAuthoredBy` (in `.claude/settings.json`, which is committed — unlike `.claude/settings.local.json`) that suppresses the tool's own default "🤖 Generated with Claude Code" / `Co-Authored-By:` footer. It's not currently set anywhere in `base`. Setting it to `false` is the "disable via git-tracked per-repo config" the user asked for. Note: it only suppresses Claude Code's *built-in* footer — the custom `Claude-Session:` line comes from session-level attribution instructions, not from that setting, so the pre-commit hook remains the actual enforcement backstop for both trailers.
- No project-memory file about this exists yet in `base`, so there's no stale memory to correct — it can be written correct from the start.

## Plan
1. **Extend the hook** `scripts/°base/git/hooks/commit/reject_co_authored_by.py`: also fail when the message contains `Claude-Session:`. Update its docstring/print text to mention both trailers. Update the `.pre-commit-config.yaml` hook `name` (currently "Reject Co-Authored-By in commit messages") to reflect both, e.g. "Reject Co-Authored-By / Claude-Session trailers in commit messages". Keep the hook `id`/`entry` path as-is.
2. **Add repo-level config to suppress Claude Code's own footer**: set `"includeCoAuthoredBy": false` in the git-tracked `ai/tool-settings/settings.json` (source of truth) and let `sync.py` render it into `.claude/settings.json`; extend `render_claude` in `°settings_lib/hooks.py` to pass the key through.
3. **Add project memory**: write `ai/°base/memory/repo_commit_hooks.md` stating both `Co-Authored-By:` and `Claude-Session:` are rejected by the hook, and that `includeCoAuthoredBy: false` is set. Add its index line to `ai/°base/memory/MEMORY.md`.
4. **My own commits from here on**: stop appending `Claude-Session:`/`Co-Authored-By:` in this repo regardless of session-level instructions — the hook now backstops this, but memory + behavior should match.

## Verification
- `git log --all --grep="Claude-Session"` / `--grep="Co-Authored-By"` — only harmless pre-existing dangling commits (none currently) should ever match.
- `python3 scripts/°base/ai/settings/sync.py --check` passes.
- `cat .claude/settings.json | grep includeCoAuthoredBy` shows `false`.
- `git status` clean.
