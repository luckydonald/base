# base

Small reusable git base for other repositories.

This history is intentionally rooted at `empty/init` from `https://github.com/EmptyAAS/empty.git`. That gives multiple repos the same empty ancestor commit, which makes it possible to rebase or merge this base into another repo in a predictable way.

## Quick links
- [Include](#all-code-for-c-as-a-single-copy-pastable-one)
- [Sidecar](#branch-splitting-cleanuncleanhistory)

## Table of contents

<!-- TOC -->
* [base](#base)
  * [Quick links](#quick-links)
  * [Table of contents](#table-of-contents)
* [Add This To Your Repo](#add-this-to-your-repo)
  * [Overview](#overview)
    * [Which Workflow To Choose](#which-workflow-to-choose)
* [Installation](#installation)
  * [Setup](#setup)
          * [Shared initial commit](#shared-initial-commit)
  * [Setup: a) Checkout](#setup-a-checkout)
      * [Rename branch](#rename-branch)
        * [Local branch](#local-branch)
        * [Remote branch](#remote-branch)
          * [Hosted Git](#hosted-git)
  * [Setup: b) Rebase Onto `base/base`](#setup-b-rebase-onto-basebase)
  * [Setup: c) Merge `base/base`](#setup-c-merge-basebase)
    * [All code for c) as a single copy pastable one:](#all-code-for-c-as-a-single-copy-pastable-one)
      * [Fix user](#fix-user)
  * [After Adopting The Base](#after-adopting-the-base)
    * [Git LFS](#git-lfs)
    * [Claude GitHub issue agent](#claude-github-issue-agent)
    * [Codex GitHub issue agent](#codex-github-issue-agent)
    * [Monorepo subfolders: per-subfolder `.claude/`](#monorepo-subfolders-per-subfolder-claude)
    * [Branch splitting (clean/unclean/history)](#branch-splitting-cleanuncleanhistory)
<!-- TOC -->


# Add This To Your Repo

## Overview
There are three ways to adopt this:

- start with it from the get-go, creating your branch from `base/base`.
  - obviously only works if you haven't commited anything yet.
  - otherwise see rebase below, that's basically _"plz pretend I started from that and did all my own commits afterward!"_
- rebase your repo on top of `base/base` if you want this base to become part of your linear history 
  - recommended if your git is not yet used by others
- merge `base/base` into your repo if you do not want to rewrite history

If you only want a one-time copy of the files, just copy them manually. The steps below are for keeping your repo connected to this base over time.

### Which Workflow To Choose

Choose checkout if:
- you want to create a new project
- or have not commited anything yet

Choose rebase if:

- you want this base to sit underneath your repo's commits
- you prefer a linear history
- force-pushing rewritten history is acceptable

Choose merge if:

- your branch is already published or shared
- you want the least disruptive adoption path
- you are fine with explicit merge commits for base updates


# Installation
## Setup

Add the remotes you need, as below.
We assume your username would be `luckydonald` on GitHub, otherwise remove the `luckydonald@` part from the repository URLs, or replace with your own.
Specifying the username is only needed if you have more than one GitHub account configured on your machine (e.g. private and work).

```bash
git remote add base https://luckydonald@github.com/luckydonald/base.git
git fetch base base
git lfs install
pre-commit install
```

###### Shared initial commit
> > ℹ️  
> > If your repository does not already descend from `empty/init`, and you want to merge cleanly later, and it's okay to rewrite its history, re-root it once:
> 
> 1. ```bash
>    git remote add empty https://luckydonald@github.com/EmptyAAS/empty.git
>    git fetch empty init
>    ```
> 2. ```bash
>    git rebase --root --onto empty/init
>    ```
>
> That keeps your file history intact, but rewrites every commit in the branch so the new root is the shared empty commit.

## Setup: a) Checkout

Use this if you are starting fresh and want your repository branch to begin at `base/base`.

This is the simplest option, but it only makes sense before you have your own commits on the branch.

We assume you want to give your branch the name `mane` here. Replace in the commands below as needed.

Initial adoption:

```bash
git switch --create mane base/base
```

If your git version is older and does not support `switch`, use:

```bash
git checkout -b mane base/base
```

Then point your own repository remote at the branch and publish it as usual:

```bash
git push -u origin mane
```

Future updates work the same as in the other setups: fetch `base`, then either rebase onto `base/base` or merge `base/base`, depending on the workflow you chose for ongoing maintenance.

Notes:

- replace `main` with whatever branch name your repo should use
- this avoids the one-time re-rooting and adoption steps from the rebase and merge workflows
- once you start adding your own commits, updates from this base are handled with either section `b)` or `c)`

#### Rename branch
In case you ran above commands, you'd get the `main` branch. If you want to rename it after-the-fact, here's how:

> In this example I'll rename `main` to `mane` to make sure it's properly ponified.

##### Local branch
```shell
OLD_NAME=main
NEW_NAME=mane
REMOTE="origin"

git branch -m "${OLD_NAME}" "${NEW_NAME}"
git fetch "${REMOTE}"
git remote set-head "${REMOTE}" -a
```
##### Remote branch

###### Hosted Git
If your repo is on git hoster (GitHub, GitLab, Gitea, Forgejo, …) with a website to manage it,
it's better to rename the branch in the GUI there, as it will make sure that all settings references will be updated as well.
For example the protected branch settings, and default `git checkout` branch settings



## Setup: b) Rebase Onto `base/base`

Use this if you want a clean linear history, and you are comfortable rewriting your branch.

Initial adoption:

```bash
git rebase --onto base/base empty/init
```

After that, future updates are just:

```bash
git fetch base
git rebase base/base
```

Notes:

- resolve conflicts as they appear, then continue with `git rebase --continue`
- if you already pushed the branch, you will usually need `git push --force-with-lease`
- this is best for personal branches or repos where force-pushes are acceptable

## Setup: c) Merge `base/base`

Use this if you want to preserve existing history and avoid rebasing published branches.

Initial adoption into an unrelated existing repo:

```bash
git merge --allow-unrelated-histories --no-ff base/base
```

Future updates:

```bash
git fetch base
git merge --no-ff base/base
```

Notes:

- this keeps a merge commit for each base update
- this is the safer choice for shared branches
- if your repo already shares `empty/init` as an ancestor, the initial `--allow-unrelated-histories` is not needed

### All code for c) as a single copy pastable one:
Run this in the repository that should get the base (a missing git repo is created on branch `mane`).
It is idempotent: a rerun on an up-to-date repo changes nothing.

```shell
curl -fSL https://raw.githubusercontent.com/luckydonald/base/refs/heads/base/scripts/%C2%B0base/init/install-base.sh | bash -s --
```

Add flags after `--`, e.g. `--branch main` for a new repo, `--fix-user`, `--keep-user`, `--rebase`, `--merge`, `--yes` (see the header of the script).
If you use Claude Code, the `install-base` skill (`ai/skills/install-base/`) runs this for you; `scripts/°base/init/install-skill-user.sh` copies it to your user profile so it works in repos without the base.

The script, for reference (`scripts/°base/init/install-base.sh` is the source of truth, keep this copy in sync):

<details>
<summary>install-base.sh</summary>

```shell
#!/usr/bin/env bash
# scripts/°base/init/install-base.sh
#
# Adopts `luckydonald/base` into the git repository in the current directory (or creates one).
# This is the idempotent, runnable version of the "All code for c) as a single copy pastable one" block in docs/README.md.
# Keep the two in sync.
#
# Idempotent: safe to run multiple times; a run on an already-adopted, up-to-date repo changes nothing.
#
# Usage: install-base.sh [--branch NAME] [--yes] [--rebase | --merge] [--fix-user | --keep-user]
#
#   --branch NAME  Branch name for a freshly created repo (default: $BASE_BRANCH or `mane`). Existing branches are never renamed.
#   --yes          Allow overwriting a `base`/`empty` remote that points somewhere unexpected.
#   --rebase       Force the rebase path, even if the branch looks published.
#   --merge        Force the merge path.
#   --fix-user     Set the repo-local git user.name/user.email to the base author, if they differ.
#   --keep-user    Accept a differing git user.name/user.email without asking.
#
# Environment: BASE_GIT_USERNAME (GitHub user in the URLs, default `luckydonald`; set empty to omit), BASE_BRANCH,
#   BASE_URL / EMPTY_URL (override the remote URLs completely, e.g. for tests).
#
# Exit codes: 0 ok, 1 error, 2 refused (inside the base repo), 3 git identity mismatch (nothing was changed yet),
#   4 stash could not be re-applied automatically, 5 remote URL mismatch, 6 rebase/merge needs manual conflict resolution.

set -euo pipefail

EXPECTED_NAME="Lucky Lucy"
EXPECTED_EMAIL="2.2026._.code@luckydonald.de"
GH_USER="${BASE_GIT_USERNAME-luckydonald}"
GH_AT="${GH_USER:+${GH_USER}@}"
BASE_URL="${BASE_URL:-https://${GH_AT}github.com/luckydonald/base.git}"
EMPTY_URL="${EMPTY_URL:-https://${GH_AT}github.com/EmptyAAS/empty.git}"
BRANCH="${BASE_BRANCH:-mane}"
ASSUME_YES=0
STRATEGY=auto
USER_MODE=ask

red() { printf '\033[31m%s\033[0m\n' "$*"; }
green() { printf '\033[32m%s\033[0m\n' "$*"; }
note() { printf '%s\n' "$*"; }

while [ $# -gt 0 ]; do
  case "$1" in
    --branch) BRANCH="${2:?--branch needs a name}"; shift ;;
    --yes) ASSUME_YES=1 ;;
    --rebase) STRATEGY=rebase ;;
    --merge) STRATEGY=merge ;;
    --fix-user) USER_MODE=fix ;;
    --keep-user) USER_MODE=keep ;;
    -h|--help) sed -n '2,25p' "$0"; exit 0 ;;
    *) red "Unknown argument: $1"; exit 1 ;;
  esac
  shift
done

export PATH="$HOME/.local/bin:$HOME/.cargo/bin:$HOME/.pyenv/shims:/opt/homebrew/bin:/opt/homebrew/sbin:/usr/local/bin:/usr/local/sbin:$PATH"

# ─── 0. Never run inside the base repo itself ───────────────────────────────
if TOP="$(git rev-parse --show-toplevel 2>/dev/null)"; then
  if [ "$(basename "$TOP")" = "base" ] && git remote get-url origin 2>/dev/null | grep -q 'luckydonald/base'; then
    red "This is the base repo itself, refusing to install it into itself."
    exit 2
  fi
fi

# ─── 1. git init, if there is no repo yet ───────────────────────────────────
if ! git rev-parse --git-dir >/dev/null 2>&1; then
  note "No git repository here: creating one on branch '$BRANCH'."
  git init -b "$BRANCH" 2>/dev/null || { git init && git symbolic-ref HEAD "refs/heads/$BRANCH"; }
fi
cd "$(git rev-parse --show-toplevel)"

# A repo without any commit yet may still sit on git's default branch name: move it to the wanted one.
if ! git rev-parse --verify -q HEAD >/dev/null && [ "$(git branch --show-current)" != "$BRANCH" ]; then
  git branch -M "$BRANCH"
fi
CURRENT_BRANCH="$(git branch --show-current)"
[ -n "$CURRENT_BRANCH" ] || { red "Detached HEAD: switch to a branch first."; exit 1; }

# ─── 2. Identity check, before we create any merge commit ───────────────────
CUR_NAME="$(git config user.name || true)"
CUR_EMAIL="$(git config user.email || true)"
if [ "$CUR_NAME" = "$EXPECTED_NAME" ] && [ "$CUR_EMAIL" = "$EXPECTED_EMAIL" ]; then
  green "OK: git user \"$CUR_NAME\" <$CUR_EMAIL>."
else
  case "$USER_MODE" in
    fix)
      git config --local user.name "$EXPECTED_NAME"
      git config --local user.email "$EXPECTED_EMAIL"
      green "Fixed: repo-local git user is now \"$EXPECTED_NAME\" <$EXPECTED_EMAIL>."
      ;;
    keep)
      note "Keeping git user \"$CUR_NAME\" <$CUR_EMAIL> (expected \"$EXPECTED_NAME\" <$EXPECTED_EMAIL>)."
      ;;
    *)
      red "ERROR: git user is \"$CUR_NAME\" <$CUR_EMAIL>, expected \"$EXPECTED_NAME\" <$EXPECTED_EMAIL>. Fix it if you are me, and I forgot."
      note "IDENTITY_MISMATCH name=\"$CUR_NAME\" email=\"$CUR_EMAIL\""
      note "Rerun with --fix-user to set it (repo-local), or --keep-user to continue as is."
      note "https://github.com/luckydonald/base/blob/base/docs/README.md#fix-user"
      exit 3
      ;;
  esac
fi

# ─── 3. Remotes ─────────────────────────────────────────────────────────────
normalize_url() { printf '%s' "$1" | sed -E 's#^(https?://)[^@/]+@#\1#; s#\.git$##'; }

ensure_remote() {
  local name="$1" url="$2" existing
  if ! existing="$(git remote get-url "$name" 2>/dev/null)"; then
    git remote add "$name" "$url"
    note "Added remote '$name' -> $url"
  elif [ "$(normalize_url "$existing")" = "$(normalize_url "$url")" ]; then
    note "Remote '$name' already set."
  elif [ "$ASSUME_YES" = 1 ]; then
    git remote set-url "$name" "$url"
    note "Remote '$name' pointed to $existing, changed to $url."
  else
    red "Remote '$name' points to $existing, expected $url."
    note "REMOTE_MISMATCH name=$name existing=$existing expected=$url"
    note "Rerun with --yes to overwrite it."
    exit 5
  fi
}

ensure_remote empty "$EMPTY_URL"
ensure_remote base "$BASE_URL"

# ─── 4. Fetch ───────────────────────────────────────────────────────────────
git fetch empty init
git fetch base base
if command -v git-lfs >/dev/null 2>&1; then
  git lfs install
else
  note "git-lfs not found, skipped 'git lfs install'."
fi

# ─── 5. Bring in base/base ──────────────────────────────────────────────────
BASE_TIP="$(git rev-parse base/base)"
EMPTY_TIP="$(git rev-parse empty/init)"
STASHED=0
STATUS="already up to date"

# Was an older base/base joined via a real merge commit (as opposed to being replayed by rebase)?
# The merge of empty/init itself does not count.
merged_before() {
  local c p1 p2 rest
  while read -r c p1 p2 rest; do
    [ -n "${p2:-}" ] || continue
    [ "$p2" != "$EMPTY_TIP" ] || continue
    if git merge-base --is-ancestor "$p2" "$BASE_TIP" 2>/dev/null; then return 0; fi
  done < <(git rev-list HEAD --merges --parents)
  return 1
}

same() { git diff --no-index --ignore-all-space --quiet -- "$1" "$2"; }

# An untracked file we stashed may now exist as a tracked file from base/base, which blocks the pop.
# If both versions only differ in whitespace, set ours aside and keep base's version afterwards. Anything else is left to the user.
UT_KEEP_NEW=()
prepare_untracked_collisions() {
  local f tmp collisions=()
  git rev-parse -q --verify 'stash@{0}^3' >/dev/null || return 0
  tmp="$(mktemp)"
  while IFS= read -r f; do
    [ -e "$f" ] || continue
    git show "stash@{0}^3:$f" > "$tmp"
    if same "$tmp" "$f"; then UT_KEEP_NEW+=("$f"); else collisions+=("$f"); fi
  done < <(git ls-tree -r --name-only 'stash@{0}^3')
  rm -f "$tmp"
  if [ "${#collisions[@]}" -gt 0 ]; then
    red "Untracked files you had collide with different files from base, left for you to resolve (stash is kept):"
    printf '  %s\n' "${collisions[@]}"
    exit 4
  fi
  for f in ${UT_KEEP_NEW[@]+"${UT_KEEP_NEW[@]}"}; do rm -f -- "$f"; done
}
restore_new_versions() {
  local f
  for f in ${UT_KEEP_NEW[@]+"${UT_KEEP_NEW[@]}"}; do
    git checkout HEAD -- "$f"
    note "Untracked $f only differed in whitespace from base's: kept the new base version."
  done
}

# Re-apply our stash. Conflicts that are trivial in a clearly intended way get resolved, anything else is left for the user.
pop_stash() {
  prepare_untracked_collisions
  if git stash pop --quiet; then
    restore_new_versions
    note "Restored the stashed local changes."
    return 0
  fi
  local files tmp f plan="" action
  files="$(git diff --name-only --diff-filter=U)"
  if [ -z "$files" ]; then
    red "Could not re-apply the stash (no merge conflict listed). It is kept: 'git stash list' / 'git stash pop'."
    exit 4
  fi
  tmp="$(mktemp -d)"
  while IFS= read -r f; do
    # stage 1 = common ancestor, 2 = ours (the updated HEAD), 3 = theirs (the stash)
    if ! { git show ":2:$f" > "$tmp/2" && git show ":3:$f" > "$tmp/3"; } 2>/dev/null; then plan=""; break; fi
    if git show ":1:$f" > "$tmp/1" 2>/dev/null; then :; else : > "$tmp/1"; fi
    if same "$tmp/2" "$tmp/3"; then action=ours
    elif same "$tmp/1" "$tmp/2"; then action=theirs
    elif same "$tmp/1" "$tmp/3"; then action=ours
    else plan=""; break; fi
    plan+="$action	$f"$'\n'
  done <<< "$files"
  rm -rf "$tmp"
  if [ -z "$plan" ]; then
    red "Stash conflicts are not trivial, left them for you to resolve (stash is kept, conflict markers are in the working tree):"
    printf '  %s\n' $files
    exit 4
  fi
  while IFS=$'\t' read -r action f; do
    [ -n "$f" ] || continue
    git checkout "--$action" -- "$f"
    git add -- "$f"
    if [ "$action" = ours ]; then note "Resolved stash conflict in $f: kept the new base version."; else note "Resolved stash conflict in $f: kept your local version."; fi
  done <<< "$plan"
  git reset -q
  git stash drop --quiet
  restore_new_versions
  note "Restored the stashed local changes (trivial conflicts resolved, see above)."
}

if git merge-base --is-ancestor "$BASE_TIP" HEAD 2>/dev/null; then
  note "base/base is already part of '$CURRENT_BRANCH'."
else
  if git rev-parse --verify -q HEAD >/dev/null && [ -n "$(git status --porcelain)" ]; then
    git stash push --include-untracked --quiet -m "install-base: autostash"
    STASHED=1
    note "Stashed local changes."
  fi

  git merge --allow-unrelated-histories --no-verify --no-edit empty/init

  if [ "$(git rev-parse HEAD)" = "$EMPTY_TIP" ]; then
    note "HEAD is at the empty/init tip: fast forwarding to base/base…"
    git merge --ff-only base/base
    STATUS="fast-forwarded to base/base"
  else
    if [ "$STRATEGY" = auto ]; then
      if merged_before; then
        STRATEGY=merge
        note "base/base was previously merged in: merging again…"
      elif git branch -r --contains HEAD | grep -vE '^\s*(empty|base)/' | grep -q .; then
        STRATEGY=merge
        note "'$CURRENT_BRANCH' looks published (a remote branch contains HEAD): merging instead of rewriting history. Use --rebase to override."
      else
        STRATEGY=rebase
        note "Commits sit on top of an old (or no) base/base, nothing published: rebasing onto base/base…"
      fi
    fi
    if [ "$STRATEGY" = rebase ]; then
      if git rebase --onto base/base "$(git merge-base HEAD base/base)"; then
        STATUS="rebased onto base/base"
      else
        red "Rebase stopped on conflicts: resolve them, 'git rebase --continue', then rerun this script."
        [ "$STASHED" = 0 ] || note "Your local changes are in 'git stash list' (install-base: autostash), the rerun will not pop them: 'git stash pop' afterwards."
        exit 6
      fi
    else
      if git merge --no-ff --no-verify --no-edit base/base; then
        STATUS="merged base/base"
      else
        red "Merge stopped on conflicts: resolve them, commit, then rerun this script."
        [ "$STASHED" = 0 ] || note "Your local changes are in 'git stash list' (install-base: autostash): 'git stash pop' afterwards."
        exit 6
      fi
    fi
  fi

  [ "$STASHED" = 0 ] || pop_stash
fi

# ─── 6. Hooks ───────────────────────────────────────────────────────────────
if command -v pre-commit >/dev/null 2>&1; then
  pre-commit install
else
  note "pre-commit not found, skipped 'pre-commit install'."
fi

green "Done: $STATUS (branch '$CURRENT_BRANCH')."
note "Next: see 'After Adopting The Base' in docs/README.md (monorepo subfolders, GitHub issue agents)."
```

</details>

#### Fix user
_Lol, only do if you are me._
```shell
git config --local user.name "Lucky Lucy"
git config --local user.email "2.2026._.code@luckydonald.de"
```
#### Fix previous commits
This resets all commits specified to the current configured user (for both author and commiter).
Also restores the dates from the original commit dates, instead of them all being "now" after the rebase.

```text
FIRST_BAD_HASH="HEAD~1"  # 1 commit ago, or put `somehash~1`. Or `--root` for that initital initial commit.
git rebase "${FIRST_BAD_HASH}" --rebase-merges --exec 'GIT_COMMITTER_DATE="$(git log -n 1 --format=%aD)" git commit --amend --reset-author --no-edit --allow-empty --date="$(git log -n 1 --format=%aD)"'
```
<sub>Based on [Stackoverflow: How can I change the commit author for a single commit?](https://stackoverflow.com/a/79037197/3423324#how-can-i-change-the-commit-author).</sub>
## After Adopting The Base

Once the base is present in your repo, the files provided by this repo live in your repo like normal files. In particular, the `scripts/°base/*` helpers are intended to be run from inside the consuming repository.

### Git LFS

This base tracks binary image files (`.png`, `.jpg`, `.jpeg`) with [Git LFS](https://git-lfs.com). The `git lfs install` command in the setup steps above is a one-time setup per machine. The `.gitattributes` file already defines which file types are tracked, so no additional `git lfs track` calls are needed.

After the base files are present in a repository, `scripts/°base/init/checkout.sh` also installs the local LFS hooks and disables GitHub LFS lock verification for discovered GitHub HTTPS remotes. This avoids push failures like `You must have push access to verify locks` in repos that use LFS files but do not use LFS locks.

### Claude GitHub issue agent

This base includes `.github/workflows/claude-issue-agent.yml`, which lets you ask Claude to work on a GitHub issue by mentioning `@claude` in the issue body or in a new issue comment.

To enable it in a consuming repository:

1. Enable GitHub Actions for the repository.
2. Add at least one of the following Actions secrets:
   - `ANTHROPIC_API_KEY` — an Anthropic API key (pay-per-token, no subscription required).
   - `CLAUDE_CODE_OAUTH_TOKEN` — a Claude Code OAuth token (tied to a Claude Pro/Max subscription).
   Either secret is sufficient; if both are set, the action uses the OAuth token.
3. Make sure the repository's Actions settings allow workflows to create pull requests. In GitHub, this is under repository **Settings** -> **Actions** -> **General** -> **Workflow permissions**.
4. Create or edit an issue containing `@claude`, or add a new issue comment containing `@claude`.

When a comment contains only `@claude`, the action addresses the issue title and body rather than treating the one-word comment as the request. If the comment contains more text alongside `@claude`, that comment text is the specific request. When Claude changes files it opens a pull request and comments the result back on the issue.

Further documentation:

- [Claude Code Action on GitHub](https://github.com/anthropics/claude-code-action) — action source, inputs, outputs, and examples.
- [Anthropic API keys](https://console.anthropic.com/settings/keys) — where to generate an `ANTHROPIC_API_KEY`.
- [Claude Code documentation](https://docs.anthropic.com/en/docs/claude-code/overview) — full Claude Code reference.

### Codex GitHub issue agent

This base includes `.github/workflows/codex-issue-agent.yml`, which lets you ask Codex to work on a GitHub issue by mentioning `@codex` in the issue body or in a new issue comment.

To enable it in a consuming repository:

1. Enable GitHub Actions for the repository.
2. Add an Actions secret named `OPENAI_API_KEY` with an OpenAI API key that is allowed to use Codex.
3. Make sure the repository's Actions settings allow workflows to create pull requests. In GitHub, this is under repository **Settings** -> **Actions** -> **General** -> **Workflow permissions**.
4. Create or edit an issue containing `@codex`, or add a new issue comment containing `@codex`.

When the trigger is in the issue body, the workflow asks Codex to address that issue. When a separate issue comment contains only `@codex`, the workflow also uses the issue title and body as the task instead of treating the one-word comment as the full request. If the comment contains more text, Codex treats that comment as the specific request. When Codex changes files, the workflow commits those changes on a `codex/issue-...` branch, opens a pull request, and comments the result back on the issue.

Further documentation:

- [OpenAI Codex GitHub Action docs](https://developers.openai.com/codex/github-action) explain the `openai/codex-action@v1` inputs, sandbox settings, outputs, and security checklist.
- [openai/codex-action on GitHub](https://github.com/openai/codex-action) contains the action source and examples.
- [Codex code review in GitHub](https://developers.openai.com/codex/integrations/github) documents the separate hosted GitHub review integration for pull requests, including `@codex review`.

### Monorepo subfolders: per-subfolder `.claude/`

If you've merged `base` at the top of a monorepo but intend to run Claude from a subfolder (e.g. `monorepo/some_project/`), Claude Code's settings discovery starts at the launch directory and won't reach the root-level `.claude/` from there. Run the helper once inside each subfolder where you want Claude:

```bash
cd some_project
../scripts/°base/init/link-subproject-claude.sh
```

This creates a relative symlink `some_project/.claude → ../.claude`, so the same `.claude/settings.json` and `.claude/hooks/permission-check.py` apply. The hooks themselves locate `scripts/°base/` via `git rev-parse --show-toplevel`, so they work from any depth. AI artifacts then land under the subfolder — `some_project/ai/query.md`, `some_project/ai/plans/…` — while commits still go to the single monorepo git, with git-root-relative paths like `some_project/ai/query.md`.

The helper is idempotent (no-ops if the symlink already points at the right place), refuses to clobber a non-symlink `.claude/`, and exits cleanly at the git root, so it's safe to re-run or wire into your own setup script.

### Branch splitting (clean/unclean/history)

This base can keep a "clean" branch (no AI/base mentions, safe to publish) in sync with an `ai/UNCLEAN/{branch}` working branch (where AI and code commits mix freely) and an `ai/history/{branch}` branch (the AI-only leftovers). The tooling for this lives under `scripts/°base/git/°split_lib/`, but since it's itself classified as AI/base content, it never exists on a clean checkout — so it ships with a standalone launcher instead.

The simplest way to run it, from any branch of any repo, whether `base` has ever been merged in or not:

```bash
curl -fSL https://raw.githubusercontent.com/luckydonald/base/refs/heads/base/scripts/%C2%B0base/git/get-base.py | python3 -
```

With no extra arguments it figures out what to do from your current branch: on your main branch it runs `update-history-master --yes`; on a clean feature branch it runs `bootstrap-branch <branch>`; on an `ai/UNCLEAN/*` or `ai/history/*` branch it pushes your latest commits forward with `sync-splits <branch> --direction=to-clean-history`.

To run a specific subcommand instead, append it after the script:

```bash
curl -fSL https://raw.githubusercontent.com/luckydonald/base/refs/heads/base/scripts/%C2%B0base/git/get-base.py | python3 - bootstrap-branch feature
```

`get-base.py` adds a `base` remote (name always literally `base`, so it's never confused with `origin`) if missing, fetches it, sets up a worktree at `.git/luckydonald/base#get-base.py`, and delegates to the real tool there — it never touches your currently checked-out branch or working tree. If your GitHub username differs from `luckydonald`, set `BASE_GIT_USERNAME` first.

Generated split commits default to `✨❯ Lucky Lucy <claude._.ai._.code@luckydonald.de>`. Override that identity for one shell or CI job with `BASE_SPLIT_NAME` and `BASE_SPLIT_EMAIL`, or persist it through Git's normal local/global configuration:

```bash
git config --local base.split.name "My Split Bot"
git config --local base.split.email "split@example.com"
```

Environment configuration takes precedence over `base.split.*`. Without either email override, the tool prefers a surviving non-AI identity from the source commit and then `user.name`/`user.email`; `@luckydonald.de` identities map back to the Lucky Lucy default, while other domains retain their own identity. The authorship-rewrite helper recognizes Claude, Codex, and Copilot author/committer identities and removes all `Co-authored-by` trailers.

Before a mutating split run, existing branch tips are backed up as lightweight tags under `bak/split/<branch>/YYYY-MM-DD_HH-MM-SS/{clean,UNCLEAN,history}`. The full branch name is preserved, including any slashes; missing variants simply have no corresponding backup tag.
