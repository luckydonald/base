# Condense autonomous-/loop-tick boilerplate in query.md

## Context

`b6c5ddf5` (`ai/°base/query.md`) shows the harness now injects a fixed,
~700-char instructional block into the conversation on every autonomous
`/loop` tick (the `<<autonomous-loop-dynamic>>`/`<<autonomous-loop>>` sentinel
text, e.g. starting `# Autonomous loop tick (dynamic pacing)` — see
`ScheduleWakeup`'s tool description for the exact wording). `save-prompt/hook.py`
currently has no special handling for this text, so it falls through to the
default path and gets appended to `ai/°base/query.md` (6442 lines and
growing) verbatim, in full, on every single tick — pure repeated boilerplate,
not user content.

The repo already has an established pattern for this exact problem: bulky,
low-signal generated text (compact autoloads, Explore/Agent results, raw
command output) is written once to a file under
`ai[/°base]/output/<kind>/...` and `query.md` gets a single short line with a
markdown link to it (see `_handle_compact_prompt`, `_handle_task_notification`,
`_capture_codex_commands` in `scripts/°base/ai/hooks/save-prompt/hook.py`).
This task extends that same pattern to autonomous-loop-tick prompts, and —
since the tick text is normally byte-identical across ticks — reuses a single
file instead of writing a new one each time, per the user's request.

This only changes behavior going forward (no rewrite of existing `query.md`
history).

## Approach

In `scripts/°base/ai/hooks/save-prompt/hook.py`, add a new detector
alongside `_handle_compact_prompt`/`_handle_task_notification`:

1. **Detection**: match prompt text (after it's been stripped of any
   `<task-notification>` block, same as the existing `remaining_after_task`
   split) against a header regex, e.g. `^#\s+Autonomous loop tick\b`. This
   covers both the dynamic-pacing (`ScheduleWakeup`) and cron
   (`CronCreate`)-triggered variants, whatever their exact trailing wording,
   without hardcoding the full boilerplate string.

2. **Dedup + storage**: under `log_path.parent / "output" / "loop"`,
   look for an existing `NNN_<slug>.md` file whose content matches the
   current tick text byte-for-byte (mirrors `compact_result.py`'s
   `reserve_artifact_directory` dedup-by-content idea, simplified to flat
   files instead of numbered directories since there's no companion artifact
   per tick). Reuse it if found; otherwise allocate the next `NNN` and write
   a new file, named via the existing `slugify()` helper (`_lib.py`) from the
   header line (e.g. `001_autonomous-loop-tick-dynamic-pacing.md`).

3. **query.md entry**: append one short line per tick using the existing
   `_markdown_file_link()` helper, e.g.:
   `❯ Autonomous loop tick → [instructions](output/loop/001_....md) (`n` chars, `size`)`
   No usage stats are available at prompt-submit time (the tick's
   noop/verbose outcome is only known later, when the model calls
   `ScheduleWakeup` again), so the line is just the link — consistent with
   how `_handle_compact_prompt` only links the autoloads file.

4. **Wire it into `main()`**: this needs to run in both places a loop-tick
   prompt can appear — (a) as the *entire* prompt when no task notification
   fired, and (b) as `remaining_after_task` when a task notification woke the
   tick. Cleanest: factor the "render this prompt body" logic (currently the
   final `content = f"{prefix} {prompt}\n\n"` line, and the small
   `remaining_after_task` append) into one shared helper that first checks
   the new loop-tick detector, falls back to the current raw-prompt
   behavior otherwise. Call that helper from both sites.

## Critical files

- `scripts/°base/ai/hooks/save-prompt/hook.py` — add the detector + shared
  render helper; call sites are the existing `remaining_after_task` block and
  the final fallback `content = ...` line in `main()`.
- `scripts/°base/ai/hooks/_lib.py` — reuse `slugify()`, `append_and_commit()`.
- `scripts/°base/ai/hooks/compact_result.py` — reference implementation for
  the dedup-by-content idea (`reserve_artifact_directory`), not modified.
- `scripts/°base/tests/test_save_prompt_queued_commands.py` (and sibling
  `test_save_*` files) — existing test patterns for `save-prompt/hook.py` to
  follow when adding coverage for: first tick (new file written), repeat
  identical tick (reused file, no new file created), and a tick embedded
  after a `<task-notification>` block.

## Verification

- Add/extend a unit test under `scripts/°base/tests/` that feeds the hook a
  synthetic `# Autonomous loop tick (dynamic pacing)` prompt via stdin twice
  (identical text) and asserts: only one file exists under
  `ai/°base/output/loop/`, and `query.md` gained two short link lines (not
  the full boilerplate twice).
- Run the existing hook test suite (`scripts/°base/tests/test_save_prompt_*.py`
  and friends) to confirm no regression to codex-command/compact/plan
  handling sharing the same `main()` control flow.
- Manually pipe a sample payload (`{"prompt": "# Autonomous loop tick ..."}`)
  through `hook.py claude` in a scratch git repo and inspect the resulting
  `query.md`/`output/loop/*.md` for the expected condensed form.

## Leftover task 1 — fold debug fixtures + relocate this plan file (do immediately)

Implementation landed as commit `bee8c85` (rebased onto `88d277140ae9`, i.e.
`88d2771`, the non-worktree `base` branch tip — merge-base already confirmed
equal to `88d2771`). Session debug-dump capture (`ai/.debug` is on) recorded
this whole task's hook payloads. Two things are still outstanding, both
git-surgery only, no code changes:

1. **Add the session's debug fixtures.** All of them currently live under
   `ai/output/debug/*.json` in this worktree (**not** under
   `ai/°base/output/debug/` — see leftover task 2, this is the same routing
   bug). None were found in the non-worktree checkout's debug dirs for this
   session (checked both `ai/output/debug/` and `ai/°base/output/debug/`
   there — zero matches), so there is nothing to copy in from there; only
   this worktree's own files need adding. The file count is a moving target
   (grows on every hook firing, was 66 then 108 over the course of this
   conversation) — recompute at execution time, don't trust a hardcoded
   count:
   ```bash
   cd /home/user/git/luckydonald/base/.claude/worktrees/claude-loop-messages
   SESSION_ID=67305175-8399-4d68-994c-af848a182963
   git add -f $(grep -l "$SESSION_ID" ai/output/debug/*.json)
   ```
   (`grep -l` on the session_id field is the reliable filter — a plain text
   search for e.g. "Autonomous loop tick" also matches unrelated sessions'
   debug dumps, since that boilerplate is harness-wide, not session-specific;
   confirmed by a false-positive match against session `8afdf7b5-...`, a
   different, unrelated autonomous-loop invocation.)

2. **Relocate this plan file** from `ai/plans/001_condense-...md` to
   `ai/°base/plans/001_condense-...md` (`git mv`), matching where a correctly
   routed base-repo plan belongs. Do **not** also relocate `ai/query.md` →
   `ai/°base/query.md` as part of this leftover task — that's a judgment call
   for whoever picks this up (the whole session's query-log entries went to
   the wrong path; merging them into `ai/°base/query.md` risks clobbering/
   reordering concurrent entries there from other sessions). Flag it, don't
   just do it.

3. **Fold everything into `bee8c85`.** Since this plan file was edited again
   after `bee8c85` landed (this section), and the ongoing conversation kept
   triggering `ai: updated prompt` auto-commits on top, there is now a run of
   commits after `bee8c85` that are pure auto-commit/documentation noise for
   the *same* task, not new work. Re-audit before trusting this list — more
   may have landed since:
   ```bash
   git log --oneline 88d2771..HEAD
   ```
   As of this writing that's `bee8c85` followed by ten `ai: updated prompt`
   commits (`281d02d 1280c19 f90779d f45904d b600075 8f0b6c1 8b6f611 4d67b0b
   96d2a17 2d434bc`, oldest to newest, touching only `ai/query.md`), then one
   more commit documenting these leftover tasks (the tip, "ai: Plan update:
   Documented the two leftover tasks ..." — its sha keeps changing as this
   file itself gets amended into it, so look it up fresh with
   `git log --oneline 88d2771..HEAD` rather than trust a literal sha here).
   Make the `git mv` + `git add -f` changes from items 1–2 above as one
   throwaway commit on top of current `HEAD` first, then fixup *every*
   commit between `bee8c85` (exclusive) and that throwaway commit
   (inclusive) into `bee8c85`, e.g.:
   ```bash
   GIT_SEQUENCE_EDITOR='cat > "$1" <<REBASE
   pick bee8c85
   fixup 281d02d
   fixup 1280c19
   fixup f90779d
   fixup f45904d
   fixup b600075
   fixup 8f0b6c1
   fixup 8b6f611
   fixup 4d67b0b
   fixup 96d2a17
   fixup 2d434bc
   fixup <tip-plan-update-sha>
   fixup <throwaway-mv/add-sha>
   REBASE' git rebase -i 88d2771
   ```
   (original order, no reordering needed — `bee8c85` is already oldest).
   `bee8c85`'s message is already correct and needs no rename/amend. Clean up
   `ai/git/rebase-todo.sh` / `rebase-msg-*.md` afterward per the lplp skill,
   and re-audit once more (`git log --oneline 88d2771..HEAD`) to confirm a
   single clean commit remains.


## Leftover task 2 — `_is_inside_base_repo` breaks under `git worktree` (needs its own `/plan`)

**Root cause, already confirmed from this session:** every routing decision
in this repo's own hooks (`ai/query.md` vs `ai/°base/query.md`, `ai/plans/`
vs `ai/°base/plans/`, `ai/output/debug/` vs `ai/°base/output/debug/`, the
`[base]` commit-subject prefix, ...) goes through
`_is_inside_base_repo(subproject_root)` in
`scripts/°base/ai/hooks/°commit_style_lib/__init__.py:34-45`:

