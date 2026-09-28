Now I have complete findings for both parts.

## 1. Skill documentation conventions

Skills live at `/home/user/git/luckydonald/DockerTgBot/ai/skills/<skill-name>/` (this is the canonical source; presumably synced/symlinked into `.claude/skills/`). No root-level `.claude/skills/` exists directly — the `ai/skills/` tree is it.

**Frontmatter format** — YAML with just `name` and `description`, both double-quoted strings, no `metadata` block on skill files (metadata blocks are used on memory files, not skills):

```yaml
---
name: "bugsink-setup"
description: "Wire up Sentry-compatible error tracking (Bugsink or Sentry SaaS) for a backend and/or frontend: SDK init, environment variables, release/build tagging, sourcemap upload, and — critical for self-hosted Bugsink — a same-origin tunnel so CORS/mixed-content doesn't silently swallow browser errors. Currently covers Python and Rust backends and Vue frontends, with more stacks addable over time. Use this whenever the user asks to add error monitoring, crash reporting, exception tracking, hook up Sentry or Bugsink, or wants to see JS/Python/Rust errors from production — even if they only mention one side of the stack, or say things like 'track errors in prod' or 'set up crash reporting' without naming Bugsink/Sentry explicitly."
---
```

A minimal single-file example (`code-style/SKILL.md`):

```yaml
---
name: "code-style"
description: "Apply project code-style rules when writing, modifying, or reviewing code. Detect the languages used by the files in scope and load only their matching references; Languages: py, ts, vue, md."
---
```

**Description convention**: always ends with an explicit "Use this whenever…"/trigger-phrase clause covering both direct asks and oblique phrasings — this is the trigger text the harness matches on.

**Layout patterns** (both exist, chosen by breadth of content):
- Single-file: `commit-with-lplp-style/SKILL.md`, `code-style/SKILL.md` (dispatcher only, or references/ for language-specific detail).
- `SKILL.md` (dispatcher) + `references/*.md` (one file per sub-topic): `bugsink-setup/` has `references/{python,rust,vue,monorepo-deploys}.md`; `code-style/` has `references/{py,ts,vue,md,yarn}.md`.

**Tone/structure**: `SKILL.md` itself stays a thin dispatcher/index — a short intro explaining the domain gotchas, then a bulleted list pointing to each `references/<name>.md` with a one-line summary of what's in it, plus explicit instructions not to read reference files that don't apply and how to add a new reference file if a stack/language is missing. It also has an "Orient yourself before writing anything" section telling the agent to locate real project files (entrypoints, settings patterns) rather than assuming paths. File:line citations aren't used inside SKILL.md itself (it stays project-agnostic); concrete file:line references belong in the reference guides / the eventual implementation, not the skill dispatcher.

## 2. The `.env`/`.env.example` merge script

**Path**: `/home/user/git/luckydonald/DockerTgBot/scripts/°base/env/merge-env.py` (368 lines), also reachable via a symlink `scripts/°base/merge_env.py`.

**Docstring** (verbatim):
```
Merge `.env.example` into `.env`, additively (never overwrites a filled value, never
removes or replaces existing comment lines — only fills empty values and appends new keys or
missing description lines). A timestamped backup of the file being written is made first.

Piping `.env`-shaped text into the script together with `--example` merges that text into
`.env.example` itself instead, without the append-only restriction (it's a template, not live
secrets), and prints a unified diff of the result.

This script never prints existing values or comment bodies in the default mode — only key
names and the literal defaults being filled or added — since an AI agent may be the one running
it and must not be able to read `.env` content through its own output.

Usage:
    python3 scripts/°base/env/merge-env.py [TARGET_DIR] [--dry-run]
    cat new_vars.txt | python3 scripts/°base/env/merge-env.py [TARGET_DIR] --example [--dry-run]
```

**CLI args** (argparse): `target_dir` (positional, optional, default `.`), `--example` (merge piped stdin into `.env.example` instead of default `.env.example → .env` mode), `--dry-run` (print report without writing).

**Behavior summary**: stdlib-only, no dependencies. Parses `.env`/`.env.example` text preserving structure (blank lines, comments-as-descriptions attached to the following key, arbitrary structural blocks). Default mode merges `.env.example` → `.env`: fills empty values, appends missing description/comment lines, inserts brand-new keys positioned right after their nearest predecessor in source order — never overwrites an already-filled value. `--example` mode (requires piped stdin) merges into `.env.example` itself with `overwrite_values=True` and prints a `difflib.unified_diff`. Every write is preceded by `write_backup()`, which creates `<path>.<YYYY-MM-DD_HH-MM-SS>.bak`. Report lines are printed per key (e.g. `"- KEY value change: filled with the default 'x'."`, `"- KEY no value change: was already filled."`) and never leak actual existing values/comments — only key names and newly-filled/added literals. Stdin detection uses `select.select` (not just `isatty()`) per code comment, "since a harness may run this script with stdin attached to a closed fd/`/dev/null`."

**`.bak` protection**: `ai/settings/settings.json` (line 367) has `{"type": "read", "path": "**/*.env*.bak"}` as a deny rule so agents can't read these backups, mirroring existing `.env` protection. `.gitignore` already covers `*.bak` broadly (lines 52, 113, 743-744), so backups are git-ignored.

**Documentation status — not yet referenced anywhere it needs to be**:
- No `CLAUDE.md` in the repo (root or any subproject) mentions `merge-env.py` or `merge_env.py`.
- The only references are transient session artifacts: `sync_todo/ai/query.md`, `sync_todo/ai/output/agents/029.a69bdd7640f4b1cb3/result.md`, and the plan file `sync_todo/ai/plans/026_env-example-env-merge-script.md` that specified/built it (plus duplicates under `.claude/worktrees/fix-bug/sync_todo/...`).
- Memory file confirms it: `/home/user/.confuig/claude/accounts/private/projects/-home-user-git-luckydonald-DockerTgBot/memory/project_merge_env_script.md`, description: `"scripts/°base/env/merge-env.py: generic .env.example → .env additive merger built 2026-09-28, meant to be cherry-picked into base/base later"`. Its "How to apply" section explicitly notes `sync_todo/` "still has no `.env.example` at all as of 2026-09-28" and that this script should be pointed at instead of writing ad hoc merge logic.

**Conclusion**: the script exists and is functionally complete but is undocumented in any `CLAUDE.md` — only tracked in the private memory file. If your new MCP-server skill's setup flow touches `sync_todo`'s `.env`/`.env.example`, it would be worth citing this script by its path (`scripts/°base/env/merge-env.py`, relative to repo root, i.e. `../scripts/°base/env/merge-env.py` from `sync_todo/`) since nothing else currently documents its existence for future readers of `CLAUDE.md`.