# Plan: Rename `query.md` to `prompt.md`

**Commit style:** Skill `/commit-with-lplp-style` is active — auto-commit following it for this implementation.

## Context

Todo `a224a3e0-f8ab-47c5-9382-437b225227de`: the prompt log file is called `query.md`, and it should be called `prompt.md`.
Projects using this base already have their own `ai/query.md` (their prompt log, with history), so the rename must migrate such files instead of leaving a stale `query.md` next to a fresh `prompt.md`.
The base repo itself has two such files: `ai/query.md` (the template shipped to other projects) and `ai/°base/query.md` (its own log).

## Findings

- All hooks get the path from `resolve_log_path("ai/query.md", "ai/°base/query.md")` in `scripts/°base/ai/hooks/_lib.py:679`, which also handles `by-issue/<KEY>/` routing.
  Callers: `_lib.py` (2×), `compact_result.py`, `save-command-decision/hook.py`, `save-compact-prompt/hook.py`, `save-decision/hook.py`, `save-plan/hook.py` (3×), `save-prompt/hook.py`.
- Other live usages:
  - `scripts/°base/init/link_subproject.py:744` seeds `ai/query.md` from `scripts/°base/init/templates/query.md`.
  - `.pre-commit-config.yaml:28-33` (`base-query-md-guard`, `files: ^ai/query\.md$`) and `scripts/°base/git/hooks/push/check_base_query_md.py` block pushing `ai/query.md` from the base repo.
  - Docs and skill text: `ai/°base/AGENTS.md:107-108`, `ai/skills/commit-with-lplp-style/SKILL.md` (lines 23, 134, 135, 159), docstrings in `sync_todos.py`.
  - Tests: `test_ai_hooks_base_routing.py` (many), `test_save_*`, `test_check_base_query_md.py`, `test_commit_style_lib.py`, `test_git_split_classify.py`, `test_git_split_push_checks.py`.
- Plan, errors and output files under `ai/°base/{plans,errors,output}` and `ai/plans` only mention `query.md` as history, so they stay untouched.
- Neither `ai/prompt.md` nor `ai/°base/prompt.md` exists yet, so there are no collisions in this repo.
- The `save-prompt` hook also names things like `000_online_query.md` (`save-prompt/hook.py:692`), which is a plan artifact and not the log, so it stays.
- Downstream merge: git's rename detection will usually carry a project's `ai/query.md` edits over to `ai/prompt.md` when it merges the renamed base file, but not reliably (a big log vs. a tiny template).
  So the migration has to live in code as well.

## Design

A single helper `migrate_query_to_prompt(query_path, prompt_path)` in `scripts/°base/ai/hooks/_lib.py`, called from `resolve_log_path` before it returns, so every hook migrates on first use.
It follows the todo's rules, working per directory (also the `by-issue/<KEY>/` ones):

1. `query.md` missing: nothing to do.
2. `prompt.md` missing, or identical to the `base/base` version (the shipped template, `scripts/°base/init/templates/prompt.md`): delete `prompt.md` if present, then `git mv query.md prompt.md`, as two separate commits (delete, rename), so git history follows the file.
3. Both exist with identical content: keep the one with the longer history in this repo.
   Compare `git log --oneline --follow` counts for each path, skipping commits that came from `base/base` (commits reachable from `base/base`, if that ref exists).
   Delete the other (1 commit), and if `query.md` is the one that remains, rename it (1 commit).
4. Both exist and differ: leave both alone and migrate nothing.
   The hooks append every entry to **both** files, so nothing gets lost, and the user will eventually merge one into the other (or delete one).
   `resolve_log_path` therefore needs a way to return both paths in this state, e.g. a sibling `resolve_log_paths(...)` returning a list, which the callers write to in turn.

### Subprojects