```python
def _is_inside_base_repo(subproject_root: Path) -> bool:
    if subproject_root.name != "base":
        return False
    origin = _git_text("remote", "get-url", "origin")
    return bool(re.search(r"(^|[:/])luckydonald/base(\.git)?/?$", origin, re.I))
```

It's called (see `_lib.py`'s `_ai_prefix_root()` and
`°commit_style_lib.py`'s `base_ai_commit_subject()`) as
`_is_inside_base_repo(subproject) or _is_inside_base_repo(git_root)`, where
`subproject = _subproject_root()` (`$CLAUDE_PROJECT_DIR` or `cwd`) and
`git_root` is `git rev-parse --show-toplevel`. **Both of those are the
worktree's own directory when running inside a linked `git worktree`**, and
a worktree's directory is named after the worktree/branch
(`claude-loop-messages`), never `base` — so the basename check fails for
every linked worktree of this repo, even though it plainly *is* the base
repo. Confirmed from this exact worktree:

```
$ git rev-parse --show-toplevel
/home/user/git/luckydonald/base/.claude/worktrees/claude-loop-messages
$ git rev-parse --git-common-dir
/home/user/git/luckydonald/base/.git
$ git rev-parse --absolute-git-dir
/home/user/git/luckydonald/base/.git/worktrees/claude-loop-messages
$ git remote get-url origin
https://luckydonald@github.com/luckydonald/base.git
$ echo "$CLAUDE_PROJECT_DIR"   # empty for a plain manual shell; hooks get it set, this worktree's is the worktree path
```

