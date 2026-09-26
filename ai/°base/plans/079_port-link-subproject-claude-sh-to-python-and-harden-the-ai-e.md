# Port `link-subproject-claude.sh` to Python and harden the `ai/.env` symlink commit

**Commit style:** Skill `/commit-with-lplp-style` is active — auto-commit following it for this implementation.

**Naming:** per `ai/skills/code-style/references/py.md`, no leading-underscore
function/module names anywhere in this work — that includes the new
`link_subproject.py` module and the purge routine (named
`purge_commit_everywhere`, not `_purge_commit_everywhere`). If any other
leading-underscore function is noticed in passing while working in this
area, fix it and commit that rename separately (its own small commit, find
and update all call sites) — no need to go hunting for more beyond what's
naturally encountered.

## Context

`scripts/°base/init/link-subproject-claude.sh` (reached via the symlink chain
`scripts/link_subproject.sh` → `scripts/°base/link_subproject.sh` →
`init/link-subproject-claude.sh`) sets up a subproject folder inside this
monorepo. One of its steps, `link_env()`, symlinks `<subfolder>/ai/.env` to
the monorepo-root `ai/.env` and stages it with `git add`.

Commit `dc3dbe2` made that symlink actually get tracked by adding a
`.gitignore` negation (`!*/**/ai/.env`) so a plain `git add` wouldn't silently
no-op. That negation pattern is fragile (it's a second, easy-to-forget place
that has to agree with the script's behavior, and it already needed one fix
already). The user wants to drop the negation — `ai/.env` goes back to being
blanket-gitignored everywhere — and instead have the script force the add
(`git add -f`) for that one path, then *prove* the commit did what was
intended before trusting it, with an automatic, tested rollback (including
purging the bad commit from history) if it didn't.

Given how much more testable/readable this state machine is in Python, and
per the user's explicit choice, this is also the moment to port the whole
script (not just `link_env`) from bash to Python, matching the existing
`scripts/°base/tests/*.py` unittest style.

## Design

### Two-commit sequencing (required)

This lands as **two separate commits**, in this order — not interleaved,
not squashed:

1. **Commit 1 — clean port, no behavior change.** Translate
   `init/link-subproject-claude.sh` to `init/link_subproject.py` as a
   literal, mechanical port: same functions, same state machine, same
   `link_env()` (including its current unconditional `git add`, no force-add,
   no commit dance, no purge logic yet), same call order, same symlink
   repointing, same `.gitignore` untouched. The only naming deviation from a
   1:1 port is the no-leading-underscore rule (below) — nothing else about
   behavior changes in this commit. This commit should be reviewable purely
   as "same script, new language."
2. **Commit 2 — the actual feature work.** On top of commit 1, make every
   behavioral change described in the rest of this plan: the `.gitignore`
   negation removal, the new `link_env()` state machine (force-add + commit
   + verify + purge-on-failure), `purge_commit_everywhere`, and the new test
   module.

Do not fold these together and do not write commit 2's logic into the same
diff as commit 1 "for convenience" — the whole point is a clean, reviewable
move (per lplp style rule 8: land a pure code move/rename before changing
that code further) followed by an isolated behavior diff.

### 1. Port to Python (commit 1)

- New file `scripts/°base/init/link_subproject.py`, executable
  (`#!/usr/bin/env python3`), replacing `init/link-subproject-claude.sh`.
  Straight port of every function, preserving all documented behavior
  (idempotency, backup-with-timestamp-suffix via `git mv` when tracked,
  `.gitkeep` seeding, `copy_if_missing`, `.run/*.run.xml` fan-out,
  `AGENTS.md`/`CLAUDE.md` swap, `.claude-project.rc` seeding, slug
  generation). Same call order at the bottom as the current script
  (lines 328–340). `link_env()` is ported as-is in this commit — still a
  plain `git add`, no force-add/commit/purge — those land in commit 2.
