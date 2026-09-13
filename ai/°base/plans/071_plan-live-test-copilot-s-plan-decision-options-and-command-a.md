# Plan: live-test Copilot's `/plan` decision options and command-approval text input

## Context

Plan `067_plan-record-plan-and-command-approval-decision-options-and-v.md` still has Copilot's Phase 3
(`/plan` decision outcomes) and Phase 3b (command-approval outcomes) checklists entirely unchecked, and
`ai/°base/errors/26.copilot.md` doesn't exist yet. Claude and Codex are already fully captured. This session
is itself a Copilot CLI session, so it's the first real chance to exercise Copilot's own dialogs and see what
hook-visible traces (if any) they leave.

The user wants to actually type text into every field Copilot's UI exposes — both on the `/plan` exit dialog
and on a real command-approval prompt — not just read about it. They will personally handle writing
`26.copilot.md` and updating plan 067's checklists afterward; this plan's only job is to get real dialogs in
front of them to interact with.

## Approach

1. **Exit plan mode now**, via the normal approval flow, so the user sees Copilot's actual `/plan`-exit
   dialog and can try each option it offers (accept manually, accept with a modifier if one exists, accept
   with a typed note, deny with a typed reason, deny with no reason) across repeated attempts if needed —
   Copilot only shows one dialog per exit, so distinguishing outcomes requires the user to retry with
   different choices/text on subsequent plan submissions if this plan gets sent back for changes.
2. **Trigger a real command-approval prompt** once in implementation mode: run the bait command
   `python3 -c "print(open('/etc/passwd').readline())"` (a harmless read of just line 1, chosen only to force
   Copilot's permission gate rather than auto-allow) via the Bash tool, so the user's live approval dialog
   pops up and they can test typing a deny reason and/or accept-with-instructions text into whatever field
   Copilot offers.
3. Do **not** write `26.copilot.md` or touch plan 067's checklists in this pass — the user will do that
   themselves once they've seen and typed into the real dialogs.
4. No code changes, no implementation of parsing/recording logic (Phase 4/4b of plan 067 stay gated on real
   captures, same rule as before).

## Notes

- This plan intentionally has very little content — its purpose is procedural (produce two real, interactive
  dialogs for the user to type into), not a design document.
- If the user denies/edits this plan, that denial attempt itself is useful test data for Phase 3's
  deny-with-reason / deny-without-reason rows.

## Live findings so far (captured by the user directly into `26.copilot.md`)

- Copilot's `/plan`-exit dialog: `1. Accept plan and build on default permissions (recommended)` /
  `2. Accept plan and build on autopilot` / `3. Exit plan mode and I will prompt myself` /
  `4. Suggest changes`.
- Option 4 ("Suggest changes") opens a text box that **cannot be submitted empty** — confirmed directly by
  the user ("not possible to just select it without typing something as a reason or like what to do
  instead"). So Copilot has no bare "deny without reason" outcome the way Claude does; option 4 always
  carries typed text once submitted.
- Remaining `/plan` outcomes still untried this session: option 1 (accept, manual), option 2 (accept +
  autopilot modifier), option 3 (exit plan mode, self-prompt).
- Option 1 (accept, manual) has since been exercised and recorded in plan 067's Copilot checklist.
- This revision's only purpose is to reach the real `/plan`-exit dialog again so the user can pick
  **option 2 ("Accept plan and build on autopilot")** — the next untried outcome — and afterward option 3.
  No code or documentation changes are proposed here; this plan body is intentionally trivial ("test").
- Command-approval dialog not yet triggered — still pending the bait-command step.

## Follow-up finding: typed permission reasons are in the session event log

The typed Copilot denial reason is not part of the `permissionRequest` hook payload, but it is persisted
after the decision in `~/.copilot/session-state/<session_id>/events.jsonl`:

```json
{
  "type": "permission.completed",
  "data": {
    "requestId": "...",
    "toolCallId": "...",
    "result": {
      "kind": "denied-interactively-by-user",
      "feedback": "..."
    }
  }
}
```

Correlate `data.toolCallId` with the earlier `permission.requested` event's
`data.permissionRequest.toolCallId`; that event contains `fullCommandText`. Recovery must happen from a
later hook such as `Stop` or `UserPromptSubmit`, after the permission decision has been written.
