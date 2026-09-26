"""Git side effects for files mentioned in a prompt, and a markdown summary
of the existing files that were mentioned."""
from __future__ import annotations

import os
import subprocess
import sys
from dataclasses import dataclass
from importlib import import_module
from pathlib import Path

# Sibling-module import (the hooks dir can't be imported as a real package
# because parent dirs contain non-ASCII / hyphenated names).
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
base_ai_commit_subject = import_module("°commit_style_lib").base_ai_commit_subject  # noqa: E402

from .mentions import Mention, find_mentions  # noqa: E402


def is_tracked(relpath: str) -> bool:
    result = subprocess.run(
        ["git", "ls-files", "--error-unmatch", "--", relpath],
        capture_output=True,
    )
    return result.returncode == 0


def is_gitignored(relpath: str) -> bool:
    result = subprocess.run(
        ["git", "check-ignore", "-q", "--", relpath],
        capture_output=True,
    )
    return result.returncode == 0


@dataclass
class ResolvedMention(Mention):
    abspath: Path
    relpath: str


def resolve_existing(mentions: list[Mention], subproject: Path) -> list[ResolvedMention]:
    """Keep only the mentions that resolve to a real file, with its git-root-relative path."""
    resolved: list[ResolvedMention] = []
    for mention in mentions:
        abspath = (subproject / mention.path).resolve()
        if not abspath.is_file():
            continue
        try:
            relpath = str(abspath.relative_to(Path.cwd()))
        except ValueError:
            continue  # outside the repo -- skip
        resolved.append(
            ResolvedMention(
                line=mention.line, display=mention.display, path=mention.path,
                abspath=abspath, relpath=relpath,
            )
        )
    return resolved


def link_target(abspath: Path, log_path: Path) -> str:
    target = os.path.relpath(abspath, log_path.parent)
    return target if target.startswith("..") else f"./{target}"


def build_summary_block(resolved: list[ResolvedMention], log_path: Path, content: str) -> str | None:
    """A blockquote note to append after a log entry, linking to each existing
    mentioned file. `None` when there's nothing to mention."""
    if not resolved:
        return None

    width = len(str(content.count("\n") + 1))

    if len(resolved) == 1:
        mention = resolved[0]
        target = link_target(mention.abspath, log_path)
        line_no = f"{mention.line:0{width}d}"
        return f"> _Mentioned file at line `{line_no}`:_ [{mention.display}]({target})"

    lines = ["> <details><summary><i>Mentioned files:</i></summary>", ">"]
    for mention in resolved:
        target = link_target(mention.abspath, log_path)
        line_no = f"{mention.line:0{width}d}"
        lines.append(f"> - line `{line_no}`: [{mention.display}]({target})")
    lines.append(">")
    lines.append("> </details>")
    return "\n".join(lines)


def process_referenced_files(
    content: str, subproject: Path, log_path: Path
) -> tuple[str, list[ResolvedMention]]:
    """Append a summary of existing mentioned files to `content` (never
    rewriting it inline, so fenced code blocks and other formatting are left
    untouched) and return the resolved mentions to stage/commit.

    Assumes cwd is already the git root (as `resolve_log_path` leaves it).
    """
    mentions = find_mentions(content)
    resolved = resolve_existing(mentions, subproject)
    block = build_summary_block(resolved, log_path, content)
    if block is None:
        return content, []
    return content.rstrip("\n") + "\n\n" + block + "\n\n", resolved


def stage_and_commit_mentions(resolved: list[ResolvedMention]) -> None:
    """Best-effort: stage/commit the files in `resolved`, respecting .gitignore."""
    seen: set[str] = set()
    for mention in resolved:
        if mention.relpath in seen:
            continue
        seen.add(mention.relpath)

        if is_tracked(mention.relpath):
            subprocess.run(["git", "add", "--", mention.relpath], capture_output=True)
            continue

        if is_gitignored(mention.relpath):
            continue

        subprocess.run(["git", "add", "--", mention.relpath], capture_output=True)
        subprocess.run(
            ["git", "commit", "--no-verify", "--only", mention.relpath,
             "-m", base_ai_commit_subject("ai: referenced file for task added.")],
            capture_output=True,
        )
