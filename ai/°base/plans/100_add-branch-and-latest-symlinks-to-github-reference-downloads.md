# Add branch and `latest` symlinks to GitHub reference downloads

**Commit style:** Skill `/commit-with-lplp-style` is active — auto-commit following it for this implementation.

## Context

Todo `3caf29dd-df53-4dd5-8f5f-3b99f41c0cf8` in `ai/todo.md` (first open item, no subtasks, nothing more urgent).
`scripts/°base/ai/references/download-link.py` turns a GitHub `blob/<branch>/<path>` URL into a commit permalink and writes the file under `ai/references/https/github.com/<owner>/<repo>/blob/<sha>/<path>`.
Existing files are never refreshed, so a human has no stable path to "the current version".
Goal: also create relative soft symlinks `blob/<ref>/<path>` and `latest/<path>` pointing at the freshly written file; a newer download overwrites those links.

## Findings

- `°dllink_lib/providers/github.py::github_plan` resolves the ref to a sha, but only keeps the permalink, so the original ref (`main`) is lost.
- `°dllink_lib/models.py::DownloadPlan` has no place for extra output paths; `cli.py::main` writes only `result.path`, then `_git_add` and `_git_commit` handle that single path.
- `paths.py::output_path_for_url` builds the path from a URL, so the symlink locations can be derived by swapping the `<sha>` segment for the ref or for `latest`.
- Tests live in `scripts/°base/tests/test_download_link.py` (`FakeFetch`, `DownloadLinkPathTests`, `DownloadLinkInputTests`).
- The todo example writes `blop/main`, which is a typo of `blob/main`; the plan uses `blob`.

## Changes

1. `models.py`: add `link_paths: tuple[Path, ...] = ()` to `DownloadPlan` (frozen dataclass, default keeps all other callers unchanged).
2. `providers/github.py`:
   - in `github_plan`, remember `ref` when it was resolved via the API (the `"/".join(rest[:index])` prefix); a 40-hex sha in the URL has no ref.
   - build `link_paths` as `blob/<ref>/<path>` (only when a ref exists) and `latest/<path>` (always), under the same `<owner>/<repo>` directory as `output_path`, using `output_path_for_url` on the rewritten URLs.
   - for non-`.md` files (HTML conversion) the final path is still `plan.output_path`, so the links stay valid.
3. New module `°dllink_lib/links.py` (no `_` prefix): `write_symlink(target: Path, link: Path) -> None`.
   It creates the parent dirs (`mkdir -p`), computes the relative target with `os.path.relpath(target, link.parent)`, removes an existing symlink or file at `link` first, then `os.symlink`.
   It never touches a real directory at `link` and raises `DownloadError` instead.
4. `cli.py::main`: after writing the file, call `write_symlink` for each of `plan.link_paths`; the `DownloadPlan` is already available there (the markdown rewrite via `markdown_plan_if_available` must carry `link_paths` along, since it builds a new plan).
   `_git_add` and `_git_commit` take the file plus its links (`git commit --only <paths…>`), and the printed output lists the links.
5. Docs: mention the two symlinks in the module help or the `ai/references` docs if `download-link.py` is described anywhere (check with grep during implementation); update `ai/todo.md` checkbox in step "Close".

## Tests (`scripts/°base/tests/test_download_link.py`)

- branch URL: plan has `link_paths` for `blob/main/docs/advanced-usage.md` and `latest/docs/advanced-usage.md`.
- sha URL: only the `latest` link.
- branch with slash (`feature/docs`): link dir uses `blob/feature/docs/…`.
- `write_symlink`: relative target (`../../<sha>/docs/x.md`), resolves to the file, overwrites an older link, refuses a real directory.
- `main` end to end with a temp git repo: links exist, are included in the commit, `--no-git` still creates them.
- non-GitHub URLs: `link_paths` is empty, behaviour unchanged.

## Verification

- `uv run --project scripts/°base python -m unittest scripts.°base.tests.test_download_link -v`, then the full suite `uv run --project scripts/°base python -m unittest discover -s scripts/°base/tests -v`, and `ruff` on the touched files.
- Live check with `--no-git`: download the `chrome-devtools-mcp` `docs/advanced-usage.md` URL and `ls -l` both links.
- Code style: `/code-style` for py (explicit `# end …` block comments, no `_` prefixes, full type hints) and md (sentence-end line breaks).

## Workflow after the code

Per `todo-loop`: tick the checkbox, `complete_todo(7, 3caf29dd-…)`, `uv run scripts/sync_todos.py --project base`, `scripts/tag_backup.py`, then rebase the `ai:` and fix commits into one work commit (message via `ai/git/pending-commit.md`, no trailers), and verify `git diff <bak-tag> HEAD` is empty.
Then stop and name the next open todo (`6bc531bc` `ai/.subDir`).
