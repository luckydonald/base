#!/usr/bin/env bash
# scripts/°base/init/link-subproject-claude.sh
#
# Idempotent per-subfolder setup for the monorepo case: creates relative
# symlinks at <cwd>/.claude, <cwd>/.codex, <cwd>/ai/settings,
# <cwd>/ai/references, <cwd>/ai/skills and <cwd>/.mcp.json pointing at their
# monorepo-root counterparts, each <cwd>/.run/*.run.xml pointing at its
# monorepo-root counterpart, an <cwd>/AGENTS.md -> CLAUDE.md symlink (moving
# any pre-existing AGENTS.md into CLAUDE.md first, mirroring the root
# layout), an empty `.gitkeep` in each of the ai/{errors,output/{agents,
# explore},plans} scratch dirs, and seeds <cwd>/ai/query.md and
# <cwd>/CLAUDE.md from templates when they don't exist yet (copied, not
# symlinked, since they're meant to diverge per subproject). This lets
# Claude Code and Codex find the shared hooks/perms/MCP config when launched
# from inside a subfolder of a monorepo that has the `base` repo merged at
# its top level.
#
# Because <cwd>/.claude is a symlink to the monorepo root's .claude, Claude
# Code's own native project-identity resolution (used for its auto-memory
# and session storage under ~/.claude/projects/<encoded>/) collapses back to
# the monorepo root instead of using this subfolder — memories saved from a
# session started here would otherwise silently attach to the wrong project.
# This script also seeds <cwd>/.claude-project.rc (named .rc, not .env, so
# it isn't swallowed by this repo's blanket `**/*.env*` .gitignore rule),
# exporting CLAUDE_CODE_PROJECT_DIR_NAME (and a CLAUDE_CONFIG_DIR
# passthrough, which Claude Code requires to be set for the override to take
# effect) pinned to a slug unique to this subfolder. **Source it before
# launching Claude Code here** — e.g. `source .claude-project.rc && claude`
# (or whichever launcher alias) — otherwise memory/session storage will
# attach to the parent project instead of this subfolder.
#
# Run once from inside the subfolder:
#
#   cd monorepo/some_project
#   ../scripts/°base/init/link-subproject-claude.sh
#
# Safe to run multiple times — already-correct symlinks/seeded files are
# left alone. Anything pre-existing that would be clobbered by a symlink is
# moved aside first, as `{name}.YYYY-MM-DD_HH-MM-SS.bak.{ext}` (via `git mv`
# when tracked). New symlinks/seeded files (and moved files) are `git add`ed.

set -euo pipefail

sub_dir="$(pwd -P)"
git_root="$(cd "$(git rev-parse --show-toplevel)" && pwd -P)"
root_claude="$git_root/.claude"

if [ "$sub_dir" = "$git_root" ]; then
  echo "$sub_dir is the git root — no symlinks needed." >&2
  exit 0
fi

if [ ! -d "$root_claude" ]; then
  echo "no $root_claude — did you merge base/base at the repo root?" >&2
  exit 1
fi

realpath_of() {
  python3 -c 'import os, sys; print(os.path.realpath(sys.argv[1]))' "$1"
}

relpath_of() {
  # relpath_of <target> <from_dir>
  python3 -c 'import os, sys; print(os.path.relpath(sys.argv[1], sys.argv[2]))' "$1" "$2"
}

is_tracked() {
  git -C "$sub_dir" ls-files --error-unmatch -- "$1" >/dev/null 2>&1
}

# backup_path <rel-to-sub_dir> — moves an existing path aside as
# {stem}.YYYY-MM-DD_HH-MM-SS.bak{ext}, using `git mv` if tracked.
backup_path() {
  local rel="$1"
  local timestamp
  timestamp="$(date +%Y-%m-%d_%H-%M-%S)"
  local bak_rel
  bak_rel="$(python3 -c '
import os, sys
rel, timestamp = sys.argv[1], sys.argv[2]
d, base = os.path.split(rel)
stem, ext = os.path.splitext(base)
print(os.path.join(d, f"{stem}.{timestamp}.bak{ext}"))
' "$rel" "$timestamp")"

  if is_tracked "$rel"; then
    git -C "$sub_dir" mv -- "$rel" "$bak_rel"
  else
    mv -- "$sub_dir/$rel" "$sub_dir/$bak_rel"
  fi
  echo "backed up $sub_dir/$rel -> $sub_dir/$bak_rel" >&2
}

