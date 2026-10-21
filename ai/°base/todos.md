# Todos

Source: `sync_todo` MCP, calendar `TODO: Today` (`calendar_id` 7), pulled 2026-10-08. Each item ends with its todo `uid`.
To complete one: tick the box and call `mcp__sync_todo__complete_todo(calendar_id=7, uid=<uid>)`.

- [x] fix the codestyle not loading for /plan. — `todo:268ba6c5-56d0-4879-9a52-50c3c9ede70c` _(done)_
  > Use the official anthropic skill creator skill to help you.
- [x] the Make sure a file mention like (@ai/somefile.txt) gets detected to not include the ).I guess the try combinations algortithm (….txt) does not exist, ….txt does exist) would work here, too. — `todo:66f35747-cd41-4646-aee5-989858265baf` _(done)_
- [x] Allow referenced file auto-commit in more git states: — `todo:b7a5299c-3989-4bc1-bef3-b12418b8249b` _(done)_
  > • for the linked file in query (@ai/whatever) detection & committing hook
  > • staged and previously commited files
  > • still must adhere to .gitignore
- [x] also link `/skill` calls to their `ai/skills/…/SKILL.md` — `todo:be604b2a-0d90-4b41-973b-d57bc48e0772` _(done)_
  > • obviously the skill must exist
- [x] add skill to use `download_ref.py` — `todo:e7df2be3-4ad7-41c4-8aab-d3a2acd1508b` _(done)_
  > So at least `--no-ide.`

## Synced from CalDAV

