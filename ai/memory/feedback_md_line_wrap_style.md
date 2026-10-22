---
name: feedback-md-line-wrap-style
description: "Markdown prose wraps at sentence ends, not at a fixed column; load the code-style skill's md.md before writing or editing any .md file, plans included"
metadata:
  type: feedback
---

Markdown prose (plan files, `CLAUDE.md`/`AGENTS.md`, `README.md`, skill docs, commit-adjacent notes) must not be hard-wrapped at an arbitrary column such as 80.
Wrap only at sentence ends, break after a comma only as a fallback for an overlong sentence, and never break mid-sentence because a word landed near a target width.
The full rule is in the `code-style` skill's `references/md.md`; code blocks and tables are exempt.

**Why:** The skill rarely loads on its own for markdown. A plan file was word-wrapped at a fixed column, and the user rejected the `ExitPlanMode` call just to send me to read `md.md` first.

**How to apply:** Before writing or editing any `.md` file, plans included, read `ai/skills/code-style/references/md.md` and write or rewrap the prose accordingly.
