# Plan: `ai/°base/todos.md`

## Context

`ai/°base/todos.md` mirrors the `TODO: Today` calendar (`calendar_id` 7) from the `sync_todo` MCP server.
All four items in the file are already ticked `[x]`, so no open work remains in the file as it stands.
The `sync_todo` MCP server failed to connect this session (`CONNECTION_CLOSED`), so I cannot check whether the calendar has newer, still-open todos.

## Proposed steps

1. Make no code changes, because every listed todo is marked done.
2. Once the `sync_todo` server is reconnected, re-sync the file from the calendar to pick up any open todos.
3. Plan the newly found open todos, if there are any.

## Verification

- Re-read `ai/°base/todos.md` after the re-sync and confirm that at least one `- [ ]` item exists before planning further.
