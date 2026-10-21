---
name: feedback-never-search-from-filesystem-root
description: "NEVER run file searches (find, grep -r, fd, rg, Glob/Grep) rooted at `/`; scope them to the project or a known directory."
metadata:
  type: feedback
---

Never run a file search rooted at the filesystem root `/`, whatever the tool (`find /`, `grep -r … /`, `fd`, `rg`, Glob or Grep with path `/`).
Search inside the project directory or a specific known subdirectory instead.

**Why:** whole-disk scans are slow, flood the output and touch unrelated or protected data.

**How to apply:** scope every search to the repo or a directory you already know; if the location is unknown, check likely directories or ask.
`find / …` is also denied in `ai/settings/settings.json`.
