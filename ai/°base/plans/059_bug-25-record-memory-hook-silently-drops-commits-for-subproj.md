# Bug 25 — `record-memory` hook silently drops commits for subproject-nested Claude sessions

## Context

In the `sticker_tag_bot` Claude Code session (`luckydonald/docker-tg-bot`, a subdirectory of the `DockerTgBot` monorepo), the assistant wrote and edited memory files through the normal auto-memory flow, but no corresponding commit ever landed in `sticker_tag_bot/ai/memory/`. The user copied that session's transcript into `ai/°base/errors/25.claude1.txt`, then turned on hook debug tracing and reproduced the same failure in a second session, captured both as `ai/°base/errors/25.claude2.txt` (transcript) and as raw hook payloads under `sticker_tag_bot/ai/output/debug/20260901-110828_704139-save-prompt.json` through `...-110902_037992-SubagentStop.json`. This plan documents the root cause found from that evidence, updates this repo's own memory index per a related request that arrived mid-session, and gets the new findings committed in this repo's `ai/°base/errors` following the existing `commit-with-lplp-style` workflow.

## Root cause

Claude Code's own auto-memory feature scopes the per-project memory directory by the **git repository root**, not by the directory Claude was actually launched from. Since `sticker_tag_bot` is a subdirectory inside the `DockerTgBot` git repo (not a repo of its own), every memory `Write`/`Edit` in that session landed under the *git-root*-encoded directory, `~/.claude/projects/-Users-user-Documents-programming-Python-DockerTgBot/memory/*.md` — confirmed by the `file_path` in both `record-memory.json` debug dumps (`20260901-110843_540969` and `20260901-110853_512295`) and by `2026-07-20-history-master-replay-guards.md`/`MEMORY.md` only existing (with today's mtime) in that directory, never under `-DockerTgBot-sticker-tag-bot` — that project's `~/.claude/projects/...` entry has no `memory/` subfolder at all.

`scripts/°base/ai/hooks/record-memory/hook.py`'s `_memory_dirs()` computes its *source* watch directory differently: `_encoded_project_dir(_subproject_root())`, where `_subproject_root()` reads `CLAUDE_PROJECT_DIR` — the literal launch directory, `sticker_tag_bot`, confirmed by the `"cwd"` field in every debug payload. That encodes to `~/.claude/projects/-Users-user-Documents-programming-Python-DockerTgBot-sticker-tag-bot/memory`, a directory that has never existed. In `main()` (`record-memory/hook.py:406-417`), the `PostToolUse` handler for `Write`/`Edit` does:

```python
src_file = Path(raw).resolve()
try:
    rel = src_file.relative_to(src_dir.resolve())
except (OSError, ValueError):
    return 0
```

Since `src_file` sits under the git-root-encoded directory and `src_dir` sits under the subproject-encoded directory, `relative_to()` always raises `ValueError`. The hook catches it and returns `0` — a silent no-op: no hardlink into `sticker_tag_bot/ai/memory/`, no `git commit`, and no error surfaced anywhere in the transcript or hook output. This reproduced identically in both sessions, and is not specific to `sticker_tag_bot` — it affects any Claude Code session launched from a subdirectory of a larger repo rather than the repo root.

Supporting evidence:

- `save-plan.json` at the same two timestamps (`110853`, `110857`) carries byte-identical payloads to the paired `record-memory.json` files — both hooks receive the same `PostToolUse` event; `save-plan`'s own Write/ExitPlanMode/Stop-only logic (per `ai/°base/AGENTS.md`) presumably no-ops on the `Edit` tool the same way and is unrelated to this bug.
- `DockerTgBot/ai/memory/2026-07-20-history-master-replay-guards.md` (the git-root-level copy last touched by commit `61e52770a`) is stale — 1063 bytes from Aug 11, versus 1658 bytes / today in the actual `~/.claude` source — confirming the new content never reached a commit.
- `SubagentStop.json`'s `last_assistant_message: "commit this"` in the second session shows a delegated agent noticing the missing commit and trying to force one manually, after the automatic hook path silently failed.

Fix direction (out of scope for this plan, noted for a follow-up): `_subproject_root()` (or `_memory_dirs()`) needs to resolve the source memory directory the same way Claude Code's own auto-memory feature apparently does — by git top-level rather than `CLAUDE_PROJECT_DIR` — whenever the launch directory is a subdirectory of a larger repo.

