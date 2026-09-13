# Codex Plan-Exit Acceptance Trial

## Observation

“Stay in Plan Mode” produced only a `Stop` hook followed by an ordinary `UserPromptSubmit`; no `exit_plan_mode` / `ExitPlanMode` event fired.

## Trial

- Make no repository changes.
- At this plan card, use the control that accepts the plan and enters implementation; choose the ordinary variant, without reset, if variants exist.
- If the client exposes only “Stay in Plan Mode,” report the exact labels instead—this Codex client has no acceptance decision to record.
- After the choice, inspect fresh `save-plan` and `save-prompt` payloads for an explicit event, modifier, or note.

Success is an exact record of the UI and resulting event stream, including a confirmed absence where applicable.
