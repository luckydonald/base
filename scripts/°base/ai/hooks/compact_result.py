"""Store Claude compact summaries as linked repository artifacts."""
from __future__ import annotations

import json
import re
import uuid
from pathlib import Path

from _lib import append_and_commit, resolve_log_path


COMPACT_DIRECTORY_PATTERN = re.compile(r"^(\d+)(?:\..+)?$")
VALID_TRIGGERS = {"manual", "auto"}


def normalized_prompt_id(payload: dict[str, object]) -> str | None:
    """Return the canonical prompt UUID, or ``None`` for older payloads."""
    value = payload.get("prompt_id")
    if not isinstance(value, str) or not value:
        return None
    # end if
    try:
        return str(uuid.UUID(value))
    except ValueError:
        return None
# end def


def compact_directory_number(path: Path) -> int | None:
    match = COMPACT_DIRECTORY_PATTERN.fullmatch(path.name)
    return int(match.group(1)) if match else None
# end def


def matching_prompt_directories(compact_root: Path, prompt_id: str) -> list[Path]:
    if not compact_root.exists():
        return []
    # end if
    suffix = f".{prompt_id}"
    matches = [
        path
        for path in compact_root.iterdir()
        if path.is_dir()
        and path.name.endswith(suffix)
        and compact_directory_number(path) is not None
    ]
    return sorted(matches, key=lambda path: compact_directory_number(path) or 0)
# end def


def next_compact_number(compact_root: Path) -> int:
    if not compact_root.exists():
        return 1
    # end if
    numbers = [
        number
        for path in compact_root.iterdir()
        if path.is_dir()
        if (number := compact_directory_number(path)) is not None
    ]
    return max(numbers, default=0) + 1
# end def


def reserve_artifact_directory(
    log_path: Path,
    payload: dict[str, object],
    artifact_name: str,
    content: str,
) -> Path | None:
    """Reuse a prompt directory or allocate the next compact directory.

    ``None`` means the same prompt already stored byte-identical artifact
    content, so the repeated hook event is a no-op.
    """
    compact_root = log_path.parent / "output" / "compact"
    prompt_id = normalized_prompt_id(payload)
    if prompt_id is not None:
        for directory in reversed(matching_prompt_directories(compact_root, prompt_id)):
            artifact = directory / artifact_name
            if not artifact.exists():
                return directory
            # end if
            try:
                if artifact.read_text(encoding="utf-8") == content:
                    return None
                # end if
            except OSError:
                continue
        # end for
    # end if

    number = next_compact_number(compact_root)
    directory_name = f"{number:03d}.{prompt_id}" if prompt_id else f"{number:03d}"
    directory = compact_root / directory_name
    directory.mkdir(parents=True, exist_ok=True)
    return directory
# end def


def human_size(path: Path) -> str:
    """Return a compact human-readable file size."""
    try:
        size = path.stat().st_size
    except OSError:
        return "? B"
    for unit in ("B", "KB", "MB", "GB"):
        if size < 1024 or unit == "GB":
            return f"{size:.0f} {unit}" if unit == "B" else f"{size:.3g} {unit}"
        # end if
        size /= 1024
    # end for
    return "? B"
# end def


def capture_summary(payload: dict[str, object], trigger: str, summary: str) -> bool:
    """Write one compact result and append its marked prompt-log entry."""
    if trigger not in VALID_TRIGGERS or not summary.strip():
        return False
    # end if
    log_path = resolve_log_path("ai/prompt.md", "ai/°base/prompt.md")
    result_directory = reserve_artifact_directory(log_path, payload, "result.md", summary)
    if result_directory is None:
        return False
    # end if

    result_file = result_directory / "result.md"
    result_file.write_text(summary, encoding="utf-8")
    result_relative = result_file.relative_to(log_path.parent).as_posix()
    result_link = (
        f"[Result (`{len(summary)}` chars, `{human_size(result_file)}`)]"
        f"({result_relative})"
    )
    content = (
        f"❯ Conversation compacted <kbd>{trigger}</kbd>:\n"
        f"> - {result_link}\n\n"
    )
    append_and_commit(
        log_path,
        content,
        commit_template_relpath="ai/commit-templates/prompt",
        default_commit_msg=f"ai: compact {result_directory.name} result",
        extra_paths=(result_file,),
    )
    return True
# end def


def capture_postcompact(payload: dict[str, object]) -> bool:
    """Capture the documented PostCompact ``compact_summary`` field."""
    if payload.get("hook_event_name") != "PostCompact":
        return False
    # end if
    trigger = payload.get("trigger")
    summary = payload.get("compact_summary")
    if not isinstance(trigger, str) or not isinstance(summary, str):
        return False
    # end if
    return capture_summary(payload, trigger, summary)
# end def


def compact_summary_from_transcript(transcript_path: Path) -> tuple[str, str] | None:
    """Return the latest transcript summary and its manual/auto trigger."""
    boundary_triggers: dict[str, str] = {}
    summaries: list[tuple[str, str]] = []
    try:
        with transcript_path.open(encoding="utf-8") as transcript:
            for line in transcript:
                try:
                    item = json.loads(line)
                except (json.JSONDecodeError, ValueError):
                    continue
                if not isinstance(item, dict):
                    continue
                # end if
                if item.get("type") == "system" and item.get("subtype") == "compact_boundary":
                    boundary_id = item.get("uuid")
                    metadata = item.get("compactMetadata")
                    trigger = metadata.get("trigger") if isinstance(metadata, dict) else None
                    if (
                        isinstance(boundary_id, str)
                        and isinstance(trigger, str)
                        and trigger in VALID_TRIGGERS
                    ):
                        boundary_triggers[boundary_id] = trigger
                    # end if
                    continue
                # end if
                if item.get("type") != "user" or item.get("isCompactSummary") is not True:
                    continue
                # end if
                parent_id = item.get("parentUuid")
                message = item.get("message")
                summary = message.get("content") if isinstance(message, dict) else None
                if isinstance(parent_id, str) and isinstance(summary, str) and summary.strip():
                    summaries.append((parent_id, summary))
                # end if
            # end for
        # end with
    except OSError:
        return None

    for parent_id, summary in reversed(summaries):
        trigger = boundary_triggers.get(parent_id)
        if trigger is not None:
            return trigger, summary
        # end if
    # end for
    return None
# end def


def capture_session_start(payload: dict[str, object]) -> bool:
    """Capture compact output from the older SessionStart transcript shape."""
    if payload.get("hook_event_name") != "SessionStart" or payload.get("source") != "compact":
        return False
    # end if
    transcript_value = payload.get("transcript_path")
    if not isinstance(transcript_value, str) or not transcript_value:
        return False
    # end if
    compact_summary = compact_summary_from_transcript(Path(transcript_value))
    if compact_summary is None:
        return False
    # end if
    trigger, summary = compact_summary
    return capture_summary(payload, trigger, summary)
# end def
