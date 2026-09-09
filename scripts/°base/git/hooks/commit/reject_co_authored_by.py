#!/usr/bin/env python3
"""Reject commit messages containing Co-Authored-By or Claude-Session trailers."""

from __future__ import annotations

import sys
from pathlib import Path

REJECTED_TRAILERS = ("Co-Authored-By", "Claude-Session")


def main(argv: list[str] | None = None) -> int:
    args = argv if argv is not None else sys.argv[1:]
    if len(args) != 1:
        print("Expected exactly one commit message filename.", file=sys.stderr)
        return 2

    message = Path(args[0]).read_text(encoding="utf-8")
    hit = next((t for t in REJECTED_TRAILERS if t in message), None)
    if hit is not None:
        print(f"Commit message contains disallowed trailer: {hit}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
