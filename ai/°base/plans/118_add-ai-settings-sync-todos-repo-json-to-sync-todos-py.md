# Add `ai/settings/sync_todos.repo.json` to `sync_todos.py`

**Commit style:** Skill `/commit-with-lplp-style` is active — auto-commit following it for this implementation.

## Context

Todo `9996eda5-960b-41fa-9d26-cc9fb3922fa4`.
Today a project's `path` can only come from the gitignored `ai/settings/sync_todos.local.json`, so every checkout needs it set by hand.
Cancelled todo `359cd2de` ("allow repo-local paths in the global `sync_todos.json`") says to do this instead.
A committed per-repo file lets a repo declare "project X lives in `./` or `./sub/dir`", which is the same on every machine.
Paths outside the repo stay machine-local, because they depend on the folder layout of each user.

## Findings

- `scripts/°base/ai/todos/sync_todos.py` has `load_config(tracked, local, write_local)`.
  It refuses a `path` in the tracked file, auto-adds `null` entries to the local file for unknown projects, then copies `path` / `commit_prefix` onto each `Project`.
- Schemas are pydantic-generated and rewritten by `main()` whenever they differ (`schema_text()`, `local_schema_text()`, `--write-schema`).
- `resolve_roots()` returns 5 paths and a test unpacks exactly 5, so the new paths are derived from `DEFAULT_CONFIG.with_name(...)` instead of widening it.
- `sync()` already prints `[name] skipped, no path …` per project, but gives no hint what to do when all of them are skipped.
- Commit prefix precedence today, lowest to highest:
  1. the top-level `commit_prefix` of `sync_todos.json`,
  2. the `commit_prefix` of the project entry in `sync_todos.json`,
  3. the `commit_prefix` in `sync_todos.local.json`.

## Design

New file `ai/settings/sync_todos.repo.json` with schema `ai/settings/sync_todos-repo.schema.json`:

```json
{
  "$schema": "./sync_todos-repo.schema.json",
  "projects": {
  }
}
```

- `projects` maps a project name (as in `sync_todos.json`) to `{"path": ..., "commit_prefix": ...}`, same shape as the local file.
- A repo `path` must be `"."` or start with `"./"`, and must not contain a `..` segment.
  The JSON schema carries a pattern (`^(?!.*(^|/)\.\.(/|$))\.(/.*)?$`), and a pydantic validator enforces the same on load, as the schema is only advisory.
  Absolute paths and `~` are rejected.
  Relative paths resolve against the git root, like local ones.
- Precedence for `path` and `commit_prefix`, lowest to highest: `sync_todos.json` (the committed tag mapping, which never holds a `path`), then the new `sync_todos.repo.json`, then `sync_todos.local.json`.
  For `commit_prefix` that means top-level of `sync_todos.json` < project entry in `sync_todos.json` < repo file < local file.
  A local value that is not `null` wins; a local `null` (including the auto-generated ones) falls through to the repo value, otherwise the repo file would never take effect.
  Consequence: a local `null` can no longer switch off a project the repo file enables; a non-null local `path` is the override.
- The empty file is created by `main()` when it is missing, and committed on its own as `{commit_prefix}[TODOs] added sync_todos.repo.json.` (only that path; skipped with `--dry-run`, written but not committed with `--no-git`).
  It lives in `ensure_repo_file()`, not in `load_config()`, so `load_config` stays free of git side effects.
- `load_config` gets an optional `repo: Path | None = None` argument.
  Projects covered by the repo file are not auto-added as `null` to the local file.
  Repo entries naming a project that is not in the tracked file are reported on stderr like the stale local ones.
- When `sync()` ends with every selected project skipped for a `null` path, print an instruction to add this repository (and/or its subprojects) to `sync_todos.repo.json`, with an example entry using a project name from the tracked file.

## Changes

- `scripts/°base/ai/todos/sync_todos.py`: `RepoProject` / `RepoConfig` models, `repo_schema_text()`, `ensure_repo_file()`, extended `load_config`, the "all skipped" hint, `--repo-config` CLI option, `--write-schema` and the schema auto-refresh cover the third schema, module docstring.
- `ai/settings/sync_todos-repo.schema.json` generated, `ai/settings/sync_todos.repo.json` created by the first run.
- `ai/settings/README.md` and the `sync-todo-mcp` skill (which mentions the local file): describe the repo file and the precedence.
- `scripts/°base/ai/todos/tests/test_sync_todos.py`: new tests below.
- Todo file: tick `9996eda5`; the cancelled `359cd2de` already is `[-]` on CalDAV, so it needs no action.

## Tests

- Repo path is used when the local one is `null`; a non-null local path wins; commit prefix precedence top-level `sync_todos.json` < its project entry < repo file < local file.
- `..`, absolute, `~` and `foo/bar` (no `./`) paths are rejected, `"."` and `./sub` accepted.
- Projects with a repo path are not added to the local file as `null`.
- `ensure_repo_file` creates the exact empty text and commits it in a temp git repo, is a no-op when the file exists, writes without commit for `--no-git`, and writes nothing for `--dry-run`.
- The all-skipped hint is printed, and not printed when at least one project has a path.
- The generated repo schema equals the file on disk (like the existing local-schema test).

## Verification

- `uv run --with pytest --with 'pydantic>=2.6' --with 'mcp>=2.3' --with python-dotenv pytest scripts/°base/ai/todos/tests` plus the repo's unittest command from `ai/°base/AGENTS.md`.
- `uv run scripts/°base/ai/todos/sync_todos.py --dry-run -v` shows no change, then a real run creates and commits the empty repo file once and nothing on the second run.
- Temporarily remove the `base` path from the local file to see the hint, then restore it.

## Open decision

The base repo is merged into other repos, so the empty `sync_todos.repo.json` this creates in base would ship to them; it holds no entries, so there is nothing to conflict on unless a consumer fills it in.
Base itself therefore keeps it empty and uses its `path: "."` from the local file.
