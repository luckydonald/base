# Plan: Add `.run/.subprojectIgnore` to skip run configs when linking into subprojects

**Commit style:** Skill `/commit-with-lplp-style` is active — auto-commit following it for this implementation.
**Code style:** Skill `/code-style` (py + md) is loaded — Python needs full type annotations, no `_` prefixed names, and `# end def`/`# end if`/... block endings; prose in markdown is not hard-wrapped.

## Context

Todo `58a06dbd-33b8-48fe-b392-9f5a67b935cc` (`ai/todo.md`): "have a `.run/.subprojectIgnore` file, defining files to not link into subprojects."

`scripts/°base/init/link_subproject.py` symlinks every `<git_root>/.run/*.run.xml` into each subproject's `.run/`, both on the manual run (`link_run_configs()` from `main()`) and in the post-merge/post-rewrite hook (`resync_all()` -> `link_run_configs(backup=False)`).
There is no way to say "this run config only makes sense at the repo root", such as the base's own `🅱️✨1🏷️ _ Tag HEAD as backup.run.xml`.
The outcome: a root file `.run/.subprojectIgnore` lists names or patterns of `.run/` files that are never linked into subprojects.

## Findings

- `link_run_configs()` (`link_subproject.py`) globs `run_dir.glob("*.run.xml")` and calls `link_path(rel, git_root / rel, backup=backup)` for each, so the filter belongs there.
- `prune_dangling_run_links()` only removes dangling symlinks pointing into the root `.run/`.
  A link that was created earlier and is now ignored is not dangling, so it stays untouched, which keeps the resync create-only and non-destructive as documented.
- Tests live in `scripts/°base/tests/test_link_subproject.py` (class around line 281+, fixture with a root `.run/` holding `a.run.xml` and an emoji-named config, resync assertions via `committed_paths()`).
- Docs: `docs/README.md` section "Monorepo subfolders: per-subfolder `.claude/`" describes the resync; the module header of `link_subproject.py` describes the `.run` linking.

## Design

- File location: `<git_root>/.run/.subprojectIgnore`, tracked, only the root one is read (per-subproject overrides are out of scope).
- Format: one pattern per line, `#` starts a comment line, blank lines are skipped, surrounding whitespace is stripped.
  Patterns are matched against the file name (not the path) with `fnmatch.fnmatchcase`, so `*.local.run.xml` and exact names both work, and emoji or spaces in names are fine.
  A trailing `\r` is stripped; no negation (`!`) support, to keep it simple.
- A missing or unreadable file means "ignore nothing", so existing behaviour does not change.
- The `.subprojectIgnore` file itself is not matched by `*.run.xml`, so it is never linked.
- Already existing links of ignored files are left alone (a printed hint is not needed), consistent with the non-destructive resync.

### Code (`scripts/°base/init/link_subproject.py`)

1. New `read_subproject_ignore() -> list[str]`: reads `git_root / ".run" / ".subprojectIgnore"`, returns the patterns, `[]` when missing.
2. New `is_subproject_ignored(name: str, patterns: list[str]) -> bool` using `fnmatch.fnmatchcase`.
3. `link_run_configs()`: read the patterns once, skip (with a `print` to stdout like the other skip messages) any `f.name` that matches.
4. Update the module header comment to mention the ignore file.

### Tests (`scripts/°base/tests/test_link_subproject.py`)

- A pattern list with comments and blank lines skips an exact name and a glob match on the manual run path, while others are still linked.
- The resync hook path (`--resync`) does not create links for a newly added ignored root config, and still creates the non-ignored one.
- A missing `.subprojectIgnore` keeps the current behaviour (existing tests already cover it).
- An already existing link of a now-ignored file is left in place.
- Emoji-named file matched by a glob.

### Docs

- `docs/README.md`: one short paragraph after the resync paragraph describing `.run/.subprojectIgnore` (format, root-only, existing links are not removed).
- Optionally add the file with a short header comment to the repo's own `.run/` as an example, containing just comments, so the format is discoverable.

## Verification

- `uv run --project scripts/°base python -m unittest discover -s scripts/°base/tests -v` passes in full.
- Manual smoke test in a scratch monorepo fixture is covered by the tests above (no real subprojects exist in this repo).
- Then follow the todo-loop close steps: tick the checkbox in `ai/todo.md`, `complete_todo(calendar_id=7, uid=58a06dbd-33b8-48fe-b392-9f5a67b935cc)`, re-sync with `uv run scripts/sync_todos.py --project base` if applicable, tag the prior HEAD with `scripts/tag_backup.py`, and fold the `ai:` auto-commits into one work commit (`[base] link_subproject: ai: Run: Added `.run/.subprojectIgnore` ...`), verifying `git diff <bak-tag> HEAD` is empty.
