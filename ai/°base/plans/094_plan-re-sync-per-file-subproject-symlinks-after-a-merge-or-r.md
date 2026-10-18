# Plan: re-sync per-file subproject symlinks after a merge or rebase

Todo `6f2b2450-103d-4be5-b029-bbe95c3e5501` ("Have a rebase or merge use git triggers to re-sync per-file subproject symlinks."), project `base`, todo file `ai/todo.md`, calendar 7.

Commit style: `commit-with-lplp-style` is active (the origin belongs to `luckydonald/*`, so it is assumed `yes` without asking).
Plain new commits while working, tag the prior HEAD with `scripts/tag_backup.py`, then interactively rebase into one work commit with its message from `ai/git/pending-commit.md`.
Commit format: `[base] hooks: ai: Run: Short summary.`

## Context

`scripts/°base/init/link_subproject.py` links shared monorepo-root files into a subfolder once, when someone runs it by hand there.
The per-file links are the `.run/*.run.xml` entries, one symlink per root file (for example `bot_manager/.run/pony_migrate - r2tg.run.xml` in DockerTgBot).
When a `base/base` merge or rebase later adds, renames or removes a root `.run/*.run.xml`, every subfolder keeps its stale set:
new root files have no link (they show up nowhere, or untracked after a manual re-run), and renamed or removed ones leave dangling symlinks.
Nothing triggers a re-link, so it only gets fixed if somebody remembers to re-run the script in each subfolder.

Goal: after a merge or a rebase, every subproject automatically gets its per-file links brought up to date, with one small automatic commit of only those links (when something changed), and without ever aborting or disturbing the merge or rebase.

## Findings

- Subfolders are not registered anywhere.
  A reliable marker is a tracked symlink `<sub>/.claude` (mode `120000`), created by `link_shared(".claude")`; DockerTgBot has `bot_manager/.claude`, `cum_time/.claude`, `_non_bot/auto_proxy/.claude`.
- `link_subproject.py` keeps `sub_dir` and `git_root` as module globals, set in `main()`, and every helper reads them.
  `link_run_configs()` is the one place that enumerates root `.run/*.run.xml`, so it is the natural seam for the follow-up todo (`.run/.subprojectIgnore`).
- `main()` also does things a hook must not do: `link_env()` makes a commit, and the seeding functions write files.
  So the hook needs its own narrow entry point, not `main()` per subfolder.
- Filenames contain emoji, spaces and `&`, so git output must be read NUL-delimited (`git ls-files -z`), like the replay guards in `history_master.py`.
- Hooks today: `checkout.sh` installs `pre-commit` and `commit-msg` through the pre-commit framework, git-lfs owns `post-checkout`, `post-commit`, `post-merge` and `pre-push`, and `pre-push` is a hand-written trampoline.
  pre-commit 3.7.0 is installed and supports the `post-merge` and `post-rewrite` stages; with a hook already present it moves it to `<hook>.legacy` and chains it, so git-lfs's `post-merge` keeps running.
- Rebase fires `post-rewrite` (argument `rebase`) once, after the rebase finished; a merge (and `pull`) fires `post-merge`.
  Under pre-commit, the post-rewrite command is available as `PRE_COMMIT_REWRITE_COMMAND` (`amend` or `rebase`), so the script can ignore amends.
  `post-checkout` is deliberately not used: the links are tracked files, so a plain checkout already restores a consistent set.

## Changes

1. `scripts/°base/init/link_subproject.py`:
   - add `resync_all()` that finds every subproject via `git ls-files -z -s` (mode `120000`, path ending in `/.claude`, not the root one), then for each sets the `sub_dir`/`git_root` globals and calls only `link_run_configs()` and a new `prune_dangling_run_links()`;
   - `prune_dangling_run_links()` looks at the symlinks in `<sub>/.run/*.run.xml` whose target points into `<git_root>/.run/` but no longer exists, and removes them (`git rm -f` when tracked, `unlink` otherwise); it never touches a non-symlink or a link that points elsewhere;
   - add a `--resync` command line flag to run `resync_all()` from the git root instead of `main()`;
   - create-only and non-destructive: never `backup_path()`, never move or overwrite an existing non-symlink (skip it with a warning), no seeding;
   - new links are `git add`ed like `link_path()` does, and every touched path is collected;
   - `commit_resync(paths)` then commits exactly those paths, with the safety rules in "Safe auto-commit" below; the message is `link_subproject: re-sync subproject links.` (same style as `commit_env_symlink`);
   - everything is printed to stderr.
2. New `scripts/°base/git/hooks/post/resync_subproject_links.py`: a thin wrapper that exits `0` unless this is a merge or `PRE_COMMIT_REWRITE_COMMAND` starts with `rebase`, then runs `python3 scripts/°base/init/link_subproject.py --resync` from the git root.
   Any failure is printed as a warning and swallowed, because a post-hook error must not look like a failed merge or rebase.
