"""AI/base content classification for paths and commits."""

from __future__ import annotations

import functools
import os
import re
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Sequence

from . import git_ops

AI_IGNORE_FILENAME = ".ai-ignore"

# Mirrors get-base.py's REMOTE_NAME/DEFAULT_USERNAME -- duplicated here
# (rather than imported) since get-base.py is deliberately stdlib-only and
# must stay importable standalone before °split_lib exists on disk.
BASE_REMOTE_NAME = "base"
BASE_REMOTE_BRANCH = "base"
DEFAULT_BASE_USERNAME = "luckydonald"

# Matches this repo's real commit convention, e.g.:
#   "ai: updated prompt"
#   "[base] topic: ai: Run: ..."
#   "[dumper] init script: ai: Run: ..."
# but not "aisle: fix typo" or "said: hello".
AI_SUBJECT_RE = re.compile(r"^(\[.*\]\s*)?.*\bai:")


class MissingAiIgnoreError(RuntimeError):
    """Raised when no `.ai-ignore` could be found anywhere -- on disk, via an
    already-fetched `base` ref, or by fetching `base` from GitHub -- so
    ai/base commit classification cannot proceed safely."""


def ai_ignore_path(repo_root: Path | None = None) -> Path:
    return (repo_root or Path.cwd()) / AI_IGNORE_FILENAME
# end def


def base_remote_url(username: str | None = None) -> str:
    username = username or os.environ.get("BASE_GIT_USERNAME", DEFAULT_BASE_USERNAME)
    return f"https://{username}@github.com/{username}/base.git"
# end def


@functools.lru_cache(maxsize=None)
def resolve_ignore_file(repo_root: Path) -> Path:
    """Resolve the root `.ai-ignore` file, falling back -- in order, warning
    on every fallback tier used -- to: an already-fetched `base/base`
    remote-tracking ref, a local branch literally named `base`, then a fresh
    fetch of the `base` remote from GitHub. Raises `MissingAiIgnoreError` if
    none of those have it either.
    """
    disk_path = ai_ignore_path(repo_root)
    if disk_path.is_file():
        return disk_path
    # end if

    remote_tracking_ref = f"refs/remotes/{BASE_REMOTE_NAME}/{BASE_REMOTE_BRANCH}"
    for description, ref in (
        ("already-fetched base/base remote-tracking ref", remote_tracking_ref),
        (f"local branch '{BASE_REMOTE_BRANCH}'", BASE_REMOTE_BRANCH),
    ):
        content = git_ops.show_path_at_or_none(ref, AI_IGNORE_FILENAME, repo_root)
        if content is not None:
            return _warn_and_materialize(description, ref, content)
        # end if
    # end for

    if git_ops.remote_url(BASE_REMOTE_NAME, repo_root) is None:
        git_ops.remote_add(BASE_REMOTE_NAME, base_remote_url(), repo_root)
    # end if
    git_ops.fetch(BASE_REMOTE_NAME, BASE_REMOTE_BRANCH, repo_root)
    content = git_ops.show_path_at_or_none(remote_tracking_ref, AI_IGNORE_FILENAME, repo_root)
    if content is not None:
        return _warn_and_materialize(f"freshly fetched {BASE_REMOTE_NAME} remote (GitHub)", remote_tracking_ref, content)
    # end if

    raise MissingAiIgnoreError(
        f"No {AI_IGNORE_FILENAME} found in {repo_root} on disk, at {remote_tracking_ref}, at branch "
        f"'{BASE_REMOTE_BRANCH}', or after fetching the '{BASE_REMOTE_NAME}' remote from GitHub. "
        "ai/base commit classification cannot proceed safely without it."
    )
# end def


def _warn_and_materialize(description: str, ref: str, content: bytes) -> Path:
    print(f"warning: {AI_IGNORE_FILENAME} not found on disk; falling back to {description} ({ref})", file=sys.stderr)
    handle = tempfile.NamedTemporaryFile(suffix=f"-{AI_IGNORE_FILENAME}", delete=False)
    try:
        handle.write(content)
    finally:
        handle.close()
    # end try
    return Path(handle.name)
# end def


