The blocked list already exists, but there is no "granted users" list anywhere. Grants exist only as per-calendar rows, so a "granted" section needs one new aggregate endpoint.

**(1) Blocked users subpage**
- The route is `/settings/blocked`. It is a category entry in `frontend/src/settings/sections.ts:14`: `{ key: 'blocked', titleKey: 'settings.blocked.title' }`.
- The UI is inline in `frontend/src/pages/SettingsPage.vue`, not a separate component:
  - `<section v-if="current?.key === 'blocked'">` is at lines 338-361. It holds the block form (username input), then a loading/error/empty state, then `<ul class="blocked-list">`. Each `<li>` shows `@{{ blocked_username ?? blocked_telegram_user_id }}` and an Unblock button.
  - State is at lines 56-58 and 76-78.
  - `loadBlocked` is at line 92, `submitBlock` at 143 and `unblock` at 157.
  - `loadBlocked` is called from `onMounted` at line 224.
  - CSS for `.blocked-list` is at lines 553-570.
- API client in `frontend/src/api.ts`: the `BlockedUser` interface is at line 72, and `listBlockedUsers`, `blockUser` and `unblockUser` are at lines 257-266.
- i18n keys in `frontend/src/i18n/locales/{en,de,fr,it,es,ru}.json`. In `en.json`:
  - `settings.blocked.{title,username,block,blocking,none,unblock}` is at lines 125-132.
  - `settings.err.{loadBlocked,block,unblock}` is at lines 164-167.
  - Grant-related keys that already exist are `accounts.noGrants`, `accounts.grant*`, `accounts.grantUser` ("Specific user: @{name}") and `accounts.grantChat` (around lines 554-568).

**(2) Backend**
- The blocked model is `BlockedUser` in `code/sync_todo_control/models.py:435`. Its table is `blocked_users`, and the columns are `blocker_telegram_user_id`, `blocked_telegram_user_id` and `created_at`. It has a unique constraint on the pair.
- The blocked endpoints are in `code/sync_todo_control/routers/me.py`:
  - `GET /me/blocked-users` at line 109.
  - `POST /me/blocked-users` at line 124. The body is `{username}`.
  - `DELETE /me/blocked-users/{id}` at line 156.
- The data shape is `BlockedUserOut` in `code/sync_todo_control/schemas.py:175`: `{id, blocked_telegram_user_id, blocked_username: str|null, created_at}`. It is newest first, joined to `User` for the username.
- Grants are `CalendarSharePermission` in `models.py:216`, with these columns:
  - `caldav_calendar_id`
  - `permission_type`, one of `SharePermissionType` (`models.py:73`): `everyone`, `any_group`, `specific_chat` or `specific_user`
  - `target_chat_id`
  - `target_telegram_user_id`
  - `created_at`
- What a grant means: the calendar owner allows that user or chat to send `@user <text>` cross-user todo invites to that calendar.
- Grant endpoints are per calendar only, in `routers/accounts.py`:
  - `GET /{account_id}/calendars/{calendar_id}/share-permissions` at line 196.
  - `POST` at line 211.
  - `DELETE .../{permission_id}` at line 262.
- The grant shape is `CalendarSharePermissionOut` (`schemas.py:118`): `{id, caldav_calendar_id, permission_type, target_chat_id, target_telegram_user_id, target_username}`.
- The only grant UI is `frontend/src/components/AccountsSection.vue`, in a per-calendar expandable panel (lines 67-145 and 553-584). The `addGrant`, `removeGrant` and `grantLabel` functions are there.
- No endpoint lists all granted users across calendars.
- The ask-first flow in `bot/handlers/invite_actions.py` ("Always Grant" adds a `SPECIFIC_USER` grant, "Always Block" adds a `BlockedUser`) never reaches the Mini App list.

**What a granted list needs**
- Backend: add one aggregate endpoint, for example `GET /me/granted-users` in `me.py`.
  - Query `CalendarSharePermission` for `permission_type == specific_user`, joined to `CaldavCalendar` and `CaldavAccount` and filtered to the owner. Outer-join `User` for the username.
  - Return one row per user with their calendars, because a single user can be granted on several calendars.
  - The shape could be `{target_telegram_user_id, target_username, grants: [{id, calendar_id, account_id, calendar_name}]}`.
  - Decide whether to also list `specific_chat`, `any_group` and `everyone` grants. They are not users.
- Revoking can reuse the existing per-calendar DELETE, which needs `account_id`, `calendar_id` and `permission_id`. Include those ids in the response, or add a `DELETE /me/granted-users/{user_id}`.
- Frontend:
  - Add the type and fetch function in `api.ts`.
  - Add a "Granted users" `<section>` above the banned one inside the existing `v-if="current?.key === 'blocked'"` block in `SettingsPage.vue`. No new route is needed.
  - Add a new `settings.blocked.granted.*` i18n group (or `settings.granted.*`) in all 6 locale JSON files. The current section title may also need renaming.
- I did not check how `accounts.py` verifies calendar ownership. Reuse the same ownership join when you write the new query.

**(3) Tests**
- Frontend: `frontend/src/settings/__tests__/sections.test.ts:20` only lists the `'blocked'` key. There are no tests for SettingsPage, AccountsSection or the blocked API.
- Backend: no test covers the `/me/blocked-users` or `/share-permissions` routers directly.
  - `code/tests/test_invite_actions.py` covers `BlockedUser` and `CalendarSharePermission` creation through the bot flow (lines 11, 14, 90, 138, 235, 240).
  - `code/tests/test_invite_trigger.py` and `test_task_ops.py` cover how invites resolve grants and blocks.
  - `code/tests/test_me_settings.py` is the closest pattern for router tests. It calls `me.*` functions directly with `tests.helpers.make_session_factory`.

**(4) `CLAUDE.md`**
- Line 58 covers cross-user invites in ask-first mode.
- Line 101 covers the Settings category pattern: an entry in `sections.ts` plus a `v-if` block in `SettingsPage.vue`. Reuse that pattern if the granted list were ever split into its own category.