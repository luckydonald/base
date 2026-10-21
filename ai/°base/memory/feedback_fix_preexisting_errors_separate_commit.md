---
name: feedback-fix-preexisting-errors-separate-commit
description: "Preexisting unittest or typing errors met during a task get fixed automatically, as their own separate commit; never hunt for them on purpose."
metadata:
  type: feedback
---

When running the unittests or a type check during a task shows errors that were already there before our change, fix them too, without asking.
Put those fixes into their own commit, separate from the task's work commit.
Do not go looking for such errors on purpose, only the ones met along the way count.

**Why:** a work commit stays focused and reviewable when unrelated repairs are not mixed in, and a green suite makes the next run easier.

**How to apply:** after the task's tests or typecheck turn up a failure that our diff did not cause, fix it and commit it on its own following [[feedback-lplp-never-drop-ai-autocommits]] (own `ai: Run:` message, own scope).
Never fold it into the task commit, and do not broaden the search for more of them.
