---
name: "commit-with-lplp-style"
description: "Activates the lplp-pipbuck commit style for the current session. Commits after every completed task as a plain new commit (never amended live), tags the prior HEAD via scripts/tag_backup.py as a safety net, then interactively rebases to fold nearby `ai:` prompt/decision auto-commits into the work commit while preserving plan-revision history, writes messages via ai/git/pending-commit.md, and never commits unrelated files. Use when the user opts in to this style at session start, or explicitly asks to enable it."
---

# lplp Commit Style

Adopt these rules for every commit made this session:

1. **Commit after every completed task.** Never leave work uncommitted.

2. **Never `--amend` for regular work — always commit fresh, then fold via rebase.** The sequence for every commit is:
   1. `git commit -F ai/git/pending-commit.md` — the new commit for the work just finished (see rule 3 for the message file, rule 4 for its format).
   2. `./scripts/tag_backup.py` — tags the new `HEAD` (after your new commit) as `bak/<hash>`, so it stays reachable through the rebase in step 3 even if a branch pointer later gets reset/rebased.
   3. Immediately fold any `ai:` auto-commit hook commits that are now sitting just before your new commit, using the interactive-rebase procedure under "Cleaning up stray `ai:` auto-commits" below — same auto-commit patterns and fold/keep-separate judgment calls as always applied.
   4. **If any rebase step needs to reset a branch pointer, use `git reset --keep`, never `git reset --hard`.** `--keep` aborts instead of clobbering if the working tree has changes the reset would overwrite, so a slip here can't quietly eat uncommitted work the way `--hard` would.

   **The user's own replies can add more `ai:` commits after your fold, including mid-cleanup.** Answering an `AskUserQuestion` (`ai: save decision <slug>`), or simply the user sending you a message/task (`ai: updated prompt`), each auto-commits on arrival — including messages sent *while you're already running this cleanup procedure*, and including a plain acknowledgement like "commit" or "squash" with nothing else in it. This is not a background risk to keep in mind — it is steps 4 and 7 of the Procedure below (**Re-audit before writing the rebase todo** / **Re-audit once more after running**), and both are mandatory, not something to remember to do. Step 4 is the one that actually matters: a rebase todo written from a stale audit is already wrong before you run it, so re-check right before you write it — especially right after any `AskUserQuestion` call in this procedure, since that call's own answer is guaranteed to leave a fresh commit on `HEAD` by the time it resolves. Step 7 only catches whatever slips in during the rebase run itself. If invoking this skill produces "nothing to do" more than once in a row, that itself is a signal — it usually means a trailing `ai:` commit landed after your last fold (often from the very message that re-invoked the skill) and was missed, not that the skill has nothing left to do. It can also mean the opposite direction: an `ai:` commit sitting *before* the range you last squashed (e.g. a memory-sync commit from another tool, or anything else that landed on the branch between your prior code commit and the one you just cleaned up) — check the commit right before your last squash's starting point too, not just what trails after it.

   Steps 1–2 run as one whitelisted command: `git commit -F ai/git/pending-commit.md && ./scripts/tag_backup.py`.

   Auto-commit patterns — fold into the preceding code commit **by default**:
   - `ai: updated prompt` — user prompt saved to `ai/query.md`
   - `ai: save decision <slug>` — resolved `AskUserQuestion`
   - `ai: agent <id> results` — subagent result record
   - `ai: record memory <slug>` — memory file written (e.g. `ai: record memory MEMORY`, `ai: record memory feedback_commit_amend_over_reset`)
   - `ai: save plan <NNN>_<slug>` — plan files

   **When to keep a commit separate instead of folding:**
   - A plan commit whose plan file content is a genuine, substantive change over the plan it follows — cutting a new version — stays its own commit. Rename it away from the raw hook message per the plan-commit format below.
   - A plan commit is followed by one or more further plan-file revisions for the *same* plan number — folding any of them would erase the revision history. Keep each version as its own commit (first one `ai: Plan:`, each later one `ai: Plan update:`).
   - A plan-save commit whose plan file content is **byte-identical** (or near-identical, no real change) to the plan it follows is not a new version — it did not "change" anything — fold it into its implementation like any other lone auto-commit.
   - Several plan-save commits landing within seconds of each other, with **non-overlapping** edits (e.g. drafting different sections back-to-back rather than revising the same content) — squash those into a single plan commit. They're one drafting burst, not distinct versions; only genuinely separate revision passes (later editing, e.g. after review or a test run surfaced something) earn their own `ai: Plan update:`.
   - A prompt commit (`ai: updated prompt`) represents a clearly new or unrelated topic — it started a different task, not a continuation of the preceding code commit.
   - When in doubt, fold. The goal is readable preserved history, not having every auto-save as separate commit.

   **Naming a plan-only commit that is kept separate:** raw hook messages like `ai: save plan <NNN>_<slug>` are placeholders, not final history — rename them to match the summary style used for real work, but with `ai: Plan:` (first version) or `ai: Plan update:` (each later revision of the same plan number) in place of `ai: Run:`:
   ```md
   [where] component-or-topic: ai: Plan: <short one-line summary of what the plan proposes><sentence-separator>
   ```
   ```md
   [where] component-or-topic: ai: Plan update: <short one-line summary of what changed in this revision><sentence-separator>
   ```
   Leaving the bare `ai: save plan <NNN>_<slug>`/`ai: Plan …` hook message on a commit that's staying in history is not wanted — always rename it once it's confirmed to be a real, kept version cut.

   The plan's summary line should read as basically the same line as the `ai: Run:` commit that eventually implements it, just in **current/imperative tense instead of past tense** — e.g. plan says `ai: Plan: Fix \`get-base.py\` auto mode failing on a fresh repo...`, the implementation says `ai: Run: Fixed \`get-base.py\` auto mode failing on a fresh repo...`. Don't invent a differently-worded plan summary; write the eventual Run summary first (even if only in your head) and de-conjugate it.

