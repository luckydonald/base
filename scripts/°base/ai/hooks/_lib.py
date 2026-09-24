#!/usr/bin/env python3
"""Shared helpers for the prompt-log hooks (save-prompt, save-decision).

Both hooks append a markdown entry to a per-repo prompt log (typically
`ai/query.md`) and auto-commit only that file, while preserving any user-staged
edits to the same file via :mod:`merge_staged`.
"""
from __future__ import annotations

import datetime
import json
import os
import re
import subprocess
import sys
import tempfile
import time
from pathlib import Path

# Sibling-module import (this package can't be imported as a real package
# because parent dirs contain non-ASCII / hyphenated names).
sys.path.insert(0, str(Path(__file__).resolve().parent))
from merge_staged import merge as _merge_lines  # noqa: E402
from importlib import import_module  # noqa: E402

_commit_style = import_module("°commit_style_lib")
base_ai_commit_subject = _commit_style.base_ai_commit_subject
_commit_message = _commit_style.commit_message
_is_inside_base_repo = _commit_style._is_inside_base_repo
_read_by_issue = _commit_style._read_by_issue


def read_payload() -> dict:
    """Parse the JSON payload from stdin, returning ``{}`` on any error."""
    try:
        return json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        return {}


def _ai_prefix_root() -> tuple[Path, str]:
    """Return (subproject_root, ai_prefix), where ai_prefix is ``ai/°base``
    inside the base repo itself and plain ``ai`` in a consuming repo."""
    subproject = _subproject_root()
    git_root_str = _git_text("rev-parse", "--show-toplevel")
    git_root = Path(git_root_str) if git_root_str else subproject
    is_base = _is_inside_base_repo(subproject) or _is_inside_base_repo(git_root)
    ai_prefix = "ai/°base" if is_base else "ai"
    return subproject, ai_prefix


def dump_debug_payload(payload: dict, hook_name: str) -> None:
    """If ai[/°base]/.debug exists, write payload JSON to ai[/°base]/output/debug/."""
    subproject, ai_prefix = _ai_prefix_root()
    if not (subproject / ai_prefix / ".debug").is_file():
        return
    ts = datetime.datetime.now().strftime("%Y%m%d-%H%M%S_%f")
    debug_dir = subproject / ai_prefix / "output" / "debug"
    debug_dir.mkdir(parents=True, exist_ok=True)
    (debug_dir / f"{ts}-{hook_name}.json").write_text(
        json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8"
    )


def _pending_decisions_dir() -> Path:
    subproject, ai_prefix = _ai_prefix_root()
    d = subproject / ai_prefix / "output" / ".pending-decisions"
    d.mkdir(parents=True, exist_ok=True)
    return d


PENDING_DECISION_STALE_SECONDS = 30 * 60  # orphan-cleanup threshold, see sweep_pending_decisions


def _pending_decision_path(session_id: str, tool_use_id: str) -> Path:
    # session_id/tool_use_id are opaque harness-generated tokens (never
    # containing path separators in practice), joined so a sweep can tell
    # which session a marker belongs to -- see sweep_pending_decisions.
    return _pending_decisions_dir() / f"{session_id or 'unknown'}__{tool_use_id}.md"


def write_pending_decision(session_id: str, tool_use_id: str, rendered_block: str) -> None:
    """Persist a pre-rendered markdown block for an in-flight AskUserQuestion
    call, keyed by ``session_id``+``tool_use_id``. Claude Code fires no
    PostToolUse, PostToolUseFailure, or PermissionDenied hook when the user
    manually declines the question (e.g. via "chat about this"), so the
    question would otherwise be lost. Written at PreToolUse time, before the
    answer is known; deleted by :func:`delete_pending_decision` if the call is
    answered normally, or picked up by :func:`sweep_pending_decisions` if it
    isn't."""
    if not tool_use_id:
        return
    _pending_decision_path(session_id, tool_use_id).write_text(rendered_block, encoding="utf-8")


