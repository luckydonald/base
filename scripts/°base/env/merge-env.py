#!/usr/bin/env python3
"""Merge `.env.example` into `.env`, additively (never overwrites a filled value, never
removes or replaces existing comment lines — only fills empty values and appends new keys or
missing description lines). A timestamped backup of the file being written is made first.

Piping `.env`-shaped text into the script together with `--example` merges that text into
`.env.example` itself instead, without the append-only restriction (it's a template, not live
secrets), and prints a unified diff of the result.

This script never prints existing values or comment bodies in the default mode — only key
names and the literal defaults being filled or added — since an AI agent may be the one running
it and must not be able to read `.env` content through its own output.

Usage:
    python3 scripts/°base/env/merge-env.py [TARGET_DIR] [--dry-run]
    cat new_vars.txt | python3 scripts/°base/env/merge-env.py [TARGET_DIR] --example [--dry-run]
"""
from __future__ import annotations

import argparse
from dataclasses import dataclass, field
from datetime import datetime
import difflib
from pathlib import Path
import re
import select
import sys


@dataclass
class StructuralItem:
    lines: list[str]
# end class


@dataclass
class EntryItem:
    key: str
    value: str
    comment_lines: list[str] = field(default_factory=list)
# end class


Item = StructuralItem | EntryItem

KEY_RE = re.compile(r"^([A-Za-z_][A-Za-z0-9_]*)=(.*)$")


def parse_env_text(text: str) -> list[Item]:
    items: list[Item] = []
    pending_comments: list[str] = []
    structural_buffer: list[str] = []

    def flush_structural() -> None:
        nonlocal structural_buffer
        if structural_buffer:
            items.append(StructuralItem(lines=structural_buffer))
            structural_buffer = []
        # end if
    # end def

    def flush_pending_comments_as_structural() -> None:
        nonlocal pending_comments
        if pending_comments:
            structural_buffer.extend(pending_comments)
            pending_comments = []
        # end if
    # end def

    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("#"):
            pending_comments.append(line)
            continue
        # end if
        match = KEY_RE.match(line)
        if match:
            flush_structural()
            items.append(EntryItem(key=match.group(1), value=match.group(2), comment_lines=pending_comments))
            pending_comments = []
        else:
            flush_pending_comments_as_structural()
            structural_buffer.append(line)
        # end if
    # end for
    flush_pending_comments_as_structural()
    flush_structural()
    return items
# end def


def build_index(items: list[Item]) -> dict[str, int]:
    index: dict[str, int] = {}
    for position, item in enumerate(items):
        if isinstance(item, EntryItem):
            index[item.key] = position
        # end if
    # end for
    return index
# end def


def render(items: list[Item]) -> str:
    lines: list[str] = []
    for item in items:
        if isinstance(item, StructuralItem):
            lines.extend(item.lines)
        else:
            lines.extend(item.comment_lines)
            lines.append(f"{item.key}={item.value}")
        # end if
    # end for
    text = "\n".join(lines)
    if text and not text.endswith("\n"):
        text += "\n"
    # end if
    return text
# end def


def merge_value(dest_entry: EntryItem, source_entry: EntryItem, *, overwrite_values: bool) -> str:
    key = dest_entry.key
    dest_has_value = dest_entry.value.strip() != ""
    source_has_value = source_entry.value.strip() != ""
    if dest_has_value:
        if overwrite_values and source_has_value and source_entry.value != dest_entry.value:
            old = dest_entry.value.strip()
            dest_entry.value = source_entry.value
            return f"- {key} value change: overwritten from '{old}' to '{source_entry.value.strip()}'."
        # end if
        return f"- {key} no value change: was already filled."
    # end if
    if source_has_value:
        dest_entry.value = source_entry.value
        return f"- {key} value change: filled with the default '{source_entry.value.strip()}'."
    # end if
    return f"- {key} no value change: remained empty (empty in merge file, too)"
# end def


def merge_description(dest_entry: EntryItem, source_entry: EntryItem) -> str:
    key = dest_entry.key
    source_comments = source_entry.comment_lines
    if not source_comments:
        return f"- {key} no description change: no description in merge file."
    # end if
    missing = [line for line in source_comments if line not in dest_entry.comment_lines]
    if not missing:
        return f"- {key} no description change: matches merge file."
    # end if
    if not dest_entry.comment_lines:
        dest_entry.comment_lines = list(source_comments)
        return f"- {key} added description: was missing before."
    # end if
    dest_entry.comment_lines = dest_entry.comment_lines + missing
    return f"- {key} added description: appended to existing description."
# end def


def insert_new_entry(
    dest_items: list[Item],
    dest_index: dict[str, int],
    anchor_key: str | None,
    source_entry: EntryItem,
) -> None:
    new_entry = EntryItem(
        key=source_entry.key,
        value=source_entry.value,
        comment_lines=list(source_entry.comment_lines),
    )
    if anchor_key is None:
        position = 0
    elif anchor_key in dest_index:
        position = dest_index[anchor_key] + 1
    else:
        position = len(dest_items)
    # end if
    dest_items.insert(position, new_entry)
    for key, index in dest_index.items():
        if index >= position:
            dest_index[key] = index + 1
        # end if
    # end for
    dest_index[source_entry.key] = position
