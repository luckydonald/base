---
name: "loop-todo-codex"
description: "Work on exactly ONE open todo like `todo-loop`, but let Codex implement it: you do intel, plan, review, commit, close and rebase, a Codex agent writes the code, tests and docs of the accepted plan. Use whenever the user asks for `/loop-todo-codex`, to do the next todo with Codex, to run the todo loop with Codex, or says 'have codex implement it' during a todo loop."
---

# Todo loop with Codex (one todo per run)

Load `/todo-loop` and follow it, with the changes below.
Load `/paseo` to run Codex.
Everything not mentioned here, the rules included, stays as in `/todo-loop`.

If the user asks for Codex in the middle of a running todo loop, continue that run from the current step instead of starting over.

## Implement: Codex does it

This replaces the "Implement" step.

### Start the agent

1. Call `list_profiles` and take the Codex profile whose notes fit implementing a written plan.
   Copy its settings into `create_agent` as `/paseo` describes.
   Without a fitting profile, pick a Codex model with the provider tools and tell the user.
2. Create the agent in the current workspace with `notifyOnFinish`.
   Follow the profile's notes on how to hand over the plan, e.g. a prompt starting with `/goal implement ai/plans/<NNN>_<slug>.md`.
3. Put into the prompt, after that first line:
   - The repository root and branch, and to follow the `CLAUDE.md` and the code-style guides.
   - Its part: code, tests and docs of the plan, plus the plan's verification (not what only works after a deploy).
   - No commit, stash, reset, rebase or push, it leaves the changes in the working tree.
     Say that this overrides the "Commit style" line of the plan.
   - No edits of the todo file and no changes to todos on CalDAV.
   - Unrelated untracked files stay as they are, and no scripts which rewrite the whole repo (e.g. a fixing `lint`).
   - No reading of `.env` files.
   - The traps of this project, e.g. which database holds real data and how to get a throwaway one instead.
   - Your intel: the root cause and how you reproduced it.
   - The report you want: changed files, each verification command with its result, whether failures also happen without the change,
     skipped parts and deviations from the plan.

### Wait for it

- Tell the user which agent and profile runs, then end the turn.
- A "finished" notification can arrive while Codex still works.
  Check the agent status and the working tree; if it is still running, run `paseo wait <agent id> --timeout 3600` as a background Bash command.
- If it asks to approve its own plan, compare that with the accepted plan before you allow it.
  Ask the user about differences which change the scope.

If Paseo is not available, use `/codex-dispatch`, which needs its Codex MCP server.
If neither works, tell the user; do not implement it yourself without asking.

## Review

New step, between "Implement" and "Commit".

- Read the whole diff against the plan, tests and docs included, and look for docs the change made outdated.
- Check why something is there before removing it, what looks like dead code might be needed by the tests.
- Fix small things yourself, send bigger ones back with `send_agent_prompt`.

## Commit, close and rebase

As in `/todo-loop`, and all of it is yours, not Codex's.

- Run the full test suite and lint/build yourself, a green report of Codex does not replace that.
- The commit message names neither Codex nor Claude (`/commit-with-lplp-style`, rule 10).

## Stop

As in `/todo-loop`.
Add what you changed on top of Codex's work, and that the idle agent is still there to inspect or archive.