def delete_pending_decision(session_id: str, tool_use_id: str) -> None:
    """Remove the pending marker for a now-answered AskUserQuestion call."""
    if not tool_use_id:
        return
    _pending_decision_path(session_id, tool_use_id).unlink(missing_ok=True)


def sweep_pending_decisions(session_id: str) -> None:
    """Append+commit any leftover pending-decision markers (AskUserQuestion
    calls the user canceled instead of answering) to query.md, then delete
    them. Safe to call often: a no-op when nothing needs sweeping.

    Two Claude Code instances can share the same working directory (two
    terminals in the same non-worktree checkout), each with its own
    in-flight, not-yet-answered question. To avoid one session's Stop hook
    misclassifying *another still-live session's* question as canceled, this
    only sweeps: (a) markers belonging to ``session_id`` itself, and (b)
    markers from *any* session old enough (`PENDING_DECISION_STALE_SECONDS`)
    that the owning session almost certainly crashed/exited without ever
    reaching its own Stop -- a live session resolves its single in-flight
    question (answered or swept) within one turn, far under that threshold."""
    pending_dir = _pending_decisions_dir()
    own_prefix = f"{session_id or 'unknown'}__"
    now = time.time()

    to_sweep: list[Path] = []
    for marker in sorted(pending_dir.glob("*.md")):
        if marker.name.startswith(own_prefix):
            to_sweep.append(marker)
            continue
        try:
            age = now - marker.stat().st_mtime
        except OSError:
            continue
        if age >= PENDING_DECISION_STALE_SECONDS:
            to_sweep.append(marker)

    blocks: list[str] = []
    for marker in to_sweep:
        try:
            text = marker.read_text(encoding="utf-8")
        except OSError:
            marker.unlink(missing_ok=True)
            continue
        if not marker.name.startswith(own_prefix):
            text = re.sub(
                r"(Question canceled \(chat about this\))\.\n",
                r"\1, stale -- orphaned session.\n",
                text,
                count=1,
            )
        blocks.append(text)
        marker.unlink(missing_ok=True)
    if not blocks:
        return
    log_path = resolve_log_path("ai/query.md", "ai/°base/query.md")
    append_and_commit(
        log_path,
        "".join(blocks),
        commit_template_relpath="ai/commit-templates/decision",
        default_commit_msg="ai: save canceled decision",
    )


def slugify(text: str, *, max_len: int = 60, fallback: str = "untitled") -> str:
    """First non-empty line → lowercase, non-alphanumeric runs → ``-``, capped."""
    line = ""
    for raw in (text or "").splitlines():
        candidate = raw.strip().lstrip("#").strip()
        if candidate:
            line = candidate
            break
    if not line:
        return fallback
    slug = re.sub(r"[^a-z0-9]+", "-", line.lower()).strip("-")[:max_len].rstrip("-")
    return slug or fallback


def _git_text(*args: str) -> str:
    result = subprocess.run(["git", *args], capture_output=True, text=True)
    return (result.stdout or "").strip()


def _git_bytes(*args: str) -> bytes:
    return subprocess.run(["git", *args], capture_output=True).stdout or b""


def running_copilot() -> bool:
    """True when this process is actually running under Copilot CLI, per its
    own env markers. Unlike Claude's/Codex's markers, these are set directly
    by the Copilot CLI process itself for every hook invocation."""
    return bool(os.environ.get("COPILOT_CLI") or os.environ.get("COPILOT_AGENT_SESSION_ID"))


def is_cross_tool_duplicate(ai_tool: str) -> bool:
    """True when this hook invocation is a redundant duplicate caused by
    Copilot CLI's unconditional cross-read of `.claude/settings.json`
    alongside its own native `.github/hooks/*.json` config: when both files
    define a hook for the same event, Copilot runs *both*, once per config
    source. The two firings differ only in the baked-in ``ai_tool`` CLI
    argument (``'copilot'`` from the native config, ``'claude'``/``'codex'``
    from the cross-read Claude config) — this detects the mismatch so the
    caller can skip the redundant one.

    Detection is intentionally narrow: it only fires when the environment
    unambiguously marks the *actually running* harness as Copilot
    (``COPILOT_CLI``/``COPILOT_AGENT_SESSION_ID``), since ambient variables
    like ``CLAUDE_CODE_SSE_PORT`` can leak into a Copilot CLI process from
    the surrounding shell/IDE and are not reliable signals on their own.
    Returns ``False`` (never a duplicate) for Claude, Codex, and any other
    harness, and for manual/test invocations where no such env var is set.
    """
    running_copilot_ = running_copilot()
    return running_copilot_ and ai_tool != "copilot"


