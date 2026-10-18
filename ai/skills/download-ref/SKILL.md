---
name: "download-ref"
description: "Download a documentation page into ai/references/ as Markdown with scripts/download_ref.py. Use whenever the user shares a docs URL to keep as a reference, asks to download/save/fetch a doc page, or points at an `@ai/references/...` file that does not exist yet."
---

# Downloading docs into `ai/references/`

`scripts/download_ref.py` fetches one documentation page and writes it to `ai/references/<host>/<path>.md`, so it can be cited as `@ai/references/<host>/...` and read offline.
It prefers a Markdown version of the page when the site offers one, has a dedicated GitHub provider, and falls back to a web archive snapshot when the page is gone.

## Run it as an agent with `--no-ide`

```sh
scripts/download_ref.py --no-ide https://code.claude.com/docs/en/hooks
```

By default the script opens the downloaded file in the user's IDE afterwards.
That is noise during an agent run, and it can fail or hang when no IDE is reachable, so always pass `--no-ide` (also spelled `--no-open-ide` or `--no-ide-open`).

## Git behavior

By default the script runs `git add` and then `git commit --no-verify --only <file>` with the message ``ai/references: Downloaded `<path>`.``.
It bypasses the commit hooks and the `commit-with-lplp-style` message flow, so pass `--no-git` (or just `--no-git-commit`) when the download is part of a larger task and the file should land in the task's own commit.
`--no-git-add` skips only the staging.

## Other options

- The URL may also be piped in: `echo URL | scripts/download_ref.py --no-ide`.
- `--output-root DIR` changes the target from `ai/references`.
- `--open-ide COMMAND` (also `--open`, `--ide`) picks a specific editor command; only useful for a human.

## Reading the result

The script prints `download:` (the URL actually fetched), `wrote:` (the file), and `git add:` / `git commit:` lines when those ran.
`archive fallback: snapshot from <timestamp>` on stderr means the live page was unavailable and an archived copy was saved, so mention that to the user.
A failure exits with status 1 and prints `download-link: <reason>`; report the reason rather than retrying blindly.
Cite the result as `@ai/references/<host>/...` using the `wrote:` path.