3. **Always write the message to `ai/git/pending-commit.md` first** like this:
   1. run exactly the whitelisted command `rm ai/git/pending-commit.md || echo 'was gone'`, which makes sure it's not gonna cause "stale unread file" issues.
   2. Write to `ai/git/pending-commit.md` using the preferred Built-in/MCP tool.
   3. Pass it to the commit with the whitelisted `git commit -F ai/git/pending-commit.md && ./scripts/tag_backup.py`. Never inline the message in the command, to avoid the need for user confirmations.

4. **Message format:**

   **Before picking `component-or-topic`, check the file's own history for an established one:**
   ```bash
   git log --oneline -5 -- <changed file(s)>
   ```
   Run this for the file(s) the current commit is actually about (the primary file if several were touched for one cohesive reason). Parse out the `component-or-topic` segment from each prior subject that matches the `[where] component-or-topic: ...` shape — the text **after the last `]`** in the subject, up to the following `: ai:`/`:`. When `[where]` itself has a leading `[base] [source-repo]`-style nested bracket, that source-repo bracket is not part of `component-or-topic` and must never be swept into the reused wording; only the text after the final `]` counts. If those subjects agree, reuse that exact wording instead of inventing a fresh label. If they disagree, prefer the wording from non-`ai: Run:` subjects — human-written commits, or renamed/kept-separate `ai: Plan:`/`ai: Plan update:` commits — over prior `ai: Run:` auto-generated ones. Only fall back to picking a new label (per the examples below) when the file is new or nothing reusable turns up.

   **This history lookup governs `component-or-topic` only.** It must never be used to infer or carry forward an optional source-repo bracket (see below) just because a prior commit on the same file happened to have one — that's a separate decision with its own freshness/relevance rule.

   ```md
   [where] component-or-topic: ai: Run: <short one-line summary><sentence-separator>

   <multiline body: what changed, why, key decisions>
   ```
   Where examples: `[.idea]`, `[git]` (gitignore etc.), `[github]` (workflows, issue templates, …), `[frontend]`, `[db]`, `[stdb]` (spacetimedb), `[api]`, `[backend]`, `[docker]`, `[coolify]`, `[infra]`, …
   The word or phrase after `[where]` is a component, feature, subsystem, or topic, not a Conventional Commit type. Do not use `feat`, `fix`, `chore`, `docs`, `test`, or `refactor` there unless that word is literally the component or topic being changed.
   Good examples:
   - `[frontend] admin: ai: Run: Implemented user deletion UI.`
   - `[backend] models: ai: Run: Added models for cool feature.`
   - <code>[backend] cool feature: ai: Run: Added the `cool` model.</code>
   - `[git] ignore rules: ai: Run: Ignored generated cache files.`
   Bad examples:
   - `[frontend] fix: ai: Run: Implement user deletion UI`
   - `[backend] feat: ai: Run: Added cool feature models`
   End every commit summary with a sentence separator: `.`, `:`, `,`, `!`, or `?`.
   Usually use `.` when the summary stands on its own and the body only adds context. Use `:` when the subject needs the body/details that follow to complete the thought.
   Both summary and body may contain pure-markdown for formatting.
   Code ticks (`` `like this` ``) are allowed in the summary line itself — e.g. to name a function, file, or flag — not just in the body.
   Do not hard-wrap the body at a fixed column width (e.g. 72 chars). Keep each paragraph or bullet point as one unbroken line, regardless of length; only break where a new paragraph or bullet genuinely starts.

   For normal use, multiple `[where]` parts can be written as one bracket with pipes, e.g. `[backend|frontend]`.

   For the base repo itself, see `ai/°base/AGENTS.md`'s "Commit format" section for the `[base] [optional source repo] topic: ai: …` rule — that bracket has its own base-specific decision criteria and doesn't belong in this shared skill.

