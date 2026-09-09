# Cherry-pick commit-trailer hygiene from todo_splits_tracker into base

## Context
The `todo_splits_tracker` repo (derived from `base`) independently developed a fix for AI-attribution
commit trailers: it extended the existing `no-co-authored-by` pre-commit hook to also reject
`Claude-Session:` lines, and disabled Claude Code's own built-in `Co-Authored-By:` footer via
`includeCoAuthoredBy: false`. Since the hook script and settings-sync code live under `scripts/°base/`
(base-owned, not project-owned), this fix belongs upstream in `base` so every consuming repo gets it via
the normal base-sync flow, instead of staying a one-off in `todo_splits_tracker`.

Four commits there capture this work: two planning commits, one implementation commit, and one earlier
memory-scaffolding commit. Per user instruction, the plan/query artifacts (commits #1/#2) are ported
adapted to base's own facts (branch `base`, no live commits found with the trailer — checked via
`git log --all --grep="Claude-Session"`, zero hits), and commits #3+#4 are squashed into one implementation
commit with the memory file written in its final, complete form (no `TODO: summarize this file.`
placeholder).

## Source commits (todo_splits_tracker, local checkout at `../todo_splits_tracker/`)
1. luckydonald/todo_splits_tracker@2a02ee6d54ea1ef4d02928835685ca16e5746d29 — plan: remove `Claude-Session:` trailer
2. luckydonald/todo_splits_tracker@54eb2749b4f03e13b6a9d1b27d4a0d36a0db9ef4 — plan update: also reject `Co-Authored-By:` via hook + `includeCoAuthoredBy`
3. luckydonald/todo_splits_tracker@01c422a38c722449d0fa159ab7bd88d776e40e06 — implementation (hook, settings, memory doc)
4. luckydonald/todo_splits_tracker@5ab74b9ae9b6510c71f3d4ec50825d3467640bc9 — original memory-scaffolding commit (squash into #3)

## Resulting base-repo commits

### Commit A (adapts #1, luckydonald/todo_splits_tracker@2a02ee6d54ea1ef4d02928835685ca16e5746d29)
- `ai/°base/plans/059_remove-claude-session-trailer-current-future.md` (new) — same structure as the
  source plan, but rewritten Findings for base's actual state: no reachable or dangling commit in `base`
  contains `Claude-Session:` (verified via `git log --all --grep="Claude-Session"`), so there is no
  "reword an existing commit" step — only "extend the hook going forward" carries over. Drop all
  `todo_splits_tracker`-specific facts (branch `mane`, commit `9fa4622`, dangling backup branches).
- `ai/°base/query.md` — append the two prompt lines from the source commit verbatim (they're generic,
  no repo-specific facts):
  - `❯ Also no `Claude-Session:` in the commit message.`
  - `❯ /plan make sure there's no `Claude-Session:` in commit messages, current and future.`

### Commit B (adapts #2, luckydonald/todo_splits_tracker@54eb2749b4f03e13b6a9d1b27d4a0d36a0db9ef4)
- Delete `059_remove-claude-session-trailer-current-future.md`, add
  `ai/°base/plans/059_remove-claude-session-and-co-authored-by-from-commits-curren.md` — rewritten
  Findings: existing hook is `scripts/°base/git/hooks/commit/reject_co_authored_by.py` (id `no-co-authored-by`
  in `.pre-commit-config.yaml`), currently only checks `Co-Authored-By`; `includeCoAuthoredBy` is a real
  Claude Code settings key not yet set anywhere in base; no project-memory file about this exists yet in
  base (so no "currently wrong" correction needed — it'll be created correct from the start). Drop the
  "reword commit" step (inapplicable, see Commit A).
- `ai/°base/query.md` — append the follow-up prompt line verbatim:
  - `❯ Note that `Co-Authored-By` is also disallowed, and has a git hook making sure, which should be extended. If you can also disable those commit system message via the git tracked per-repo config file, please do so. Add/fix the memory(-ies) to disallow both.`

### Commit C (squash of #3 + #4, luckydonald/todo_splits_tracker@01c422a38c722449d0fa159ab7bd88d776e40e06 + luckydonald/todo_splits_tracker@5ab74b9ae9b6510c71f3d4ec50825d3467640bc9)
Apply directly — base's current file contents match the parent-commit versions in
`todo_splits_tracker`, so these are clean patches:
- `scripts/°base/git/hooks/commit/reject_co_authored_by.py` — add `REJECTED_TRAILERS = ("Co-Authored-By", "Claude-Session")`, check tuple, print which trailer hit.
- `scripts/°base/ai/settings/°settings_lib/hooks.py` — `render_claude` passes through `shared["includeCoAuthoredBy"]` when present.
- `ai/tool-settings/settings.json` — add `"includeCoAuthoredBy": false` (top-level, after `version`).
- `.claude/settings.json` — add `"includeCoAuthoredBy": false` (generated output, kept in sync with the above — run `python3 scripts/°base/ai/settings/sync.py` rather than hand-editing, then verify the diff matches).
- `.pre-commit-config.yaml` — rename hook `name` to "Reject Co-Authored-By / Claude-Session trailers in commit messages".
- `ai/°base/memory/MEMORY.md` — add one index line for the new memory file, written with a real summary
  (not the source's placeholder `TODO: summarize this file.`), following this repo's existing entry style,
  e.g.:
  `- [Repo commit hooks](repo_commit_hooks.md) — pre-commit hook rejects Co-Authored-By/Claude-Session commit trailers; includeCoAuthoredBy: false set in .claude/settings.json.`
- `ai/°base/memory/repo_commit_hooks.md` (new) — final content matching source commit #3's version
  (frontmatter `name: repo-commit-hooks`, `metadata.type: project`, matching this repo's existing memory
  file conventions per `ai/°base/memory/feedback_commit_prefix_ssp_tag.md`), describing both rejected
  trailers and the `includeCoAuthoredBy` setting — written directly in final form, skipping the
  intermediate "only Co-Authored-By" placeholder state from source commit #4.

Commit message for C: `[base] git hooks: ai: Run: Extended the commit-msg hook to also reject the AI session-link trailer, and disabled Claude Code's own AI-authorship footer via includeCoAuthoredBy: false.` (adapted from source, base's `[topic]` convention per `AGENTS.md`).

## Verification
- `python3 scripts/°base/ai/settings/sync.py --check` passes (settings.json / .claude/settings.json stay in sync).
- `uv run --project scripts/°base python -m unittest discover -s scripts/°base/tests -v` — full suite still green (existing `reject_co_authored_by` behavior unchanged for `Co-Authored-By`, new `Claude-Session` branch covered if a test exists; add a case only if the test file already parametrizes over trailers).
- Manually invoke the hook against a scratch commit-msg file containing `Claude-Session:` and confirm exit code 1 with the new stderr message.
- `git log --stat` on the 3 new commits to confirm each is scoped only to the files listed above.
- `git status` clean afterward.
