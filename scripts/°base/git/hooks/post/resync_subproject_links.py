#!/usr/bin/env python3
"""Re-sync the per-file symlinks of monorepo subprojects after a merge or rebase.

Runs as the pre-commit `post-merge` and `post-rewrite` hook. Only merges and rebases act: a
`post-rewrite` for an amend is ignored. A failure here is printed but never makes the merge or
rebase look failed, so this always exits 0.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

LINK_SUBPROJECT = Path(__file__).resolve().parents[3] / "init" / "link_subproject.py"
MIGRATE_QUERY_TO_PROMPT = Path(__file__).resolve().parents[3] / "ai" / "migrate_query_to_prompt.py"


def main() -> int:
    rewrite_command = os.environ.get("PRE_COMMIT_REWRITE_COMMAND")
    args = [sys.executable, str(LINK_SUBPROJECT), "--resync", "--event", "merge"]

    if rewrite_command is not None:
        if not rewrite_command.startswith("rebase"):
            return 0
        # end if
        args[-1] = "rebase"
    # end if

    try:
        migrated = subprocess.run([sys.executable, str(MIGRATE_QUERY_TO_PROMPT), "--event", args[-1]])
        if migrated.returncode != 0:
            print(f"warning: migrating query.md to prompt.md exited with {migrated.returncode}", file=sys.stderr)
        # end if
        result = subprocess.run(args)
    except OSError as e:
        print(f"warning: subproject link re-sync could not run: {e}", file=sys.stderr)
        return 0
    # end try
    if result.returncode != 0:
        print(f"warning: subproject link re-sync exited with {result.returncode}", file=sys.stderr)
    # end if
    return 0
# end def


if __name__ == "__main__":
    sys.exit(main())
# end if