def ai_ignore_rules(ignore_file: Path | None = None) -> list[str]:
    path = ignore_file or ai_ignore_path()
    if not path.is_file():
        return []
    # end if

    return [line for line in path.read_text(encoding="utf-8").splitlines() if line and not line.startswith("#")]
# end def


def ai_ignore_files(path: PurePosixPath, root_ignore_file: Path | None = None) -> list[tuple[Path, PurePosixPath]]:
    root_ignore_file = root_ignore_file or ai_ignore_path()
    ignore_files = [(root_ignore_file, path)]
    directory = root_ignore_file.parent

    for depth, part in enumerate(path.parts[:-1], start=1):
        directory /= part
        ignore_file = directory / AI_IGNORE_FILENAME
        relative_path = PurePosixPath(*path.parts[depth:])
        ignore_files.append((ignore_file, relative_path))
    # end for

    return ignore_files
# end def


def glob_segment_to_regex(segment: str) -> str:
    regex = ""
    index = 0
    while index < len(segment):
        character = segment[index]
        index += 1
        if character == "*":
            regex += "[^/]*"
        elif character == "?":
            regex += "[^/]"
        elif character == "[" and "]" in segment[index + 1:]:
            end = segment.index("]", index + 1)
            body = segment[index:end]
            if body.startswith("!"):
                body = "^" + body[1:]
            # end if
            regex += f"[{body.replace(chr(92), chr(92) * 2)}]"
            index = end + 1
        else:
            regex += re.escape(character)
        # end if
    # end while
    return regex
# end def


@functools.lru_cache(maxsize=None)
def glob_to_regex(pattern: str) -> re.Pattern[str]:
    """Compiles a glob like `PurePosixPath.full_match` does, for Python before 3.13."""
    segments = pattern.split("/")
    regex = ""
    for index, segment in enumerate(segments):
        is_last = index == len(segments) - 1
        if segment == "**":
            regex += ".*" if is_last else "(?:[^/]+/)*"
        else:
            regex += glob_segment_to_regex(segment) + ("" if is_last else "/")
        # end if
    # end for
    return re.compile(regex, re.DOTALL)
# end def


def full_match(path: PurePosixPath, pattern: str) -> bool:
    if hasattr(path, "full_match"):
        return path.full_match(pattern)
    # end if
    return glob_to_regex(pattern).fullmatch(path.as_posix()) is not None
# end def


def path_matches_glob(path: PurePosixPath, pattern: str) -> bool:
    pattern = pattern.removeprefix("/")
    if pattern.endswith("/"):
        pattern = f"{pattern}**"
    # end if

    patterns = [pattern]
    if "/" not in pattern and any(character in pattern for character in "*?["):
        patterns.append(f"**/{pattern}")
    # end if
    return any(full_match(path, candidate) for candidate in patterns)
# end def


def is_ai_base_path(path: str, *, ignore_file: Path | None = None) -> bool:
    path_parts = PurePosixPath(path)
    is_ai_path = False

    for current_ignore_file, relative_path in ai_ignore_files(path_parts, ignore_file):
        for rule in ai_ignore_rules(current_ignore_file):
            is_negation = rule.startswith("!")
            pattern = rule[1:] if is_negation else rule
            if path_matches_glob(relative_path, pattern):
                is_ai_path = not is_negation
            # end if
        # end for
    # end for

    return is_ai_path
# end def


@dataclass(frozen=True)
class CommitClassification:
    sha: str
    subject: str
    paths: tuple[str, ...]
    is_ai_only_commit: bool
    is_ai_tainted_commit: bool
    is_code_containing_commit: bool


def classify_commit(
    sha: str,
    subject: str,
    paths: Sequence[str],
    *,
    ignore_file: Path | None = None,
) -> CommitClassification:
    paths = tuple(paths)
    ai_flags = [is_ai_base_path(path, ignore_file=ignore_file) for path in paths]

    is_ai_only = bool(paths) and all(ai_flags)
    is_code_containing = any(not flag for flag in ai_flags)
    is_ai_tainted = is_ai_only or any(ai_flags) or bool(AI_SUBJECT_RE.match(subject))

    return CommitClassification(
        sha=sha,
        subject=subject,
        paths=paths,
        is_ai_only_commit=is_ai_only,
        is_ai_tainted_commit=is_ai_tainted,
        is_code_containing_commit=is_code_containing,
    )
