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
EXPECTED_EMAIL="2.2026._.code@luckydonald.de"  # what --fix-user sets
# Emails that count as the base author: anything at luckydonald.de or luckylu.cy.
email_ok() { case "$1" in *@luckydonald.de|*@luckylu.cy) return 0 ;; *) return 1 ;; esac; }
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
if [ "$CUR_NAME" = "$EXPECTED_NAME" ] && email_ok "$CUR_EMAIL"; then
  green "OK: git user \"$CUR_NAME\" <$CUR_EMAIL>."
else
  case "$USER_MODE" in
    fix)
      git config --local user.name "$EXPECTED_NAME"
      git config --local user.email "$EXPECTED_EMAIL"
      green "Fixed: repo-local git user is now \"$EXPECTED_NAME\" <$EXPECTED_EMAIL>."
      ;;
    keep)
      note "Keeping git user \"$CUR_NAME\" <$CUR_EMAIL> (expected \"$EXPECTED_NAME\" <*@luckydonald.de or *@luckylu.cy>)."
      ;;
    *)
      red "ERROR: git user is \"$CUR_NAME\" <$CUR_EMAIL>, expected \"$EXPECTED_NAME\" <*@luckydonald.de or *@luckylu.cy>. Fix it if you are me, and I forgot."
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
# --local: a plain `git lfs install` exits non-zero (and would abort us) when a global filter.lfs.* config differs from git-lfs' defaults,
# e.g. an absolute /opt/homebrew/bin/git-lfs. --local --force only (re)writes this repo's own config, never the global ~/.gitconfig;
# the absolute-path filters are set again in step 7.
if command -v git-lfs >/dev/null 2>&1; then
  git lfs install --local --force || note "WARNING: 'git lfs install --local --force' failed, continuing."
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

# ─── 7. LFS hardening (helpers that came in with the base) ──────────────────
# Make the repo-local filter.lfs.* use the absolute git-lfs path (IDE gits run with a restricted PATH),
# and disable LFS lock verification (lfs.<endpoint>.locksverify) for GitHub remotes, which would otherwise fail pushes.
if command -v git-lfs >/dev/null 2>&1; then
  if [ -x scripts/°base/init/git-lfs-full-path.sh ]; then scripts/°base/init/git-lfs-full-path.sh || note "WARNING: git-lfs-full-path.sh failed."; fi
  if [ -f scripts/°base/git/remote/fix_username.py ] && command -v python3 >/dev/null 2>&1; then
    python3 scripts/°base/git/remote/fix_username.py --fix-lfs-locks-only || note "WARNING: fixing LFS lock verification failed."
  fi
fi

# ─── 8. Initial plan template ───────────────────────────────────────────────
# Copy the template to ai/initial.md (never overwriting) and get it edited: open $EDITOR for a human, or tell the agent how.
# A human is detected by a terminal on stdout plus a readable /dev/tty, not by stdin, because `curl … | bash` occupies stdin.
TEMPLATE="ai/°base/initial_template.md"
INITIAL="ai/initial.md"
if [ -f "$TEMPLATE" ] && [ ! -e "$INITIAL" ]; then
  mkdir -p ai
  cp "$TEMPLATE" "$INITIAL"
  note "Created $INITIAL from the template."
  if [ -t 1 ] && { : < /dev/tty; } 2>/dev/null; then
    sh -c "${EDITOR:-nano} \"\$1\"" _ "$INITIAL" < /dev/tty > /dev/tty || note "Editor exited with an error, $INITIAL is still there."
  else
    note "INITIAL_TEMPLATE path=$INITIAL"
    note "Agent: tell the user to fill in the initial plan in $INITIAL (print the command: \`${EDITOR:-nano} $INITIAL\`), and to send it once happy with \`@$INITIAL\`."
  fi
fi

green "Done: $STATUS (branch '$CURRENT_BRANCH')."
note "Next: see 'After Adopting The Base' in docs/README.md (monorepo subfolders, GitHub issue agents)."
