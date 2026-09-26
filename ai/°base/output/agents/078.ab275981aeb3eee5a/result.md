Full report below.

## Files

**1. `/home/user/git/luckydonald/base/scripts/link_subproject.sh`**
Symlink -> `°base/link_subproject.sh` (`lrwxrwxrwx`, `scripts/link_subproject.sh -> °base/link_subproject.sh`).

**2. `/home/user/git/luckydonald/base/scripts/°base/link_subproject.sh`**
Symlink -> `init/link-subproject-claude.sh` (`°base/link_subproject.sh -> init/link-subproject-claude.sh`). So all three names (`scripts/link_subproject.sh`, `scripts/°base/link_subproject.sh`, `scripts/°base/init/link-subproject-claude.sh`) are one and the same 341-line bash file; there is only one implementation, at `scripts/°base/init/link-subproject-claude.sh`.

**3. `/home/user/git/luckydonald/base/scripts/°base/init/link-subproject-claude.sh`** (341 lines) — full contents read above. Key structure:
- `set -euo pipefail`; computes `sub_dir` (cwd), `git_root` (via `git rev-parse --show-toplevel`); bails if run at repo root or if `$git_root/.claude` is missing.
- Helpers: `realpath_of`/`relpath_of` (python3 one-liners), `is_tracked` (git ls-files), `backup_path` (renames existing file to `{stem}.YYYY-MM-DD_HH-MM-SS.bak{ext}`, via `git mv` if tracked, else plain `mv`).
- `link_path <rel> <source>` — generic relative-symlink creator with backup-if-conflicting logic; ends with `git -C "$sub_dir" add -- "$rel"`.
- `link_shared <rel>` — thin wrapper: `link_path "$rel" "$git_root/$rel"`.
- `copy_if_missing <rel> <template_name>` — copies from `scripts/°base/init/templates/$template_name` only if target doesn't already exist; `git add`s the copy.
- `link_run_configs` — loops `$git_root/.run/*.run.xml`, symlinking each individually via `link_shared`.
- `touch_scratch_gitkeeps` — creates `.gitkeep` in `ai/{errors,output/agents,output/explore,plans}`, `git add`s each.
- `link_agents_claude` — symlinks `AGENTS.md -> CLAUDE.md`, moving a pre-existing real `AGENTS.md` into `CLAUDE.md` first (via `git mv` if tracked); `git add`s both `AGENTS.md` and `CLAUDE.md`.
- `project_dir_name_slug` / `seed_claude_project_env` — writes `.claude-project.rc` (once only) with `CLAUDE_CODE_PROJECT_DIR_NAME`/`CLAUDE_CONFIG_DIR`; `git add`s it. Named `.rc` specifically to dodge the repo's blanket `**/*.env*` gitignore rule.
- Bottom: sequential calls — `link_shared ".claude"`, `".codex"`, `"ai/settings"`, `"ai/references"`, `"ai/skills"`, `".mcp.json"`, then `link_env`, `link_run_configs`, `touch_scratch_gitkeeps`, `copy_if_missing "ai/query.md" "query.md"`, `copy_if_missing "CLAUDE.md" "CLAUDE.md"`, `link_agents_claude`, `seed_claude_project_env`.

**`link_env` (lines 199–238) — the `.env` logic specifically:**
```bash
link_env() {
  local rel="ai/.env"
  local source="$git_root/$rel"

  if [ ! -e "$source" ]; then
    mkdir -p "$(dirname "$source")"
    touch "$source"
    echo "touched $source"
  fi
  ...
  ln -s "$rel_link" "$target"
  echo "linked $target -> $rel_link"
  git -C "$sub_dir" add -- "$rel"
}
```
- If the monorepo-root `ai/.env` doesn't exist, it's `touch`ed into existence first (since it's gitignored and otherwise never seeded).
- Then behaves like `link_path`: backs up any pre-existing non-matching file/symlink at `$sub_dir/ai/.env`, creates the relative symlink `$sub_dir/ai/.env -> $git_root/ai/.env`.
- **The symlink IS staged** (`git -C "$sub_dir" add -- "$rel"`) — this is a duplicated, hand-rolled copy of `link_path`'s body rather than reusing `link_path`/`link_shared` directly, because it needs the "touch root ai/.env if missing" step first.
- Comment (lines 199–205) explicitly documents: only the root-level `ai/.env` (per-machine secrets) stays gitignored; the subproject symlink is meant to be tracked "like the other `link_shared` targets."

## Plan doc: `ai/°base/plans/058_extend-link-subproject-claude-sh-scaffolding.md`
This is the plan that added the `ai/references`, `ai/skills`, `.run/*.run.xml`, scratch-dir gitignores, and `copy_if_missing` scaffolding described above. It does **not** mention `ai/.env` at all — the `link_env`/`.env`-symlink handling was added later, separately (per the commit below), and post-dates or is orthogonal to plan 058's scope. Note the plan's proposed final call order differs slightly from what's actually in the script today (plan doesn't list `link_env`, and uses old naming `ai/tool-settings` vs. actual `ai/settings` — the plan is stale relative to the current script, consistent with later renames, e.g. plan 066 "rename-ai-tool-settings-ai-settings").