5. **Stage only files you changed yourself as part of the current task.** Before staging, run `git status` and `git diff --name-only` to confirm every file you are about to add. Never stage:
   - `ai/git/pending-commit.md` (it is gitignored)
   - files modified by the user, by hooks, or by other tooling that you did not touch
   - files unrelated to the task at hand, even if they appear modified
   - if there are other files changed, someone (user or other agent) else might be working here, in that case check that we only stage our own diff lines.

   Add files by explicit path — never `git add .` or `git add -A`.

6. Once this skill is activated, keep commiting after every completed task automatically without asking again.
   If the user responds with a simple `commit` or similar (`commit plz`, `keep commiting`, etc.), this means they want to remind you, to follow the "keep automatically committing" instruction, which you should already anyway.

7. **Rule 2's post-commit fold is about the commit chain you just made — not a license to rewrite older history.** Folding the `ai:` auto-commits sitting immediately before the commit you just made (rule 2, step 3) is routine and needs no extra permission. But if you spot a stray un-folded `ai:` auto-commit further back in existing history (e.g. a leftover `ai: updated prompt` because an unexpected commit landed in between on some earlier task), do not reach back and rebase/`reset --soft`/amend it away on your own initiative — ask the user first (e.g. via `AskUserQuestion`) whether they want it cleaned up. An explicit cleanup request from the user (e.g. "clean up the commits since last push") still authorizes the full procedure below over whatever range they specify.

8. **Land a pure code move/rename as its own commit before changing that code further.** When relocating code (e.g. splitting a function into its own module), commit the move with identical content first — so git's diff/rename detection shows it as a move, not a rewrite — then commit the actual behavioral or style change on top. Keeps both diffs small and independently reviewable instead of one large tangle of "what moved" and "what changed."

9. **Activating this skill while a plan is still being drafted means noting it in the plan file, not just this conversation.** A plan's implementation frequently happens somewhere this chat history isn't visible — a fresh session picking the plan back up later, or a subagent (e.g. via the `Agent`/`Task` tool) that only ever receives the plan document itself and "writes back" a finished result, never this conversation's context. If the activation only lives in the chat, that implementer has no way to know the style is expected and will default to plain commits. So once the skill is turned on during planning, add one short line to the plan file itself before it's saved (or as a small follow-up edit if the skill was turned on right after saving), e.g. right after the title:
   ```md
   **Commit style:** `commit-with-lplp-style` is active — follow it for this implementation.
   ```
   This is in addition to, not instead of, keeping the style active for the rest of the current session.

## Cleaning up stray `ai:` auto-commits

Run this procedure after every commit as rule 2, step 3, to fold that commit's immediately preceding `ai:` auto-commits. It also works standalone before merging or review when a branch has stray prompt/decision commits mixed further back into its history (rule 7).

Handles these hook-created commits:

- **`ai: updated prompt`** — one per user prompt; touches only `ai/query.md` or `ai/°base/query.md`.
- **`ai: save decision <slug>`** — one per resolved `AskUserQuestion`; touches only `ai/query.md` or `ai/°base/query.md`. The slug is derived from the first question's text.
- **`ai: agent <id> results`** — subagent result record; touches only agent result files.
- **`ai: record memory <slug>`** — memory file written; touches only files under the memory directory.
- **Plan commits** — `ai: Plan …`, `ai: Plan Update …`, or `ai: save plan <NNN>_<slug>`; touches only `ai/plans/<NNN>_*.md` or `ai/°base/plans/<NNN>_*.md`. Keep separate — and renamed to `ai: Plan: …`/`ai: Plan update: …` (never left as the raw hook message) — when the plan file content is a genuine change cutting a new version, or when there are multiple revisions of the same plan number (the sequence records how the plan evolved). A plan commit whose content is unchanged/near-identical to the plan before it, or a lone plan commit with no real content and no follow-up updates, may be folded into its implementation instead.

### Procedure

**1. Audit the branch**

