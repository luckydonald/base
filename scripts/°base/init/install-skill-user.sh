#!/usr/bin/env bash
# scripts/°base/init/install-skill-user.sh
#
# Copies the `install-base` skill, plus the installer script it runs, into the user's Claude profile,
# so it also works in repositories that don't have the base checked out (yet).
# A copy, not a symlink: a symlink would dangle once this checkout moves or isn't there.
#
# Usage: install-skill-user.sh [--codex]
#   --codex  Also install into ~/.agents/skills (Codex).
#
# Target: ${CLAUDE_CONFIG_DIR:-$HOME/.claude}/skills/install-base/
# Idempotent: unchanged files are left alone.

set -euo pipefail

REPO_ROOT="$(git -C "$(dirname "$0")" rev-parse --show-toplevel)"
SKILL_SRC="$REPO_ROOT/ai/skills/install-base/SKILL.md"
SCRIPT_SRC="$REPO_ROOT/scripts/°base/init/install-base.sh"
TARGETS=("${CLAUDE_CONFIG_DIR:-$HOME/.claude}/skills/install-base")
[ "${1-}" = "--codex" ] && TARGETS+=("$HOME/.agents/skills/install-base")

for src in "$SKILL_SRC" "$SCRIPT_SRC"; do
  [ -f "$src" ] || { echo "Missing source file: $src" >&2; exit 1; }
done

for dest in "${TARGETS[@]}"; do
  mkdir -p "$dest"
  for src in "$SKILL_SRC" "$SCRIPT_SRC"; do
    target="$dest/$(basename "$src")"
    if [ -f "$target" ] && [ ! -L "$target" ] && cmp -s "$src" "$target"; then
      echo "Unchanged: $target"
    else
      rm -f "$target"
      cp "$src" "$target"
      echo "Installed: $target"
    fi
  done
  chmod +x "$dest/install-base.sh"
done
