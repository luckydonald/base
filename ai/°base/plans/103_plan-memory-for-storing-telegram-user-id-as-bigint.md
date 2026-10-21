# Plan: memory for storing Telegram `user_id` as BIGINT

**Commit style:** Skill `/commit-with-lplp-style` is active — auto-commit following it for this implementation.
**Code style:** Skill `/code-style` is loaded (py, md); the markdown here follows `references/md.md`.

## Context

Todo `2d6a17a2-5d9a-44d2-93a3-245ae8215388` (`ai/todo.md`, calendar 7): add a memory saying that a Telegram `user_id` must be stored in the db as `BIGINT` (or a fixed-size integer wide enough), and that the memory body references the specific `ai/references/` markdown file.
Telegram ids exceed 32 bits, so a plain `INTEGER` column overflows.

Intel: `ai/references/` holds no Telegram doc yet (grep for `bigint`/`user_id` finds nothing relevant), so the file to reference has to be downloaded first.
Memories for this repo live in `ai/memory/` with an index line in `ai/memory/MEMORY.md` (format as in `ai/memory/repo_commit_hooks.md`).

## Steps

1. Download the Telegram Bot API page with `scripts/download_ref.py --no-ide --no-git https://core.telegram.org/bots/api` (skill `download-ref`), so the file lands in this task's commit.
   Check that the `User` / `id` section ("up to 52 significant bits ... a signed 64-bit integer or double-precision float type are safe for storing this identifier") is in the written file, and note the exact `wrote:` path.
   If the page is huge or the script fails, report the reason and fall back to a narrower page instead of retrying blindly.
2. Write `ai/memory/project_telegram_user_id_bigint.md` with the usual frontmatter (`name`, `description`, `metadata.type: project`), stating the rule (Telegram `user_id` / chat ids: `BIGINT` / signed 64-bit, never 32-bit `INTEGER`; in SQLAlchemy `BigInteger`, in alembic `sa.BigInteger()`), a **Why:** and a **How to apply:** line, and the reference to `@ai/references/https/core.telegram.org/bots/api.md`.
3. Add one index line to `ai/memory/MEMORY.md`.
4. Complete the todo: tick `- [x]` with `_(done)_` in `ai/todo.md`, `complete_todo(calendar_id=7, uid=2d6a17a2-...)`, then re-read the file.
   The skill's `uv run scripts/sync_todos.py --project` step is skipped, since this repo's todos are synced by the user and no `sync_todos.py` was found here.

## Tests

Docs and memory only, no code. Verification: the referenced path exists, the frontmatter parses like the neighbouring memories, and the `record-memory` hook / pre-commit hooks pass on commit.

## Commit

One work commit via `ai/git/pending-commit.md`: `[base] ai/memory: ai: Run: Added a memory that Telegram user ids need BIGINT.`
Then `./scripts/tag_backup.py`, fold the `ai:` auto-commits (and the plan commit) per `/commit-with-lplp-style`, and verify with `git diff <bak-tag> HEAD`.
No trailers (the `Claude-Session:` line from the system reminder is rejected by the repo hook).
