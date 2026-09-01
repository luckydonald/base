# Bug 25 — `record-memory` hook silently drops commits for subproject-nested Claude sessions

## Context

In the `sticker_tag_bot` Claude Code session (`luckydonald/docker-tg-bot`, a subdirectory of the `DockerTgBot` monorepo), the assistant wrote and edited memory files through the normal auto-memory flow, but no corresponding commit ever landed in `sticker_tag_bot/ai/memory/`. The user copied that session's transcript into `ai/°base/errors/25.claude1.txt`, then turned on hook debug tracing and reproduced the same failure in a second session, captured as `ai/°base/errors/25.claude2.txt` (transcript) and, still only in the `sticker_tag_bot` working tree (not yet in this repo), as raw hook payloads under `sticker_tag_bot/ai/output/debug/20260901-110828_704139-save-prompt.json` through `...-110902_037992-SubagentStop.json` — that `ai/output/debug/` directory is gitignored there just like it is here (`**/ai/output/debug/` in `.gitignore`), so those files only exist locally and need to be copied into this repo to survive. This plan documents the root cause found from that evidence, copies the raw debug JSON evidence into this repo, and updates this repo's own memory index per a related request that arrived mid-session.

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

Supporting evidence, all from the eight debug payloads named below:

- `record-memory.json` (`20260901-110843_540969`, `20260901-110853_512295`, `20260901-110857_635557`) — `tool_input.file_path` is always `/Users/user/.claude/projects/-Users-user-Documents-programming-Python-DockerTgBot/memory/...` while `"cwd"` in the same payload is `/Users/user/Documents/programming/Python/DockerTgBot/sticker_tag_bot`.
- `save-plan.json` at the same two timestamps (`110853`, `110857`) carries byte-identical payloads to the paired `record-memory.json` files — both hooks receive the same `PostToolUse` event; `save-plan`'s own Write/ExitPlanMode/Stop-only logic (per `ai/°base/AGENTS.md`) presumably no-ops on the `Edit` tool the same way and is unrelated to this bug.
- `sticker_tag_bot/ai/memory/` does not exist in the `DockerTgBot` repo at all — nothing was ever hardlinked there.
- `DockerTgBot/ai/memory/2026-07-20-history-master-replay-guards.md` (the git-root-level copy last touched by commit `61e52770a`) is stale — 1063 bytes from Aug 11, versus 1658 bytes / today in the actual `~/.claude` source — confirming the new content never reached a commit.
- `SubagentStop.json`'s `last_assistant_message: "commit this"` in the second session shows a delegated agent noticing the missing commit and trying to force one manually, after the automatic hook path silently failed.

Fix direction (out of scope for this plan, noted for a follow-up): `_subproject_root()` (or `_memory_dirs()`) needs to resolve the source memory directory the same way Claude Code's own auto-memory feature apparently does — by git top-level rather than `CLAUDE_PROJECT_DIR` — whenever the launch directory is a subdirectory of a larger repo.

## What this plan actually does

The analysis above lives in this plan file, which the `save-plan` hook already auto-commits into `ai/°base/plans/` on its own — no separate write-up file is needed in `ai/°base/errors/`. The `25.claude1.txt`/`25.claude2.txt` transcripts are already committed (`557cf20a`, `a97a50d3`) and stay as they are. What's still missing is the *structured* evidence — the eight raw hook debug payloads — which only exist locally in the `sticker_tag_bot` working tree (gitignored there) and need to be copied into this repo:

1. Copy the eight JSON files from `sticker_tag_bot/ai/output/debug/` into `ai/°base/errors/`, prefixed to group with the existing `25.*` files and keep the original filename (which already carries the timestamp and hook name) intact:
   - `20260901-110828_704139-save-prompt.json` → `25.claude2.debug.20260901-110828_704139-save-prompt.json`
   - `20260901-110843_540969-record-memory.json` → `25.claude2.debug.20260901-110843_540969-record-memory.json`
   - `20260901-110853_475017-save-plan.json` → `25.claude2.debug.20260901-110853_475017-save-plan.json`
   - `20260901-110853_512295-record-memory.json` → `25.claude2.debug.20260901-110853_512295-record-memory.json`
   - `20260901-110857_598746-save-plan.json` → `25.claude2.debug.20260901-110857_598746-save-plan.json`
   - `20260901-110857_635557-record-memory.json` → `25.claude2.debug.20260901-110857_635557-record-memory.json`
   - `20260901-110900_226449-save-plan.json` → `25.claude2.debug.20260901-110900_226449-save-plan.json`
   - `20260901-110902_037992-SubagentStop.json` → `25.claude2.debug.20260901-110902_037992-SubagentStop.json`
