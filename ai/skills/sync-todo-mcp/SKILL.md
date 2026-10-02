---
name: "sync-todo-mcp"
description: "Use sync_todo's own /mcp server -- the Telegram-todo-CalDAV bot's admin-token-gated MCP server exposing todos/settings/calendar-account tools. Use this whenever the user asks to enable, register, or troubleshoot the sync_todo MCP server, wants Claude Code (or another MCP client) to read/write their sync_todo todos or CalDAV account config directly, or asks about mcp_todos_read/mcp_settings_* scopes or MCP tokens in sync_todo."
---

# sync_todo MCP server

`sync_todo` (the Telegram todo <-> CalDAV sync bot) exposes its own MCP server, separate from
its Mini App. It's a Streamable HTTP server mounted directly inside the bot's own FastAPI app at
`/mcp` (`sync_todo/code/sync_todo_control/main.py`), so it runs on the same host/port as
everything else -- no separate service, no separate deploy.

## Auth model

Every call needs `Authorization: Bearer <token>`. This is a **different** mechanism from the Mini
App's JWT (`sync_todo/code/sync_todo_control/routers/auth.py`) -- MCP tokens are their own thing,
created and revoked via `routers/tokens.py`, admin-only for now (`TELEGRAM_ADMIN_IDS`). A token
is HMAC-hashed at rest (`crypto.py::hash_mcp_token`, keyed by `MCP_TOKEN_HMAC_KEY`); the plaintext
is shown exactly once, at creation, in the sync_todo Mini App's Settings page -- there is no way
to recover it afterward, only revoke and issue a new one.

Auth resolution and scope checks live in `sync_todo/code/sync_todo_control/mcp/auth.py`
(`resolve_mcp_token`, `require_scope`); the tool implementations themselves are in
`sync_todo/code/sync_todo_control/mcp/server.py`.

## Scopes (`models.py::McpScope`)

| Scope | Grants |
|---|---|
| `mcp_todos_read` / `mcp_todos_write` | List/create/update/complete/delete todos on any of the token owner's subscribed calendars. |
| `mcp_settings_user_read` / `mcp_settings_user_write` | Read/patch the same account-wide settings the Mini App's Settings page exposes (discoverability, invite-failure-reason reveal). |
| `mcp_settings_calendar_read` / `mcp_settings_calendar_write` | List/read/update CalDAV account config (name/url/username/readonly) -- **never** the password. |
| `mcp_settings_calendar_password_read` / `mcp_settings_calendar_password_write` | Read/rotate the account's actual CalDAV password. Deliberately split out from the config scopes above -- treat these two as high-sensitivity; a token only needs them if it genuinely has to manage credentials, not just calendar settings. |

A token can hold any subset. Grant the minimum needed.

## Getting a token

1. Sign in as a `TELEGRAM_ADMIN_IDS` user in the sync_todo Mini App.
2. Settings page -> MCP API tokens -> pick a name, description, scopes, optional expiry -> Create.
3. Copy the plaintext shown once. It's never shown again -- only revoke-and-recreate if lost.

## Wiring it into this repo's own Claude Code

Registered in `ai/settings/settings.json`'s `mcp.servers.sync_todo` (disabled by default -- flip `enabled` to `true` once a real token exists).
It's a `stdio` entry, not a native `http` one: there's no `${VAR}` substitution for `http`-type `headers` anywhere in this repo's sync tooling (`scripts/°base/ai/settings/°settings_lib/mcp_servers.py` copies `headers` verbatim), so the entry instead bridges through [`mcp-remote`](https://www.npmjs.com/package/mcp-remote) (`npx -y mcp-remote "$SYNC_TODO_MCP_URL" --header "Authorization:Bearer $SYNC_TODO_MCP_TOKEN"`).
Wrapped in the existing `mcp.tools[".env"]` prefix (same mechanism `bugsink`'s entry already uses -- `npx -y envmcp --env-file ai/.env`), that env var comes from `ai/.env`.

How the variable actually reaches `mcp-remote`, and why the header argument is written the way it is:

- `envmcp` only loads the file into its own `process.env` and then `spawn`s the rest of the command with `shell: true`, so it is `/bin/sh` that expands `$SYNC_TODO_MCP_TOKEN`.
- The value is the bare token `sytd_...`; the `Bearer ` prefix is part of the argument.
  It contains a space, so the argument carries its own literal double quotes (`"\"Authorization:Bearer $SYNC_TODO_MCP_TOKEN\""` in JSON).
  Unquoted, the shell splits it into `Authorization:Bearer` and `sytd_...` and `mcp-remote` exits.
- Never write it as `${SYNC_TODO_MCP_TOKEN}`: Claude Code itself expands that form in `.mcp.json` from *its own* environment before `envmcp` ever runs, and the variable only exists in `ai/.env`.
- The sync (`sync.py`) merges edits to `.mcp.json` / `.codex/config.toml` back into `settings.json`, and the native files win on a difference.
  To change this entry, edit all three consistently, or the sync silently reverts your `settings.json` edit.

Symptom of getting this wrong (with a valid `ai/.env` symlink): `CONNECTION_CLOSED` or `Failed to reconnect to sync_todo` in `/mcp`.
A tool call answering `Missing or malformed Authorization header` means the header arrived without `Bearer `, e.g. the prefix is missing from the config, or `ai/.env` holds it a second time.

To actually enable it:

1. Get a token (above).
2. Add `SYNC_TODO_MCP_TOKEN=sytd_...` (the bare token, no `Bearer ` -- the config adds that) to
   `ai/.env`. This file is `.env`-shaped and therefore off-limits to an agent's own
   tools in this repo (hard denylist) -- a human has to do this step.
3. Add `SYNC_TODO_MCP_URL=http://localhost:8000/api/mcp/` (or `<PUBLIC_URL>/mcp` for a deployed bot) next to it.
4. Flip `ai/settings/settings.json`'s `mcp.servers.sync_todo.enabled` to `true`.
5. Start a new Claude Code session (the `SessionStart` hook re-runs
   `scripts/°base/ai/settings/sync.py` automatically) or run that script by hand to re-render
   `.mcp.json`.

The URL comes from `SYNC_TODO_MCP_URL` for the same reason as the token, and is quoted the same way.
For a locally running dev instance use `http://localhost:8000/api/mcp/` (`sync_todo/CLAUDE.md`'s documented `uvicorn sync_todo_control.main:app --reload --port 8000`, with `POLLING=1`).
The direct backend needs the `/api` prefix and trailing slash (the app has `root_path="/api"`, and a bare `/mcp/` is a 404 there).
For the deployed bot use `<PUBLIC_URL>/mcp`, where the frontend nginx adds that prefix.
An unset `SYNC_TODO_MCP_URL` gives `mcp-remote` an empty URL and the same `Failed to reconnect` symptom.

## Extending it

New tools go in `sync_todo/code/sync_todo_control/mcp/server.py`, following the existing pattern:
open a session via `authed_session(ctx, McpScope.X)`, then delegate to the same single write
paths every other router uses (`caldav_sync/todo_ops.py` for todos, never touching CalDAV/DB
directly). Add tests to `sync_todo/code/tests/test_mcp_server.py`.
