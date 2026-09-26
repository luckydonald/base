This confirms: no `filter-branch`/`filter-repo`/BFG anywhere in the repo (confirmed independently now and in a prior agent run at `ai/°base/output/agents/008.a80951b12e37c8497/result.md`). Here is the full picture.

## 1. History-rewriting tooling and patterns

No `git filter-branch`, `git-filter-repo`, or BFG usage anywhere in the repo (grep returns zero hits, corroborated by a prior agent investigation at `/home/user/git/luckydonald/base/ai/°base/output/agents/008.a80951b12e37c8497/result.md`).

What does exist, all built on plain plumbing (`cherry-pick`, `update-ref`, `commit-tree`, `rev-list`, `cat-file`), never `git gc`:

- **`/home/user/git/luckydonald/base/scripts/°base/git/°split_lib/history_master.py`** — the main "rewrite/replay history onto a new branch tip" engine (part of the `git split` tooling). Key mechanics:
  - `replay_commit()` (line 417): cherry-picks a commit onto a scratch branch (`_base_split_scratch`, `refs/heads/_base_split_scratch`), falling back to `git commit --allow-empty --no-edit` when a pick becomes empty, and to conflict auto-resolvers (`_resolve_documentation_conflict`, `_resolve_already_replayed_conflict`) for known-safe conflict classes.
  - `recreate_base_merge()` (line 456) / `_fold_base()` (line 581): recreate merge commits with per-path blob reuse from the original merge, never a wholesale tree replace.
  - Ref moves go through `git_ops.move_ref()` → `git update-ref <ref> <new_sha> <old_sha>` (compare-and-swap), not a bare force-update, and always guarded by `_refuse_if_checked_out_dirty()` first.
  - Internal replay commits force `-c core.hooksPath=/dev/null` (`_commit()`, `_finish_merge_commit()`, and `git_ops.cherry_pick*`) specifically so repo pre-commit/commit-msg hooks don't interfere with synthetic history-rewrite commits.
  - Crash-safe resumable state lives in `.git/BASE_SPLIT_HISTORY_MASTER_STATE` (`_read_state`/`_write_state`/`_clear_state`), with `--continue`/`--abort` entry points (`_do_continue`, `_do_abort`).
  - Relevant memory file `2026-07-20-history-master-replay-guards.md` (full content, quoted below) documents hard-won gotchas specific to this replay logic.

- **`/home/user/git/luckydonald/base/scripts/°base/git/°split_lib/git_ops.py`** — shared low-level plumbing wrappers: `rev_parse`, `rev_list_reverse`/`rev_list_first_parent_reverse`, `is_ancestor`, `merge_base`, `move_ref` (uses `update-ref` with old-sha compare-and-swap, line 206), `create_branch`/`create_refs`, `tree_for_commit`, `commit_tree`, `cherry_pick`/`cherry_pick_continue`/`cherry_pick_abort`, `show_path_at`, `rev_exists` (`git cat-file -e <sha>^{commit}`, line 26-28).

