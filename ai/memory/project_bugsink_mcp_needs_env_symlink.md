---
name: project-bugsink-mcp-needs-env-symlink
description: "bugsink MCP CONNECTION_CLOSED in a subproject or worktree usually means its ai/.env symlink is missing, not bad credentials."
metadata:
  node_type: memory
  type: project
  originSessionId: 015EL99F33bzNYzH8kCYWuxn
  modified: 2026-09-28T00:00:00.000Z
---

The root `bugsink` MCP server is wired via the root `.mcp.json` (`npx envmcp --env-file ai/.env npx bugsink-mcp`), and subproject/worktree `.mcp.json` files inherit it (symlinked to `../.mcp.json` or equivalent). The `--env-file ai/.env` path is relative and resolves against the **spawning process's cwd** — the Claude Code session's working directory — not against wherever the physical `.mcp.json` lives. Each subproject or worktree has its own real (non-symlinked) `ai/` directory holding task-local `query.md`/`plans`/`errors`/`output`, with only some entries (`references`/`settings`/`skills`) symlinked back to the shared root `ai/`. If nobody's added an `ai/.env` symlink there too, `envmcp` fails to find the file and the MCP client reports it opaquely as `CONNECTION_CLOSED`.

**Fix per subproject/worktree:**
```bash
ln -s <path-to-repo-root>/ai/.env <subproject-or-worktree>/ai/.env
```
(mirrors the existing `references`/`settings`/`skills` symlink pattern). Confirmed and fixed previously for `sync_todo/`, and again for the `.claude/worktrees/fix-bug` git worktree (2026-09-28).

**Important:** fixing the symlink mid-session is not enough — the MCP connection attempt already happened (and failed) at session start and does not auto-retry. A fresh session (or an explicit MCP reconnect) is needed before `bugsink` tools become available again.

**Why:** discovered 2026-09-22 while debugging why `mcp__bugsink__*` tools were unavailable in a `sync_todo` session; recurred 2026-09-28 in a fresh git worktree that also lacked the symlink. `bugsink-triage`'s own `enable.md` doc covers the "disabled by default" case but not this cwd/symlink gotcha.

**How to apply:** if `bugsink` (or any other root-`.mcp.json`-inherited server using a relative `--env-file`/similar path) shows `CONNECTION_CLOSED` in a different subproject or worktree session, check first whether `<subproject>/ai/.env` or `<worktree>/ai/.env` exists as a symlink before assuming a credentials or server problem — and remember that a fresh session is required after adding it. See also [[feedback_env_file_tool_denylist]].
