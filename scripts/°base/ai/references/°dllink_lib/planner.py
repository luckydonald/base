from __future__ import annotations

import os
import urllib.parse
from pathlib import Path

from .archive import is_cloudflare_challenge, latest_snapshot_url
from .html import final_output_path, html_to_markdown
from .http import fetch_url
from .log import log
from .models import DownloadError, DownloadPlan, DownloadResult, Fetch, Response
from .paths import output_path_for_url, strip_fragment, unique
from .providers import generic_forge_plan, github_plan, unsupported_forge_reason


def markdown_candidate_urls(url: str) -> list[str]:
    base = strip_fragment(url)
    parts = urllib.parse.urlsplit(base)
    if parts.path.endswith(".md"):
        return [base]

    candidates: list[str] = []
    path = parts.path or "/"
    stem, ext = os.path.splitext(path)
    if ext:
        candidates.append(urllib.parse.urlunsplit(parts._replace(path=f"{stem}.md")))
        candidates.append(urllib.parse.urlunsplit(parts._replace(path=f"{path}.md")))
    else:
        candidates.append(urllib.parse.urlunsplit(parts._replace(path=f"{path.rstrip('/')}.md")))
        candidates.append(urllib.parse.urlunsplit(parts._replace(path=f"{path.rstrip('/')}/content.md")))
        candidates.append(urllib.parse.urlunsplit(parts._replace(path=f"{path.rstrip('/')}/index.md")))
        candidates.append(urllib.parse.urlunsplit(parts._replace(path=f"{path.rstrip('/')}/README.md")))
        segments = [part for part in path.split("/") if part]
        if segments:
            candidates.append(
                urllib.parse.urlunsplit(
                    parts._replace(path=f"/{segments[0]}/llms.mdx{path.rstrip('/')}/content.md")
                )
            )
        # end if
    return unique(candidates)


def looks_markdown(response: Response) -> bool:
    content_type = response.content_type.lower()
    if "markdown" in content_type or "text/plain" in content_type:
        return True
    if "html" in content_type:
        return False
    text = response.text.lstrip()
    return not text.startswith("<!doctype") and not text.startswith("<html")


def resolve_plan(url: str, output_root: Path, fetch: Fetch = fetch_url) -> DownloadPlan:
    cleaned = strip_fragment(url)
    for resolver in (github_plan,):
        plan = resolver(cleaned, output_root, fetch)
        if plan is not None:
            return plan

    generic = generic_forge_plan(cleaned, output_root)
    if generic is not None:
        return generic

    unsupported = unsupported_forge_reason(cleaned)
    if unsupported:
        raise DownloadError(unsupported)

    parts = urllib.parse.urlsplit(cleaned)
    if not parts.scheme or not parts.netloc:
        raise DownloadError(f"expected absolute URL, got: {url!r}")
    if parts.path.endswith(".md"):
        return DownloadPlan(
            source_url=cleaned,
            download_url=cleaned,
            output_path=output_path_for_url(output_root, cleaned),
            convert_html=False,
        )

    return DownloadPlan(
        source_url=cleaned,
        download_url=cleaned,
        output_path=output_path_for_url(output_root, cleaned) / "_.md",
        convert_html=True,
    )


def markdown_plan_if_available(plan: DownloadPlan, output_root: Path, fetch: Fetch) -> DownloadPlan:
    if not plan.convert_html:
        return plan
    for candidate in markdown_candidate_urls(plan.download_url):
        response = fetch(candidate, "GET")
        if response.status == 200 and looks_markdown(response):
            source_candidate = candidate
            if candidate == plan.download_url:
                source_candidate = plan.source_url
            log(f"rewrite: {plan.download_url} -> {candidate}")
            return DownloadPlan(
                source_url=source_candidate,
                download_url=candidate,
                output_path=output_path_for_url(output_root, source_candidate),
                convert_html=False,
            )
        # end if
    log(f"no markdown rewrite found for {plan.download_url}, converting HTML")
    return plan


def download(plan: DownloadPlan, fetch: Fetch = fetch_url) -> DownloadResult:
    response = fetch(plan.download_url, "GET")
    archive_timestamp: str | None = None
    if is_cloudflare_challenge(response):
        log(f"cloudflare challenge on {plan.download_url}, trying archive.org snapshot")
        snapshot = latest_snapshot_url(plan.source_url, fetch)
        if snapshot is not None:
            archive_timestamp, archive_url = snapshot
            log(f"using archive.org snapshot from {archive_timestamp}")
            response = fetch(archive_url, "GET")
        # end if
    # end if
    if response.status != 200:
        raise DownloadError(f"HTTP {response.status}: {plan.download_url}")
    # end if
    if plan.convert_html:
        path = final_output_path(plan, response.text)
        return DownloadResult(
            path=path,
            content=html_to_markdown(response.text).encode("utf-8"),
            downloaded_url=response.url,
            archive_timestamp=archive_timestamp,
        )
    # end if
    return DownloadResult(
        path=plan.output_path,
        content=response.content,
        downloaded_url=response.url,
        archive_timestamp=archive_timestamp,
    )