3. `.pre-commit-config.yaml`: add two `repo: local` hooks, `stages: [post-merge]` and `stages: [post-rewrite]`, both `always_run: true`, `pass_filenames: false`, `language: system`, entry `scripts/°base/git/hooks/tool_path.sh python3 scripts/°base/git/hooks/post/resync_subproject_links.py`.
4. `scripts/°base/init/checkout.sh`: install the two new hook types next to the existing ones (`pre-commit install --hook-type post-merge` and `--hook-type post-rewrite`) and add them to `add_path_to_pre_commit_hooks`'s loop, so the Xcode/IDE PATH wrapper covers them too.
   Also make `repair_git_lfs_hooks_path` repair `post-merge.legacy`, since git-lfs's stub gets renamed there and would otherwise lose its PATH fix.
5. Docs: extend the "Monorepo subfolders" section of `docs/README.md` (the re-sync happens automatically after merge or rebase, and `link_subproject.py --resync` does it by hand), and list the new hook script in `ai/°base/AGENTS.md` under "Pre-commit hooks".

## Safe auto-commit

The commit happens inside the `post-merge` / `post-rewrite` hook, so it must not disturb git's own operation or the user's work:

- Path-limited: `git commit --only --no-verify -m … -- <link paths>`, so other staged or unstaged changes (autostash, work in progress) stay exactly as they were and never end up in this commit. Removed links are committed the same way, they are already staged by `git rm`.
- Hooks bypassed with `-c core.hooksPath=/dev/null` (as `commit_env_symlink` does for its bookkeeping commit): no pre-commit run, no `post-*` re-entry, no trailer checks. Git does not fire `post-merge`/`post-rewrite` for a plain commit anyway, and the `amend` rewrite event is ignored by the wrapper, so there is no loop.
- Skipped, leaving the links only staged plus a warning, when: a merge, cherry-pick, revert or bisect is still in progress (`MERGE_HEAD`, `CHERRY_PICK_HEAD`, `REVERT_HEAD`, `BISECT_LOG`, `sequencer/`), HEAD is detached, or `index.lock` exists.
  A `rebase-merge/` or `rebase-apply/` directory is tolerated only for the `post-rewrite` rebase event, since git runs that hook exactly once, after the last pick has finished and the branch ref was moved.
- Only fires when something changed. A merge or rebase that adds or removes no root `.run/*.run.xml` produces no commit, so the usual `git diff <bak-tag> HEAD` check after a rebase stays empty. When it is not empty, that is because the rebase genuinely brought in new shared files.
- One commit for all subprojects together, never an empty one, and a failing commit is swallowed (links stay staged, exit code `0`).
- Opt-out: `SUBPROJECT_RESYNC_COMMIT=0` in the environment stages only, without committing.

## Tests

Add to `scripts/°base/tests/test_link_subproject.py`, using the existing `build_merged_monorepo_fixture()` and `build_subproject_repo()` helpers (throwaway repos only):

- a new root `.run/new.run.xml` gets linked into an existing subproject, and the link is staged;
- a root file that was removed leaves a dangling link, which `resync_all()` removes; a link pointing elsewhere and a regular file are left alone;
- a second run changes nothing (idempotent) and `HEAD` is unchanged (no commit made);
- a folder without a tracked `.claude` symlink is ignored; the git root itself is ignored;
- names with spaces, emoji and `&` work;
- the commit contains exactly the link paths even when an unrelated file is staged, and that unrelated file is still staged afterwards;
- no commit (links stay staged) with `MERGE_HEAD` present, detached HEAD, an `index.lock`, or `SUBPROJECT_RESYNC_COMMIT=0`; no commit when nothing changed;
- the hook wrapper: `PRE_COMMIT_REWRITE_COMMAND=amend` does nothing, `rebase` re-syncs, an error in the script still exits `0`.

New i18n keys: none.

## Verification

1. `uv run --project scripts/°base python -m unittest discover -s scripts/°base/tests -v` is green, and `python3 scripts/°base/ai/settings/sync.py --check` is still clean.
2. End to end in a scratch clone, including a real `git rebase -i` and a `git pull --rebase --autostash` with a dirty file, to confirm the commit lands on the rebased branch tip, the rebase finishes cleanly, and the dirty file is restored untouched.
   Also: build a monorepo fixture with one subproject, run `scripts/°base/init/checkout.sh`, confirm `.git/hooks/post-merge` and `post-rewrite` are the pre-commit stubs and `post-merge.legacy` still holds the git-lfs stub.
   Add a root `.run/x.run.xml` on a side branch, then `git merge` it and later `git rebase` another change; the subproject link appears in one new `link_subproject: re-sync subproject links.` commit both times, and a conflict or a failing script does not break either command.

## Risks

- The new `post-merge` stub replaces git-lfs's file; if the `.legacy` chain were ever skipped, LFS would stop updating after merges.
  The verification above checks exactly this, and it is the reason `repair_git_lfs_hooks_path` has to learn the `.legacy` name.
- A commit made from inside `post-rewrite` runs while git is just finishing the rebase; the scratch-clone check above is what proves this is safe, and if it is not, the fallback is stage-only for the rebase event.
- Pruning is limited to dangling symlinks into the root `.run/`; it never deletes user data.
- The `.run/.subprojectIgnore` todo (`58a06dbd…`) will later change only `link_run_configs()`, which both `main()` and the hook use, so the two stay consistent.
