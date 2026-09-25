# Fix stale `[optional source repo]` commit-tag reuse

## Context

Commit `9d799aba` (`[base] [hoass_plugin-template] ai/hooks: ai: Run: Added \`push\`/\`push it\` to the save-prompt hook's ignored-phrase set.`) tagged the change with `[hoass_plugin-template]`, but nothing about that specific task ties it to the `hoass_plugin-template` repo — it's a generic save-prompt hook tweak. Checking history for the touched file confirms the problem: every prior `[hoass_plugin-template]`-tagged commit on `scripts/°base/ai/hooks/save-prompt/hook.py` (and everywhere else it appears) dates to **2026-07-17**, over two months before this **2026-09-25** commit. Reusing that tag now was a stale guess, not a signal that was actually true for this session.

Two root causes, both in how the `commit-with-lplp-style` skill is written:

1. **Ambiguous history-lookup parsing.** `ai/skills/commit-with-lplp-style/SKILL.md` (rule 4, "Before picking `component-or-topic`...") says to parse the reusable label as "the text between `]` and the following `: ai:`/`:`". For a subject like `[base] [hoass_plugin-template] ai/hooks: ai: Run: ...` there are two `]` characters, and the instruction never says which one to anchor on. In practice this let the optional `[source repo]` sub-bracket get swept into the reused "component-or-topic" wording and copied forward verbatim, with no freshness or relevance check — it's the direct mechanism that produced the bad tag.
2. **No real decision rule for when to add `[optional source repo]` at all.** The only place this bracket is documented is one line in the generic (non-base-specific) `commit-with-lplp-style` SKILL.md: `For the base repo itself, use \`[base] [optional source repo] topic: ai: …\`.` — no criteria for when to include it, where the name comes from, or how stale a prior usage is allowed to be. The base-repo-scope instruction file (`ai/°base/AGENTS.md`, which `CLAUDE.md` routes to for this repo) has its own "Commit format" section but doesn't mention this bracket at all, so the one base-specific wrinkle in a generic skill lives nowhere a reader would expect, and got no scrutiny.

Per the user's own rule of thumb: only tag a commit with a source-repo bracket when that source is either **stated explicitly this session** (e.g. at session start, or the user names it while describing the task) or backed by **recent, topically-matching** history for the exact file/area — never a stale, unrelated-vintage match.

## Changes

### 1. `ai/skills/commit-with-lplp-style/SKILL.md` — fix the parsing ambiguity, narrow its scope
- In rule 4's history-lookup paragraph, make explicit that `component-or-topic` is parsed from **after the last `]`** in the subject, up to `: ai:`/`:` — so a leading `[base] [source-repo]` prefix is never absorbed into the reused topic wording.
- State plainly that this file-history reuse rule governs `component-or-topic` only. It must never be used to infer or carry forward an optional source-repo bracket — that's a separate decision (see AGENTS.md change below), not something to copy because a prior commit on the same file happened to have one.
- Replace the single unqualified line about `[base] [optional source repo] topic: ...` with a short pointer to the base repo's own AGENTS.md "Commit format" section for the actual rule, since this skill is shared across repos and shouldn't own base-specific policy.

### 2. `ai/°base/AGENTS.md` — own the `[optional source repo]` decision rule
Expand the existing "Commit format" section (currently just `[base] topic: ai: Run: ...`) to cover the optional source-repo bracket explicitly:
- Format: `[base] [source repo] topic: ai: Run: ...` — the bracket names a `luckydonald/`-owned repo whose work is *why* this base change is happening (e.g. a hook/feature ported in from, or requested by, a session working in that linked repo).
- **Only add it when one of these holds:**
  - The source repo was stated explicitly this session (session start, or named while describing the task), or
  - The exact file/area has a source-repo tag in *recent* history (not a months-old match) that matches the current change's topic.
- **Otherwise omit the bracket entirely** — plain `[base] topic: ai: Run: ...` is the correct default when there's no current-session signal. Do not guess a source repo from a stale or topically-unrelated prior commit just because it touched the same file.
- Note that this is distinct from feature-area tags like `[ssp]` (see `ai/°base/memory/feedback_commit_prefix_ssp_tag.md`), which are a standing convention for a specific feature area, not a "where did this originate" tag — don't conflate the two lookup rules.

### 3. Fix today's commit tags
The user has clarified that this whole work bunch (today's session, 2026-09-25) is actually sourced from `sync_todo` work, not `hoass_plugin-template`. `9d799aba` isn't the only commit in the affected range — the range runs from today's first real commit (`adbfe106`) through the current tip (`d4acd145`, an `ai: updated prompt` auto-commit). Since this info only exists as something the user just said this session, it's exactly the "stated explicitly this session" case from rule 2 above, so:
- Interactively rebase `adbfe106^..HEAD`.
- Reword `9d799aba`'s subject from `[hoass_plugin-template]` to `[sync_todo]`.
- For every other real (non-`ai:`-auto-commit) commit in that range that currently has no source-repo bracket (`b69e545c`, `49642ca6`, `170b78b5`, `071b119e`, `3473c194`, `57ca8b00`, `ca2c77c7`, `08bbdb87`, `8008f27b`, `abc8e0bf`, `adbfe106`), insert `[sync_todo]` after `[base]` in the subject, leaving the rest of each message untouched.
- Leave `ai:`-prefixed auto-commits (`ai: updated prompt`, `ai: save plan ...`) alone — this reword is only about the real work commits' `[where]` tags, not a fold/cleanup pass, and untouched auto-commits keep the rest of history stable.
- Tag the pre-rebase tip via `./scripts/tag_backup.py` first, same safety-net habit as the lplp style's own rule 2.

## Verification
- Re-read both edited files to confirm the parsing rule and the decision rule are unambiguous and don't contradict each other.
- `git log --oneline adbfe106^..HEAD` after the rebase: every real work commit in range should show `[base] [sync_todo] ...`, `9d799aba` specifically no longer says `hoass_plugin-template`, and the `ai:` auto-commits are byte-identical to before.
