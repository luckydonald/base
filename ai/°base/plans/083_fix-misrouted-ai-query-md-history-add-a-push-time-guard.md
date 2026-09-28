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

Existing infra: `.git/hooks/pre-push` → `scripts/°base/git/hooks/push/pre_push.sh` → `python3 scripts/°base/git/split.py check-push` → `°split_lib/cli.py:_check_push()`, which already computes, per ref update, `commits: list[CommitClassification]` (each with a `.paths` tuple) via `git_ops.commits_new_to_remote()` + `classify.classify_commit()`, then calls `push_checks.evaluate_ref_update(...)` and aggregates returned violation strings; any violations → prints them and returns exit `1`, which `pre_push.sh` propagates as the hook's exit code (rejects the push).

**Changes:**

1. In `scripts/°base/git/°split_lib/push_checks.py`, add a self-contained "is this repo `luckydonald/base` itself" check. Per this codebase's existing convention (`°split_lib` deliberately has no import edges to/from `ai/hooks`; `classify.py` already duplicates small constants rather than cross-import), duplicate the ~20-line `_is_inside_base_repo` + `_main_checkout_root` logic from `scripts/°base/ai/hooks/°commit_style_lib/__init__.py:34-73` into `push_checks.py` (or a small sibling module if that reads cleaner) rather than reaching across the tree. It needs `repo_root` (already available in `cli._check_push`) and shells out to `git remote get-url origin` / `git rev-parse --git-common-dir`.
2. Add `check_base_query_md_policy(repo_root: Path, commits: list[CommitClassification]) -> list[str]`: if the repo isn't `luckydonald/base`, return `[]`. Otherwise, for each commit where `"ai/query.md" in commit.paths`, add a violation message (e.g. `f"{commit.sha[:8]} touches ai/query.md — the base repo must log to ai/°base/query.md instead."`).
3. Wire it into `cli._check_push()`: call once per push (not per ref-update — the "is this base repo" answer doesn't vary within one push invocation) and extend `all_violations` with commits gathered across all ref updates, or call it once per ref-update's `commits` list, consistent with how `evaluate_ref_update` is currently called in the loop — simplest is adding it inside that same per-ref-update loop, passing `commits` and `root`.
4. Tests in `scripts/°base/tests/test_git_split_push_checks.py` (already uses `ai/query.md` as its example ai-tainted path in several existing tests — this new check slots in next to them): an `EndToEndCheckPushTests`-style test with `origin` set to a `luckydonald/base`-matching URL and a commit touching `ai/query.md` → push blocked with the new message; a control test with a non-matching `origin` URL and the same commit → push allowed (this check doesn't apply outside the base repo).
5. Update `ai/°base/todo.md` (~line 155-163) to document this third check alongside the existing name/content policy notes, matching `push_checks.py`'s own docstring convention of pointing back at that section.

## Verification

- Part 1: run the diff/stat checks above before touching `refs/heads/base`; after updating, `git log --oneline origin/base..HEAD` should be empty pre-push (everything force-pushed matches), and `ai/query.md` on disk should be back to the 17-line template with `ai/°base/query.md` containing the recovered content in the right place.
- Part 2: `python3 -m unittest scripts/°base/tests/test_git_split_push_checks.py -v` covering the new tests; manually exercise `pre_push.sh`/`split.py check-push` once against a synthetic commit touching `ai/query.md` to confirm the hook actually rejects it end-to-end, not just the unit-tested function.