## What this plan actually does

1. Write up the analysis above as `ai/°base/errors/25.md`, alongside the existing `25.claude1.txt`/`25.claude2.txt` transcripts (matching the repo's existing pattern of a bare `<n>.md` write-up next to numbered raw-transcript siblings, e.g. `23.md` + `23.expected.md`).
2. Force-add and commit it, then fold it together with the two already-committed "referenced file for task added." commits (`557cf20a` for `25.claude1.txt`, `a97a50d3` for `25.claude2.txt`) into one clean, properly-described commit, per the LPLP squash convention (see `[[feedback_squash_ai_log_commits]]` and the `commit-with-lplp-style` skill) — this repo's origin is `luckydonald/base`, so that skill is already the active convention for this session per `ai/°base/AGENTS.md`'s Plan mode section.
3. Separately, per the mid-session request, update this repo's own memory index entry for `2026-07-20-history-master-replay-guards.md` — currently still `TODO: summarize this file.` in `/Users/user/.claude/projects/-Users-user-Documents-programming-Python-base/memory/MEMORY.md` — to the same one-line summary already used for the equivalent memory in the `DockerTgBot` project. This is a plain memory-file edit (not a manual git action): base's own `CLAUDE_PROJECT_DIR` **is** its git root, so the same `record-memory` hook picks it up and hardlinks/commits it into `ai/°base/memory/` correctly on its own — no mismatch here, unlike the bug above.

No code fix is included in this plan — only documenting the bug and its evidence, plus the housekeeping memory-index update.

## `ai/°base/errors/25.md` — content to write

```markdown
# Bug 25 — `record-memory` hook silently drops commits for subproject-nested Claude sessions

## Symptom

In the `sticker_tag_bot` Claude Code session (`luckydonald/docker-tg-bot`, a subdirectory of the `DockerTgBot` monorepo), the assistant wrote and edited memory files through the normal auto-memory flow, but no corresponding commit ever landed in `sticker_tag_bot/ai/memory/`. Reproduced in two separate sessions: `25.claude1.txt` (a `feedback_squash_ai_log_commits.md` memory write) and `25.claude2.txt` (a `2026-07-20-history-master-replay-guards.md` edit, captured with hook debug tracing turned on — raw payloads in that session's `ai/output/debug/20260901-110828_704139-save-prompt.json` through `...-110902_037992-SubagentStop.json`).

## Root cause

Claude Code's own auto-memory feature scopes the per-project memory directory by the **git repository root**, not by the directory Claude was actually launched from. Since `sticker_tag_bot` is a subdirectory inside the `DockerTgBot` git repo (not a repo of its own), every memory `Write`/`Edit` in that session landed under the *git-root*-encoded directory, `~/.claude/projects/-Users-user-Documents-programming-Python-DockerTgBot/memory/*.md` — confirmed by the `file_path` in both `record-memory.json` debug dumps (`20260901-110843_540969` and `20260901-110853_512295`) and by `2026-07-20-history-master-replay-guards.md`/`MEMORY.md` only existing (with today's mtime) in that directory, never under `-DockerTgBot-sticker-tag-bot` — that project's `~/.claude/projects/...` entry has no `memory/` subfolder at all.

`scripts/°base/ai/hooks/record-memory/hook.py`'s `_memory_dirs()` computes its *source* watch directory differently: `_encoded_project_dir(_subproject_root())`, where `_subproject_root()` reads `CLAUDE_PROJECT_DIR` — the literal launch directory, `sticker_tag_bot`, confirmed by the `"cwd"` field in every debug payload. That encodes to `~/.claude/projects/-Users-user-Documents-programming-Python-DockerTgBot-sticker-tag-bot/memory`, a directory that has never existed. In `main()` (`record-memory/hook.py:406-417`), the `PostToolUse` handler for `Write`/`Edit` does:

\`\`\`python
src_file = Path(raw).resolve()
try:
    rel = src_file.relative_to(src_dir.resolve())
except (OSError, ValueError):
    return 0
\`\`\`

Since `src_file` sits under the git-root-encoded directory and `src_dir` sits under the subproject-encoded directory, `relative_to()` always raises `ValueError`. The hook catches it and returns `0` — a silent no-op: no hardlink into `sticker_tag_bot/ai/memory/`, no `git commit`, and no error surfaced anywhere in the transcript or hook output. This reproduced identically in both sessions, and is not specific to `sticker_tag_bot` — it affects any Claude Code session launched from a subdirectory of a larger repo rather than the repo root.

## Evidence

- `record-memory.json` (`20260901-110843_540969`, `20260901-110853_512295`, `20260901-110857_635557`) — `tool_input.file_path` is always `/Users/user/.claude/projects/-Users-user-Documents-programming-Python-DockerTgBot/memory/...` while `"cwd"` in the same payload is `/Users/user/Documents/programming/Python/DockerTgBot/sticker_tag_bot`.
- `save-plan.json` at the same two timestamps carries byte-identical payloads to the paired `record-memory.json` files — both hooks receive the same `PostToolUse` event; `save-plan`'s own Write/ExitPlanMode/Stop-only logic is unrelated to this bug.
- `sticker_tag_bot/ai/memory/` does not exist in the `DockerTgBot` repo at all — nothing was ever hardlinked there.
- `DockerTgBot/ai/memory/2026-07-20-history-master-replay-guards.md` (the git-root-level copy, last touched by commit `61e52770a`) is stale — 1063 bytes from Aug 11, versus 1658 bytes / today in the actual `~/.claude` source — confirming the new content never reached a commit.
- `SubagentStop.json`'s `last_assistant_message: "commit this"` in the second session shows a delegated agent noticing the missing commit and trying to force one manually, after the automatic hook path silently failed.

## Fix direction (not implemented here)

`_subproject_root()` (or `_memory_dirs()`) needs to resolve the source memory directory the same way Claude Code's own auto-memory feature apparently does — by git top-level rather than `CLAUDE_PROJECT_DIR` — whenever the launch directory is a subdirectory of a larger repo.
```

## Copy & commit steps

Checklist (going through the `commit-with-lplp-style` skill rather than raw `git rebase` plumbing, since that skill already implements exactly this fold-nearby-`ai:`-auto-commits workflow and this repo's origin auto-enables it):

- [ ] Write the file above to `ai/°base/errors/25.md`.
- [ ] `git add -f "ai/°base/errors/25.md"` (force, matching how the existing `25.claude1.txt`/`25.claude2.txt` were added).
- [ ] Invoke the `commit-with-lplp-style` skill's commit flow for this change. It will:
  - Tag current `HEAD` as a backup via `scripts/tag_backup.py`.
  - Commit `25.md` as a new commit with message `[base] errors: ai: Run: Documented bug 25 — record-memory hook drops commits when the launch dir differs from git root.`
  - Interactively rebase to fold the two existing "ai: referenced file for task added." commits (`557cf20a` for `25.claude1.txt`, `a97a50d3` for `25.claude2.txt`) into that new commit, leaving one clean commit containing all three files.
  - Leave the plan-revision commit (`769733ed [base] ai: updated prompt`, this turn's saved prompt) and everything below `e3f875aa` untouched.
- [ ] Verify with `git log --oneline -5 --stat` that the result is one commit touching `25.claude1.txt`, `25.claude2.txt`, and `25.md`, with no stray "referenced file for task added." commits left behind.

## Memory-index update (separate from the git steps above)

- [ ] Edit `/Users/user/.claude/projects/-Users-user-Documents-programming-Python-base/memory/MEMORY.md`, replacing the line:
  `- [History-master replay guards](2026-07-20-history-master-replay-guards.md) — TODO: summarize this file.`
  with:
  `- [History-master replay guards](2026-07-20-history-master-replay-guards.md) — git-plumbing pitfalls in \`°base\`'s history_master.py merge-replay (conflict paths, cherry-pick, hooks, diff parsing)`
  (the same one-line summary already used for the equivalent memory entry in the `DockerTgBot` project). This runs through the normal `record-memory` hook and commits into `ai/°base/memory/MEMORY.md` on its own, since base's `CLAUDE_PROJECT_DIR` is its own git root — no path-mismatch bug applies here.

## Verification

- `git log --oneline -5 --stat` in `base` shows the squashed commit and no leftover loose "referenced file" commits.
- `git diff` (or `git show`) on the squashed commit contains exactly `ai/°base/errors/25.claude1.txt`, `25.claude2.txt`, and the new `25.md`.
- `ai/°base/memory/MEMORY.md` (base repo, not `~/.claude`) picks up the updated summary line after the memory edit, via its own commit.
