# Add `ai/settings/sync_todos.repo.json` to `sync_todos.py`

**Commit style:** Skill `/commit-with-lplp-style` is active — auto-commit following it for this implementation.

## Context

Todo `9996eda5-960b-41fa-9d26-cc9fb3922fa4`.
Today a project's `path` can only come from the gitignored `ai/settings/sync_todos.local.json`, so every checkout needs it set by hand.
Cancelled todo `359cd2de` ("allow repo-local paths in the global `sync_todos.json`") says to do this instead.
A committed per-repo file lets a repo carry its own settings, so that usually no local file is needed any more.
Paths outside the repo stay machine-local, because they depend on the folder layout of each user.

## Findings

- `scripts/°base/ai/todos/sync_todos.py` has `load_config(tracked, local, write_local)`.
  It refuses a `path` in the tracked file, auto-adds `null` entries to the local file for unknown projects, then copies `path` / `commit_prefix` onto each `Project`.
- Schemas are pydantic-generated and rewritten by `main()` whenever they differ (`schema_text()`, `local_schema_text()`, `--write-schema`).
- `resolve_roots()` returns 5 paths and a test unpacks exactly 5, so the new paths are derived from `DEFAULT_CONFIG.with_name(...)` instead of widening it.
- `sync()` already prints `[name] skipped, no path …` per project, but gives no hint what to do when all of them are skipped.
- Commit prefix precedence today, lowest to highest: the top-level `commit_prefix` of `sync_todos.json`, then the project entry's `commit_prefix` in `sync_todos.json`, then the one in `sync_todos.local.json`.

## Design

### The repo file

`ai/settings/sync_todos.repo.json`, committed, with schema `ai/settings/sync_todos-repo.schema.json`.
It can set everything that the committed `sync_todos.json` ("global") and the local file can set, combined:

- Top-level: `url_env`, `token_env`, `env_file`, `commit_prefix`, `calendar_id`, all optional.
- `projects`: a dictionary from project name to settings, like in the local file.
  The settings are `tags`, `todo_file`, `commit_prefix`, `path` and `no-add-to-repo-hint` (see below), all optional.
  An entry whose name exists in `sync_todos.json` overrides just the fields it sets; an unknown name adds a new project (then `tags` is required).

The file is created empty by the script when missing:

```json
{
  "$schema": "./sync_todos-repo.schema.json",
  "projects": {
  }
}
```

### Layering

Lowest to highest: `sync_todos.json`, then `sync_todos.repo.json`, then `sync_todos.local.json`.
This holds for every field, including `commit_prefix` (top-level `sync_todos.json` < project entry in `sync_todos.json` < repo top-level < repo project entry < local).
A local value that is `null` (including the auto-generated ones) falls through to the repo value, otherwise the repo file would never take effect.
Consequence: a local `null` can no longer switch off a project the repo file enables; a non-null local `path` is the override.
After merging, the `Config` validators (unique names, no tag shared between projects) run again on the result.

### Repo path rule

A `path` in the repo file must be `"."` or start with `"./"`, and must not contain a `..` segment.
Absolute paths and `~` are rejected.
The JSON schema carries a pattern (`^(?!.*(^|/)\.\.(/|$))\.(/.*)?$`), and a pydantic validator enforces the same on load, as the schema is only advisory.
Relative paths resolve against the git root, like local ones.

### Creating the file

`ensure_repo_file()` in `main()`, not in `load_config()`, so loading has no git side effects.
It writes the empty file when missing and commits only that path as `{commit_prefix}[TODOs] added sync_todos.repo.json.`.
`--dry-run` writes nothing, `--no-git` writes without committing.

### Migrating repo-internal local paths

A local `path` is repo-internal when, after `~` expansion and resolving, it lies inside the git root and has no `..` left over (`"."` or a relative path counts too).

- New flag `--migrate-local-paths`: for every such project whose repo entry has no `path` yet, write `./<relative>` to the repo file's project entry (creating the entry with just `name` and `path` if needed) and set the local `path` back to `null`.
  The local `commit_prefix` is moved the same way when set.
  A project whose repo entry already has a `path` is left alone and reported.
  The repo file is committed on its own as `{commit_prefix}[TODOs] moved local project paths into sync_todos.repo.json for <projects>.`; the local file is gitignored.