```bash
git log --oneline origin/<upstream>..HEAD
for sha in <shas>; do
  echo "$sha $(git log -1 --format='%s' $sha): $(git show --name-only --format='' $sha | tr '\n' ' ')"
done
```

**2. Plan groups**

- **`ai: updated prompt`**, **`ai: save decision <slug>`**, **`ai: agent <id> results`**, and **`ai: record memory <slug>`** commits → fix up under the **preceding** code commit by default. Exception: a prompt commit that clearly starts a different/unrelated task should stay as its own `pick`.
- **Plan commits** → fix up into the implementation commit if the plan was never revised, or if a follow-up plan-save's content turned out unchanged/near-identical (no real "change" happened, so it didn't earn a new version). Plan-saves seconds apart with non-overlapping edits (one drafting burst) squash together into a single plan `pick`. If the plan was genuinely revised in separate passes, keep each version as a separate `pick` and rename it — `ai: Plan: …` for the first, `ai: Plan update: …` for each later revision — instead of leaving the raw `ai: save plan <NNN>_<slug>` hook message. Word each summary as the eventual `ai: Run: …` summary in current tense rather than past tense.
- **Mislabeled commits** → flag commits whose message does not match the files they actually changed. Rename them as part of the rebase instead of silently folding them the wrong way.

**3. Write renamed commit messages** to `ai/git/rebase-msg-<sha>.md` for any commits needing a label fix.

**4. Re-audit before writing the rebase todo — this is the one that actually matters**

```bash
git log --oneline -5
```

Steps 1–3 take real time, and any `AskUserQuestion` call along the way (including rule 7's own confirmation prompt) auto-commits `ai: save decision <slug>` the instant it's answered. A rebase todo written from a stale step-1 audit is wrong before it's even run — it will silently omit whatever landed since, and running it produces a plan that *looks* successful while leaving a new stray commit sitting right on top. If the tip commit here isn't the one your plan from steps 1–3 was built on, go back and fold it into the plan now, before step 5 — don't write the todo script first and hope to catch it after.

**5. Write the rebase todo script**

```bash
cat > ai/git/rebase-todo.sh << 'SCRIPT'
cat > "$1" << 'REBASE'
pick <code-commit>
fixup <prompt-commit>          # ai: updated prompt; backward-fold
fixup <decision-commit>        # ai: save decision <slug>; backward-fold
fixup <agent-commit>           # ai: agent <id> results; backward-fold
fixup <memory-commit>          # ai: record memory <slug>; backward-fold
exec git commit --amend -F ai/git/rebase-msg-<sha>.md
pick <plan-commit>             # plan with follow-up updates: keep separate
# fixup <plan-commit>         # lone plan (no updates): may fold into implementation
pick <next-code-commit>
fixup <prompt-commit>
...
REBASE
SCRIPT
chmod +x ai/git/rebase-todo.sh
```

Put `exec git commit --amend -F ...` after all fixups for that group to rename the squashed result.

**6. Run**

Gate the actual rebase on a `current commit = <expected sha>` precondition, using the tip sha confirmed in step 4 — never run the rebase itself unguarded:

```bash
test "$(git rev-parse HEAD)" = "<expected-sha-from-step-4>" && \
GIT_SEQUENCE_EDITOR=ai/git/rebase-todo.sh git rebase -i origin/<upstream>
```

`test ... &&` makes the rebase a no-op instead of running against a HEAD your plan wasn't built on: if any commit landed between step 4's audit and this call (however unlikely), the check fails, the rebase never starts, and you go back to step 1 for a fresh pass — instead of silently rewriting a HEAD your rebase-todo doesn't actually match.

`ai/git/` is gitignored, so `rebase-todo.sh` and the `rebase-msg-<sha>.md` files never leak into a commit — clean them up (`rm ai/git/rebase-todo.sh ai/git/rebase-msg-*.md`) once the rebase lands.

**7. Re-audit once more after running**

```bash
git log --oneline -5
```

This is the safety net for whatever lands *during* the rebase itself (e.g. a message arriving mid-run) — step 4 is what prevents writing a stale plan in the first place, this just catches the remainder. If the tip commit is an `ai:` auto-commit not covered by the plan you just ran, treat it as a new pass and go back to step 1. Only consider the branch clean once this comes back with nothing new — "ran the rebase" is not the same as "done."

**8. Optional — rewrite HEAD as branch summary**

Write to `ai/git/pending-commit.md`:

```md
[scope] category: ai: Run: <summary>

Branch `<name>` based on `origin/<upstream>` @ <sha>.

- bullet: key decisions
- bullet: what changed and why
```

Then:

```bash
git commit --amend -F ai/git/pending-commit.md
```
