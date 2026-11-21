# Plan: `bak_push.py` for repo use, with layered `backup_tags` settings

## Context

`fedora_bak_2026/scripts/bak_push.py` pushes a repo's local `bak/*` tags (made by `scripts/°base/tag_backup.py`) to a private shared backup repo.
It has hardcoded constants (`BAK_URL`, a persistent `bak` remote), a `--all` multi-repo mode, and no cleanup afterwards.
For use inside this base repo it must read its target from layered settings and optionally delete the pushed tags locally and on `origin`.

Decisions confirmed with the user:

- Settings files are `ai/settings/settings.json` (tracked, holds the defaults), `ai/settings/settings.repo.json` (optional, committed, **read only if it exists, never created**), `ai/settings/settings.local.json` (gitignored), then env vars.
- Key names are `backup_tags.repo` and `backup_tags.delete_tags.{local,origin}`.

## Settings

Defaults, added to the tracked `ai/settings/settings.json`:

```json
"backup_tags": {
  "repo": "https://luckydonald@github.com/luckydonald/bak.git",
  "delete_tags": {"local": false, "origin": false}
}
```

Merge order, the latest overwriting keys of the former only if set: `settings.json`, `settings.repo.json`, `settings.local.json`, env.
The merge is a deep merge limited to the `backup_tags` subtree, so `delete_tags.local` set in one file does not wipe `delete_tags.origin` from another.
Env vars: `BACKUP_TAGS_REPO`, `BACKUP_TAGS_DELETE_TAGS_LOCAL`, `BACKUP_TAGS_DELETE_TAGS_ORIGIN`.
Bools parse `1/true/yes/on` and `0/false/no/off` case-insensitively, an unset or empty variable means "not set", and anything else is an error.
The same defaults live in code as a fallback, so the script also works when `settings.json` lacks the block.
A missing file is skipped; invalid JSON or a wrongly-typed value raises a `SystemExit` naming the file.

## Script behaviour

New `scripts/°base/git/bak_push.py`, plus a `scripts/bak_push.py -> °base/git/bak_push.py` symlink following the other entries in `scripts/` (check how `tag_backup.py` is linked first).
It is derived from the fedora script, with these changes:

- **Drop** `--all`, `find_repos` and the persistent `bak` remote (`ensure_bak_remote`, `BAK_REMOTE`).
  The script pushes straight to the configured URL (`git push --force -q <url> <sha>:refs/tags/<ref>`) and never edits `.git/config`.
  `has_empty` fetches `refs/heads/mane` from that URL instead of the `bak` remote.
- **Keep** the remote ref layout `bak/+/<host/owner/repo>/+/<tag|branch>/<on-empty|no-empty|-rebased->/+/<name>`, `url_path`, `origin_url`, `rebase_on_empty` and the `--dry-run` flag.
  The backup repo is shared across repos, so namespacing is needed to avoid collisions.
- **Keep** `-C REPO` and the positional `names`, which default to all local `bak/*` tags.
  Add `--delete-local/--no-delete-local` and `--delete-origin/--no-delete-origin` CLI overrides on top of the env layer.
  Drop `--bak-url` in favour of `--repo`.
- Settings loading goes in its own module, `scripts/°base/git/°bak_lib/settings.py` (no `_` prefix per the code-style guide, and the `°` namespace matches `°split_lib`), with `load_backup_tags(root: Path, env: Mapping[str, str]) -> BackupTags` returning a typed dataclass.
  The git root comes from `git rev-parse --show-toplevel`, as in `°settings_lib/paths.py`.

### Deletion (only when the flag is on, only for refs whose push succeeded)

Per tag, with `sha` the tag's commit, and none of it done on `--dry-run` (which prints `DRY would delete …`):

1. **Origin** (done first, because it needs the local tag to compare):
   - Skip if there is no origin remote.
   - Skip if the normalized origin URL equals the normalized `backup_tags.repo`.
     Normalizing means no scheme, no `user@`, no `.git`, no trailing `/`, and a lowercased host.
     The check reuses the `url_path` logic.
   - Skip if `git ls-remote --tags origin refs/tags/<name> refs/tags/<name>^{}` shows a different commit than the local tag (peeled for annotated tags), or no such tag.
   - Otherwise run `git push origin :refs/tags/<name>`.
   - A failure to delete only warns and continues.
2. **Local**: `git tag -d <name>`.
   Branch-kind names are never deleted, because only `bak/*` tags are in scope.
   Explicit `names` that are branches are still pushed, as in the original.

If any push for a tag failed, or the tag was skipped as invalid, nothing is deleted for it.
The `-rebased-` variant counts as optional: its failure does not block deleting, but the main variant's failure does.

## Other files

- `ai/settings/settings.schema.json`: add a `backup_tags` property with `repo` (string, `minLength` 1) and `delete_tags` (object with boolean `local` and `origin`), `additionalProperties: false`.
  `settings-local.schema.json` inherits it.
- `ai/settings/README.md`: document the block, the layer order and the env vars.
- Confirm `scripts/°base/ai/settings/sync.py` keeps the unknown `backup_tags` key: run `sync.py` and `sync.py --check`, then check that the diff is only the added block.
- `scripts/°base/tests/test_bak_push.py`, using `_git_test_helpers` and a local bare repo (a `file://` URL) as the backup repo:
  - Layering: each layer overrides only the keys it sets, a missing `.repo` file is fine, env beats files, and bool parsing and error cases.
  - Push: refs land under the namespaced name for `on-empty` and `no-empty`, and `.git/config` is unchanged.
  - Delete local: removes only pushed tags.
  - Delete origin:
    - removed when origin has the same commit
    - kept when origin has a different commit
    - kept when origin normalizes to the backup repo (`https://user@host/o/r.git` equals `https://host/o/r`)
    - kept when the tag is absent on origin
  - Dry run changes nothing.

## Verification

- `uv run --project scripts/°base python -m unittest discover -s scripts/°base/tests -p "test_bak_push.py" -v`, then the full discover run to check for regressions.
- `python3 scripts/°base/ai/settings/sync.py --check`.
- Manual check with `--dry-run` against this repo's existing `bak/*` tags, which prints the planned refs and deletions.
  It shows the settings resolved from each layer and does not touch the real backup repo.
  A real push needs the user's go-ahead because it is outward-facing.
- Commit in separate steps: script and lib, then settings/schema/README, then tests.
  Any preexisting failures found along the way go in their own commit, per the saved feedback.
