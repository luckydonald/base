In the repo /home/user/git/luckydonald/DockerTgBot, focused on the sync_todo/ subproject, I need to write a Python script that merges sync_todo/.env.example into sync_todo/.env. Please investigate and report back:

1. Full contents of sync_todo/.env.example (I need the exact format: comment style, blank lines, KEY=value vs KEY= empty patterns, any multi-line comments above keys).
2. Full contents of sync_todo/.env if it exists (or confirm it doesn't exist yet).
3. Full contents of sync_todo/.gitignore and the repo-root .gitignore — specifically check whether `.env` and backup-style files (e.g. `*.bak`, `.env.*.bak`) are already ignored.
4. Look for any Claude Code settings files that define "disallowed commands" or tool permission denylists — check for .claude/settings.json, .claude/settings.local.json, and any ~/.claude or global config referenced within the repo (search for "disallow" or "deny" keywords in any settings.json in the repo, e.g. under sync_todo/.claude/ or repo root .claude/). Report exact paths and current content of any "deny" or "ask" permission rules related to Bash or file patterns like ".env".
5. Check if there's an existing similar script anywhere in the repo (e.g. in _scripts/ or sync_todo/) that copies/merges .env.example to .env, or that generates secrets — report its path and approach if found.
6. Report the exact list of environment variables documented in sync_todo/CLAUDE.md's "Required environment variables" section for cross-reference.

Report all findings concisely but completely (full file contents where small, like .env.example and .gitignore).