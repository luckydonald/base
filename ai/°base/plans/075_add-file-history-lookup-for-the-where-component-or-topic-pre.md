# Add file-history lookup for the `[where] component-or-topic:` prefix in commit-with-lplp-style

## Context
The lplp commit-style skill (`ai/skills/commit-with-lplp-style/SKILL.md`, symlinked from `.claude/skills/` and `.agents/skills/`) tells the agent to write commit subjects as `[where] component-or-topic: ai: Run: <summary>` (rule 4, "Message format"), but gives no guidance on *how* to pick `component-or-topic` for a given file/area. In practice this label should stay consistent per file/area over time (e.g. this very skill file has used `lplp commit style` across ~8 commits — see `git log --oneline -8 -- ai/skills/commit-with-lplp-style/SKILL.md`), but nothing currently tells the agent to check for that existing convention before inventing a new label. The user wants the agent to glance at recent history for the file(s) being committed and reuse the established topic wording instead of drifting, preferring human-authored commits over previous `ai: Run:` auto-generated ones when history isn't uniform.

## Change
Edit `ai/skills/commit-with-lplp-style/SKILL.md` only (the two skill paths are symlinks to it, so editing the target updates all three).

Add a new step to rule 4 ("Message format"), inserted **before** the existing format block/examples, describing this lookup:

- Before picking `component-or-topic`, run `git log --oneline -5 -- <changed file(s)>` for the file(s) the current commit touches (the primary file if several were touched for one cohesive reason; the shared one(s) if the task spans a known area).
- Parse the `component-or-topic` segment out of each prior subject line matching the `[where] component-or-topic: ...` shape (the text between `]` and the next `: ai:`/`:`).
- If those prior subjects agree on a topic string, reuse it verbatim rather than rewording it.
- If they disagree (not uniform), prefer the phrasing from non-`ai: Run:` subjects (i.e. human-written commits, or renamed/kept-separate `ai: Plan:`/`ai: Plan update:` commits) over prior `ai: Run:` auto-generated ones — human wording wins as the source of truth.
- If there is no prior history for the file (new file) or nothing reusable turns up, fall back to today's existing behavior: pick a sensible new component-or-topic label per the existing good/bad examples.

Keep this as a short, numbered/bulleted addition consistent with the terse, directive style already used throughout the skill (see rules 2, 4, 7 for tone/format reference) — not a new top-level rule, just folded into rule 4 since it's part of composing the message format.

## Verification
- Read back the edited `ai/skills/commit-with-lplp-style/SKILL.md` to confirm the new guidance reads clearly in context and doesn't contradict the existing "Good examples"/"Bad examples" block.
- Confirm via `ls -la .claude/skills/commit-with-lplp-style .agents/skills/commit-with-lplp-style` (already verified during planning) that both are symlinks to `ai/skills/commit-with-lplp-style`, so no further file edits are needed.
- No code/tests to run — this is a documentation/skill-instruction change.
</content>
