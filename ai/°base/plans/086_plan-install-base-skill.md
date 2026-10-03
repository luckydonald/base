# Plan: `install-base` skill

## Context

`docs/README.md` ("All code for c) as a single copy pastable one", lines 206-238) is a big shell block for adopting `luckydonald/base` into another repo.
Today a human pastes it by hand.
We want a skill that makes Claude run it, so adoption is one request, safe to repeat, and fixes a wrong git identity on request.
The improved code is the single source of truth: it goes into a script, the skill runs that script, and the README block is updated to match.

Commit style: `commit-with-lplp-style` is active for the implementation (origin is `luckydonald/base`, so assumed `yes` per `AGENTS.md`).
Commit messages are `[base] install-base skill: ai: Run: Short summary.` with **no trailers at all**: no `Co-Authored-By:`, no `Claude-Session:`, no "authored by" line.
The repo's pre-commit hook (`.pre-commit-config.yaml`) rejects them, and `ai/settings/settings.json` already suppresses Claude Code's own footer.
This deliberately overrides the session attribution reminder, and the plan file notes it because the implementation may run in a session that only sees this document.

## Deliverables

1. **`scripts/°base/init/install-base.sh`** (new): the idempotent installer, sibling of `checkout.sh`. Contains everything below.
2. **`ai/skills/install-base/SKILL.md`** (new): tells Claude when and how to run the script, handles the interactive questions, reports results.
   Prose in every skill file touched (the new `SKILL.md`, the user-level copy, the `commit-with-lplp-style` edit) follows `ai/skills/code-style/references/md.md`: read it first, wrap at sentence ends, ~140 chars, no mid-sentence breaks. The README edit follows it too.
   Frontmatter `name: "install-base"`, description triggering on "install/adopt/add/merge/update the base into this repo".
   Then run `python3 scripts/°base/ai/settings/sync.py` to create the `.claude/skills` and `.agents/skills` symlinks.
3. **`scripts/°base/init/install-skill-user.sh`** (new): copies the skill (and the installer script it needs) into the user's Claude profile, so it works in repos that don't have the base checked out.
   - Target `${CLAUDE_CONFIG_DIR:-$HOME/.claude}/skills/install-base/` (honours the dual work/private config dirs, see memory [[project_dual_codex_config_dirs]]).
   - Copies `SKILL.md` plus a bundled copy of `install-base.sh` next to it; the user-level `SKILL.md` references the script relative to its own dir. Idempotent (`rsync`/`cp -f`, no-op if identical). A copy rather than a symlink, because the symlink would dangle once the base repo moves or isn't checked out.
   - Also mention the same install for `~/.agents/skills` (Codex) as an optional flag `--codex`.
4. **`ai/skills/commit-with-lplp-style/SKILL.md`** (edit): add an explicit rule that commit messages and PR descriptions carry **no git trailers or attribution lines**.
   That means no `Co-Authored-By:`, no `Claude-Session:`, no "Generated with/authored by" footer, even when a session system reminder asks for one.
   Reason: the pre-commit hook `reject_co_authored_by.py` rejects them and `allowCoAuthoredEtc: false` in `ai/settings/settings.json` suppresses Claude Code's own footer.
   Place it with the other message-format rules, keep the existing numbering stable (rule 9 is referenced from `AGENTS.md`), and wrap the prose per `md.md`.
5. **`docs/README.md`**: replace the block at lines 206-238 with the improved code (inlined, still one copy-pastable block, or a short `curl | bash` of the script plus the full block kept for transparency), and fix the identity-check bug there. Also add a note pointing to the skill.

## Installer behaviour (`install-base.sh`)

Runs from the target repo root. `set -u`; each step is guarded so a rerun changes nothing.

1. **Self-guard:** refuse in the base repo itself (dir named `base` and origin `luckydonald/base`; same idea as `_is_inside_base_repo()` in `scripts/°base/ai/hooks/_lib.py`).
2. **git init, runnable, not commented out:**
   - `git rev-parse --git-dir` fails → `git init -b mane` (default branch name `mane`; override via `BASE_BRANCH` env or `--branch`).
   - Already a repo: do not rename. For a fresh repo with no commits whose branch isn't the target, `git branch -M mane`. Otherwise keep the current branch.