# link_path <rel> <source> — symlinks <sub_dir>/<rel> -> <source>,
# backing up whatever is already at the target if it's not already the
# right symlink.
link_path() {
  local rel="$1"
  local source="$2"
  local target="$sub_dir/$rel"
  local target_dir
  target_dir="$(dirname "$target")"

  if [ ! -e "$source" ]; then
    echo "no $source — skipping $rel" >&2
    return
  fi

  mkdir -p "$target_dir"

  if [ -L "$target" ]; then
    if [ "$(realpath_of "$target")" = "$(realpath_of "$source")" ]; then
      echo "$target already linked to $source"
      return
    fi
    echo "$target is a symlink but points elsewhere ($(readlink "$target")) — backing up." >&2
    backup_path "$rel"
  elif [ -e "$target" ]; then
    echo "$target exists and is not a symlink — backing up." >&2
    backup_path "$rel"
  fi

  local rel_link
  rel_link="$(relpath_of "$source" "$target_dir")"
  ln -s "$rel_link" "$target"
  echo "linked $target -> $rel_link"
  git -C "$sub_dir" add -- "$rel"
}

# link_shared <rel> — symlinks <sub_dir>/<rel> -> <git_root>/<rel>.
link_shared() {
  local rel="$1"
  link_path "$rel" "$git_root/$rel"
}

# copy_if_missing <rel> <template_name> — seeds <sub_dir>/<rel> from the
# shared template if it doesn't exist yet. Never touches an existing file.
copy_if_missing() {
  local rel="$1"
  local template_name="$2"
  local source="$git_root/scripts/°base/init/templates/$template_name"
  local target="$sub_dir/$rel"

  if [ -e "$target" ] || [ -L "$target" ]; then
    echo "$target already exists — leaving it alone."
    return
  fi

  if [ ! -e "$source" ]; then
    echo "no $source — skipping $rel" >&2
    return
  fi

  mkdir -p "$(dirname "$target")"
  cp -- "$source" "$target"
  echo "seeded $target from $source"
  git -C "$sub_dir" add -- "$rel"
}

