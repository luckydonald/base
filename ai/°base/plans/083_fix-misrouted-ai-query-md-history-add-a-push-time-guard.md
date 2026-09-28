# Fix misrouted `ai/query.md` history + add a push-time guard

## Context

`ai/query.md` is the consuming/subproject query log; the base repo (`luckydonald/base`, this repo) must log to `ai/°base/query.md` instead. `resolve_log_path()` (`scripts/°base/ai/hooks/_lib.py:670`) picks between the two via `_is_inside_base_repo()` (`scripts/°base/ai/hooks/°commit_style_lib/__init__.py:56`).

Investigation found the requested commit, `99098937009ba32beeadb5b8aeced54e80dd1ea7` ("Condensed autonomous-`/loop`-tick boilerplate into a linked `query.md` entry"), is **not** the root cause — its own code (`_render_loop_tick_entry`/`_reserve_loop_tick_file`) correctly threads through whatever `log_path` it's given. The actual bug was in `_is_inside_base_repo()`: it only checked `subproject_root.name == "base"`, which is false inside any linked *worktree* (named after its branch, not `base`), so every hook call from a worktree misrouted to `ai/query.md`. This was already fixed forward in `d7d40ef9a` (2026-09-27, "Fixed `_is_inside_base_repo` misdetecting every linked `git worktree`..."), following the exact same worktree-proofing pattern as an earlier occurrence of this bug class (`73a213a9a`, 2026-08-12, "Moved wrongly root `ai` folder plan/query to `./ai/°base/`").

Between the bug's introduction and its fix (plus two stragglers from a worktree branch that hadn't yet picked up the fix), **7 commits** wrote content into `ai/query.md` that belongs in `ai/°base/query.md`:

| commit | date | lines added to `ai/query.md` |
|---|---|---|
| `990989370` | 09-26 19:03 | 92 |
| `927e13661` | 09-26 | 47 |
| `026495715` | 09-26 | 28 |
| `3d06a5898` | 09-26 | 9 |
| `98f9a7a27` | 09-26 | 6 |
| `f4f2d7196` | 09-28 | 16 |
| `7a7fb3ad5` | 09-28 | 26 |

All 224 lines are pure additions (`git show --numstat` confirms `0` deletions on every one) — the hook only ever appends. `ai/query.md` was untouched between the prior cleanup (`73a213a9a`) and `990989370`, so **every** line currently in `ai/query.md` beyond its 17-line template header is misplaced; nothing legitimate needs to stay.

Two of the seven commits (`f4f2d7196`, `7a7fb3ad5`) *also* legitimately touched `ai/°base/query.md` in the same commit (concurrent sessions/worktrees whose auto-commits got batched together) — also pure additions there.

