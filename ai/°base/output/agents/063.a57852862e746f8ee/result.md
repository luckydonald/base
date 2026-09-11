Now I have a full picture. Report below.

## Summary

**1. `scripts/°base/ai/hooks/save-decision/hook.py`** — records `AskUserQuestion`/`request_user_input` answers.
- Reads `payload.tool_input.questions` and `payload.tool_response.answers`/`.annotations` (lines 101–175 for Claude; 178–278 for Codex; there's also a Copilot parser further down, ~line 281+).
- Builds a `Question`/`Choice` pydantic model per question (lines 32–71) where each choice carries `selection` (bool or 1-based click order) and `note`. A synthetic "Other" choice is always appended to represent free-text/no-match answers.
- Renders selections as markdown checkboxes into `ai/query.md` via `append_and_commit` (imported from `_lib.py`). This is the established pattern the todo item wants replicated for plan decisions.

**2. `scripts/°base/ai/hooks/save-plan/hook.py`** — current `ExitPlanMode` handling.
- `main()` (lines 445–556): on `tool_name in ("ExitPlanMode", "exit_plan_mode")`, it only extracts plan **text** — `tool_input.get("plan")`, falling back to `_plan_from_response(tool_response)` (lines 56–72, reads `tool_response["plan"]` or a `filePath`) and then `_plan_from_copilot_session` (lines 119–130).
- It then snapshots that text to `ai/plans/NNN_slug.md` and commits (lines 461–556), and marks the session `"done": True` (lines 550–554).
- **It never inspects any "decision" field.** There is no branching for approved/denied/denied-with-reason/accepted-with-note/modifier anywhere in the file — it unconditionally treats any `ExitPlanMode` PostToolUse call that yields a non-empty plan as a save-worthy event. Nothing is written to `query.md` for plan decisions at all today (only `ai/plans/*.md` snapshots of the plan text itself).

**3/4. Real `ExitPlanMode` payload shapes in the repo.**
- Checked all 25 captured `ai/°base/output/debug/*-save-plan.json` files with `tool_name == "ExitPlanMode"`. Every single one has the identical `tool_response` key set: `['plan', 'isAgent', 'filePath', 'planWasEdited']` (a couple are `null` — likely denied/aborted calls where no snapshot exists, but no example was ever captured with content in that state).
- No field like `approved`, `denied`, `decision`, `note`, or `modifier` appears in any captured payload. `_lib.py` has no references to `ExitPlanMode`, `approved/denied`, or plan-decision concepts (grep for `permission_decision|plan_decision|approved|denied|deny` in `_lib.py` returned nothing).
- `ai/°base/errors/15.md` / `15.expected.md` mention `ExitPlanMode` only in passing (as descriptive text inside an unrelated AskUserQuestion test fixture, e.g. "Exercise the plan-capture flow for `Write`, `ExitPlanMode`, or `Stop`"), not as an actual captured deny/accept-with-note JSON payload. No `errors/NN.md` file documents `ExitPlanMode` decision payloads the way `errors/12.md`/`12.expected.md`/`12.questions.md` document AskUserQuestion cases.

**5. Conclusion.** This todo item is genuinely unimplemented, and — more importantly — there is currently **no real example data** in the repo of what `tool_response` (or any other hook field) looks like for a denied plan, a denied-with-reason plan, or an accepted-with-note/modifier plan; every captured sample so far is the plain "plan text approved" case. Before writing parsing logic analogous to `save-decision`'s `Choice`/`Question` model, someone needs to actually trigger those code paths (deny, deny+reason, accept+note, accept+"Reset conversation"/"Autopilot" modifier, and the Copilot empty-whitespace-reason edge case) across Claude/Codex/Copilot and capture the resulting debug JSON under `ai/°base/output/debug/` (and ideally a new `ai/°base/errors/NN.md` fixture set), the same way `errors/12.*` was built for questions.