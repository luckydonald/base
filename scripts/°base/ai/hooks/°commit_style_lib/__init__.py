#!/usr/bin/env python3
"""AI auto-commit subject-line styling: the `[base]`/issue-key wrap
(`base_ai_commit_subject`) and the per-repo commit-message override lookup
(`_commit_message`), split out of `_lib.py` so this styling-specific surface
has its own smaller merge-conflict footprint.

Self-contained (duplicates a few tiny helpers `_lib.py` also defines, e.g.
`_git_text`/`_subproject_root`) rather than importing them back from `_lib.py`,
since `_lib.py` itself imports `base_ai_commit_subject`/`_commit_message` from
here — importing the other direction too would be circular.
"""
from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path


def _git_text(*args: str, cwd: Path | str | None = None) -> str:
    result = subprocess.run(["git", *args], capture_output=True, text=True, cwd=cwd)
    return (result.stdout or "").strip()


def _subproject_root() -> Path:
    """The directory Claude was launched from. Claude Code sets
    ``CLAUDE_PROJECT_DIR`` for hook commands; manual invocations and the test
    suite fall back to the current working directory."""
    raw = os.environ.get("CLAUDE_PROJECT_DIR") or os.getcwd()
    return Path(raw).resolve()


def _main_checkout_root(cwd: Path) -> Path | None:
    """Resolve the root of the *main* checkout that `cwd` belongs to, even
    when `cwd` is inside a linked `git worktree` (whose own directory is
    named after the worktree/branch, never `base`). Returns None if `cwd`
    isn't inside a git working tree at all, or if the repo is bare (no single
    "main checkout root" concept applies there -- bare-repo support is out of
    scope for this repo today)."""
    common_dir_text = _git_text("rev-parse", "--git-common-dir", cwd=cwd)
    if not common_dir_text:
        return None
    common_dir = Path(common_dir_text)
    if not common_dir.is_absolute():
        common_dir = cwd / common_dir
    common_dir = common_dir.resolve()
    if common_dir.name != ".git":
        # Bare repo: --git-common-dir points at the bare dir itself (e.g.
        # "repo.git"), not a ".git" inside a checkout -- no sibling checkout
        # root to take .parent of.
        return None
    return common_dir.parent


def _is_inside_base_repo(subproject_root: Path) -> bool:
    """True iff we are inside the `base` meta-repo: main-checkout directory
    named `base` (checked directly, or -- when `subproject_root` is itself a
    linked `git worktree` named after its branch -- via the worktree-proof
    `--git-common-dir` lookup in `_main_checkout_root`), with origin pointing
    at luckydonald/base.

    Bare repositories (`git init --bare` + `git worktree add`) are treated as
    "not the base repo" (returns False) -- not a supported way to work with
    this repo today; see `_main_checkout_root`.
    """
    root = subproject_root
    if root.name != "base":
        root = _main_checkout_root(subproject_root)
        if root is None or root.name != "base":
            return False
    origin = _git_text("remote", "get-url", "origin", cwd=root)
    return bool(re.search(r"(^|[:/])luckydonald/base(\.git)?/?$", origin, re.I))


def _read_by_issue(subproject: Path, ai_prefix: str) -> str:
    """Read the issue key from <subproject>/<ai_prefix>/.by-issue.

    Returns the stripped content (e.g. ``PROJ-1234``) or ``""`` when the file
    is absent or empty."""
    by_issue = subproject / ai_prefix / ".by-issue"
    if by_issue.is_file():
        return by_issue.read_text(encoding="utf-8").strip()
    return ""


def base_ai_commit_subject(msg: str) -> str:
    """Prefix AI auto-commit subjects with the base marker and issue key."""
    subproject = _subproject_root()
    git_root_text = _git_text("rev-parse", "--show-toplevel")
    git_root = Path(git_root_text) if git_root_text else subproject
    is_base = _is_inside_base_repo(subproject) or _is_inside_base_repo(git_root)
    ai_prefix = "ai/°base" if is_base else "ai"
    issue = _read_by_issue(subproject, ai_prefix)

    subject = msg
    for _ in range(2):
        if issue and subject.startswith(f"{issue}: "):
            subject = subject[len(issue) + 2:]
        if is_base and subject.startswith("[base] "):
            subject = subject[len("[base] "):]

    if is_base:
        subject = f"[base] {subject}"
    if issue:
        if is_base:
            subject = f"[base] {issue}: {subject[len('[base] '):]}"
        else:
            subject = f"{issue}: {subject}"
    return subject


def _load_py_override(template_py: Path, msg: str, extra: dict) -> str | None:
    """Import `template_py` as a standalone module and call its
    `format_message(msg, **extra) -> str`. Returns None (never raises) on any
    failure, so a broken override file falls through to the `.md` template or
    the plain default instead of breaking the commit."""
    try:
        import importlib.util

        spec = importlib.util.spec_from_file_location(f"commit_style_override_{template_py.stem}", template_py)
        if spec is None or spec.loader is None:
            return None
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        format_message = getattr(module, "format_message", None)
        if format_message is None:
            return None
        return str(format_message(msg, **extra))
    except Exception:
        return None


def _load_md_override(template_md: Path, msg: str, extra: dict) -> str:
    """Read `template_md` as a `str.format()` template (`{msg}` plus any
    `extra` keys). Falls back to the raw template text if it references a
    placeholder not supplied here (e.g. stray literal braces), and to `msg`
    itself when the file doesn't exist."""
    text = template_md.read_text(encoding="utf-8").replace("\n", "").replace("\r", "").strip()
    if not text:
        return msg
    try:
        return text.format(msg=msg, **extra)
    except (KeyError, IndexError):
        return text


def commit_message(template_relpath: str, msg: str, **extra: str) -> str:
    """Style an auto-commit subject, honoring an optional per-repo override at
    `<template_relpath>.py` (preferred — a real `format_message(msg, **extra)`
    function, for repos that need runtime logic like a conditional prefix) or
    `<template_relpath>.md` (a static `str.format()` template) before falling
    back to `msg` unchanged. `template_relpath` is given without an extension,
    e.g. `"ai/commit-templates/prompt"` — templates live alongside the AI
    artifacts, so they're subproject-scoped (relevant in monorepos where cwd
    is the git root, not the subproject)."""
    root = _subproject_root()
    template_py = root / f"{template_relpath}.py"
    if template_py.is_file():
        formatted = _load_py_override(template_py, msg, extra)
        if formatted is not None:
            return base_ai_commit_subject(formatted)

    template_md = root / f"{template_relpath}.md"
    if template_md.is_file():
        return base_ai_commit_subject(_load_md_override(template_md, msg, extra))

    return base_ai_commit_subject(msg)