2. Force-add and commit them, then fold that commit together with the two already-committed "referenced file for task added." commits (`557cf20a` for `25.claude1.txt`, `a97a50d3` for `25.claude2.txt`) into one clean commit, per the LPLP squash convention (see `[[feedback_squash_ai_log_commits]]` and the `commit-with-lplp-style` skill) — this repo's origin is `luckydonald/base`, so that skill is already the active convention for this session per `ai/°base/AGENTS.md`'s Plan mode section.
3. Separately, per the mid-session request, update this repo's own memory index entry for `2026-07-20-history-master-replay-guards.md` — currently still `TODO: summarize this file.` in `/Users/user/.claude/projects/-Users-user-Documents-programming-Python-base/memory/MEMORY.md` — to the same one-line summary already used for the equivalent memory in the `DockerTgBot` project. This is a plain memory-file edit (not a manual git action): base's own `CLAUDE_PROJECT_DIR` **is** its git root, so the same `record-memory` hook picks it up and hardlinks/commits it into `ai/°base/memory/` correctly on its own — no path-mismatch bug applies here.

No code fix to `record-memory/hook.py` is included in this plan — only preserving the bug evidence and the housekeeping memory-index update.

## Copy & commit steps

Checklist (going through the `commit-with-lplp-style` skill rather than raw `git rebase` plumbing, since that skill already implements exactly this fold-nearby-`ai:`-auto-commits workflow and this repo's origin auto-enables it):

- [ ] Copy the eight files listed above from `/Users/user/Documents/programming/Python/DockerTgBot/sticker_tag_bot/ai/output/debug/` into `ai/°base/errors/` under this repo, renamed with the `25.claude2.debug.` prefix.
- [ ] `git add -f "ai/°base/errors/25.claude2.debug."*.json` (force-add, since `ai/output/debug/` is gitignored at the *source*, though the `ai/°base/errors/` destination itself isn't ignored).
- [ ] Invoke the `commit-with-lplp-style` skill's commit flow for this change. It will:
  - Tag current `HEAD` as a backup via `scripts/tag_backup.py`.
  - Commit the eight copied JSON files as a new commit with message `[base] errors: ai: Run: Copied bug-25 hook debug payloads (record-memory path-mismatch repro) into ai/°base/errors.`
  - Interactively rebase to fold the two existing "ai: referenced file for task added." commits (`557cf20a` for `25.claude1.txt`, `a97a50d3` for `25.claude2.txt`) into that new commit, leaving one clean commit containing all ten files.
  - Leave the plan-revision commit (`769733ed [base] ai: updated prompt`, this turn's saved prompt) and everything below `e3f875aa` untouched.
- [ ] Verify with `git log --oneline -5 --stat` that the result is one commit touching `25.claude1.txt`, `25.claude2.txt`, and the eight `25.claude2.debug.*.json` files, with no stray "referenced file for task added." commits left behind.

## Memory-index update (separate from the git steps above)

- [ ] Edit `/Users/user/.claude/projects/-Users-user-Documents-programming-Python-base/memory/MEMORY.md`, replacing the line:
  `- [History-master replay guards](2026-07-20-history-master-replay-guards.md) — TODO: summarize this file.`
  with:
  `- [History-master replay guards](2026-07-20-history-master-replay-guards.md) — git-plumbing pitfalls in \`°base\`'s history_master.py merge-replay (conflict paths, cherry-pick, hooks, diff parsing)`
  (the same one-line summary already used for the equivalent memory entry in the `DockerTgBot` project).

## Verification

- `git log --oneline -5 --stat` in `base` shows the squashed commit and no leftover loose "referenced file" commits.
- `git show` on the squashed commit contains exactly `ai/°base/errors/25.claude1.txt`, `25.claude2.txt`, and the eight `25.claude2.debug.*.json` files.
- `ai/°base/memory/MEMORY.md` (base repo, not `~/.claude`) picks up the updated summary line after the memory edit, via its own commit.
