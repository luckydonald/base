# download_ref.py: fix Coolify docs (and Fumadocs-style sites) + add fetch/redirect/rewrite logging

## Context

The user asked whether `download_ref.py` would pick up the clean Markdown source
for `https://coolify.io/docs/applications/configuration/advanced`
(i.e. `https://coolify.io/docs/llms.mdx/docs/applications/configuration/advanced/content.md`)
or fall back to converting the raw HTML page.

I traced the code (`scripts/download_ref.py` → symlink to
`scripts/°base/ai/references/download-link.py` → `°dllink_lib` package) and verified
against the live site with `curl`:

- `resolve_plan()` has no forge match for `coolify.io`, so it falls into the generic
  HTML-conversion branch (`convert_html=True`).
- `markdown_plan_if_available()` (`°dllink_lib/planner.py:15-32`) only tries four
  candidate rewrites: `<path>.md`, `<path>/content.md`, `<path>/index.md`,
  `<path>/README.md`. For this URL, **all four return HTTP 302 → `/docs`** (verified
  live), so none qualify (`response.status == 200` check fails).
- The actual working Markdown URL uses a different, Fumadocs-specific shape:
  `/{first-path-segment}/llms.mdx{full-original-path}/content.md`. This candidate is
  never tried today.
- Result: **confirmed** — `download_ref.py` currently raw-dogs the HTML page through
  `html_to_markdown()` for this URL instead of fetching the clean source Markdown.

Separately, the user asked (and noted it's generally useful) that the tool should log
which URL it actually ends up loading, plus any redirects and rewrite attempts along
the way. Right now there is **no logging at all** inside `°dllink_lib` — `cli.py` only
prints a final one-line summary after everything succeeds, so a failed/wrong-path run
gives no visibility into what was tried.

## Changes

### 1. Add a Fumadocs-style markdown candidate

File: `°dllink_lib/planner.py`, function `markdown_candidate_urls()` (the `else`
branch for extension-less paths, lines 27-31).

Add one more candidate, built from the first path segment (Fumadocs' doc-route
prefix) plus the full original path plus `/content.md`:

```python
segments = [part for part in path.split("/") if part]
if segments:
    candidates.append(
        urllib.parse.urlunsplit(
            parts._replace(path=f"/{segments[0]}/llms.mdx{path.rstrip('/')}/content.md")
        )
    )
```

This reproduces `/docs/applications/configuration/advanced` →
`/docs/llms.mdx/docs/applications/configuration/advanced/content.md` (verified live:
returns HTTP 200, `content-type: application/octet-stream`, body is the clean
Markdown). It's a cheap extra probe tried after the existing four candidates, so it
doesn't change behavior for sites that don't use this pattern (those just 404/302 and
get skipped, same as today).

No change needed to `looks_markdown()` — `application/octet-stream` content that
doesn't start with `<!doctype`/`<html` already passes.

### 2. Add fetch/redirect/rewrite logging

New tiny helper module `°dllink_lib/log.py`:

```python
from __future__ import annotations
import sys

def log(msg: str) -> None:
    print(f"[dllink] {msg}", file=sys.stderr)
```

**`°dllink_lib/http.py`** (`fetch_url()`): log every outgoing request and its result,
including redirects, using `response.geturl()` vs the requested `url`:

- Before request: `log(f"GET {url}")`
- After success: if `response.geturl() != url`, `log(f"redirect: {url} -> {response.geturl()}")`; then `log(f"<- {status} {content_type}")`
- Same treatment in the `HTTPError` branch (log the error status too)

This covers "the URL it's actually loading from" and "redirects" for every request
made anywhere in the tool (planner, archive fallback, github provider, generic forge
provider all funnel through `fetch_url`).

**`°dllink_lib/planner.py`** (`markdown_plan_if_available()`): log the rewrite search
itself, since `http.py` doesn't know these requests are speculative candidates:

- On success: `log(f"rewrite: {plan.download_url} -> {candidate}")`
- If no candidate matched after the loop: `log(f"no markdown rewrite found for {plan.download_url}, converting HTML")`

**`°dllink_lib/planner.py`** (`download()`): log the Cloudflare-challenge → Wayback
Machine fallback path when it triggers:

- `log(f"cloudflare challenge on {plan.download_url}, trying archive.org snapshot")`
- On finding a snapshot: `log(f"using archive.org snapshot from {archive_timestamp}")`

`cli.py` keeps its existing final `download: {result.downloaded_url}` summary print
(stdout) unchanged — the new logging is all on stderr as a trace of the attempts, not
a replacement for it.

## Files touched

- `scripts/°base/ai/references/°dllink_lib/log.py` (new)
- `scripts/°base/ai/references/°dllink_lib/http.py`
- `scripts/°base/ai/references/°dllink_lib/planner.py`

## Verification

1. Run `scripts/download_ref.py https://coolify.io/docs/applications/configuration/advanced --no-git-add --no-open-ide` and confirm:
   - stderr shows the four failing candidates (302 redirects to `/docs`), then the
     `llms.mdx/.../content.md` candidate succeeding, then a `rewrite:` line.
   - the written file is the clean Markdown (starts with `# Advanced
     (/docs/applications/configuration/advanced)`), not an HTML-derived conversion.
2. Run it again on a URL that has no markdown rewrite available (e.g. a random HTML
   page) and confirm the `no markdown rewrite found` log line appears and the HTML
   conversion path still works as before.
3. Run it on an existing GitHub blob URL to confirm the github provider path and
   redirect logging still behave correctly (no regressions from the shared `fetch_url`
   change).