Subprojects are sub folders of the git root that share the `ai/query.md` style, and each has its own `ai/query.md` (seeded by `link_subproject.py`'s `copy_if_missing`), or a symlink back to the root one.
They are found the way `link_subproject.py` already does it, plus a recursive scan for the logs themselves:

- `find_subproject_dirs()` (`link_subproject.py:468`) lists folders with a tracked `.claude` symlink.
- Additionally the migration scans `git ls-files -z` plus untracked files (`git ls-files -z --others --exclude-standard`), NUL-delimited, for every `query.md` directly in `ai/`, `ai/°base/`, `ai/by-issue/<KEY>/` and `ai/°base/by-issue/<KEY>/` at any depth, so subprojects without a `.claude` link are found, too.
- A `query.md` that is a symlink (pointing back to the root one, relative or absolute) is migrated as a link: the link is renamed and its target is retargeted to the root's `prompt.md`, never copied into a regular file.
  Two links to the same root file count as the same file for the "both exist and equal" case.

The scanning and the four cases live in a new `scripts/°base/ai/migrate_query_to_prompt.py` (`migrate_all(git_root)` plus a `main()` for running it by hand), which `_lib.py` imports for the single-directory call.
It runs from:

1. `resolve_log_path`, for the directory about to be written to (cheap, only acts when a `query.md` is there).
2. `link_subproject.py` (replacing the `copy_if_missing("ai/query.md", …)` seed by `prompt.md`, after migrating the subproject).
3. The existing `post-merge` / `post-rewrite` hook (`resync_subproject_links.py`), which calls `migrate_all`, so a merge of the renamed base migrates the root and every subproject at once.

### Dirty files

A dirty `query.md` does not stop the migration.
The helper migrates the **clean** (committed) version and commits as usual, then puts the working-tree changes back under the new name:

1. Snapshot the working-tree content of `query.md`.
2. `git stash`-free approach: `git checkout -- query.md` is avoided; instead the helper commits the rename of the `HEAD` blob (`git mv` plus `git commit -- <paths>` restricted to the two paths, using the index state of `HEAD`), then overwrites `prompt.md` with the snapshot.
3. The overwrite only happens when exactly one of the two files existed (the straightforward case), since then `prompt.md` is nothing but the freshly migrated copy.
4. If both files exist and at least one of them is dirty: do not migrate at all (case 4 behaviour, append to both).

The migration commits only use explicit paths (never `git add -A`) and keep any user-staged changes intact via the existing `_staged_snapshot` / `_restore_staged` helpers in `_lib.py`.

### Push guard

`check_base_query_md.py` becomes `check_base_prompt_md.py` and blocks pushes of **both** `ai/query.md` and `ai/prompt.md` from the base repo (`files: ^ai/(query|prompt)\.md$`).
The single rename commit is exempt and is pushed by hand (no code for the exemption):

1. Push everything up to the commit before the rename commit.
2. Push the rename commit with `--no-verify`.
3. Push the rest normally.

I will not push anything myself, I only report this order.

## Steps

1. Pure rename first (so git shows moves, per the commit style):
   - `git mv ai/query.md ai/prompt.md`, `git mv "ai/°base/query.md" "ai/°base/prompt.md"`, `git mv scripts/°base/init/templates/query.md scripts/°base/init/templates/prompt.md`.
   - Also `git mv ai/plans/000_online_query.md ai/plans/000_online_prompt.md` (the tracked one; the `°base` copy is created by the hook), and rename the artifact name in `save-prompt/hook.py:692` plus the two tests in `test_ai_hooks_base_routing.py:784-840`.
     The `_online_query_*` helper names in `hook.py` become `_online_prompt_*`.
   - Commit as its own commit with content unchanged.
2. Point the code at the new name:
   - `resolve_log_path` call sites and docstrings: `ai/query.md` becomes `ai/prompt.md`, `ai/°base/query.md` becomes `ai/°base/prompt.md`.
   - `link_subproject.py` copies `prompt.md` and runs the same migration for the subproject; `resync_subproject_links.py` calls `migrate_all`.
   - Rename `check_base_query_md.py` to `check_base_prompt_md.py` (and its test), update the hook id, name and `files:` regex in `.pre-commit-config.yaml`, and make the test cover both the old and the new name.
   - Update `AGENTS.md`, `SKILL.md` (all four mentions) and the `sync_todos.py` docstrings.
   - Update the `ai/query.md` classification entries in tests and in the split classifier if it has a path list (`.ai-ignore` fallback), checking `scripts/°base/git/°split_lib/classify.py` for the literal.
3. Add `scripts/°base/ai/migrate_query_to_prompt.py` and call it from `resolve_log_path`, `link_subproject.py` and `resync_subproject_links.py`.
4. Tests (`scripts/°base/tests/`):
   - New `test_migrate_query_to_prompt.py`, unit tests for the helper: the four cases, a `by-issue` directory, a `query.md` symlink to the root one, and append-to-both.
   - The sweep of the existing tests from `query.md` to `prompt.md`.
   - New end-to-end `test_migrate_query_to_prompt_clone.py` on a real clone, set up once per test run:
     1. Shallow-clone (`git clone --depth 1`) the current version of this repository into a temp dir.
     2. If the clone already holds migrated files, rename every `prompt.md` back to `query.md` (root, `°base`, subprojects), so the test can be re-run later.
     3. Write 10-50 random lines each to `./ai/query.md` and `./ai/°base/query.md`, and commit both.
     4. Create the subproject `./subproject/` and let `link_subproject.py` link and write everything it needs.
     5. Create `./longer/deeper/path/with/ai/in/its/name/but/its/actually/just/a/subproject/` the same way, to prove the recursive scan does not mistake the `ai` in the path for a log location.
     6. Commit with `git add ./subproject/ ./longer/` (allow empty), so nothing is left uncommitted.
     7. Store this `HEAD` and reset to it for every case (or use a local clone per case, to run in parallel).
     8. A `for`-loop-driven matrix over the locations (root, `°base`, both subprojects) × the four cases × clean/dirty variants of the existing files.
        For each combination, the case setup writes 10-50 random lines into the log files of that location, depending on the setting: committed or dirty (uncommitted working-tree lines on top), new file only, old name only, both, or none.
        The root and `°base` files of step 3 and the subproject files (`ai/` of both subprojects) are all treated this way, so every location is exercised with every state.
        Every combination has an exact expectation table, computed from the generated lines, and the test compares the result against it, not just "looks plausible":
        - File existence: which of `query.md` / `prompt.md` exist afterwards, per location.
        - Committed content: `git show HEAD:<path>` of each file equals exactly the expected lines (for the migrated clean version, the original committed lines under the new name).
        - Dirty content: the working-tree content of each file equals exactly the expected lines (committed lines plus the dirty lines, restored under the new name, or appended to both in case 4), and `git status --porcelain` lists exactly the expected dirty paths and nothing else.
        - History: `git log --follow` on the new path reaches the old commits, and the number and messages of the migration commits match the case (delete + rename, delete only, rename only, none).
5. Docs: note the rename and the migration in `ai/°base/AGENTS.md`.
6. Add the new i18n keys: none (no UI strings).

## Verification

- `uv run python -m unittest discover -s scripts/°base/tests` (or the repo's usual test command) is green, including the new migration tests.
- Run `pre-commit run --all-files` for the renamed guard hook.
- Manual check in a scratch git repo: an old `ai/query.md` log is renamed to `ai/prompt.md` by the next hook run, history intact (`git log --follow`).
- `git grep -n "query\.md"` outside `ai/°base/{plans,errors,output}`, `ai/plans` and `ai/output` returns nothing.

## Pushing

The push guard (`check_base_prompt_md.py`) blocks every push that contains `ai/query.md` or `ai/prompt.md` in the base repo, so the pure rename commit has to be pushed without hooks, in between the other commits.
Upstream is `base/base`, so the remote is `base` and the branch `base`.
Each push is gated on the expected commit, so nothing that is not part of this plan goes out.

Commits, oldest first (the todo syncs and the earlier work before them go out with the first push):

| Commit | Content | Push |
|---|---|---|
| `4fca9e43f1a837da6217d441d2fae70404827dbd` | `ai: Plan:` and the decisions | with hooks |
| `0e9a6ac2dfec4153b58b911805ffffd099e6aca3` | pure rename of the log files | `--no-verify` |
| `cf732306b9598c515b5e2c31df3185797a158854` | code, migration, tests, docs | with hooks |

```bash
# 1. Everything up to the plan commit, i.e. before the rename.
test "$(git rev-parse 4fca9e43f1a837da6217d441d2fae70404827dbd)" = "4fca9e43f1a837da6217d441d2fae70404827dbd" && \
git push base 4fca9e43f1a837da6217d441d2fae70404827dbd:refs/heads/base

# 2. The rename commit on its own, without the hooks (they would block it).
test "$(git rev-parse 0e9a6ac2dfec4153b58b911805ffffd099e6aca3)" = "0e9a6ac2dfec4153b58b911805ffffd099e6aca3" && \
git push --no-verify base 0e9a6ac2dfec4153b58b911805ffffd099e6aca3:refs/heads/base

# 3. The rest, normally, as long as HEAD is still the commit that was checked.
test "$(git rev-parse HEAD)" = "<expected sha of HEAD>" && git push base base
```

Notes:

- The refspec `<sha>:refs/heads/base` pushes up to that commit and nothing after it, and it only fast-forwards.
- Step 3 runs the guard on the range after the rename, which holds no `ai/query.md` / `ai/prompt.md` change, so it passes.
  The log `ai/°base/prompt.md` is not matched by the guard's `^ai/(query|prompt)\.md$` filter.
- Replace `<expected sha of HEAD>` by `git rev-parse HEAD` as it is when pushing.
  The `ai: updated prompt` commits and the commit of this section go out with it.
- Nothing was pushed when this section was written.
