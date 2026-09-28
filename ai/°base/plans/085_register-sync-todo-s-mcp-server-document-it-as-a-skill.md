# Register sync_todo's /mcp server + document it as a skill

**Commit style:** Skill `/commit-with-lplp-style` is active — auto-commit following it for this implementation.

## Context

The previous session built sync_todo's own `/mcp` server (admin-token-gated, 8 scopes, mounted in `sync_todo/code/sync_todo_control/main.py`). The user now wants Claude Code itself (working in this repo) to be able to use it as a registered MCP server, plus a skill documenting it for future sessions. Two blockers surfaced during research and are resolved below:

- **No committed secret.** `ai/settings/settings.json` is checked into git (it's a hardlink shared across the whole repo and every subproject, confirmed identical inode at `sync_todo/ai/settings/settings.json`). The schema's `http`-type servers (`url`/`headers`) have no substitution mechanism in `scripts/°base/ai/settings/°settings_lib/mcp_servers.py` — headers are copied verbatim into `.mcp.json`/`config.toml`. Extending that shared renderer was one option, but a web search confirmed `mcp-remote` (`npx -y mcp-remote`, the standard stdio↔HTTP MCP bridge) already does `${VAR}` expansion inside `--header` values, sourced from the subprocess environment. That means expressing the sync_todo server as a **`stdio`** entry that shells out to `mcp-remote` lets it reuse this repo's *existing* `.env` tools wrapper (`mcp.tools["."env"]`, `npx -y envmcp --env-file ai/.env -- ...` — exactly what `bugsink`'s entry already uses) with **zero changes to shared sync tooling**. The real token only ever lives in `sync_todo/ai/.env` (gitignored, already exists), never in the committed JSON.
- **Skill location:** user chose the repo-root `ai/skills/sync-todo-mcp/` (canonical source, synced into every `.claude/skills/`), matching `bugsink-setup`'s precedent, over a sync_todo-local skill.

## 1. Register the server in `ai/settings/settings.json`

Edit the shared file (either path — `ai/settings/settings.json` or `sync_todo/ai/settings/settings.json`, same inode). Add to `mcp.servers` (alongside the existing `bugsink`/`chrome-devtools` entries):

```json
"sync_todo": {
  "enabled": false,
  "type": "stdio",
  "tools": [".env"],
  "cmd": [
    "npx", "-y", "mcp-remote", "http://localhost:8000/mcp",
    "--header", "Authorization:${SYNC_TODO_MCP_TOKEN}"
  ]
}
```

