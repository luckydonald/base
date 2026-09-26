"""Pure text extraction of file-path mentions from a prompt."""
from __future__ import annotations

import re
from dataclasses import dataclass

_AT_MENTION_RE = re.compile(r"(?<!\S)@([^\s`]+)")
_BACKTICK_MENTION_RE = re.compile(r"`([^`\n]+)`")
_TRAILING_PUNCT = ".,;:!?)]}\"'"
_FENCE_RE = re.compile(r"^(```|~~~)")


def extract_candidate_paths(prompt: str) -> list[str]:
    """@mention and backtick-quoted candidate paths containing '/', deduped, order-preserved."""
    seen: set[str] = set()
    out: list[str] = []
    for regex in (_AT_MENTION_RE, _BACKTICK_MENTION_RE):
        for m in regex.finditer(prompt):
            candidate = m.group(1).strip().rstrip(_TRAILING_PUNCT)
            if "/" in candidate and candidate not in seen:
                seen.add(candidate)
                out.append(candidate)
    return out


@dataclass
class Mention:
    line: int       # 1-indexed line number within the scanned text
    display: str    # original text to show as the link label, e.g. "@src/other_file.py" or "`ai/some_file.md`"
    path: str       # candidate path used for filesystem resolution


def _line_mentions(line: str) -> list[tuple[str, str]]:
    """(display, path) pairs for @mentions and backtick mentions on a single line."""
    found: list[tuple[str, str]] = []
    for m in _AT_MENTION_RE.finditer(line):
        path = m.group(1).strip().rstrip(_TRAILING_PUNCT)
        if "/" in path:
            found.append((f"@{path}", path))
    for m in _BACKTICK_MENTION_RE.finditer(line):
        raw = m.group(1)
        path = raw.strip().rstrip(_TRAILING_PUNCT)
        if "/" in path:
            found.append((f"`{raw}`", path))
    return found


def find_mentions(content: str) -> list[Mention]:
    """Like `extract_candidate_paths`, but per-line and fence-aware: skips any
    line inside a ``` or ~~~ fenced code block (including the fence delimiter
    lines themselves), so example diffs/snippets are never mistaken for real
    mentions.

    Unlike `extract_candidate_paths`, matches are not deduplicated -- each
    occurrence becomes its own `Mention` so a summary can list every line a
    file was referenced on.
    """
    mentions: list[Mention] = []
    in_fence = False
    for lineno, line in enumerate(content.split("\n"), start=1):
        if _FENCE_RE.match(line.lstrip()):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        for display, path in _line_mentions(line):
            mentions.append(Mention(line=lineno, display=display, path=path))
    return mentions
