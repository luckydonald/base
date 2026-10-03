---
name: "install-base"
description: "Install (adopt) or update luckydonald/base in the current git repo: adds the `empty` and `base` remotes, merges or rebases `base/base`, installs git-lfs and pre-commit hooks, and checks the git identity. Idempotent, creates the repo on branch `mane` if there is none yet. Use whenever the user asks to install, adopt, add, merge, set up or update the base (or `luckydonald/base`) in a repository, even if they only say 'add the base to this repo' or 'pull in the latest base'."
---

# Install the base

Runs `install-base.sh`, the runnable, idempotent form of the big copy-pastable block in `docs/README.md` ("All code for c) as a single copy pastable one").
Run it from the root of the repository that should receive the base, never from the `base` repo itself (the script refuses).

## Finding the script

Use the first one that exists:

1. `install-base.sh` next to this `SKILL.md` (user-level install under `${CLAUDE_CONFIG_DIR:-~/.claude}/skills/install-base/`).
2. `scripts/°base/init/install-base.sh` in the current repository (the base is already adopted, this is an update).
3. Otherwise fetch it: `curl -fSL https://raw.githubusercontent.com/luckydonald/base/refs/heads/base/scripts/%C2%B0base/init/install-base.sh -o "$TMPDIR/install-base.sh"`, and run that.

Run it with `bash <path>` from the target repo root.
Read the output and report to the user which path was taken (fast-forward, rebase, merge, or already up to date).

## What it does

The script is safe to rerun, and a rerun on an up-to-date repo changes nothing.

1. No git repository yet: `git init -b mane`.
   A repo with no commits is moved to `mane` as well, an existing branch is never renamed. Another name for a new repo: `--branch NAME`.
2. Checks the git identity (see below) before it creates any commit.
3. Adds the `empty` and `base` remotes if missing, then fetches them and runs `git lfs install --local`.
   `--local` matters: a plain `git lfs install` fails when a global `filter.lfs.*` config differs from git-lfs' defaults (e.g. an absolute `/opt/homebrew/bin/git-lfs`), and it would rewrite the global `~/.gitconfig` with `--force`.
4. Brings in `base/base`:
   - already contained → nothing to do.
   - repo only at `empty/init` → fast-forward.
   - own commits on top of an older or no base → rebase onto `base/base`, unless the branch looks published (a remote branch contains `HEAD`), then merge instead.
   - an older base was merged before → merge again.
   - Local changes are stashed and re-applied afterwards. Trivial conflicts (whitespace-only differences, or only one side changed) are resolved and reported, anything else is left for the user.
5. Runs `pre-commit install`.
6. LFS hardening, using the helpers that came in with the base: repo-local `filter.lfs.*` pointing at the absolute `git-lfs` path (`git-lfs-full-path.sh`), and `lfs.<endpoint>.locksverify false` for GitHub remotes (`fix_username.py --fix-lfs-locks-only`).

Flags: `--rebase` / `--merge` force the strategy (rebase rewrites history, so only force it when the user is fine with a later force-push), `--yes` allows overwriting a differing `base`/`empty` remote URL.
The `luckydonald@` part of the remote URLs only matters with several GitHub accounts; set `BASE_GIT_USERNAME` to another user, or empty to drop it.
7. Copies `ai/°base/initial_template.md` to `ai/initial.md` if that doesn't exist yet. A human on a terminal gets `$EDITOR` opened on it; when run by an agent (no terminal) the script prints an `INITIAL_TEMPLATE path=ai/initial.md` line instead.
   In that case print the command to the user (`${EDITOR:-vi} ai/initial.md`) and tell them to send the file with `@ai/initial.md` once they're happy with it. Don't fill in or edit the plan yourself.

## Exit codes and what to do

| Code | Meaning | Do |
|---|---|---|
| 0 | done | Report the summary line. Point to "After Adopting The Base" in `docs/README.md`. |
| 3 | git `user.name`/`user.email` is not `Lucky Lucy` with an email `*@luckydonald.de` or `*@luckylu.cy` (`--fix-user` sets `2.2026._.code@luckydonald.de`); nothing has been changed yet | Ask the user via `AskUserQuestion` whether to fix it (this is only right if they are the owner of the base). Yes → rerun with `--fix-user`. No → rerun with `--keep-user`. |
| 4 | the stash could not be re-applied automatically | The stash is kept. Show the listed files and help resolve them, then `git stash drop`. |
| 5 | an existing `base`/`empty` remote points elsewhere | Show both URLs, ask whether to overwrite, then rerun with `--yes`. |
| 6 | rebase or merge stopped on conflicts | Help resolve, `git rebase --continue` (or commit the merge), then rerun the script. Local changes are in `git stash list`. |
| 2 | this is the base repo itself | Tell the user, nothing to install. |

Never rewrite already existing commits' authors on your own.
If the identity was wrong earlier, mention the "Fix previous commits" recipe in `docs/README.md` and let the user decide.
