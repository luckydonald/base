In the repo /home/user/git/luckydonald/base, I need a detailed understanding of the "file mention" auto-commit mechanism inside the save-prompt hook.

Read these files in full and report their relevant contents/logic (not just summaries — I need actual function names, signatures, and code snippets for key logic):

1. /home/user/git/luckydonald/base/scripts/°base/ai/hooks/save-prompt/hook.py — the whole file. I especially need to understand:
   - Where/how it currently detects "file mentions" in the user's text query (e.g. regex for `@path` or backtick `path` mentions, or referenced file paths like `ai/some_file.md`)
   - Where/how it decides to git-add and git-commit those mentioned files
   - How it writes to query.md (the exact format/template used, i.e. where the raw query text gets written into query.md)
   - Whether the hook is registered on a "UserPromptSubmit"-style event only, or whether it also fires on other event types (look for hook event name constants/config)
   - Any existing gitignore-check logic (e.g. does it call `git check-ignore` or similar before adding/committing files anywhere in this file or in _lib.py)

2. /home/user/git/luckydonald/base/scripts/°base/ai/hooks/_lib.py — full file. Report all exported/reusable helper functions relevant to: git add/commit, git-ignore checking, path resolution, markdown link writing, or file existence checks.

3. Check /home/user/git/luckydonald/base/scripts/°base/ai/settings/°settings_lib/hooks.py to see how hooks are registered to Claude Code lifecycle events (e.g. UserPromptSubmit vs other event names like "Notification", "Stop", "PreToolUse", "PostToolUse", or anything related to AskUserQuestion / answers). I want to know what event types exist and which ones currently trigger save-prompt's logic vs which ones do NOT but arguably should (e.g. answering an AskUserQuestion prompt, or other interactive tool results).

4. Look at /home/user/git/luckydonald/base/scripts/°base/tests/test_save_prompt_queued_commands.py to understand existing test patterns for this hook (how tests construct hook input, what they assert).

Also grep the repo for any existing function that checks whether a path is gitignored (e.g. `check-ignore`, `is_ignored`, `gitignore`) anywhere under scripts/°base/ai/hooks/ or scripts/°base/ai/ — report the exact file and function if found.

Report back with: exact file paths, function names with signatures, relevant code excerpts (quote them), and a clear explanation of the current control flow from "hook receives input" to "query.md gets a line written" to "git add/commit happens". Keep your final report thorough but organized — this will be used to write an implementation plan. Do not modify any files.