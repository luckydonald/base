---
name: "move-ai-to-project"
description: "Use at the end of a task that edited a different (sub)project than the one the session started in, for example a /todo-loop run that fell through to `dumper/` while the session cwd was `sync_todo/`. The hook commits (`ai: updated prompt`, `ai: save decision`, `ai: save plan`, agent results) land in the session's own `ai/` folder, so this moves them into the edited project's `ai/` and folds them into its commits. Also use when the user says the prompt/plan commits are in the wrong folder."
---

# Move the run's `ai:` files to the project that was edited

The hooks write to the `ai/` of the **session's working directory**, not of the project the work happened in.
After a run on another (sub)project, `sync_todo/ai/prompt.md` and `sync_todo/ai/plans/` hold the prompts and the plan of a `dumper` change, and `sync_todo`'s history would show commits that have nothing to do with it.
This skill is the cleanup aftermath: it relocates those files, so the edited project owns its prompts and plans, and the session project has no trace.

## When

- **Last, never earlier.** Run it when the feature is implemented, tests are green, the todo is closed and synced, and no more user interaction can land.
  Every answer to a question and every message creates another `ai:` commit in the wrong folder, so moving early just means moving twice.
  Do not ask for or announce the move before that, and do not do it per commit.
- Skip it if the session project **is** the edited project.
- A single prompt commit that arrives after the move (the message that follows the final report) may still land in the old folder.
  Say so in the report instead of chasing it.

## Procedure

Work from the repo root and use `git -C` or absolute paths; the shell resets its directory after each call and a `cd` prefix breaks the whitelisted commands.

1. **Audit** `git log --name-status <last commit of the previous task>..HEAD`.
   List the commits of this run that touch only the session project's `ai/prompt.md`, `ai/plans/…` or `ai/output/agents/…` (the `ai:` commits), the work commit(s) of the edited project, and the todo sync (`[TODOs] synced todos for <project>.`).
   Anything else is not yours; leave it.
2. **Tag the tip** with `scripts/tag_backup.py` and remember the sha.
   Gate the rewrite on that sha (`test "$(git rev-parse HEAD)" = <sha> && …`), so a commit that landed meanwhile aborts it.
3. **Decide the groups** by the rules of `/commit-with-lplp-style`:
   - Every plan revision except the last one stays its own commit: `ai: Plan:` for the first, `ai: Plan update:` for each later one.
     Prompt and decision commits fold into the plan commit before them.
   - The last plan revision, all remaining prompt, decision and agent commits, the work, and the todo sync fold into **one** `ai: Run:` commit.
     Its body names what the last plan revision changed against the last kept one.
   - Scope in every subject is the edited project, `[dumper] stickers: ai: Run: …`.
     Reuse the `component-or-topic` label of the files' history (`git log --oneline -5 -- <files>`).
4. **Path mapping**, applied to the content of each commit:
   - `<session>/ai/prompt.md`: the lines the run added (it is append-only, so the delta is `new[len(base):]` against the file at the last commit before the run) are appended to `<edited>/ai/prompt.md`; the session file goes back to its base content.
   - `<session>/ai/plans/<NNN>_<slug>.md` becomes `<edited>/ai/plans/<NNN'>_<slug>.md`, where `NNN'` is the edited project's next number (`ls <edited>/ai/plans | tail`); its own numbering is independent of the session project's.
   - `<session>/ai/output/agents/<id>/…`: same, into the edited project's `ai/output/agents/`.
5. **Rewrite**, from a clean tracked tree (untracked clutter is fine): `git reset --keep <base>`, then per group put the mapped files in place (`git show <commit>:<path>` for each revision), `git checkout <tip> -- <the edited project's work files>` for the last group, `git add` by explicit path, `git commit -F <message file>`.
   Messages go to files in the scratchpad (`ai/git/pending-commit.md` belongs to one project and can hold a stale text); never `git add .`.
   A small script keeps this reproducible, and a rebase todo cannot rename paths.
6. **Verify**:
   - `git diff --stat <bak-tag> HEAD` shows only the moved files (prompt lines out of the session project, in to the edited one; the plan file renamed).
   - `git diff --stat <base> HEAD -- <session project>` is empty.
   - The edited project's tests still pass; `git log --oneline -5` shows the new commits and no stray `ai:` commit on top.
7. **Report** the new hashes, that the old folder has no trace, and any commit that is still expected to land afterwards.

## Rules

- Never `git reset --hard`; use `--keep`, so a slip cannot eat uncommitted work.
- Never push, and never touch commits older than the run.
- Do not delete the backup tag.
- Untracked files (`ai/output/agents/…` not yet committed, local clutter) are left where they are and reported.
- If the audit shows commits you cannot attribute with certainty to this run, ask before moving them.
