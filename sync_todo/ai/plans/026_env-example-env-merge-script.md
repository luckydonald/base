# `.env.example` → `.env` merge script

## Context

Every subproject that follows the `secrets.py` reads-env-vars pattern needs a way to bring an
existing (possibly hand-edited, possibly secret-filled) `.env` up to date with new keys added to
`.env.example`, without ever destroying a value someone already set. No such tool exists in the
repo today (confirmed: no script anywhere merges `.env.example` → `.env`). `sync_todo/` itself
doesn't even have a `.env.example` yet — that's out of scope here; this script is a *generic*,
repo-wide utility, not sync_todo-specific, and the user plans to cherry-pick it into the separate
`base/base` project later, so it must stay dependency-free (stdlib only) and self-contained.

Two extra constraints come from how this will actually be *run*: the AI agent driving it must
never be able to read `.env`/`.env.example` content directly (existing `Read(**/.env*)` deny rule
in `ai/settings/settings.json`) — so all parsing/diffing must happen *inside* the script's own
process, with the script only ever printing key names + defaults/status, never full values or
comment bodies. And any backup file the script creates must stay safe from accidental deletion or
exposure, consistent with the existing untracked-file backup convention.

## Location

New file: `scripts/°base/env/merge-env.py` (stdlib-only, executable, shebang `#!/usr/bin/env
python3`), following the existing `scripts/°base/<domain>/<name>.py` layout (`git/tag-backup.py`,
`ai/settings/sync.py`, etc.) and its code style (`from __future__ import annotations`, `# end
def`/`# end if` closing comments, `argparse` with a `parse_args()` function, plain functions over
classes — see `scripts/°base/git/tag-backup.py` as the closest precedent in size/shape).

Add a top-level convenience symlink `scripts/°base/merge_env.py -> env/merge-env.py`, matching the
existing symlink convention (`tag_backup.py -> git/tag-backup.py`, `sync_settings.py ->
ai/settings/sync.py`).

## CLI shape

```
python3 scripts/°base/env/merge-env.py [TARGET_DIR] [--example] [--dry-run]
```

- `TARGET_DIR` (positional, optional, default `.`): directory containing `.env.example` and
  `.env`.
- Default mode (no `--example`, no stdin): merge `TARGET_DIR/.env.example` → `TARGET_DIR/.env`,
  **additive only** (never overwrites a non-empty value, never removes/replaces existing comment
  lines — only fills empty values and appends missing description lines / whole new keys).
- `--example` + piped stdin (`cat new_vars.txt | python3 merge-env.py --example`): merges the
  piped `.env`-formatted text *into* `TARGET_DIR/.env.example` itself, using the same
  parsing/categorization logic as the default mode, but **without** the append-only restriction —
  a value already in `.env.example` for a key stdin also defines gets overwritten if different
  (it's a template, not live secrets). If stdin has data but `--example` was not passed, the
  script errors out rather than silently ignoring the piped input.
- `--dry-run`: valid for both modes; computes and prints the full report but writes nothing and
  creates no backup.
- Piping without `--example`, and using `--example` without piped stdin, are both usage errors.

## Parsing model

An `.env`-file "entry" = an optional comment block + a `KEY=VALUE` line. The comment block is
found by walking upward from the `KEY=` line and collecting consecutive lines starting with `#`,
stopping at the first non-`#` line (this naturally stops at blank lines too, per the user's
spec). Lines that aren't part of any entry (blank lines, section-header comments separated by a
blank line from the next key) are structural and preserved verbatim but not attached to any key.

Represent a parsed file as an ordered list of entries (`key`, `value`, `comment_lines`,
plus enough position info to reconstruct the file byte-for-byte when nothing changes) — reuse one
parser for both `.env` and `.env.example` (and piped stdin, which is `.env`-shaped text).

## Merge algorithm & report format

For every key that appears in the source (`.env.example`, or stdin in `--example` mode) and/or
the destination (`.env`, or `.env.example` in `--example` mode), emit **up to two** report lines —
one for the value aspect, one for the description aspect — using exactly the phrasing the user
specified. A key gets one line per aspect that is "notable"; when a key is brand new (only in the
source), a single "added value" line covers the whole entry (its comment block is copied in
verbatim, no separate description line).

