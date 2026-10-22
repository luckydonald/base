---
name: feedback-file-deletion
description: "Remove tracked files with git rm; rename untracked files to *.YYYY-MM-DD.bak.ext instead of deleting them"
metadata:
  type: feedback
---

Only delete files with `git rm`, and only git-tracked ones.
Untracked files that are no longer needed, or that shadow something, get renamed to `*.YYYY-MM-DD.bak.ext` (e.g. `secrets.py` → `secrets.2025-05-18.bak.py`) instead of being deleted.

**Why:** The user does not want untracked files silently deleted, since they exist nowhere else. Renaming keeps them and still makes the shadowing or conflict clear.

**How to apply:** Check `git status` (or `git ls-files <path>`) before removing any file. Tracked: `git rm`. Untracked: `mv` to the `.bak.ext` name.