def _claude_config_dir() -> Path:
    """Claude Code's config root: ``~/.claude`` by default, or
    ``$CLAUDE_CONFIG_DIR`` when relocated (e.g. multi-account setups like
    ``~/.config/claude/accounts/<name>`` used to keep separate logins)."""
    config_dir = os.environ.get("CLAUDE_CONFIG_DIR")
    if config_dir:
        return Path(config_dir).expanduser()
    return Path.home() / ".claude"


_PROJECT_DIR_NAME_RE = re.compile(r"^[A-Za-z0-9_-]{1,64}$")


def _project_dir_name_override() -> str | None:
    """``CLAUDE_CODE_PROJECT_DIR_NAME`` pins Claude Code's per-project state
    directory name, but Claude Code itself only honors it when
    ``CLAUDE_CONFIG_DIR`` is also set in the environment, and only when it
    matches ``^[A-Za-z0-9_-]{1,64}$`` (verified against the installed CLI:
    ``/home/user/.local/share/claude/versions/*``). Mirroring both
    conditions here keeps this repo's own hooks looking in the same
    directory Claude Code actually wrote to — e.g. for a monorepo subfolder
    seeded with ``.claude-project.env`` by ``link-subproject-claude.sh``,
    where the subfolder's own encoded cwd path is not what Claude used."""
    if not os.environ.get("CLAUDE_CONFIG_DIR"):
        return None
    name = os.environ.get("CLAUDE_CODE_PROJECT_DIR_NAME")
    if name and _PROJECT_DIR_NAME_RE.match(name):
        return name
    return None


def _encoded_project_dir(subproject: Path) -> Path:
    """Claude Code stores per-project state at
    ``<config-dir>/projects/<encoded>/``, where <encoded> is either the
    ``CLAUDE_CODE_PROJECT_DIR_NAME`` override (see
    :func:`_project_dir_name_override`) or, by default, the absolute
    project path with all non-alphanumeric characters (including `/` and
    `_`) replaced by `-`."""
    override = _project_dir_name_override()
    encoded = override or re.sub(r"[^a-zA-Z0-9]", "-", str(subproject))
    return _claude_config_dir() / "projects" / encoded


def _subproject_root() -> Path:
    """The directory Claude was launched from. Claude Code sets
    ``CLAUDE_PROJECT_DIR`` for hook commands; manual invocations and the test
    suite fall back to the current working directory."""
    raw = os.environ.get("CLAUDE_PROJECT_DIR") or os.getcwd()
    return Path(raw).resolve()


def _chdir_to_git_root() -> Path:
    root = _git_text("rev-parse", "--show-toplevel")
    if not root:
        sys.exit(1)
    os.chdir(root)
    return Path(root)


def resolve_log_path(default_relpath: str, base_relpath: str) -> Path:
    """Return the absolute AI-artifact path under the *subproject* root (with
    the base-repo reroute and optional ``by-issue/<KEY>/`` sub-directory
    applied) and cd to the git root so subsequent git operations resolve
    relpaths uniformly. Creates parent directories as needed.

    When ``ai[/°base]/.by-issue`` exists and contains an issue key such as
    ``PROJ-1234``, every path is routed through
    ``ai[/°base]/by-issue/PROJ-1234/…`` instead of ``ai[/°base]/…``."""
    subproject = _subproject_root()
    git_root = _chdir_to_git_root()
    is_base = _is_inside_base_repo(subproject) or _is_inside_base_repo(git_root)
    ai_prefix = "ai/°base" if is_base else "ai"
    relpath = base_relpath if is_base else default_relpath

    issue = _read_by_issue(subproject, ai_prefix)
    if issue:
        # Insert by-issue/<KEY>/ immediately after the ai prefix.
        rest = relpath[len(ai_prefix) + 1:]  # strip "ai[/°base]/"
        relpath = f"{ai_prefix}/by-issue/{issue}/{rest}"

    log_path = (subproject / relpath).resolve()
    log_path.parent.mkdir(parents=True, exist_ok=True)
    return log_path