Notes:
- `enabled: false` by default — flipping it to `true` requires a real token to exist first (see step 3), same reasoning as `chrome-devtools`'s existing disabled-by-default entry.
- `"tools": [".env"]` wraps the `cmd` with `npx -y envmcp --env-file ai/.env` (the existing `mcp.tools["".env"]` prefix, same as `bugsink`), which injects `sync_todo/ai/.env`'s vars into the subprocess environment.
- `--header "Authorization:${SYNC_TODO_MCP_TOKEN}"` (no space around the colon, full "Bearer sytd_..." value goes *inside* the env var) — this exact shape avoids a documented Windows arg-escaping bug in `mcp-remote` (spaces inside a single arg get mangled by some clients' npx invocation).
- URL is `http://localhost:8000/mcp`, matching `sync_todo/CLAUDE.md`'s documented dev command (`uvicorn sync_todo_control.main:app --reload --port 8000`, run with `POLLING=1`) — this is for Claude Code's own dev-time use against a locally running instance, not production (`PUBLIC_URL` isn't a value I can read — `.env`-adjacent files are tool-denylisted for me).

No `°settings_lib`/`sync.py` changes needed — this is a pure data addition using existing rendering logic (already verified: `bugsink`'s identically-shaped stdio+`.env`-tools entry renders correctly into `.mcp.json`/`config.toml` today).

## 2. Document the required manual step (I cannot touch `.env`)

The plan's execution must **not** attempt to read/write/ls/symlink any `.env`-named path (hard tool denylist, this repo's convention). Instead, the skill (step 4) documents, and the final turn's response to the user states plainly:

1. Sign in as an admin in the sync_todo Mini App's Settings page, create an MCP token with whichever scopes are needed (e.g. `mcp_todos_read`), copy the shown plaintext once.
2. Add `SYNC_TODO_MCP_TOKEN=Bearer sytd_...` (the full header value, including `Bearer `) to `sync_todo/ai/.env`.
3. Flip `"enabled": false` → `true` for the `sync_todo` entry in `ai/settings/settings.json`.
4. Either start a new Claude Code session (the `SessionStart` hook re-runs `scripts/°base/ai/settings/sync.py` automatically) or run it manually to re-render `.mcp.json`.

This step is **not part of the commit** — it's user-performed, post-merge, and involves a live secret.

## 3. New skill: `ai/skills/sync-todo-mcp/SKILL.md`

Single-file skill (matching `commit-with-lplp-style`'s precedent — narrow scope, no need for a `references/` split). Frontmatter matching this repo's exact convention (verified against `bugsink-setup`/`code-style`):

```yaml
---
name: "sync-todo-mcp"
description: "Use sync_todo's own /mcp server -- the Telegram-todo-CalDAV bot's admin-token-gated MCP server exposing todos/settings/calendar-account tools. Use this whenever the user asks to enable, register, or troubleshoot the sync_todo MCP server, wants Claude Code (or another MCP client) to read/write their sync_todo todos or CalDAV account config directly, or asks about mcp_todos_read/mcp_settings_* scopes or MCP tokens in sync_todo."
---
```

Content to cover (concise, following this repo's existing skill tone — short prose, cite real file:line, no invented paths):

- What it is: a Streamable HTTP MCP server mounted at `/mcp` inside `sync_todo`'s own FastAPI app (`sync_todo/code/sync_todo_control/main.py`), gated by `McpToken` bearer tokens (`sync_todo/code/sync_todo_control/models.py::McpScope`, `routers/tokens.py`) — separate from the Mini App's own JWT auth.
- The 8 scopes and what each gates (`mcp_todos_read`/`_write`, `mcp_settings_user_read`/`_write`, `mcp_settings_calendar_read`/`_write`, `mcp_settings_calendar_password_read`/`_write` — flag the password scopes as high-sensitivity, matching the commit history's own callout).
- How to get a token: admin-only (`TELEGRAM_ADMIN_IDS`), Settings page in the Mini App, one-time plaintext reveal.
- How this repo's Claude Code registers it: the `ai/settings/settings.json` `mcp.servers.sync_todo` entry (step 1 above), bridged via `mcp-remote` + the `.env` tools wrapper — link to `sync_todo/ai/.env`'s `SYNC_TODO_MCP_TOKEN` var and the manual enable steps from step 2, so a future session (or this one, later) can pick this up without re-deriving it.
- Pointer to `sync_todo/code/sync_todo_control/mcp/server.py` for the actual tool implementations, and `mcp/auth.py` for the auth/scope-check flow, for anyone extending it.

## 4. Commit

One `/commit-with-lplp-style` commit covering both `ai/settings/settings.json` and the new `ai/skills/sync-todo-mcp/SKILL.md` — no `.env` file touched, no other unrelated files staged. Suggested message shape:

```
[root] [ai] mcp: ai: Run: Registered sync_todo's /mcp server (disabled by default) and documented it as a skill.
```

(Confirm the actual `component-or-topic` wording against `git log --oneline -5 -- ai/settings/settings.json` per the lplp skill's own history-lookup rule before finalizing the message at commit time.)

## Verification

- `python3 -c "import json; json.load(open('ai/settings/settings.json'))"` — valid JSON after the edit.
- Validate the new `sync_todo` entry against `ai/settings/mcp.schema.json` if a validator is easily available (otherwise eyeball against `bugsink`'s existing entry shape, which is schema-valid today).
- `git log --oneline -5 -- ai/settings/settings.json` — confirm the commit message wording matches this file's established `component-or-topic` history per the lplp skill's own rule.
- Do **not** run `scripts/°base/ai/settings/sync.py` against a filled-in secret during this session (no real token exists yet, and `.env` isn't touched) — rendering into `.mcp.json` happens automatically for the user on their next session start, or manually once they've completed step 2.
- Read back the written `ai/skills/sync-todo-mcp/SKILL.md` once more before committing to confirm frontmatter matches the exact `name`/`description` quoting style used by existing skills.
