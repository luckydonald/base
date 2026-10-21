# Memory: fix preexisting test and typing errors as a separate commit

**Commit style:** Skill `/commit-with-lplp-style` is active — auto-commit following it for this implementation.

Todo `8ae825eb-3ef2-4d84-8180-a937d7e2bb3c` (calendar 7, `ai/todos.md`, base repo).

## Context

When a task runs the unittests or a type check and stumbles over errors that were already there before our change, those get fixed too.
They go into their own commit, automatically, so the work commit stays focused on the task.
There is no need to search for such errors on purpose, only the ones met along the way count.

## Findings

- The base repo's own memory lives in `ai/°base/memory/` (tracked, hardlinked to `~/.claude/projects/-Users-user-Documents-programming-Python-base/memory/` by the `record-memory` hook).
  `ai/memory/` is the shared one that other projects inherit, so it is the wrong place for a base-workflow rule.
- Existing `feedback_*.md` files there (e.g. `feedback_lplp_never_drop_ai_autocommits.md`) give the format: frontmatter plus `Why:` and `How to apply:`.
- `ai/°base/memory/MEMORY.md` is the index, one line per memory.
- No existing memory covers preexisting errors, so no file to update instead.

## Changes

1. New `ai/°base/memory/feedback_fix_preexisting_errors_separate_commit.md`
   - Frontmatter: `name: feedback-fix-preexisting-errors-separate-commit`, one-line description, `metadata.type: feedback`.
   - Body: preexisting unittest or typing errors met during a task get fixed automatically, each group as its own commit apart from the task's work commit, without asking and without hunting for them.
   - **Why:** keeps the work commit reviewable, and leaves the suite green for the next run.
   - **How to apply:** commit the unrelated fix first or separately (lplp style, own `ai: Run:` message, own scope), never fold it into the task commit, never search the codebase for more of them.
   - Link `[[feedback-lplp-never-drop-ai-autocommits]]` for the commit workflow.
2. `ai/°base/memory/MEMORY.md`: add one index line pointing at the new file.

No code changes, so no tests; the only check is that the memory hook syncs the file and the index line resolves.

## Verification

- `git status` shows only the new memory file and the `MEMORY.md` line.
- The hardlink exists in `~/.claude/projects/-Users-user-Documents-programming-Python-base/memory/` after the hook ran.
- Commit scope `[base] memory:`, see `git log --oneline -5 -- ai/°base/memory`.
