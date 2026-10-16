# Todos

Source: `sync_todo` MCP, calendar `TODO: Today` (`calendar_id` 7), pulled 2026-10-08. Each item ends with its todo `uid`.
To complete one: tick the box and call `mcp__sync_todo__complete_todo(calendar_id=7, uid=<uid>)`.

- [!] fix the codestyle not loading for /plan. — `todo:268ba6c5-56d0-4879-9a52-50c3c9ede70c` _(needs action)_
  > Use the official anthropic skill creator skill to help you.
- [!] the Make sure a file mention like (@ai/somefile.txt) gets detected to not include the ).I guess the try combinations algortithm (….txt) does not exist, ….txt does exist) would work here, too. — `todo:66f35747-cd41-4646-aee5-989858265baf` _(needs action)_
- [!] Allow referenced file auto-commit in more git states: — `todo:b7a5299c-3989-4bc1-bef3-b12418b8249b` _(needs action)_
  > • for the linked file in query (@ai/whatever) detection & committing hook
  > • staged and previously commited files
  > • still must adhere to .gitignore
- [!] also link `/skill` calls to their `ai/skills/…/SKILL.md` — `todo:be604b2a-0d90-4b41-973b-d57bc48e0772` _(needs action)_
  > • obviously the skill must exist
- [!] add skill to use `download_ref.py` — `todo:e7df2be3-4ad7-41c4-8aab-d3a2acd1508b` _(needs action)_
  > So at least `--no-ide.`

## Synced from CalDAV

- [ ] Strip `Note: The user's next message may contain a correction or preference. Pay close attention — if they explain what went wrong or how they'd prefer you to work, consider saving that to memory for future sessions.` from plan decisions. — `todo:5e80abad-4a70-4e79-b210-14ac7b639f88`
- [ ] Have a rebase or merge use git triggers to re-sync per-file subproject symlinks. — `todo:6f2b2450-103d-4be5-b029-bbe95c3e5501`
- [ ] have a `.run/.subprojectIgnore` file, defining files to not link into subprojects. — `todo:58a06dbd-33b8-48fe-b392-9f5a67b935cc`
- [ ] `ai/memories/MEMORY.md` is skipped in commit — `todo:b8ae433f-4258-4549-b98c-cc3ceded8903`
  > • but it’s written and then a dirty file
  > • figure out why; I even got you an example:
  > • DockerTgBot
  > • claude possibly running from the `sync_todo` subdirectory.
  > • The files themselves were eventually squashed into b6bab629bce68382369588a25f448afaaf66c6b8.
  > • backup tags should exist with possibly the original commit
  > • search for filename in commit msg
  > • I manually added the `ai/memories/MEMORY.md` in 3927b1d4cc654ec54bba23997c7f448e193b4cab there.
- [ ] have the sync ai settings script show a propper diff — `todo:51f4adc0-dc22-43c4-92cf-4bf9475b9ba1`
  > Both for dry run and the actual execution. This is to catch errors if the wrong file was detected as newest, and the changes are removed by syncing an older file over it. This allows the AI agent or user to detect that.
- [ ] have the show-plan-confirm-action for claude also sync the plan once more — `todo:7eb9a977-d3d3-4ba0-9889-39732d4c7f1a`
  > Sometimes it uses echo or python scripts to edit the plan file, also usually not mentioning the full path in one go, but `CLAUDE_PLAN_DIR + PLAN_NAME + ‘.md’` or something weird.
  > Hence it’s best to write & commit it once more. You can also use the plan decision hook for that, if that’s better.
- [x] add missing `mcp__bugsink__*` permissions — `todo:9adc5376-530b-4020-9cf4-6f7e55ff3ac1` _(done)_
  > Add to @ai/settings/settings.json:
  > ```json
  > // TODO: fix quotes
  > “mcp__bugsink__list_events”,
  > “mcp__bugsink__get_event”,
  > “mcp__bugsink__get_stacktrace”,
  > “mcp__bugsink__test_connection”,
  > ```
- [x] checkout.sh: skip symlinked hooks in repair_git_lfs_hooks_path — `todo:56f6ee1a-63c7-4c77-9588-174c3f48d98d` _(done)_
  > `scripts/°base/init/checkout.sh` `repair_git_lfs_hooks_path()` rewrote symlinked hooks (e.g. `.git/hooks/pre-push` -> tracked `.hooks/pre-push.bash`) through the link, stripping the repo's own hook content on every Claude session start.
  > Fixed in luckydonald/docker-tg-bot with a `[ -L "$hook_file" ] && continue` guard plus `scripts/°base/tests/test_checkout_lfs_hooks.py`; bring the same change into luckydonald/base.