def _staged_snapshot(relpath: str) -> tuple[Path, Path] | None:
    """If ``relpath`` is staged with content different from HEAD, snapshot the
    HEAD and staged blobs to temp files. Returns ``(base_tmp, staged_tmp)`` or
    ``None`` when there is nothing to preserve."""
    staged_line = _git_text("ls-files", "--stage", relpath)
    if not staged_line:
        return None
    staged_hash = staged_line.split()[1]

    head_line = _git_text("ls-tree", "HEAD", relpath)
    head_hash = head_line.split()[2] if head_line else ""
    if staged_hash == head_hash:
        return None

    base_tmp = Path(tempfile.mkstemp(prefix="prompt-log-base-")[1])
    staged_tmp = Path(tempfile.mkstemp(prefix="prompt-log-staged-")[1])
    base_tmp.write_bytes(_git_bytes("cat-file", "blob", head_hash) if head_hash else b"")
    staged_tmp.write_bytes(_git_bytes("cat-file", "blob", staged_hash))
    return base_tmp, staged_tmp


def _restore_staged(snap: tuple[Path, Path], relpath: str) -> None:
    base_tmp, staged_tmp = snap
    try:
        new_head_bytes = _git_bytes("show", f"HEAD:{relpath}")
        new_head_lines = new_head_bytes.decode("utf-8", errors="replace").splitlines(keepends=True)
        base_lines = base_tmp.read_text(encoding="utf-8", errors="replace").splitlines(keepends=True)
        staged_lines = staged_tmp.read_text(encoding="utf-8", errors="replace").splitlines(keepends=True)

        merged = _merge_lines(base_lines, staged_lines, new_head_lines)
        merged_path = Path(tempfile.mkstemp(prefix="prompt-log-merged-")[1])
        try:
            merged_path.write_text("".join(merged), encoding="utf-8")
            new_blob = _git_text("hash-object", "-w", str(merged_path))
            if new_blob:
                subprocess.run(
                    ["git", "update-index", "--cacheinfo", f"100644,{new_blob},{relpath}"],
                    capture_output=True,
                )
        finally:
            merged_path.unlink(missing_ok=True)
    finally:
        base_tmp.unlink(missing_ok=True)
        staged_tmp.unlink(missing_ok=True)


def append_and_commit(
    log_path: Path,
    content: str,
    *,
    commit_template_relpath: str,
    default_commit_msg: str,
    extra_paths: tuple[Path, ...] = (),
) -> None:
    """Append ``content`` to ``log_path``, commit only those AI artifact files,
    then re-apply any user-staged edits to the log on top of the new HEAD."""
    relpath = str(log_path.relative_to(Path.cwd()))
    extra_relpaths = [str(path.relative_to(Path.cwd())) for path in extra_paths]
    snap = _staged_snapshot(relpath)

    with log_path.open("a", encoding="utf-8") as f:
        f.write(content)

    msg = _commit_message(commit_template_relpath, default_commit_msg)
    # `git commit --only` requires the path to be tracked, so make sure the
    # file is in the index first. Idempotent on already-tracked files.
    subprocess.run(["git", "add", "--", relpath, *extra_relpaths], capture_output=True)
    subprocess.run(
        ["git", "commit", "--no-verify", "--only", relpath, *extra_relpaths, "-m", msg],
        capture_output=True,
    )

    if snap is not None:
        _restore_staged(snap, relpath)
