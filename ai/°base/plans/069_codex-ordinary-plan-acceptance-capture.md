# Codex ordinary plan-acceptance capture

## Summary

Capture the event stream produced by the ordinary Codex plan-acceptance action.

## Steps

- Make no repository changes.
- Choose “Yes, implement this plan” without clearing context.
- Inspect the fresh `save-plan`, `save-prompt`, and transcript records.
- Record whether `exit_plan_mode`/`ExitPlanMode`, an acceptance modifier, or a note is present; explicitly record absence if none appears.

## Acceptance

- Evidence is tied to this capture’s session and distinguishes it from the prior “Stay in Plan mode” result.