The user confirmed (via `AskUserQuestion`):
- Fix **all** misrouted content, not just `990989370`'s.
- Rewrite the **historical commits themselves** (not a forward-fix commit), i.e. these 7 commits (and everything after them, since they're mid-branch) get new trees/hashes and the change is **force-pushed** to `origin/base`. All 7 bad commits are already on `origin/base`, so this is a rewrite of shared history — the user explicitly opted into this over the lower-risk forward-fix alternative.

Second part of the request: since worktree checkouts can still run stale (pre-fix) hook code and reintroduce this exact mistake, add a push-time guard (defense in depth) that rejects any push to `origin` when a commit being pushed touches `ai/query.md` **and** the repo being pushed is `luckydonald/base` itself.

Investigating where to wire this in surfaced two more findings, both confirmed with the user:
- The tracked `scripts/°base/git/hooks/push/pre_push.sh` → `split.py check-push` → `push_checks.py` chain (existing branch name/content policy) is **not currently active** in this checkout — `.git/hooks/pre-push` here is an unrelated git-lfs-only script with no marker from `scripts/°base/git/hooks/install`, so that installer was never (re-)run locally. It's real, tracked code, just currently dead.
- pre-commit's `pre-push` stage (used for every other local check here — commit-msg, settings-sync, yarn-4, all via `.pre-commit-config.yaml`) has a materially different execution model than `push_checks.py` assumes: it drains stdin itself and exposes only a single computed `PRE_COMMIT_FROM_REF`/`PRE_COMMIT_TO_REF` range (picking the *first* ref-update line), not the full multi-ref-update/branch-name list `push_checks.py`'s branch-format policy needs. Migrating that whole module onto pre-commit's model would mean redesigning it around a single-range view and losing multi-branch-push handling — out of scope here.

Decision: keep the new `ai/query.md` guard small and put it on pre-commit's `pre-push` stage (consistent with how every other local hook here runs), and separately restore the existing custom installer so `push_checks.py`'s branch policy is active again — the two are made to coexist via pre-commit's legacy-hook chaining (see below), not left to clobber each other.

## Part 1 — Rewrite the 7 commits (and everything after them)

**Approach: direct tree reconstruction via git plumbing, not `git rebase`/patch application.** A normal interactive rebase would re-apply each commit's *patch*, and since content shifts, patches for commits that touch either query file later in the range would very likely conflict against each other. Instead, walk the commit range in order and build each new commit's tree directly from the original tree with just the two query-file blobs replaced — no patch application, so no conflicts are possible.

**Range:** `88d277140..HEAD` (i.e. `990989370`'s parent through the current tip — re-resolve `HEAD` at execution time, don't hardcode, since more commits may have landed since this plan was written).

**Algorithm** (implement as a one-off Python script, e.g. under the scratchpad — not meant to be a committed repo tool):

1. `git tag bak/<current-HEAD-short>` first (existing `scripts/tag_backup.py` convention), so the pre-rewrite tip stays reachable.
2. `shas = git rev-list --reverse 88d277140..HEAD` (oldest → newest).
3. Maintain a running string `base_query_content`, seeded from `git show 88d277140:"ai/°base/query.md"`.
4. For each `sha` in `shas`, in order:
   - Read the *original* per-file diffs for this commit against its *original* first parent, for both `ai/query.md` and `ai/°base/query.md` (`git diff <parent> <sha> -- <path>`). Both are append-only by construction (assert this — abort loudly if a `-` line/deletion ever appears in either, since that would invalidate the pure-append assumption).
   - If the commit added lines to `ai/°base/query.md` originally, append that added text to `base_query_content` first (it was already correctly placed).
   - If the commit added lines to `ai/query.md` originally (the misplaced case), append that added text to `base_query_content` next.
   - If neither file changed in this commit, `base_query_content` is unchanged.
   - Build the new tree: start from the *original* commit's tree (`git rev-parse <sha>^{tree}` — this already has every other file correct), then overwrite just two blobs:
     - `ai/query.md` → always the fixed 17-line template (`git show 73a213a9a:ai/query.md`, i.e. never changes again in this range).
     - `ai/°base/query.md` → current `base_query_content`.
     Do this via `git hash-object -w --stdin` for each new blob, then `git read-tree <orig-tree>` into a scratch index, `git update-index --cacheinfo 100644,<new-blob-sha>,<path>` for each of the two paths, `git write-tree`.
   - `git commit-tree <new-tree> -p <new-parent-sha>` with `GIT_AUTHOR_*`/`GIT_COMMITTER_*` env copied from the original commit (`git log -1 --format='%an|%ae|%ad'` etc., preserving original dates) and the original commit message verbatim (`git log -1 --format=%B <sha>`) — nothing about authorship, message, or any other file changes.
   - Track `new_parent_sha := <output of commit-tree>` for the next iteration.
5. After the loop, `git update-ref refs/heads/base <final-new-sha>` (only after verifying — see below).

**Verification before updating the branch ref:**
- `git diff <old-HEAD> <new-tip>` must show **only** `ai/query.md` and `ai/°base/query.md` changes across the whole range (i.e. diffing old tip against new tip directly — not per-commit — should net out to: `ai/query.md` reset to template, `ai/°base/query.md` containing the union of both, everything else byte-identical). Confirm via `git diff --stat <old-HEAD> <new-tip> -- . ':!ai/query.md' ':!ai/°base/query.md'` being empty.
- Spot-check that `base_query_content`'s final form is what a human would expect reading it top to bottom (no interleaving mistakes) — dump it and skim, especially around the two dual-touching commits.
- `python3 -m unittest discover -s "scripts/°base/tests"` should still pass (tree rewrite doesn't touch code, but cheap to confirm nothing else regressed).

**Then, only with explicit user go-ahead at execution time** (this is a force-push of shared history — confirm again immediately before doing it, even though the user already chose this option in planning):
- `git push --force-with-lease origin base`.

## Part 2 — Push-time guard against `ai/query.md` on `luckydonald/base`

### 2a. New pre-commit-managed `pre-push` check

Add a small standalone script, e.g. `scripts/°base/git/hooks/push/check_base_query_md.py`:
- Duplicate the small `_is_inside_base_repo`/`_main_checkout_root` logic (`scripts/°base/ai/hooks/°commit_style_lib/__init__.py:34-73`) rather than importing across the `ai/hooks` ⟷ `git` tree boundary — matches this codebase's existing convention of duplicating tiny self-contained helpers instead of adding cross-tree import edges (e.g. `classify.py`'s comment about duplicating constants from `get-base.py`).
- If not the base repo (per that check against the current working directory), exit `0` immediately (no-op).
- Otherwise print an error naming the offending path and `exit(1)`.

It doesn't need to re-detect *which* commit touched `ai/query.md` itself: wire it into `.pre-commit-config.yaml` with `stages: [pre-push]` and `files: ^ai/query\.md$` — pre-commit itself computes `PRE_COMMIT_FROM_REF`/`PRE_COMMIT_TO_REF` from the push's ref-update line and only invokes file-filtered hooks when a matching path actually changed in that range (confirmed via `pre_commit/commands/run.py:262-263`'s `git.get_changed_files(from_ref, to_ref)` and the `environ['PRE_COMMIT_FROM_REF'/'_TO_REF'/'_REMOTE_NAME'/'_REMOTE_URL']` assignments around `run.py:386-405`). So by the time the script runs at all, `ai/query.md` is already known to be in the pushed diff — the script only has to answer "is this the base repo," which keeps it compatible with pre-commit's single-range model (unlike `push_checks.py`'s multi-branch policy).

```yaml
- id: base-query-md-guard
  name: Block ai/query.md pushes from the base repo
  entry: scripts/°base/git/hooks/tool_path.sh python3 scripts/°base/git/hooks/push/check_base_query_md.py
  language: system
  stages: [pre-push]
  files: ^ai/query\.md$
  pass_filenames: false
```

Add a unit test (new `scripts/°base/tests/test_check_base_query_md.py` or alongside an existing push-hook test file) covering: base-repo origin URL → nonzero exit; non-base origin URL → zero exit. Follow the subprocess-invocation test pattern already used for the other `git/hooks/commit/*.py` scripts if one exists (check `scripts/°base/tests/` for e.g. `test_reject_co_authored_by.py` and mirror its structure).

### 2b. Restore the existing (currently-dead) branch-policy hook, without the two installers clobbering each other

`.git/hooks/pre-push` in this checkout is currently an unrelated git-lfs-only script (no `scripts/°base/git/hooks/install` marker), so `split.py check-push` → `push_checks.py`'s branch name/content policy isn't running at all right now. Fix by:

1. Run the existing installer (`python3 -m scripts.°base.git.hooks.install` or however it's normally invoked — check `install/__main__.py`/README for the exact entry point) so `.git/hooks/pre-push` becomes the tracked trampoline calling `scripts/°base/git/hooks/push/pre_push.sh` (which runs git-lfs, then `split.py check-push`).
2. **Then** run `pre-commit install --hook-type pre-push` (in addition to whatever hook types are already installed — check current install invocations, likely in a setup script or README, for the existing `pre-commit install --hook-type commit-msg` equivalent to mirror). Because a non-pre-commit-managed `pre-push` hook now exists (step 1's trampoline), pre-commit's installer will back it up as `.git/hooks/pre-push.legacy` and its own generated `pre-push` script will chain-call that legacy script (confirmed via `pre_commit/commands/hook_impl.py`'s `_run_legacy()`, which execs `<hook_dir>/pre-push.legacy` with the original stdin before running pre-commit's own configured hooks). Net result: one push triggers git-lfs → `split.py check-push` (via the legacy chain) → pre-commit's own hooks including the new `base-query-md-guard`, in that order, with no installer overwriting the other.
3. Verify ordering by pushing (or dry-running) against a throwaway branch: confirm both the legacy branch-policy output and the new query.md guard's behavior are visible.

Note in the commit message / a short doc comment near the installer why this two-step order matters, so a future re-install doesn't silently drop one half again.

## Verification

- Part 1: run the diff/stat checks above before touching `refs/heads/base`; after updating, `git log --oneline origin/base..HEAD` should be empty pre-push (everything force-pushed matches), and `ai/query.md` on disk should be back to the 17-line template with `ai/°base/query.md` containing the recovered content in the right place.
- Part 2: `python3 -m unittest` the new test module; then do a real end-to-end check — reinstall both hooks per 2b's ordering, attempt (in a scratch/throwaway branch or repo clone) to push a commit touching `ai/query.md`, confirm it's rejected with the new message, and confirm a normal push still runs git-lfs + the existing branch-policy checks (e.g. push an `unclean`-format branch to `origin` and confirm it's still blocked by the pre-existing name policy).
