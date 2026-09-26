Repo: /home/user/git/luckydonald/base/.claude/worktrees/fix-plan-decision

I'm designing a change to this repo's Claude/Codex/Copilot hook scripts under `scripts/°base/ai/hooks/`. Context: `scripts/°base/ai/hooks/save-plan/hook.py` has a function `record_claude_plan_rejections(payload)` that scans `payload["transcript_path"]` via `_lib.find_tool_rejections()` for denied `ExitPlanMode` tool calls not yet recorded (tracked via a `tool_use_id` set in a state file `save-plan-rejections-state.json` in the OS tempdir), and commits a `query.md` entry for each one found. Currently this is only called from `scripts/°base/ai/hooks/save-prompt/hook.py`'s `UserPromptSubmit` handler.

I need to change this so the same "scan for and flush any pending unrecorded plan rejections" check runs at the START of every hook that makes its own git commit — not just save-prompt — so a denial gets committed before that hook's own commit, preserving correct chronological commit ordering. This means the transcript-scanning function will now run on nearly every hook invocation across the session, so I need to understand what's expensive and what patterns already exist for efficient/incremental scanning, to avoid re-parsing the whole transcript file on every single tool call.

Please investigate and report back (concise, structured):

1. **`scripts/°base/ai/hooks/_lib.py`**: full implementation of `load_transcript_tool_events()` and `find_tool_rejections()` — how do they read/parse the transcript file (`transcript_path`, a `.jsonl` file)? Do they read the whole file every call? Is there any existing caching, memoization, offset-tracking, or incremental-read pattern anywhere in `_lib.py` (e.g. for `record-memory`, `save-decision`'s pending-decision sweep, or anywhere else)? Quote relevant code.

2. **List every hook.py under `scripts/°base/ai/hooks/*/hook.py`** that makes a git commit (calls `append_and_commit`, or its own `subprocess.run(["git", "commit", ...])`, or similar). For each, note: what event(s) it fires on (PreToolUse/PostToolUse/UserPromptSubmit/Stop/etc.), and roughly how often it's invoked per session (e.g. save-decision only fires on AskUserQuestion, but record-memory or save-command-decision might fire on nearly every tool call — check `is_cross_tool_duplicate` and any per-hook frequency notes in docstrings).

3. **`is_cross_tool_duplicate`** in `_lib.py`: what does it do and how is it used — is this itself an existing "run this check once per something" optimization pattern I could reuse/model?

4. Any existing state-file patterns keyed by `tool_use_id` or `session_id` that track "last processed position" in a transcript (search for anything like a byte offset, line count, or last-seen id stored alongside a mtime or file size) — I want to know if there's already a precedent for incremental transcript scanning I should follow, or if this would be new.

5. Roughly how large real transcript `.jsonl` files can get in this repo's actual sessions (check `ai/°base/output/debug/*.json` `transcript_path` values if helpful, or just note if you have no way to check actual file sizes).

Report under 500 words, with file:line references. This is pure research — do not write or edit any files.