#!/usr/bin/env python3
"""Save compact prompts before compaction and results after compaction.

Usage: hook.py [ai_tool_name]
"""
from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import compact_result  # noqa: E402
from _lib import (  # noqa: E402
    append_and_commit,
    base_ai_commit_subject,
    dump_debug_payload,
    flush_pending_rejections,
    is_cross_tool_duplicate,
    read_payload,
    resolve_log_path,
)

INSTRUCTION_KEYS = ("custom_instructions", "custom_instruction", "customInstructions", "instructions")


def custom_instructions(payload: dict[str, object]) -> str:
    for key in INSTRUCTION_KEYS:
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
        # end if
    # end for
    return ""
# end def


def next_compacted_number(compacted_dir: Path) -> int:
    if not compacted_dir.exists():
        return 1
    # end if
    nums = [
        int(m.group(1))
        for f in compacted_dir.glob("*.md")
        if (m := re.fullmatch(r"(\d+)\.md", f.name))
    ]
    return max(nums, default=0) + 1
# end def


def main() -> int:
    ai_tool = sys.argv[1] if len(sys.argv) > 1 else "unknown"
    payload = read_payload()
    if is_cross_tool_duplicate(ai_tool):
        return 0
    # end if
    flush_pending_rejections(payload)
    dump_debug_payload(payload, "save-compact-prompt")

    if payload.get("hook_event_name") == "PostCompact":
        compact_result.capture_postcompact(payload)
        return 0
    # end if
    if payload.get("trigger") != "manual":
        return 0
    # end if
    text = custom_instructions(payload)
    if not text:
        return 0
    # end if

    log_path = resolve_log_path("ai/query.md", "ai/°base/query.md")
    compacted_dir = log_path.parent / "output" / "compacted"
    num = next_compacted_number(compacted_dir)
    dir_name = f"{num:03d}"
    compacted_dir.mkdir(parents=True, exist_ok=True)
    compacted_file = compacted_dir / f"{dir_name}.md"
    compacted_file.write_text(text, encoding="utf-8")

    cwd = Path.cwd()
    compacted_rel = str(compacted_file.relative_to(cwd))
    subprocess.run(["git", "add", "--", compacted_rel], capture_output=True)
    subprocess.run(
        ["git", "commit", "--no-verify", "--only", compacted_rel,
         "-m", base_ai_commit_subject(f"ai: compact {dir_name} prompt")],
        capture_output=True,
    )

    rel_compacted = f"output/compacted/{dir_name}.md"
    content = f"- [`/compact` possible prompt](./{rel_compacted})\n"
    append_and_commit(
        log_path,
        content,
        commit_template_relpath="ai/commit-templates/prompt",
        default_commit_msg=f"ai: link compact {dir_name} prompt",
    )
    return 0
# end def


if __name__ == "__main__":
    sys.exit(main())
# end if