Value aspect (destination-mode wording; `--example` mode additionally allows an "overwritten"
case since it's not append-only):
- Key exists in destination, non-empty value → `no value change: was already filled.`
- Key exists in destination, empty; source has non-empty value → `value change: filled with the
  default '<value>'.`
- Key exists in destination, empty; key not in source at all → `no value change: remained empty:
  not in merge file`
- Key exists in destination, empty; source also empty → `no value change: remained empty (empty
  in merge file, too)`
- Key not in destination at all; source has non-empty value → `added value: with default
  '<value>'.` (whole entry, incl. comments, appended)
- Key not in destination at all; source empty → `added value: with empty default.`
- (`--example` mode only) destination non-empty, source non-empty and different → `value change:
  overwritten from '<old>' to '<new>'.`

Description aspect (only evaluated for keys that already existed in the destination — new keys
get their comment block copied silently as part of the "added value" line):
- Destination had no comment block; source has one → `added description: was missing before.`
- Destination had some comment lines; source has lines not already present → `added description:
  appended to existing description.` (append only the new lines, preserving existing ones, still
  directly above the `KEY=` line)
- Source's comment lines are already all present in destination's → `no description change:
  matches merge file.`
- Source has no comment block for that key → `no description change: no description in merge
  file.`
- Key not in source at all → `no description change: not in merge file.`

Print header `Merging .env.example into .env:` (default mode) or `Merging into .env.example:`
(`--example` mode), then one `- KEY <message>` line per notable aspect, sorted by key's order of
first appearance. **Never print a value or comment body except the literal default being
filled/added/overwritten** — no existing content, no unrelated comment text, ever reaches stdout
(the whole point of doing this in-process instead of via `Read`/`cat`).

New keys are appended at the end of the destination file (blank line separator, then the source's
comment block + `KEY=VALUE` line, in source order). If the destination file doesn't exist yet,
treat it as empty (every key becomes an "added value").

## Backups

Before writing anything (skip entirely in `--dry-run`, and skip if the merge is a true no-op —
nothing to write):
1. Copy the destination file (`.env` in default mode, `.env.example` in `--example` mode) to
   `<name>.YYYY-MM-DD_HH-MM-SS.bak` in the same directory, using `datetime.now()` at run time.
2. Only then overwrite the destination in place.

Verify (no `.gitignore` edit expected to be needed — confirm, don't assume):
- `git check-ignore -v TARGET_DIR/.env.YYYY-MM-DD_HH-MM-SS.bak` and the `.env.example.*.bak`
  equivalent both report ignored (root `.gitignore`'s `**/*.env*` / `**/*.bak` patterns should
  already cover these; this is a read-only sanity check, not a script feature).

## Protecting the backup file from deletion/reading

Add one new deny entry to `ai/settings/settings.json`'s `permissions.deny` list (canonical source,
synced into `.claude/settings.json` etc. by `scripts/°base/ai/settings/sync.py`), mirroring the
existing `.env` entry exactly:

```json
{"type": "read", "path": "**/*.env*.bak"}
```

placed right after the existing `{"type": "read", "path": "**/.env*"}` entry. (The `.env*` pattern
already technically matches `.env.<timestamp>.bak` by prefix, but the user asked for an explicit,
self-documenting entry the same way `.env` has one — this also unambiguously covers the
`.env.example.<timestamp>.bak` variant.) This is a one-time manual addition alongside creating the
script, not something the script does at runtime. After editing, run `python3
scripts/°base/ai/settings/sync.py` (already allow-listed) so `.claude/settings.json` picks it up
immediately instead of waiting for next `SessionStart`.

## Verification

- Manually create a scratch directory with a small synthetic `.env.example` covering all the
  report cases (filled/empty values, present/missing keys, with/without/overlapping comment
  blocks) plus a pre-existing `.env`, then run the script and check the printed report matches the
  documented phrasing exactly and that `.env`'s untouched parts are byte-identical to before.
- Run again with `--dry-run` and confirm no files are written/backed up.
- Test the `--example` + stdin path: pipe a small `.env`-shaped snippet with an overlapping key
  that has a different value than the existing `.env.example`, confirm it overwrites (unlike the
  default mode) and reports `value change: overwritten from ... to ...`, and that a `.bak` of the
  old `.env.example` was created.
- Test error paths: stdin piped without `--example`, and `--example` passed with no stdin data.
- `git check-ignore -v` on a generated `.bak` file (see above).
- After the `ai/settings/settings.json` edit + running `sync.py`, confirm `.claude/settings.json`
  now contains the new `**/*.env*.bak` deny entry.
