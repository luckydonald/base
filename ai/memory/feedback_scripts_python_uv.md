---
name: feedback-scripts-python-uv
description: "New helper and hook scripts are Python with a `uv run --script` shebang and inline dependencies, not bash"
metadata:
  type: feedback
---

Write new scripts (hooks, tooling) in Python with `#!/usr/bin/env -S uv run --script` and PEP 723 inline dependencies, not as shell scripts.
A thin bash wrapper is fine only where git itself needs one, e.g. `.hooks/pre-push.bash`.

**Why:** The user rejected a plan that proposed a `tag_on_push.bash` ("prefer python over shell scripts").

**How to apply:** Follow the style of `scripts/°base/ai/todos/sync_todos.py`, and run its tests with `uv run --with pytest pytest`.
