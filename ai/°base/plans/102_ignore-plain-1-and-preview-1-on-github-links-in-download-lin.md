# Ignore `?plain=1` and `?preview=1` on GitHub links in `download-link.py`

**Commit style:** Skill `/commit-with-lplp-style` is active — auto-commit following it for this implementation.
Load the skills `/code-style` (read `references/py.md` and `references/md.md`) and `/commit-with-lplp-style` before implementing.

## Context

Todo `71a4bb57-51ba-4875-91f2-d5b1451aa801` (calendar 7): make sure `?plain=1` and `?preview=1` are properly ignored for GitHub links, e.g. `https://github.com/mdn/content/blob/main/files/en-us/web/api/navigator/registerprotocolhandler/index.md?plain=1`.

## Findings

- Probing `resolve_plan` (`scripts/°base/ai/references/°dllink_lib/planner.py`) with a faked fetch shows `blob` URLs are already safe, because `github_plan` / `parse_github_blob` (`providers/github.py`) only look at `parts.path`, so source URL, raw URL, output path and the `main` / `latest` symlinks are identical with and without either parameter.
- The query is only dropped by accident of that parsing, and `strip_fragment` (`paths.py`) deliberately keeps queries.
- Every other GitHub shape that reaches `generic_forge_plan`, the HTML fallback or `markdown_plan_if_available` (e.g. `tree`, `issues`, `README` pages) keeps `?plain=1` in `download_url`, so GitHub would serve a different view of the page and the converted output would differ.
- No test covers any of this (`scripts/°base/tests/test_download_link.py`).

## Changes

1. `°dllink_lib/paths.py`: add `strip_github_view_params(url: str) -> str`.
   For host `github.com` (case-insensitive) it removes the query keys `plain` and `preview` (via `urllib.parse.parse_qsl(keep_blank_values=True)` / `urlencode`) and keeps every other parameter, so `?tab=readme` survives; other hosts are returned unchanged.
2. `°dllink_lib/planner.py`: in `resolve_plan`, apply it once on `cleaned` so every downstream branch (github, generic forge, fallback) sees the stripped URL.
3. Tests in `test_download_link.py`:
   - `blob/main/...md?plain=1`, `?preview=1` and `?plain=1&preview=1` give the same `DownloadPlan` as the bare URL (`source_url`, `download_url`, `output_path`, `link_paths`).
   - A non-`blob` GitHub URL has the two keys removed from its `download_url` while `?tab=readme` stays.
   - A non-GitHub URL with `?plain=1` keeps its query.
4. Follow `references/py.md`: no `_` prefixes, full type annotations, `# end if` / `# end for` block endings.

## Verification

- `uv run --project scripts/°base python -m unittest discover -s scripts/°base/tests -v` stays green (the new tests fail before step 1 for the non-`blob` case).
- Re-run the probe script against the real `mdn/content` URL with a faked fetch.

## Close

Plain commits via `ai/git/pending-commit.md` (scope `[base] ai/references`, matching recent `download-link.py` commits), then tick the box in `ai/todo.md`, `complete_todo(calendar_id=7, uid=71a4bb57-51ba-4875-91f2-d5b1451aa801)`, run `uv run scripts/sync_todos.py --project base` (the user already synced once, but completing changes the file), `tag_backup.py`, interactive rebase into one work commit, verify `git diff <bak-tag> HEAD` is empty.
Do not push.
