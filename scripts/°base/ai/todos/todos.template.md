# Todos

## For Agents
If you are an agent tasked to process/fix this file:

- Fix the outstanding issues (unchecked items) below.
- At least 1 commit (/commit-with-lplp-style) per task, possibly more where it makes sense.
- You are allowed to plan for one or more items as it makes sense.


## How to sync from CalDAV

Source: `sync_todo` MCP, calendar `TODO: Today` (`calendar_id` {{calendar_id}}). Each item ends with its todo `uid`, and may optionally include a body as blockquote the next lines.

To complete one:
1. tick the box - good to squash into the code commit
2. call `mcp__sync_todo__complete_todo(calendar_id={{calendar_id}}, uid=<uid>)`.
3. Finally call `{{script}} --project {{project}}` to update this file, which may add new tasks.
   - Generally, leaving out the project parameter is fine, too, as this syncs all projects, which is what you want to do eventually anyway.
   - If you specify the project you may also occasionally add flags to reduce the length, which may be good if you got more than 20 todos completed.
     - Add `--purge-missing` if you want to remove items not tracked in the todo list. Still incompleted ones should be duplicated to the `sync_todo` MCP first.
     - Add `--purge-complete` to clean up completed tasks.

## Todos synced from CalDAV