- [x] Strip `Note: The user's next message may contain a correction or preference. Pay close attention — if they explain what went wrong or how they'd prefer you to work, consider saving that to memory for future sessions.` from plan decisions. — `todo:5e80abad-4a70-4e79-b210-14ac7b639f88` _(done)_
- [x] Have a rebase or merge use git triggers to re-sync per-file subproject symlinks. — `todo:6f2b2450-103d-4be5-b029-bbe95c3e5501` _(done)_
  > for now skip this todo (it is already being worked on in the base repository itself, don't do it from another project)
- [x] have a [`.run/.subprojectIgnore`](../.run/.subprojectIgnore) file, defining files to not link into subprojects. — `todo:58a06dbd-33b8-48fe-b392-9f5a67b935cc` _(done)_
- [x] `ai/memories/MEMORY.md` is skipped in commit — `todo:b8ae433f-4258-4549-b98c-cc3ceded8903` _(done)_
  > • but it’s written and then a dirty file
  > • figure out why; I even got you an example:
  > • DockerTgBot
  > • claude possibly running from the `sync_todo` subdirectory.
  > • The files themselves were eventually squashed into b6bab629bce68382369588a25f448afaaf66c6b8.
  > • backup tags should exist with possibly the original commit
  > • search for filename in commit msg
  > • I manually added the `ai/memories/MEMORY.md` in 3927b1d4cc654ec54bba23997c7f448e193b4cab there.
- [x] have the sync ai settings script show a propper diff — `todo:51f4adc0-dc22-43c4-92cf-4bf9475b9ba1` _(done)_
  > Both for dry run and the actual execution. This is to catch errors if the wrong file was detected as newest, and the changes are removed by syncing an older file over it. This allows the AI agent or user to detect that.
- [x] have the show-plan-confirm-action for claude also sync the plan once more — `todo:7eb9a977-d3d3-4ba0-9889-39732d4c7f1a` _(done)_
  > Sometimes it uses echo or python scripts to edit the plan file, also usually not mentioning the full path in one go, but `CLAUDE_PLAN_DIR + PLAN_NAME + ‘.md’` or something weird.
  > Hence it’s best to write & commit it once more. You can also use the plan decision hook for that, if that’s better.
- [x] add missing `mcp__bugsink__*` permissions — `todo:9adc5376-530b-4020-9cf4-6f7e55ff3ac1` _(done)_
  > Add to [@`ai/settings/settings.json`](./settings/settings.json):
  > ```json
  > // TODO: fix quotes
  > “mcp__bugsink__list_events”,
  > “mcp__bugsink__get_event”,
  > “mcp__bugsink__get_stacktrace”,
  > “mcp__bugsink__test_connection”,
  > ```
- [x] checkout.sh: skip symlinked hooks in repair_git_lfs_hooks_path — `todo:56f6ee1a-63c7-4c77-9588-174c3f48d98d` _(done)_
  > [`scripts/°base/init/checkout.sh`](../scripts/°base/init/checkout.sh) `repair_git_lfs_hooks_path()` rewrote symlinked hooks (e.g. [`.git/hooks/pre-push`](../.git/hooks/pre-push) -> tracked `.hooks/pre-push.bash`) through the link, stripping the repo's own hook content on every Claude session start.
  > Fixed in luckydonald/docker-tg-bot with a `[ -L "$hook_file" ] && continue` guard plus [`scripts/°base/tests/test_checkout_lfs_hooks.py`](../scripts/°base/tests/test_checkout_lfs_hooks.py); bring the same change into luckydonald/base.
- [x] design auto-commit to be scoped only to the link paths, bypass hooks, skip during merges/rebases/detached HEAD, and safely fall back to staged-but-uncommitted if anything fails — `todo:163fb511-e999-42c1-b288-818da77d2e40` _(done)_
  > - ˋlink_subproject.pyˋ already does it now
  > - the other things should do that too
  > - ideally a shared python function
- [x] Remove the `_` prefix from private-style functions in `record-memory/hook.py` — `todo:fded287a-f92c-4f4f-a632-8b3f373eba44` _(done)_
  > • code-style says no `_` prefix for ordinary identifiers; hook.py still has ~20 (`_commit`, `_sync_all`, `_git_root`, `_rm_targets`, …)
  > • rename them and their callers/tests
  > • or extract into a module instead of hiding them
  > • low prio, pure cleanup
- [x] for github links, which are turned into a git commit, keep a `latest` folder with symlinks. — `todo:3caf29dd-df53-4dd5-8f5f-3b99f41c0cf8` _(done)_
  > • It should link the individual files each
  >   • because existing files are not updated to new versions automatically.
  >   • however pulling a new file which writes a new commit will overwrite that file's latest symlink with the new symlink target
  > • Keep the directory structure up to the file symlink.
  >
  > #### Example
  >
  > 1. We instruct to download `https://github.com/ChromeDevTools/chrome-devtools-mcp/blob/main/docs/advanced-usage.md`
  > 2. It writes the file[`ai/references/https/github.com/ChromeDevTools/chrome-devtools-mcp/blob/882f93e9a8809fe88eced35d793951fb456b7117/docs/advanced-usage.md`](./references/https/github.com/ChromeDevTools/chrome-devtools-mcp/blob/882f93e9a8809fe88eced35d793951fb456b7117/docs/advanced-usage.md) as expected
  >    - Note: the hash is likely different in a test today, this is the old file already in git.
  > 3. NEW: it creates a symlink for that branch.
  >    1. It creates the directory path recursively for the current branch
  >       - so like the existing output path in **2.** but instead of `blob/<commit-sha>` it uses the specified `blob/main/docs/`
  >         - probably you recalculate that path with `blob/main` instead.
  >     - basically `mkdir -p ai/references/https/github.com/ChromeDevTools/chrome-devtools-mcp/blob/main/`
  >    2. it adds the symlink under that dir to the downloaded file (soft symlink)
  >       - in that folder created by **3.1.**
  >       - The symlink should be relative
  >         - use `../` repeateatly to get where it needs to go
  >         - `pathlib` does that for you already
  >       - basically `ln -s ../../882f93e9a8809fe88eced35d793951fb456b7117/docs/advanced-usage.md`
  >         - symlink goes from `blob/main/docs/advanced-usage.md` up to the `blob` dir,
  >         - then into the correct git hash one,
  >         - then down to that file there.
  >       - instead of `blob/<commit-sha>` it uses `blob/<branch>`
  >    - You may combine the steps **3.1** and **3.2** if that make sense
  >      - Use `pathlib.Path` for efficiency.
  >    - So the symlink will be at `ai/references/https/github.com/ChromeDevTools/chrome-devtools-mcp/blop/main/docs/advanced-usage.md`, pointing to the written file
  > 4. NEW: it creates a latest symlink
  >    - similarly to **3.**
  >    - instead of `blob/<commit-sha>` or `blob/<branch>` it uses `latest`
  >      - which is not a valid github URL, but helpful for a human.
  >    - So the symlink will be at `ai/references/https/github.com/ChromeDevTools/chrome-devtools-mcp/latest/docs/advanced-usage.md`, pointing to the written file
  >    - which is not a valid github URL, but helpful for a human.
  >
  > #### TL;DR:
  >
  > Path | What
  > --- | ---
  > `https://github.com/ChromeDevTools/chrome-devtools-mcp/blob/main/docs/advanced-usage.md` | URL
  > [`ai/references/https/github.com/ChromeDevTools/chrome-devtools-mcp/blob/882f93e9a8809fe88eced35d793951fb456b7117/docs/advanced-usage.md`](./references/https/github.com/ChromeDevTools/chrome-devtools-mcp/blob/882f93e9a8809fe88eced35d793951fb456b7117/docs/advanced-usage.md) | download
  > `ai/references/https/github.com/ChromeDevTools/chrome-devtools-mcp/blop/main/docs/advanced-usage.md` | branch symlink
  > `ai/references/https/github.com/ChromeDevTools/chrome-devtools-mcp/latest/docs/advanced-usage.md` | latest symlink
- [x] Add a `ai/.subDir` file, instructing which [`ai/query.md`](./query.md) etc. is to be used. — `todo:6bc531bc-61bf-46b2-9bd1-2955685b80db` _(done)_
  > • not present: as before
  > • present: contains the relative path from the git root to the subproject to use
  > • This would be an extension of the exisiting subproject detection in the path generation of `query.md` and generally the `ai/` folder to use
  > • That `ai/.subDir` file is added to `.gitignore`
- [x] make sure `?plain=1` and `?preview=1` is properly ignored for github links in [`scripts/download_ref.py`](../scripts/°base/ai/references/download-link.py). — `todo:71a4bb57-51ba-4875-91f2-d5b1451aa801` _(done)_
  > • e.g. https://github.com/mdn/content/blob/main/files/en-us/web/api/navigator/registerprotocolhandler/index.md?plain=1
- [x] add memory for storing telegram `user_id` to db or fixed integer size to be BIGINT. — `todo:2d6a17a2-5d9a-44d2-93a3-245ae8215388` _(done)_
  > • reference the specific `ai/references/` markdown file for this in the memory's body.
- [x] allow `/code-style` and suffix like `/code-style .md .py` or `/code-style md` in the query-autocommit hook to not be displayed — `todo:2eaeb8ce-67be-4878-a8df-3fb3311a4be8` _(done)_
  > • there's an array to fill
- [x] add `mcp__sync_todo__list_calendars` to allowed calls in [`ai/settings/settings.json`](./settings/settings.json). — `todo:87dac3b4-331e-4043-8f5b-cc5e45c113ab` _(done)_
- [x] add memory that if we stumble over preexisting errors in unittests or typing, those should be fixed as a separate commit automatically, too. No need to explicitly seach for those though. — `todo:8ae825eb-3ef2-4d84-8180-a937d7e2bb3c` _(done)_
- [ ] Write memory to NEVER EVER run file searches from `/`. — `todo:d23bc543-c583-4dc1-a8ed-1141c92f6822`
  > Also disallow `find / …` via [`ai/settings/settings.json`](./settings/settings.json).
