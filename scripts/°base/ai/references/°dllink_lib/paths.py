from __future__ import annotations

import os
import urllib.parse
from pathlib import Path


def strip_fragment(url: str) -> str:
    parts = urllib.parse.urlsplit(url.strip())
    return urllib.parse.urlunsplit((parts.scheme, parts.netloc, parts.path, parts.query, ""))


GITHUB_VIEW_PARAMS: frozenset[str] = frozenset({"plain", "preview"})


def strip_github_view_params(url: str) -> str:
    parts = urllib.parse.urlsplit(url)
    if parts.netloc.lower() != "github.com" or not parts.query:
        return url
    # end if
    kept = [(key, value) for key, value in urllib.parse.parse_qsl(parts.query, keep_blank_values=True) if key not in GITHUB_VIEW_PARAMS]
    return urllib.parse.urlunsplit(parts._replace(query=urllib.parse.urlencode(kept)))
# end def


def sanitize_path_segment(value: str) -> str:
    value = urllib.parse.unquote(value)
    value = value.replace("\x00", "")
    value = value.replace(os.sep, "_")
    if os.altsep:
        value = value.replace(os.altsep, "_")
    if value in {"", ".", ".."}:
        return "_"
    return value


def url_path_segments(url: str) -> list[str]:
    parts = urllib.parse.urlsplit(strip_fragment(url))
    segments = [parts.scheme.rstrip(":") or "unknown", parts.netloc]
    path = parts.path.lstrip("/")
    if path:
        segments.extend(part for part in path.split("/") if part)
    return [sanitize_path_segment(part) for part in segments if part]


def output_path_for_url(output_root: Path, url: str) -> Path:
    return output_root.joinpath(*url_path_segments(url))


def unique(values: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        out.append(value)
    return out