- Delete `init/link-subproject-claude.sh`; repoint the two existing
  symlinks (`scripts/link_subproject.sh`, `scripts/°base/link_subproject.sh`)
  at `init/link_subproject.py` (symlink names don't need to match the
  target's extension — nothing invokes them by extension, only by path).
- Carry over the module docstring/header comment from the current script's
  lines 1–42 almost verbatim (it's accurate and non-obvious — explains *why*
  `.claude-project.rc` is named `.rc` and why the project-dir-name override
  is needed).

### 2. `.gitignore` (commit 2)

Remove the `!*/**/ai/.env` line (~line 781). `ai/.env` (root and every
subfolder) goes back to blanket-ignored by `**/*.env*`. Tracking the
subfolder symlink now happens purely via `git add -f` in the script, not via
a gitignore exception.

### 3. New `link_env()` state machine (commit 2)

Target = `<sub_dir>/ai/.env`. Behavior branches on what's currently there:

| Target state | Action |
|---|---|
| Doesn't exist | Create source (`touch` root `ai/.env` if missing, as today) → create the symlink → **commit dance** (below) |
| Symlink already pointing at the correct source, **and already tracked/committed** | No-op |
| Symlink already pointing at the correct source, **but not tracked** (e.g. created by hand, or a prior run's commit got reverted/removed some other way) | **Commit dance** (below) — re-running the script must still get it committed, not just leave it linked-but-untracked |
| Regular file, **or** symlink pointing elsewhere | **Graceful skip**: log a warning, leave it completely untouched, do not back it up, do not attempt any commit logic. (This replaces the old backup-and-replace behavior for `.env` specifically — unlike the other `link_*` targets, we must not silently reroute or move aside something that might be a real, user-authored `.env` or a symlink to a different secrets store.) |

"Tracked" here means `git ls-files --error-unmatch -- ai/.env` succeeds *and*
the currently-committed blob for that path matches the symlink's actual
target (not just present-in-index — some other, stale symlink content could
technically be tracked at that path). Check both before treating it as done.

**Commit dance** (only on first-time creation):

1. Assert `target` is now a symlink whose realpath matches the root
   `ai/.env`'s realpath (defends against a race/bug between creating and
   committing it).
2. `git add -f -- ai/.env` (force, since it's gitignored).
3. `git commit -- ai/.env -m "<message>"` — pathspec-scoped so it never
   scoops up whatever else is currently staged from the other `link_*` steps
   that already ran earlier in the same script invocation.
4. Re-verify: target is still a symlink, still resolves to the correct
   source. If **verification fails**, run the purge routine below to fully
   undo step 2–3 as if they'd never happened, then leave the file untracked
   (`git rm --cached -- ai/.env`) and exit non-zero — do not raise/print any
   file content anywhere in this path.

### 4. Purge routine (commit 2, only reached on verification failure)

Isolate this in its own function, `purge_commit_everywhere(repo_root, bad_sha)`,
so it's independently unit-testable:

1. **Find every ref that can reach `bad_sha`**: iterate
   `git for-each-ref refs/heads refs/tags --format='%(refname)'`, and for
   each, `git merge-base --is-ancestor <bad_sha> <ref>`.
2. **Rebuild each affected ref without `bad_sha`**:
   - If `ref` points directly at `bad_sha` (the common case — we just made
     it and nothing else has run since): CAS-move it back to `bad_sha^`
     via `git update-ref <ref> <parent> <bad_sha>` (branches) or
     `git tag -d <ref>` + recreate at `<parent>` if the tag needs to keep
     existing (tags aren't CAS'able the same way; check the tag's current
     target equals `bad_sha` immediately before deleting).
   - If `bad_sha` is an ancestor of `ref`'s tip (something got committed on
     top before we noticed the problem): replay every commit strictly
     between `bad_sha` and `ref` onto `bad_sha^` via `git cherry-pick`
     (reusing the plain-cherry-pick approach already established in
     `scripts/°base/git/°split_lib/history_master.py`'s `replay_commit()` —
     same `core.hooksPath=/dev/null` guard, same `--allow-empty --no-edit`
     fallback for now-empty picks), then CAS-move `ref` to the new tip.
3. **Precise object cleanup, never `git gc`/`git prune`/`git repack`**:
   - Collect the blob sha for `ai/.env` in `bad_sha`, and the tree shas
     `bad_sha`'s commit introduced that weren't already in `bad_sha^`'s tree
     (via `git diff --raw bad_sha^ bad_sha` for the trees on the path, plus
     the commit object itself).
   - After the ref rewrite, for each such object, check reachability from
     any current ref (`git rev-list --objects --all` — after the rewrite,
     `bad_sha` and its now-orphaned tree shouldn't appear; but the **blob**
     might still be reachable if the exact same symlink-target string is
     committed anywhere else in the repo, e.g. another subproject's
     identical `ai/.env` symlink).
   - Delete only objects that are (a) confirmed unreachable and (b) loose
     (`.git/objects/<xx>/<rest>` exists as a regular file — never touch
     anything only present in a packfile, since that would require
     repacking). Leave the blob alone if it's still reachable elsewhere —
     this is the documented, acceptable "can't fully purge" corner case.
4. **Never print file content** anywhere in this routine (no `git show`,
   no `cat-file -p` piped to stdout/logs) — only shas, ref names, and
   boolean outcomes.

Reusable pieces to lean on rather than reinvent:
- `scripts/°base/tests/_git_test_helpers.py` (`git`, `init_repo`,
  `make_commit`) for test scaffolding.
- `scripts/°base/git/°split_lib/git_ops.py` (`move_ref`, `rev_exists`,
  `is_ancestor`, `cherry_pick*`) — these already wrap exactly the plumbing
  calls this routine needs (CAS `update-ref`, ancestry checks, hook-safe
  cherry-pick); import and reuse rather than re-implementing subprocess
  calls.
- `scripts/°base/git/°split_lib/recovery.py`'s snapshot/backup-tag-before-
  mutating pattern, for taking a `refs/tags/bak/...` safety snapshot of
  every ref this routine is about to rewrite, before touching anything.

## Files

- Add: `scripts/°base/init/link_subproject.py` (full port + new `link_env`
  state machine + `purge_commit_everywhere`)
- Delete: `scripts/°base/init/link-subproject-claude.sh`
- Modify: `scripts/link_subproject.sh`, `scripts/°base/link_subproject.sh`
  (repoint symlinks)
- Modify: `.gitignore` (drop `!*/**/ai/.env`)
- Add: `scripts/°base/tests/test_link_subproject.py`

## Tests

New test module using `_git_test_helpers.init_repo`/`git`/`make_commit`,
with a small local fixture helper (mirroring `_git_split_e2e_fixtures.py`'s
`ensure_base_remote()`) that builds a throwaway `/tmp` repo by pointing the
`empty`/`base` remotes at *this actual on-disk checkout* instead of GitHub
URLs, then runs the simplified version of the
`docs/README.md#all-code-for-c-as-a-single-copy-pastable-one` block the user
confirmed: `git remote add`, `git fetch`, `git lfs install`, `git merge
--allow-unrelated-histories --no-verify empty/init` then merge/rebase onto
`base/base` — dropping the `user.name` check and `pre-commit install` (not
relevant for a throwaway test repo). This gives tests a real root with an
actual `.claude` dir etc., so `link_subproject.py` has genuine targets to
link against.

Cases to cover for `link_env`/the purge routine specifically:
1. Fresh subfolder: symlink created, committed, verified — happy path.
2. Target pre-exists as a plain regular file → graceful skip, file
   untouched, no commit attempted, nothing staged.
3. Target pre-exists as a symlink to something else → graceful skip,
   symlink untouched, no commit attempted.
4. Re-running on an already-correctly-linked *and already-committed* target
   → no-op, no second commit created.
4b. Re-running on a target that's already the correct symlink but was never
    committed (or got untracked some other way) → the commit dance still
    runs and it ends up committed.
5. Simulated post-commit verification failure (swap the file out from under
   the script between commit and re-check) → commit is purged: `ai/.env`
   ends up untracked again, the branch tip no longer contains the bad
   commit, `git log` shows no trace of it.
6. Same as (5) but with a second branch/tag also pointing at the bad commit
   (or a descendant of it) → both refs get correctly rewritten to exclude it.
7. Same as (5) but the exact same symlink-target content is also committed
   reachably elsewhere in the repo → refs are rewritten to drop the bad
   commit, but the shared blob is confirmed to still exist (`git cat-file
   -e <blob>`) since it's still reachable from the other location.
8. Assert no test in this file ever invokes `git gc`/`git prune`/`git
   repack` (grep the subprocess call list used, or monkeypatch to fail the
   test if called).
9. Capture all stdout/stderr produced by the purge routine across cases
   5–7 and assert it never contains raw blob content, only shas/paths/refs.

## Verification

- Run the new suite: `uv run --project scripts/°base python -m unittest
  scripts.°base.tests.test_link_subproject -v` (or via
  `python -m unittest discover -s scripts/°base/tests`, matching
  `scripts/°base/tests/README.md`).
- Run the full existing suite once to confirm nothing else references the
  deleted `.sh` file by path.
- Manually run `scripts/link_subproject.sh` from a scratch subfolder in a
  throwaway clone to confirm end-to-end behavior matches the old script
  (idempotent re-run, `.env` symlink committed, everything else unchanged).
