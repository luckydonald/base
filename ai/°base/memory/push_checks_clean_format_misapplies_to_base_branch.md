---
name: push-checks-clean-format-misapplies-to-base-branch
description: "split.py check-push's branch-format policy blocks pushing base's own `base` branch to origin; the legacy pre-push chain for it must stay disabled until fixed"
metadata:
  node_type: memory
  type: project
  originSessionId: 4251b919-29cd-4f65-b668-85f37e212151
  modified: 2026-09-28T17:24:57.946Z
---

`scripts/°base/git/°split_lib/push_checks.py`'s branch-format content policy (`check_content_policy`, via `branches.classify_branch`) classifies any branch name that doesn't match `ai/UNCLEAN/...` or `ai/history/...` as **clean** format, and clean-format branches may not contain AI-tainted commits. `base`'s own primary branch (`base`) falls through to this default and is treated as clean — but it legitimately contains almost nothing *but* AI-tainted commits (hooks, plans, `ai/°base/query.md`, etc.), since `base` itself is the tool that *produces* clean/unclean/history splits for *consuming* repos, not a split output itself.

Discovered 2026-09-28 while restoring the (previously dead) `scripts/°base/git/hooks/install` pre-push trampoline so `split.py check-push` would actually run: the very first push attempt on `base` was rejected wholesale (~20 violations, one per AI-tainted commit in history). Reverted by restoring `.git/hooks/pre-push.legacy` to the git-lfs-only script (dropping the `split.py check-push` call) rather than leaving pushes to `base`/`origin` broken — see `bak/ed9dde08b7f4` (pre-incident origin/base tip, also pushed as a tag) for reference if this needs re-investigation.

**How to apply:** before ever re-enabling the `split.py check-push` chain for this repo's own `base` branch, `classify_branch`/the content policy needs an explicit exemption for base's own primary branch pushed to `origin` (or the check needs to only run when this repo is acting as a split *source* for another target, not when developing on `base` itself). Don't re-chain it into `.git/hooks/pre-push.legacy` without that fix first. The new, narrower `ai/query.md`-only guard (`scripts/°base/git/hooks/push/check_base_query_md.py`, via `.pre-commit-config.yaml`'s `stages: [pre-push]`) is unaffected and stays active — it doesn't go through this branch-format logic at all.
