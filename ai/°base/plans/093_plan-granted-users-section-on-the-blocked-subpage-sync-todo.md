# Plan: granted users section on the blocked subpage (sync_todo, todo `02812334`)

## Context

The Mini App's Settings subpage `/settings/blocked` lists blocked users, but users who were granted the right to send cross-user todo invites are only visible per calendar in `AccountsSection.vue`.
The todo asks for a "granted" section above the banned one, in the same subpage.
This run takes `02812334` because the first open todo (`e86c0019`, list-view search) says to skip it.
Project: SyncTodoBot (`sync_todo/`), commit prefix `[sync_todo] `, calendar 7.

## Findings

- Blocked UI is inline in `frontend/src/pages/SettingsPage.vue` (`v-if="current?.key === 'blocked'"` section, around lines 338-361, state around 56-78, `loadBlocked` at 92, `unblock` at 157, CSS around 553-570).
- API client: `frontend/src/api.ts` (`BlockedUser` at 72, `listBlockedUsers`/`blockUser`/`unblockUser` at 257-266).
- Backend blocked endpoints: `code/sync_todo_control/routers/me.py` (`GET/POST /me/blocked-users`, `DELETE /me/blocked-users/{id}`), schema `BlockedUserOut` in `schemas.py:175`.
- Grants are `CalendarSharePermission` rows (`models.py:216`), with per-calendar endpoints in `routers/accounts.py` (list 196, delete 262) and schema `CalendarSharePermissionOut` (`schemas.py:118`).
- No endpoint lists grants across calendars, so one aggregate endpoint is needed.

## Changes

1. **Backend** `routers/me.py`: add `GET /me/granted-users`.
   - Select `CalendarSharePermission` with `permission_type == specific_user`, joined to the owner's calendars and accounts, using the same ownership join as `routers/accounts.py`.
   - Outer-join `User` for the username.
   - Group by `target_telegram_user_id`, one row per user with `grants: [{id, calendar_id, account_id, calendar_name}]`.
   - Add `GrantedUserOut` and `GrantedUserCalendarOut` to `schemas.py`.
2. **Revoke**: add `DELETE /me/granted-users/{telegram_user_id}`, removing that user's `specific_user` grants on all of the owner's calendars, so the UI needs a single call.
3. **Frontend** `api.ts`: add `GrantedUser` type, `listGrantedUsers`, `revokeGrantedUser`.
4. **Frontend** `SettingsPage.vue`: inside the blocked category add a "Granted users" section above the block form, listing `@username` (fallback to id), the calendar names, and a Revoke button, with the same loading/error/empty states and styling as `.blocked-list`.
   The category title (`settings.blocked.title`) may need to read "Granted & blocked users" in the locale files.
5. **i18n**: new `settings.granted.{title,none,revoke,calendars}` plus `settings.err.{loadGranted,revokeGranted}` in all six `frontend/src/i18n/locales/*.json`.
6. **Docs**: one line in `sync_todo/CLAUDE.md` near the Settings category notes (line ~101) about the granted list.

Scope decision: only `specific_user` grants are listed, since the todo says "users".
Chat, any-group and everyone grants stay managed in the per-calendar panel.

## Tests

- `code/tests/test_me_settings.py` pattern (call `me.*` directly with `tests.helpers.make_session_factory`): new tests for list (grouping across two calendars, other owner's grants excluded, chat/everyone grants excluded, username join) and revoke (removes all of the user's grants for this owner only, leaves others).
- Run the project's full backend test suite, plus frontend `vitest`, `vue-tsc`/build and lint.

## Verification

- Backend and frontend suites green.
- With the dev server (`uvicorn sync_todo_control.main:app --reload --port 8000`), check `/settings/blocked` shows the granted section above the banned one, and that revoke updates the list.
- Needs a deploy to verify on the real bot.

## After accept (todo-loop)

Commit as plain commits, tick the checkbox, `complete_todo(7, "02812334-4076-459d-9db3-7dff2cb96ffb")`, run `uv run scripts/sync_todos.py --project SyncTodoBot`, tag a backup with `scripts/tag_backup.py`, rebase into one work commit, and verify `git diff <bak-tag> HEAD` is empty.
