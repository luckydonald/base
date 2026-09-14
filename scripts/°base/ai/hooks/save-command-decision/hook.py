#!/usr/bin/env python3
"""Record command-approval text that the normal prompt hook cannot see.

Claude puts a manual denial's reason in the rejected tool result and puts
accepted instructions in a sibling transcript text block. Copilot instead
writes an interactive denial's feedback to its per-session ``events.jsonl``.
Codex's command dialog has no such hidden text path: follow-up instructions
are ordinary prompts and are already saved by ``save-prompt``.
"""
from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from _lib import (  # noqa: E402
    append_and_commit,
    dump_debug_payload,
    find_tool_rejections,
    is_cross_tool_duplicate,
    load_transcript_tool_events,
    read_payload,
    resolve_log_path,
)


STATE_FILE = Path(tempfile.gettempdir()) / "save-command-decision-state.json"
CLAUDE_COMMAND_TOOLS = {"Bash", "shell", "unified_exec", "Write", "Edit", "Read", "apply_patch"}


def load_recorded_ids() -> set[str]:
    try:
        state = json.loads(STATE_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, TypeError):
        return set()
    # end try
    return set(state) if isinstance(state, list) else set()
# end def


def save_recorded_ids(ids: set[str]) -> None:
    STATE_FILE.write_text(json.dumps(sorted(ids)), encoding="utf-8")
# end def


def command_label(tool_name: str) -> str:
    return f"`{tool_name}`" if tool_name else "a tool"
# end def


def render_decision(label: str, detail: str | None = None) -> str:
    lines = [f"❯ {label}\n"]
    if detail:
        for line in detail.splitlines():
            lines.append(f"> {line}\n" if line else ">\n")
        # end for
    # end if
    lines.append("\n")
    return "".join(lines)
# end def


def append_decisions(blocks: list[str]) -> None:
    if not blocks:
        return
    # end if
    append_and_commit(
        resolve_log_path("ai/query.md", "ai/°base/query.md"),
        "".join(blocks),
        commit_template_relpath="ai/commit-templates/decision",
        default_commit_msg="ai: save command decision",
    )
# end def


def record_claude_decisions(payload: dict) -> None:
    """Record denied command calls on a later hook and completed instructions.

    A denial never reaches PostToolUse, so every invocation scans for new
    transcript rejections. A completed call can be recorded immediately when
    its sibling transcript text carries user instructions. The latter is
    deliberately labelled as tool instructions, not a proven permission
    approval: Claude uses the same transcript shape for any in-flight tool.
    """
    transcript_path = payload.get("transcript_path")
    if not isinstance(transcript_path, str) or not transcript_path:
        return
    # end if

    recorded = load_recorded_ids()
    blocks: list[str] = []
    rejections = find_tool_rejections(transcript_path, CLAUDE_COMMAND_TOOLS, recorded)
    for rejection in rejections:
        reason = rejection["reason"]
        label = f"Command denied: {command_label(rejection['tool_name'])}"
        blocks.append(render_decision(label, reason))
        recorded.add(rejection["tool_use_id"])
    # end for

    tool_use_id = payload.get("tool_use_id")
    if isinstance(tool_use_id, str) and tool_use_id and tool_use_id not in recorded:
        event = load_transcript_tool_events(transcript_path).get(tool_use_id)
        if event and event["tool_name"] in CLAUDE_COMMAND_TOOLS and not event["is_error"] and event["note"]:
            blocks.append(render_decision(f"Instructions for {command_label(event['tool_name'])}:", event["note"]))
            recorded.add(tool_use_id)
        # end if
    # end if

    append_decisions(blocks)
    if blocks:
        save_recorded_ids(recorded)
    # end if
# end def


def copilot_events(session_id: str) -> list[dict]:
    if not session_id:
        return []
    # end if
    path = Path.home() / ".copilot" / "session-state" / session_id / "events.jsonl"
    try:
        return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    except (OSError, json.JSONDecodeError):
        return []
    # end try
# end def


def copilot_denials(events: list[dict], recorded: set[str]) -> list[tuple[str, str, str]]:
    """Return unrecorded ``(toolCallId, command, feedback)`` denials."""
    commands: dict[str, str] = {}
    for event in events:
        if event.get("type") != "permission.requested":
            continue
        # end if
        data = event.get("data")
        request = data.get("permissionRequest") if isinstance(data, dict) else None
        if not isinstance(request, dict):
            continue
        # end if
        tool_call_id = request.get("toolCallId")
        command = request.get("fullCommandText")
        if isinstance(tool_call_id, str) and isinstance(command, str):
            commands[tool_call_id] = command
        # end if
    # end for

    results: list[tuple[str, str, str]] = []
    for event in events:
        if event.get("type") != "permission.completed":
            continue
        # end if
        data = event.get("data")
        if not isinstance(data, dict):
            continue
        # end if
        tool_call_id = data.get("toolCallId")
        result = data.get("result")
        if not isinstance(tool_call_id, str) or tool_call_id in recorded or not isinstance(result, dict):
            continue
        # end if
        if result.get("kind") != "denied-interactively-by-user":
            continue
        # end if
        feedback = result.get("feedback")
        results.append((tool_call_id, commands.get(tool_call_id, ""), feedback.strip() if isinstance(feedback, str) else ""))
    # end for
    return results
# end def


def record_copilot_decisions(payload: dict) -> None:
    session_id = payload.get("session_id") or payload.get("sessionId") or ""
    if not isinstance(session_id, str):
        return
    # end if
    recorded = load_recorded_ids()
    denials = copilot_denials(copilot_events(session_id), recorded)
    blocks = [
        render_decision(f"Command denied: `{command}`" if command else "Command denied:", feedback or None)
        for _, command, feedback in denials
    ]
    append_decisions(blocks)
    if denials:
        recorded.update(tool_call_id for tool_call_id, _, _ in denials)
        save_recorded_ids(recorded)
    # end if
# end def


def main() -> int:
    ai_tool = sys.argv[1] if len(sys.argv) > 1 else "claude"
    payload = read_payload()
    if is_cross_tool_duplicate(ai_tool):
        return 0
    # end if
    dump_debug_payload(payload, "save-command-decision")
    if ai_tool == "claude":
        record_claude_decisions(payload)
    elif ai_tool == "copilot":
        record_copilot_decisions(payload)
    # Codex deliberately has no branch: its permission-dialog follow-up is a
    # normal UserPromptSubmit and save-prompt already records it.
    # end if
    return 0
# end def


if __name__ == "__main__":
    raise SystemExit(main())