- **`/home/user/git/luckydonald/base/scripts/°base/git/°split_lib/recovery.py`** — a crash-safe recovery-log pattern worth reusing for a "remove commit from all branches/tags" feature:
  - `resolve_watched_refs()` enumerates every ref an invocation could plausibly move.
  - `snapshot()` records `{ref: sha}` before mutation.
  - `backup_split_refs()` tags existing tips under `refs/tags/bak/split/<branch>/<timestamp>/<label>` before any rewrite (via `git_ops.create_refs`), so a rewrite can always be undone.
  - `format_recovery_entry()` builds ready-to-run undo commands (`git update-ref -d '<ref>' || true` for refs that didn't exist before, else `git update-ref '<ref>' '<old_sha>'`) and appends them to `.rebase-recovery.tmp` in the repo root before anything is touched — this is the repo's actual, tested pattern for "always leave an undo trail."

- **`/home/user/git/luckydonald/base/scripts/tag_backup.py`** — standalone safety-net script: tags the current `HEAD` as `bak/<hash>` before risky operations (used by the `commit-with-lplp-style` skill). Also has a `--remove-old-tags`/`--rm` flag (see `ai/°base/query.md:4770` and `ai/°base/plans/076_fix-stale-optional-source-repo-commit-tag-reuse.md`) that removes only `bak/*`-prefixed tags of *ancestor* commits already reachable via the new tag — i.e., existing logic for "delete tags whose target is now subsumed by a descendant," which is the inverse of what your feature needs but structurally close (walks tag targets, checks ancestry, deletes via `git tag -d`). Its test suite lives at `/home/user/git/luckydonald/base/scripts/°base/tests/test_tag_backup.py`.

- **`/home/user/git/luckydonald/base/scripts/°base/git/rebase_strip_claude_authorship.py`** — the other rebase/history-adjacent script in the repo. Uses plain `git rebase --exec` (not filter-branch/filter-repo), amending each replayed commit's author/committer/trailers. Its docstring/comments in `history_master.py` (lines 3-9) explicitly explain *why* history-master deliberately avoids `git rebase --exec` in favor of a plain Python loop: a `--exec`-driven rebase already hit two real failure classes (documented in `ai/°base/errors/16.txt`, `17.txt`) — a stale self-relocated script path, and an unhandled manual-resolution conflict.

No existing code does "delete one committed blob's content from history across all branches/tags while leaving byte-identical content elsewhere in the repo intact" (a blob-content-scoped rewrite) — this would be new work, though `history_master.py`'s scratch-branch-and-cherry-pick approach (rewrite forward via a fresh chain of commits, then CAS-swap every ref that pointed at the old chain, using recorded tag/branch snapshots to update descendants) is the closest structural template, and `recovery.py`'s snapshot/backup/undo-command pattern is the closest safety-net template.

## 2. Memory file `2026-07-20-history-master-replay-guards.md`

Full contents of `/home/user/.confuig/claude/accounts/private/projects/-home-user-git-luckydonald-base/memory/2026-07-20-history-master-replay-guards.md`:

```
# History-master replay guards

- `recreate_base_merge()` can encounter Git-generated conflict paths of the form `path~<40-hex-oid>` that are absent from the original merge tree. Never blindly run `git rm` on any missing historical path; require the synthetic suffix and evidence that the normal counterpart exists on the target side. Raise `HistoryMasterError` for unrelated missing paths.
- When a cherry-pick becomes empty after conflict resolution, use `git commit --allow-empty --no-edit`, not `git cherry-pick --skip`, so the replay keeps the original commit message and `X-*` history trailers.
- Internal replay commits and cherry-pick continuation may need `core.hooksPath=/dev/null` because target repositories can have hooks that assume project-specific configuration; otherwise hook failures obscure the actual Git operation.
- After scratch-branch conflict resolution, reset the scratch checkout hard to its committed tip before restoring the caller's branch. Otherwise an unstaged conflict artifact can make a successful replay appear to fail on dirty-worktree restoration.
- Parse `git diff --name-only --diff-filter=U -z` as NUL-delimited output; quoted line-oriented parsing breaks on paths containing spaces or special characters.
```

(Note: the harness flagged this memory as 45 days old — point-in-time observation, verify against current `history_master.py` before relying on line numbers, though the content above was cross-checked against the current file and still matches, e.g. lines 430, 192/198.)

## 3. `history_master.py` — see section 1 above for the full read-through; no logic in this file removes/deletes commits or blobs — everything it does is additive/replaying (build new commits, then CAS-move the branch ref). The closest things to "restoring branches" are `_do_abort()`/`_restore_checkout()`, which restore a checkout/branch pointer to its pre-run state on failure, not a permanent-deletion feature.

## 4. Throwaway `/tmp`-style test repos with `git init`

- **`/home/user/git/luckydonald/base/scripts/°base/tests/_git_test_helpers.py`**: canonical shared helper. `init_repo(cwd, *, branch="master")` runs `git init -b <branch>`, then sets `user.email`/`user.name` to `test@example.com`/`Test`. `make_commit(cwd, filename, message, content=None)` writes a file, `git add`, `git commit -m`. `git(args, cwd)` is a thin `subprocess.run(["git", *args], ..., check=True)` wrapper. This pair (`git`, `init_repo`, `make_commit`) is imported and reused across the e2e fixtures, e.g. in `_git_split_e2e_fixtures.py` (`from _git_test_helpers import git, init_repo, make_commit`).
- **`/home/user/git/luckydonald/base/scripts/°base/tests/_git_split_e2e_fixtures.py`**: builds fixture repos (e.g. `make_empty_init_remote()`, `_init_bare()`) using the same `git init` + `git config user.*` pattern, plus `ensure_base_remote()` to point a fixture repo's `base` remote back at this actual on-disk repo (never GitHub) for hermetic tests.
- Actual test-repo locations are wherever `tmp_path`/`tmp_root` fixtures point (standard pytest tmp dirs), not hardcoded `/tmp` paths — worth mirroring for any new test repo you add.

## 5. Git hooks that could interfere with force-committing a single file, or with `/tmp` test repos

- **Real repo hooks** (`/home/user/git/luckydonald/base/.git/hooks/`): `pre-commit`, `commit-msg`, `post-checkout`, `post-commit`, `post-merge`, `pre-push` — all pre-commit-framework-generated shims (`exec python3 -mpre_commit hook-impl --config=.pre-commit-config.yaml ...`).
- **`/home/user/git/luckydonald/base/.pre-commit-config.yaml`** (and mirrored `.pre-commit-hooks.yaml`) wires up 4 local hooks:
  - `no-co-authored-by` (commit-msg stage) → `scripts/°base/git/hooks/commit/reject_co_authored_by.py` — rejects `Co-Authored-By`/`Claude-Session` trailers.
  - `require-memory-delete-marker` (commit-msg stage) → `/home/user/git/luckydonald/base/scripts/°base/git/hooks/commit/require_memory_delete_marker.py` — inspects `git diff --cached --name-only --diff-filter=D` for deleted `.md` files under `ai/memory/` or `ai/°base/memory/`, and **requires** the commit message to contain a literal `Deleted Memory: <name>.md` marker line for each. This is the one most relevant to "force-removing a single committed file": if your feature ever deletes a tracked memory-directory file via a normal commit (as opposed to history-rewrite), this hook will block it without the marker line.
  - `ai-settings-sync` (always_run) → `scripts/°base/ai/settings/sync.py --check`.
  - `require-yarn-4` (always_run) → `scripts/°base/git/hooks/commit/require_yarn_4.py`.
- **These hooks are per-repo** (installed only in `/home/user/git/luckydonald/base/.git/hooks/`, generated by `pre-commit install`). A fresh `git init` in a `/tmp`/tmp_path scratch repo (as used by `_git_test_helpers.init_repo`) gets **no hooks by default** — `.git/hooks/*.sample` only — so throwaway test repos are naturally unaffected unless something explicitly runs `pre-commit install` inside them (nothing found doing so in `scripts/°base/tests/`).
- `history_master.py`'s own internal commits proactively disable hooks via `-c core.hooksPath=/dev/null` (see section 1) specifically because target repos it operates on may have hooks like the above that would otherwise interfere with synthetic rewrite commits — the same trick (`-c core.hooksPath=/dev/null`, or `--no-verify` on plain `git commit`) is the established way in this repo to force a commit while sidestepping hooks such as `require-memory-delete-marker`.
- Hook installer helpers at `/home/user/git/luckydonald/base/scripts/°base/git/hooks/install/__init__.py` (line ~100) and `.../install/setup.py` (line ~66) explicitly `git config --unset-all core.hooksPath` when (re)installing, "to clear any explicit core.hooksPath config that might interfere" — relevant if your feature needs to temporarily disable then re-enable hooks in the *real* repo rather than a scratch one.