- Without the flag, for each migratable project not silenced, print a hint that tells the user to either
  - add the path to the repo file (absolute path of `sync_todos.repo.json` printed), as `"<name>": { "path": "./<relative>" }` under `projects`, which `--migrate-local-paths` does automatically, or
  - silence the hint by setting `"no-add-to-repo-hint": true` in that project's entry in any one of the three files, and all three absolute paths are printed: `sync_todos.json` (there the entry is a list item, so `{ "name": "<name>", "no-add-to-repo-hint": true, … }`), `sync_todos.repo.json` and `sync_todos.local.json` (both `"<name>": { "no-add-to-repo-hint": true, … }` under `projects`).
- `no-add-to-repo-hint` is a per-project, optional field (missing means `false`), added to the project models of all three files (alias, so the JSON key has hyphens) and thus to all three schemas.
  A project is silenced when any of the three files sets it to true for it.

### Nothing to write

When `sync()` ends with every selected project skipped for a `null` path, print an instruction to add this repository (and/or its subprojects) to `sync_todos.repo.json`, with an example entry using a project name from the tracked file.

### Other

- `load_config` gets an optional `repo: Path | None = None` argument.
  Projects that have a path from the repo file are not auto-added as `null` to the local file.
  Repo project names that are neither in `sync_todos.json` nor fully defined are an error; local names unknown to the merged config keep the existing stale warning.
- New CLI option `--repo-config PATH`, mirroring `--config` and `--local-config`.

## Changes

- `scripts/°base/ai/todos/sync_todos.py`: `RepoProject` / `RepoConfig` models, `repo_schema_text()`, `ensure_repo_file()`, merge in `load_config`, migration function and flag, both hints, `--repo-config`, `--write-schema` and the schema auto-refresh cover the third schema, module docstring.
- `ai/settings/sync_todos-repo.schema.json` generated, `ai/settings/sync_todos.repo.json` created by the first run; the other two schemas regenerate because of the new hint field.
- `ai/settings/README.md` and the `sync-todo-mcp` skill (which mention the local file): describe the repo file, layering, migration and hint.
- `scripts/°base/ai/todos/tests/test_sync_todos.py`: new tests below.
- Todo file: tick `9996eda5`; the cancelled `359cd2de` already is `[-]` on CalDAV, so it needs no action.

## Tests

- Layering of `path`, `commit_prefix`, `calendar_id` and the other top-level fields: repo beats `sync_todos.json`, non-null local beats repo, local `null` falls through.
- A repo `projects` entry with an unknown name and `tags` adds a project; without `tags` it errors; duplicate tags across projects still error.
- Repo `path` validation: `..`, absolute, `~` and `foo/bar` rejected, `"."` and `./sub` accepted.
- Projects with a repo path are not added to the local file as `null`.
- `ensure_repo_file`: exact empty text, committed in a temp git repo, no-op when present, no commit with `--no-git`, nothing with `--dry-run`.
- Migration: inside-repo absolute / `~` / relative local paths move to `./…` and local becomes `null`; outside-repo paths stay; existing repo path is not overwritten; commit is made.
- Hint: shown per migratable project when the flag is off, naming the repo file and all three file paths; silenced per project by `no-add-to-repo-hint` in each of the three files; other projects still show it; not shown with the flag.
- All-skipped instruction printed, and not printed when at least one project has a path.
- Generated repo schema equals the file on disk, like the existing local-schema test.

## Verification

- `uv run --with pytest --with 'pydantic>=2.6' --with 'mcp>=2.3' --with python-dotenv pytest scripts/°base/ai/todos/tests` plus the repo's unittest command from `ai/°base/AGENTS.md`.
- `uv run scripts/°base/ai/todos/sync_todos.py --dry-run -v` writes nothing; a real run creates and commits the empty repo file once and nothing on the second run, and prints the migration hint for `base` (`path: "."`).
- Run `--migrate-local-paths --project base` on a copy of the local file (`--local-config`, `--repo-config` pointing into the scratchpad) to check the result without touching the real files.

## Open decision

The base repo is merged into other repos, so the empty `sync_todos.repo.json` this creates in base would ship to them.
It holds no entries, so there is nothing to conflict on until a consumer fills it in.
Base itself keeps it empty by default; running `--migrate-local-paths` in base would put `base: ./` into it, which is wrong for consumers, so that is not done here.