## Python port search
No `link_subproject.py` or similarly-named Python file exists anywhere in the repo (checked `scripts/°base/` and `scripts/`, and did a repo-wide filename/content search). `grep -l "link_subproject"` across all `.py` files only hit `scripts/°base/ai/hooks/_lib.py` (unrelated coincidental match, not a port) — there is no Python implementation or in-progress port of this script. It is currently pure bash.

## `.gitignore` handling of `ai/.env`
`/home/user/git/luckydonald/base/.gitignore`, dotenv-related block (lines ~775–781):
```
**/*.env
**/*.env*
**/*.env.*
!/.env.example
!**/*.example.env
!ai/.env.example
!*/**/ai/.env
```
- The blanket `**/*.env*` (and duplicates) ignores every `.env`-ish file anywhere.
- `!/.env.example`, `!**/*.example.env`, `!ai/.env.example` are pre-existing negation exceptions for example files.
- `!*/**/ai/.env` (line 781) is the newest negation: un-ignores `ai/.env` at any subfolder depth (`*/**/ai/.env` requires at least one path segment before `ai/.env`, so it does **not** un-ignore the root-level `$git_root/ai/.env`, which stays ignored as intended).
- There's also a second occurrence of `.env`-adjacent ignore rules earlier (lines 617–621: `.env`, `env/`, `**/.env`, `/.env`) in an unrelated "python gitignore template" block — largely redundant/overlapping with the block at 775+.

## Commit `dc3dbe2` — exact change
Title: `[base] init: ai: Run: Made link-subproject-claude.sh's ai/.env symlink actually get committed`

Diff summary (3 files):
1. **`.gitignore`**: added `!*/**/ai/.env` (line 781 today).
2. **`ai/°base/query.md`**: appended prompt-log entries recording the user's back-and-forth ("Will the `subfoldr/ai/.env` symlink ... be committed? We might have forgotten to add that." → "Actually add that the subfolder symlink (not root ai/.env) gets committed." → "It should be committed, fix `.gitignore` then.").
3. **`scripts/°base/init/link-subproject-claude.sh`**: in `link_env`, added the missing `git -C "$sub_dir" add -- "$rel"` line, and rewrote the comment from "Not `git add`ed — ai/.env is gitignored and meant to hold per-machine secrets" to the current comment explaining only the root file stays ignored.

So before this commit, `link_env` created the symlink but never staged it (bug — matched the pattern of all other `link_*`/`link_shared` calls except this one was intentionally excluded, until the user caught it was actually needed).

## Existing git-add / commit patterns in these scripts
No commit logic at all — only staging (`git add`), never `git commit`. Patterns present:
- `git -C "$sub_dir" add -- "$rel"` at the end of `link_path`, `copy_if_missing`, `touch_scratch_gitkeeps`, `link_env`, `link_agents_claude`, `seed_claude_project_env` — i.e., every mutating helper stages exactly the file(s) it just touched (a "whitelist just this file" pattern already exists, just via plain `git add --`, never `-f`).
- `git -C "$sub_dir" mv -- "$rel" "$bak_rel"` in `backup_path`, and `git -C "$sub_dir" mv -- "AGENTS.md" "CLAUDE.md"` in `link_agents_claude` — used instead of `mv` whenever the source path is `is_tracked`.
- No use anywhere of `git add -f`/`--force`, `git rm --cached`, `git commit`, or `git stash`. The "actually get committed" fix in `dc3dbe2` was purely about the `.gitignore` negation pattern (`!*/**/ai/.env`) plus a plain `git add`, not a forced add — meaning if a user's local `.gitignore` state is stale/uncached, a plain `git add` on an ignored path will silently no-op (this is a candidate gotcha for the rewrite: consider `git add -f` as a more robust guarantee instead of/alongside the gitignore negation, since relying solely on a gitignore negation pattern is what caused this to need a fix in the first place, and negation patterns are fragile — e.g. this one doesn't cover the root-level case, which is deliberate, but subtle).

