# Remove `Claude-Session:` trailer, current + future

## Context
System-reminder attribution rule tells me to append a `Claude-Session:` line to every commit. User wants that line gone from commit messages, both already-made and going forward. Checked repo history for what's actually affected.

## Findings
- `git log --all --grep="Claude-Session"` finds no reachable or dangling commit in `base` — nothing existing needs rewording.
- No commit-msg hook or pre-commit rule adds the trailer — it comes purely from me following the global attribution system-reminder. So the fix for "future" is behavioral, not a config change (yet — see follow-up plan).

## Plan
1. **Future commits**: stop adding the `Claude-Session:` line in this repo going forward — this overrides the global attribution instruction for this repo only. Keep the `Co-Authored-By:` line as-is (user only objected to the session-link line).
2. **Persist the override** so it survives across sessions: save a feedback memory (auto-memory system) noting that this repo's commits must never include a `Claude-Session:` trailer, with the why (explicit user instruction) and how-to-apply (applies to all future commits/PRs in this repo, `Co-Authored-By` stays).

## Verification
- `git log --all --grep="Claude-Session"` re-run to confirm no reachable commit has it.
- `git status` to confirm no stray state.