# link_run_configs — symlinks each <git_root>/.run/*.run.xml individually
# into <sub_dir>/.run/, so consuming repos can add their own local-only
# run configs alongside the shared ones without a whole-directory symlink.
link_run_configs() {
  local run_dir="$git_root/.run"
  local f rel

  if [ ! -d "$run_dir" ]; then
    echo "no $run_dir — skipping .run configs" >&2
    return
  fi

  for f in "$run_dir"/*.run.xml; do
    [ -e "$f" ] || continue
    rel=".run/$(basename "$f")"
    link_shared "$rel"
  done
}

# touch_scratch_gitkeeps — creates empty `.gitkeep` markers in the ai/
# scratch dirs, creating the dirs if needed, so the otherwise-empty
# directories exist in a fresh checkout.
touch_scratch_gitkeeps() {
  local rel target
  for rel in "ai/errors" "ai/output/agents" "ai/output/explore" "ai/plans"; do
    target="$sub_dir/$rel/.gitkeep"
    if [ -e "$target" ]; then
      echo "$target already exists — leaving it alone."
      continue
    fi
    mkdir -p "$sub_dir/$rel"
    touch "$target"
    echo "touched $target"
    git -C "$sub_dir" add -- "$rel/.gitkeep"
  done
}

# link_agents_claude — ensures <sub_dir>/AGENTS.md -> CLAUDE.md, moving a
# pre-existing real AGENTS.md into CLAUDE.md first (like the repo root).
link_agents_claude() {
  local agents="$sub_dir/AGENTS.md"
  local claude="$sub_dir/CLAUDE.md"

  if [ -L "$agents" ]; then
    if [ -e "$claude" ] && [ "$(realpath_of "$agents")" = "$(realpath_of "$claude")" ]; then
      echo "$agents already linked to $claude"
      return
    fi
    echo "$agents is a symlink but points elsewhere ($(readlink "$agents")) — backing up." >&2
    backup_path "AGENTS.md"
  elif [ -e "$agents" ]; then
    if [ -e "$claude" ]; then
      echo "$agents and $claude both exist — backing up $agents." >&2
      backup_path "AGENTS.md"
    else
      echo "moving $agents -> $claude" >&2
      if is_tracked "AGENTS.md"; then
        git -C "$sub_dir" mv -- "AGENTS.md" "CLAUDE.md"
      else
        mv -- "$agents" "$claude"
      fi
    fi
  fi

  if [ ! -e "$claude" ]; then
    echo "no $claude — nothing to point AGENTS.md at, skipping." >&2
    return
  fi

  ln -s "CLAUDE.md" "$agents"
  echo "linked $agents -> CLAUDE.md"
  git -C "$sub_dir" add -- "AGENTS.md" "CLAUDE.md"
}

# project_dir_name_slug <rel> — a stable, Claude-Code-safe slug (matching
# ^[A-Za-z0-9_-]{1,64}$) unique to this subfolder within the monorepo, for
# CLAUDE_CODE_PROJECT_DIR_NAME. Non-matching characters become `-`; if the
# git-root-basename + sanitized relative path would exceed 64 chars, it's
# truncated and suffixed with an 8-hex-char sha1 of the absolute path to
# avoid collisions.
project_dir_name_slug() {
  local rel="$1"
  python3 -c '
import hashlib, os, re, sys
git_root, rel = sys.argv[1], sys.argv[2]
raw = f"{os.path.basename(git_root)}-{rel}"
slug = re.sub(r"[^A-Za-z0-9_-]", "-", raw).strip("-")
if len(slug) > 64:
    digest = hashlib.sha1(os.path.join(git_root, rel).encode()).hexdigest()[:8]
    slug = f"{slug[:55]}-{digest}"
print(slug)
' "$git_root" "$rel"
}

# seed_claude_project_env — writes <sub_dir>/.claude-project.rc (once; never
# overwrites an existing one) so sourcing it before launching Claude Code
# here pins CLAUDE_CODE_PROJECT_DIR_NAME to a slug unique to this subfolder,
# working around Claude Code's own project-identity resolution collapsing
# back to the monorepo root through the symlinked .claude (see header).
# Named .rc rather than .env so it isn't swallowed by this repo's blanket
# `**/*.env*` .gitignore rule.
seed_claude_project_env() {
  local target="$sub_dir/.claude-project.rc"
  if [ -e "$target" ]; then
    echo "$target already exists — leaving it alone."
    return
  fi

  local rel
  rel="$(relpath_of "$sub_dir" "$git_root")"
  local slug
  slug="$(project_dir_name_slug "$rel")"

  cat > "$target" <<EOF
# Generated by link_subproject.sh — source before launching Claude Code here:
#   source .claude-project.rc && claude
# Without this, Claude Code's native memory/session storage attaches to the
# monorepo root instead of this subfolder (its .claude is a symlink there).
export CLAUDE_CONFIG_DIR="\${CLAUDE_CONFIG_DIR:-\$HOME/.claude}"
export CLAUDE_CODE_PROJECT_DIR_NAME="$slug"
EOF
  echo "seeded $target (CLAUDE_CODE_PROJECT_DIR_NAME=$slug)"
  git -C "$sub_dir" add -- ".claude-project.rc"
}

link_shared ".claude"
link_shared ".codex"
link_shared "ai/settings"
link_shared "ai/references"
link_shared "ai/skills"
link_shared ".mcp.json"
link_run_configs
touch_scratch_gitkeeps
copy_if_missing "ai/query.md" "query.md"
copy_if_missing "CLAUDE.md" "CLAUDE.md"
link_agents_claude
seed_claude_project_env