**Promising fix direction (verify, don't just apply blind):**
`git rev-parse --git-common-dir` always resolves to the *original*
checkout's `.git` directory, identically from the main checkout and from
every one of its linked worktrees (verified above — same absolute path from
this worktree as from `/home/user/git/luckydonald/base` itself). Its
resolved parent directory's basename (`Path(common_dir).resolve().parent.name`)
should be a worktree-proof stand-in for "the checkout directory is literally
named `base`" — check that basename instead of (or in addition to)
`subproject_root.name`. Needs a real `/plan` because:
- Confirm this holds for a *bare* main checkout too (`git worktree add` from
  a bare repo has no non-`.git` "original" directory at all).
- Decide whether the existing `subproject_root.name != "base"` check should
  be replaced outright or kept as a fast-path with the common-dir check as a
  fallback.
- Audit every caller of `_is_inside_base_repo` (`_lib.py`'s
  `_ai_prefix_root()`/`base_ai_commit_subject()` in
  `°commit_style_lib/__init__.py`, and anywhere else it's imported) — a
  behavior change here reroutes `query.md`/plans/output/debug paths and the
  `[base]` commit prefix for every hook, repo-wide.
- Decide the fate of this session's already-misrouted files: `ai/query.md`
  (this whole session's entries — see leftover task 1, item 2), and whether
  other already-existing linked worktrees
  (`claude-split-impl`, `claude-split-improvement`, `fix-plan-decision`,
  per `git worktree list`) have the same misrouted `ai/query.md`/`ai/plans/`
  drift that should be swept up in the same pass.
- Add/extend `scripts/°base/tests/test_commit_style_lib.py` with a
  worktree-shaped fixture (a real `git worktree add`, not just a
  differently-named directory) so this regression can't silently return.

## Continuation query (paste into the repo-root Claude session)

```
Continue work from worktree /home/user/git/luckydonald/base/.claude/worktrees/claude-loop-messages
(branch worktree-claude-loop-messages), per
ai/°base/plans/001_condense-autonomous-loop-tick-boilerplate-in-query-md.md
in that worktree (it may still be at ai/plans/... — that's leftover task 1,
item 2, below).

Do "Leftover task 1" now, immediately (git-surgery only, no code changes):
fold this conversation's stray `ai: updated prompt`/`ai: save plan` commits
into commit bee8c85, git-mv the plan file into ai/°base/plans/, and
`git add -f` this session's debug fixtures (session_id
67305175-8399-4d68-994c-af848a182963) from ai/output/debug/*.json — full
recipe is in that section, including the exact commands and the rebase todo
shape. Work directly in the worktree directory above (cd into it; this is a
normal multi-worktree git operation, not something to route around).

Then start a fresh `/plan` for "Leftover task 2": `_is_inside_base_repo()`
in scripts/°base/ai/hooks/°commit_style_lib/__init__.py (lines 34-45)
misdetects every linked git worktree of this repo as *not* being the base
repo (checked via directory-basename == "base", which is never true for a
worktree's own directory), silently misrouting ai/query.md, ai/plans/,
ai/output/debug/, and the [base] commit prefix for the whole session. All
the diagnostic groundwork (confirmed root cause, a promising fix direction
using `git rev-parse --git-common-dir`, and the open questions to resolve)
is already written up in that plan section — turn it into a proper
implementation plan, don't just patch the regex.
```