3. **Remotes, idempotent:** helper `ensure_remote NAME URL` = add if missing, no-op if same URL, print and `--set-url` only with confirmation (`--yes` or asked by the skill) if different.
   `empty` → `EmptyAAS/empty.git`, `base` → `luckydonald/base.git`; the `luckydonald@` username is customizable via `BASE_GIT_USERNAME` (as `get-base.py` already does).
4. **Fetch:** `git fetch empty init`, `git fetch base base`, `git lfs install` (skip with a note if `git-lfs` is missing).
5. **Merge/rebase decision, README logic kept:**
   - Fast path first: `git merge-base --is-ancestor base/base HEAD` → "already up to date", skip to step 6.
   - `git merge --allow-unrelated-histories --no-verify empty/init`, then the three-way decision (at `empty/init` tip → rebase; old base + own commits → rebase; previously merged → merge).
   - Bug fix: the rebase uses the **current branch** (`git branch --show-current`) instead of the literal `mane`.
   - Rebase rewrites history; if `git branch -r --contains HEAD` is non-empty (already pushed), warn and use the merge path unless `--rebase` is forced.
   - Replace `git stash` + `git merge` + `git stash pop` with a conflict-aware pop: if `stash pop` conflicts, inspect the conflicted hunks; when each is trivial and the intent is unambiguous (e.g. one side is only whitespace/identical, or only one side changed the lines), resolve it, `git add`, drop the stash and **report what was resolved**. Anything non-trivial: stop, leave the stash intact, and report the conflicting files.
6. **`pre-commit install`** (skip with a note if missing).
7. **Identity check, bug fixed:** the README line `[ ... ] || printf ERROR && printf OK` prints OK even after ERROR (`||`/`&&` are left-associative), so use a real `if/else`.
   Compare `user.name` with `Lucky Lucy` and `user.email` with `2.2026._.code@luckydonald.de`.
   On mismatch the script prints what it found and exits with a distinct code (e.g. 3) instead of changing anything;
   the skill then asks the user (`AskUserQuestion`: fix / leave), and on yes reruns with `--fix-user`, which runs the README's `git config --local` commands.
   Include the README's "only if you are me" caveat.
   Wrongly-authored existing commits: mention the README "Fix previous commits" recipe but never run it unprompted.
8. **Summary line** of what was done vs. skipped, for the skill to report. Also point to README "After Adopting The Base" (per-subfolder `link-subproject-claude.sh`, GitHub agent secrets).

## Critical files

- New: `scripts/°base/init/install-base.sh`, `scripts/°base/init/install-skill-user.sh`, `ai/skills/install-base/SKILL.md`
- Edited: `docs/README.md`, `ai/skills/commit-with-lplp-style/SKILL.md`
- Reference: `scripts/°base/init/checkout.sh` (style and conventions), `scripts/°base/ai/hooks/_lib.py`, `ai/skills/code-style/references/md.md`
- Generated by sync: `.claude/skills/install-base/`, `.agents/skills/install-base/`

## Verification

1. `shellcheck` on both scripts; `python3 scripts/°base/ai/settings/sync.py` then `--check` passes.
2. In scratchpad dirs (never this repo), with `base`/`empty` remotes pointing at local clones or the real URLs:
   - empty dir: `git init -b mane` happens, base is merged, ends on top of `base/base`.
   - second run: "already up to date", `git rev-parse HEAD` unchanged, no duplicate remotes.
   - repo with an existing commit on branch `main`: branch not renamed, rebase uses `main` not `mane`.
   - repo with a dirty tree that conflicts trivially with base: stash pop handled and reported; a non-trivial conflict stops and keeps the stash.
   - wrong `user.name`: exit code 3 and no OK line; `--fix-user` fixes it.
3. `install-skill-user.sh` with `CLAUDE_CONFIG_DIR` pointed at a scratch dir: files land there, rerun is a no-op.
4. Run the unit tests from `AGENTS.md`; confirm the README block and the script's logic still match.