# end def


def merge(
    dest_items: list[Item],
    dest_index: dict[str, int],
    source_items: list[Item],
    *,
    overwrite_values: bool,
) -> list[str]:
    report: list[str] = []
    source_entries = [item for item in source_items if isinstance(item, EntryItem)]
    source_keys = {entry.key for entry in source_entries}
    anchor_key: str | None = None

    for source_entry in source_entries:
        key = source_entry.key
        if key in dest_index:
            dest_entry = dest_items[dest_index[key]]
            assert isinstance(dest_entry, EntryItem)
            report.append(merge_value(dest_entry, source_entry, overwrite_values=overwrite_values))
            report.append(merge_description(dest_entry, source_entry))
        else:
            insert_new_entry(dest_items, dest_index, anchor_key, source_entry)
            if source_entry.value.strip() != "":
                report.append(f"- {key} added value: with default '{source_entry.value.strip()}'.")
            else:
                report.append(f"- {key} added value: with empty default.")
            # end if
        # end if
        anchor_key = key
    # end for

    for item in dest_items:
        if not isinstance(item, EntryItem) or item.key in source_keys:
            continue
        # end if
        if item.value.strip() != "":
            report.append(f"- {item.key} no value change: was already filled.")
        else:
            report.append(f"- {item.key} no value change: remained empty: not in merge file")
        # end if
        report.append(f"- {item.key} no description change: not in merge file.")
    # end for
    return report
# end def


def read_text(path: Path) -> str:
    return path.read_text() if path.exists() else ""
# end def


def write_backup(path: Path) -> None:
    if not path.exists():
        return
    # end if
    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    backup_path = path.with_name(f"{path.name}.{timestamp}.bak")
    backup_path.write_text(path.read_text())
# end def


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("target_dir", nargs="?", default=".", help="directory containing .env.example and .env")
    parser.add_argument(
        "--example",
        action="store_true",
        help="merge piped stdin into .env.example instead of merging .env.example into .env",
    )
    parser.add_argument("--dry-run", action="store_true", help="print the report without writing any files")
    return parser.parse_args(argv)
# end def


def run_example_mode(target_dir: Path, stdin_text: str, *, dry_run: bool) -> int:
    example_path = target_dir / ".env.example"
    old_text = read_text(example_path)
    dest_items = parse_env_text(old_text)
    dest_index = build_index(dest_items)
    source_items = parse_env_text(stdin_text)
    report = merge(dest_items, dest_index, source_items, overwrite_values=True)
    new_text = render(dest_items)

    print("Merging into .env.example:")
    for line in report:
        print(line)
    # end for

    diff_lines = list(
        difflib.unified_diff(
            old_text.splitlines(keepends=True),
            new_text.splitlines(keepends=True),
            fromfile=f"{example_path} (before)",
            tofile=f"{example_path} (after)",
        )
    )
    if diff_lines:
        print()
        print("Diff:")
        sys.stdout.writelines(diff_lines)
    # end if

    if dry_run or new_text == old_text:
        return 0
    # end if
    write_backup(example_path)
    example_path.write_text(new_text)
    return 0
# end def


def run_default_mode(target_dir: Path, *, dry_run: bool) -> int:
    env_path = target_dir / ".env"
    example_path = target_dir / ".env.example"
    old_text = read_text(env_path)
    dest_items = parse_env_text(old_text)
    dest_index = build_index(dest_items)
    source_items = parse_env_text(read_text(example_path))
    report = merge(dest_items, dest_index, source_items, overwrite_values=False)
    new_text = render(dest_items)

    print("Merging .env.example into .env:")
    for line in report:
        print(line)
    # end for

    if dry_run or new_text == old_text:
        return 0
    # end if
    write_backup(env_path)
    env_path.write_text(new_text)
    return 0
# end def


def try_read_stdin() -> str | None:
    """Return piped stdin text, or None if nothing was actually piped in.

    `isatty()` alone is unreliable here: a harness may run this script with stdin attached to a
    closed fd/`/dev/null` rather than a tty, which also reports `isatty() == False`. `select`
    with a zero timeout distinguishes "nothing to read" from "a real pipe with content" without
    blocking either way — a closed fd is immediately "ready" but yields an empty read.
    """
    if sys.stdin.isatty():
        return None
    # end if
    try:
        ready, _, _ = select.select([sys.stdin], [], [], 0)
    except OSError:
        return None
    # end try
    if not ready:
        return None
    # end if
    data = sys.stdin.read()
    return data if data.strip() else None
# end def


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    target_dir = Path(args.target_dir)
    stdin_text = try_read_stdin()

    if args.example:
        if stdin_text is None:
            print("Error: --example requires piped stdin data.", file=sys.stderr)
            return 2
        # end if
        return run_example_mode(target_dir, stdin_text, dry_run=args.dry_run)
    # end if

    if stdin_text is not None:
        print("Error: piped stdin requires --example.", file=sys.stderr)
        return 2
    # end if
    return run_default_mode(target_dir, dry_run=args.dry_run)
# end def


if __name__ == "__main__":
    sys.exit(main())
