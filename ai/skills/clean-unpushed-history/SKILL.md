---
name: "clean-unpushed-history"
description: "Clean up all unpushed history (everything since the upstream, usually `base/base`), write a summary naming the exact tip hash, and push only after the user replies `continue`, using a sha-gated, leased force-push if the history was rewritten. Use when the user asks to clean up older/unpushed commits, tidy history before pushing, or says 'clean up, summarize, then push on continue'."
---

# Clean unpushed history, summarize, then push on `continue`

Two phases, separated by the user's explicit `continue`. Never push in phase 1.

## Phase 1: clean and summarize

1. Find the range: `git rev-parse --abbrev-ref @{u}` (normally `base/base`), then `git fetch` that remote and list `git log --oneline <upstream>..HEAD`.
   Everything in that range is fair game, not just the newest commits. Anything at or before the upstream is never touched.
2. Tag a safety net first: `./scripts/tag_backup.py`.
3. Clean the whole range with the "Cleaning up stray `ai:` auto-commits" procedure of the `commit-with-lplp-style` skill (fold `ai:` and `[TODOs]` auto-commits, keep plan revisions, fix subjects). Beyond that, also:
   - squash fixups and commits that only undo or repeat each other,
   - fix wrong or placeholder messages,
   - never include unrelated or untracked files (e.g. `scripts/.DS_Store`, scratch `aaa.py`),
   - use `git reset --keep`, never `--hard`.
4. Re-audit afterwards: auto-commits can land during the cleanup, including from the user's own messages.
5. Verify nothing was lost: `git diff <backup-tag> HEAD` must be empty (or only the intended message-independent changes you can explain).
6. Write the summary. It must contain:
   - the upstream and its current sha (`git rev-parse <upstream>`),
   - the final local tip as a **full 40-char sha**: `git rev-parse HEAD`,
   - the new `git log --oneline <upstream>..HEAD`, and what was folded or rewritten,
   - the backup tag name,
   - whether pushing needs a force (is `git merge-base --is-ancestor <upstream> HEAD` false?) and the exact command that will run on `continue`.
7. Stop and wait. Do not push.

## Phase 2: only after the user sends `continue`

1. Re-check the gate: `git rev-parse HEAD` must equal the sha named in the summary, and the working tree's commits must be unchanged.
   If it differs (new `ai:` commit, etc.), do not push. Report it, clean again, and write a new summary.
2. Fast-forward case (`<upstream>` is an ancestor of `HEAD`): plain `git push <remote> HEAD:<branch>`.
3. Rewritten case: lease on the remote sha you saw in the summary, and push that exact commit rather than `HEAD`:
   ```sh
   git push --force-with-lease=<branch>:<upstream-sha> <remote> <tip-sha>:refs/heads/<branch>
   ```
   Never use bare `--force`, and never `--force-with-lease` without the explicit expected sha.
   If the lease is rejected, someone pushed meanwhile: stop and report, do not retry with a looser flag.
4. Confirm with `git fetch <remote>` and `git rev-parse <upstream>`, which must equal `<tip-sha>`.
   Report the result plainly.