## Test infrastructure
- No test file exists for `link_subproject.sh` / `link-subproject-claude.sh` itself. Repo-wide, references to `link_subproject`/`link-subproject` outside the scripts themselves are only in plan docs and `ai/°base/query.md`/agent output logs (`ai/°base/plans/058_...md`, `066_rename-ai-tool-settings-ai-settings.md`, `073_fix-linked-subprojects-can-t-save-claude-memories.md`, `ai/°base/memory/fix-subproject-memory-project-dir-name-override.md`, and various `ai/°base/output/agents/*/result.md`).
- General test suite lives at `scripts/°base/tests/` (`~40` test files, all Python `unittest`-style, e.g. `test_git_split_*.py`, `test_get_base.py`, `test_ai_settings_sync.py`, etc.) — run via `uv run --project scripts/°base python -m unittest discover -s scripts/°base/tests -v` per `scripts/°base/tests/README.md`.
- Reusable git-repo test helper: `/home/user/git/luckydonald/base/scripts/°base/tests/_git_test_helpers.py` (short, 27 lines):
```python
def git(args: list[str], cwd: Path) -> str: ...
def make_commit(cwd: Path, filename: str, message: str, content: str | None = None) -> str: ...
def init_repo(cwd: Path, *, branch: str = "master") -> None:
    git(["init", "-b", branch], cwd)
    git(["config", "user.email", "test@example.com"], cwd)
    git(["config", "user.name", "Test"], cwd)
```
  This is exactly the kind of helper a new test suite for `link_subproject`/its Python port would reuse to spin up throwaway git repos (would be used with `tmp_path`/`TemporaryDirectory`, not literally `/tmp`, per unittest/pytest conventions elsewhere in the suite — no test currently hardcodes `/tmp` paths).
- Bottom line: writing tests for the `.env`-symlink-and-commit behavior would be new work; there's a solid, minimal helper module to build on, but nothing today exercises `link_env` or the gitignore-negation interaction.

## `docs/README.md` "all code for c) as a single copy pastable one" anchor
File: `/home/user/git/luckydonald/base/docs/README.md`. TOC references it at line 8/30 (`#all-code-for-c-as-a-single-copy-pastable-one`); the actual heading is at **line 206**: `### All code for c) as a single copy pastable one:`.

This section (lines 206–238) is **not** about `link_subproject.sh` at all — it's part of the "Setup: c) Merge `base/base`" onboarding flow (adopting this `base` repo into a consuming repo via merge, as opposed to rebase). It's a single copy-pasteable shell block that: adds `empty`/`base` remotes, fetches, merges `--allow-unrelated-histories`, decides fast-forward vs. rebase vs. re-merge depending on prior history, runs `pre-commit install`, and sanity-checks `git config user.name`. Relevant excerpt:
```shell
git remote add empty https://luckydonald@github.com/EmptyAAS/empty.git
git remote add base https://luckydonald@github.com/luckydonald/base.git
git fetch empty init
git fetch base base
git lfs install
git merge --allow-unrelated-histories --no-verify empty/init
...
pre-commit install
[ "$(git config user.name)" = "Lucky Lucy" ] || printf ...
```
So the anchor `docs/README.md#all-code-for-c-as-a-single-copy-pastable-one` is a real, existing section, but it documents the *initial repo-merge onboarding* flow, not `link_subproject`. If the rewrite plan wants a similarly-named "single copy-pasteable" reuse note specific to `link_subproject`/`.env` handling, that would need to be a **new** section — this existing anchor is a different (adjacent) topic and shouldn't be conflated with or reused for the subproject-linking rewrite, though it's a useful precedent for the "one copy-pasteable code block" documentation style used in this repo.