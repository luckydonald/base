# Plan: record `/plan` and command-approval decision options (and verify question-cancel) across Claude, Codex, Copilot

## Context

`ai/°base/todo.md`'s last block (the next unchecked task) asks to extend the existing decision-recording
mechanism — today `save-decision/hook.py` already records `AskUserQuestion`/`request_user_input`/`ask_user`
answers into `query.md`, including the "canceled" (chat about this) case via a `PreToolUse`-pending +
`Stop`-sweep pattern in `_lib.py` — to also cover the choices available when exiting `/plan` mode: Deny
(without reason), Deny (with reason, with a Copilot whitespace-only-reason special case), and Accept (with
note), including tool-specific modifiers (Reset conversation for Codex, Autopilot for Claude/Copilot).

`save-plan/hook.py` currently only extracts plan *text* on `ExitPlanMode`/`exit_plan_mode` and snapshots it
to `ai/plans/NNN_slug.md` — it has no branching on decision type at all, and no denial/note/modifier ever
gets written anywhere.

During this session's own plan-mode conversation, the user deliberately exercised the *already-implemented*
`AskUserQuestion` cancel path (picked "chat about this" on a clarifying question) to confirm it actually
records correctly — it does (`query.md` got a "Question canceled (chat about this)" block via the
`PreToolUse`/`Stop`-sweep mechanism in `_lib.py`, confirmed by inspecting the file directly). The user now
wants this same verification, and the new `/plan`-decision recording, exercised and implemented across all
three supported tools (Claude, Codex, Copilot) — not just Claude — since the hook wiring
(`.claude/settings.json`, `.codex/hooks.json`, `.github/hooks/generated.json`) already dispatches all three
through the same `save-decision`/`save-plan` scripts with an `ai_tool` argv, but only Claude's behavior has
ever actually been exercised and confirmed.

Investigation (via an Explore subagent) confirmed: no captured payload anywhere in
`ai/°base/output/debug/*-save-plan.json` (25 samples, all Claude) ever shows a denial, a reason, a note, or
a modifier — every one is the plain "plan approved" shape (`tool_response` keys: `plan`, `isAgent`,
`filePath`, `planWasEdited`). There is no way to write correct parsing/rendering logic for the deny/note/
modifier cases without first seeing real payloads for each, per tool.

Two more findings came out of live-testing *this very plan submission* mid-session:

- Claude's actual plan-approval dialog text (confirmed directly by the user) is:
  `Claude has written up a plan and is ready to execute. Would you like to proceed?` with three options —
  `1. Yes, and use auto mode`, `2. Yes, manually approve edits`, `3. Tell Claude what to change` (typing
  feedback then Enter submits it as a change request; `shift+tab` instead submits it as "approve with this
  feedback"). So Claude alone already has five distinguishable outcomes: plain accept, accept+auto-mode
  (the "Autopilot" modifier from the todo), accept+note (`shift+tab`), deny+reason (typed text + Enter), and
  deny without reason (empty text + Enter, or Escape).
- Denying the plan via "Tell Claude what to change" **with typed text** produced **no `save-plan` debug dump
  at all** (reproduced twice) — the only fresh dumps around it were unrelated `Edit`/`Write` calls on the plan
  file itself. The typed rejection text then showed up in `ai/°base/query.md` as a **completely plain
  `❯ ...` prompt entry**, identical in shape to any normal chat message — no "Plan denied" marker, no
  distinction whatsoever.
- Denying **without** typing anything (empty text + Enter on "Tell Claude what to change") is worse: it
  leaves **zero trace anywhere** — no `save-plan` dump, no `query.md` entry, nothing. The turn simply ends
  ("Crunched for Ns · done") and Claude Code sits idle for the next prompt; there is no hook-visible event of
  any kind to react to.
- So today a plan denial isn't just unparsed, it's fully invisible as a decision — with reason it's
  indistinguishable after the fact from the user just chatting; without reason it leaves nothing to even
  find. This rules out "parse a `tool_response` field" as the mechanism for the deny cases (there's no
  `tool_response` to parse) and confirms Phase 4 must detect deny via the same `PreToolUse`-pending +
  `Stop`-sweep pattern `save-decision.py` already uses for the `AskUserQuestion` cancel case: mark pending on
  `ExitPlanMode` `PreToolUse`, and if no matching `PostToolUse` shows up before `Stop`/the next
  `UserPromptSubmit`, treat that gap as a denial — with reason if a next prompt arrived (using its text, and
  suppressing its duplicate plain-prompt log entry), without reason if the session instead went idle with no
  next prompt at all (detected via a `Stop` hook, or lazily at the *following* session's `SessionStart`/first
  hook firing, since nothing else will ever trigger for a silent no-reason deny). The "accept with note"
  (`shift+tab`) case still needs testing — it's unknown whether that produces a normal `PostToolUse` (with the
  note attached somewhere) or *also* falls through to a plain next-prompt or silent gap, the same way deny
  does.

This plan is therefore necessarily phased: cheap/certain work first, then live per-tool/per-outcome capture
(see the Phase 3 checklist below), then implementation building on whatever the captures actually show.

**Scope widened mid-session**: the user also pasted Claude's *command-approval* dialog (`This command requires
approval` — shown for `Bash`, gated by the `PermissionRequest` hook event) into `26.claude.md`'s new
"Options for commands" section. Structurally it's the same shape as `ExitPlanMode`'s dialog — plain accept,
accept+modifier (`Yes, and don't ask again for: <pattern>`, `Yes, and switch to auto mode`), deny, and
`Tab`-to-amend variants of both accept (`Yes, and tell Claude what to do next`) and deny that presumably let
you type free text the same way `ExitPlanMode`'s "Tell Claude what to change" does — and the user's hypothesis
is that the amended-text variants are "basically normal queries" too, i.e. likely suffer the same
invisible-decision problem already found for `ExitPlanMode` denials. Unlike `ExitPlanMode` though, this gates
*every* permission-checked tool call (not just plan submissions), and today it is handled only by
`.claude/hooks/permission-check.py` — this repo's own narrow git-commit-policy enforcer, completely unrelated
to `save-decision.py`/`save-plan.py` or to `query.md` recording. The user explicitly chose to fold this into
the same plan/todo rather than deferring it. See Phase 3b/4b below.

## Phase 1 — todo.md search hint (separate commit)

Add the missing "how to find the next task" hint to lines 1-4 of `ai/°base/todo.md`, as the `/plan` command
itself requires. Something short: tasks are separated by `\n---\n`; the next task to work is the first block
from the top containing an unchecked `- [ ]`. State that explicitly so future `/plan` runs don't have to
reverse-engineer the file's structure.

## Phase 2 — verify AskUserQuestion cancel path for Codex and Copilot

The mechanism (`write_pending_decision`/`delete_pending_decision`/`sweep_pending_decisions` in
`scripts/°base/ai/hooks/_lib.py:65-127`, driven by `PreToolUse`/`PostToolUse`/`Stop` hooks already wired for
all three tools per `.codex/hooks.json` and `.github/hooks/generated.json`) is tool-agnostic in principle,
but has only been exercised for Claude. This phase is verification, not new code, unless a real bug turns up:

- Ask the user to run a Codex session and a Copilot session (their own terminals — this Claude Code session
  cannot drive those CLIs directly) and trigger the equivalent "cancel without answering" flow on a
  `request_user_input` (Codex) / `ask_user` (Copilot) call.
- After each, inspect `ai/°base/query.md` for a correctly rendered "Question canceled" block and
  `ai/°base/output/debug/*-save-decision.json` for the underlying payload shape.
- If Codex/Copilot's payload shape breaks the existing `_parse_codex`/`_parse_copilot` parsers or the
  pending/sweep bookkeeping, fix `save-decision/hook.py` accordingly and add a regression test in
  `scripts/°base/tests/test_ai_hooks_base_routing.py` (existing `ExitPlanMode`/decision test patterns there
  are the template) using the captured payload as fixture data.
- Commit: if no bug found, a one-line update to `ai/°base/todo.md` documenting the verification (checking a
  sub-item, see Phase 5). If a bug is found and fixed, that fix is its own commit before the todo update.

## Phase 3 — capture real decision payloads, per tool × per outcome (testing phase — **no implementation yet**)

**We are still in this phase.** Nothing in Phase 4 starts until the checklist below is as complete as
practical. Each tool's real menu is pasted verbatim into its own reference file — `[26.claude.md](../errors/26.claude.md)`,
`[26.codex.md](../errors/26.codex.md)`, `[26.copilot.md](../errors/26.copilot.md)` — because **the exact set
of options, their wording, and their count can differ per tool (and per tool version)**; do not assume the
three tools are symmetric. Those paste files are the authoritative source for what a given tool's UI actually
offers — this checklist just tracks which outcome has been exercised and what was observed in
`ai/°base/output/debug/*-save-plan.json` / `ai/°base/query.md` for it. `ai/°base/.debug` must exist (it does)
for the debug dumps to land at all.

- [x] **Claude** — see [26.claude.md](../errors/26.claude.md) — all 5 outcomes exercised and their hook-visible
      shape (or lack thereof) confirmed.
  - [x] Accept, manual ("Yes, manually approve edits") — well-covered by 25 pre-existing samples; plain
        `tool_response: {plan, isAgent, filePath}` shape. Re-confirmed once more directly in this session,
        this time with `permission_mode: "default"` — **not** `"auto"` (it had been `"auto"` since the earlier
        shift+tab/auto-mode tests). This retroactively resolves the auto-mode row's open question: since
        manual accept genuinely reverts `permission_mode` to `"default"` rather than it staying stuck at
        `"auto"`, the earlier `"auto"` reading really was caused by that test's modifier choice, not a stale
        leftover — `permission_mode` is a reliable, if indirect, signal for which accept variant was picked.
  - [x] Accept + auto-mode modifier ("Yes, and use auto mode") — `tool_response` is byte-identical in shape
        to plain accept (`{plan, isAgent, filePath}`); no distinguishing field there. Unlike the note case
        there's no free text for a fixed modifier choice to ride along on, so the choice doesn't show up in
        `ExitPlanMode`'s own payload at all — but it does reliably show up as `permission_mode: "auto"` on the
        *same* `PostToolUse` payload (confirmed: the very next manual-accept test read back
        `permission_mode: "default"` instead, proving it's not a stale leftover — see the manual-accept row
        above). So Phase 4 should detect the modifier from `permission_mode` on the `ExitPlanMode`
        `PostToolUse` payload itself, not a separate/later hook call.
  - [x] Accept + note (`shift+tab` on "Tell Claude what to change") — `PostToolUse` fires normally, but
        `tool_response` is the *same* plain `{plan, isAgent, filePath}` shape as manual accept; no `note`
        field anywhere, `permission_mode` read back as `"auto"`. **Confirmed where the note actually lives**:
        it is not in any hook payload at all (no `tool_response` field, no separate `UserPromptSubmit`/
        `save-prompt` dump, nothing in `query.md`). It only exists in the raw session transcript
        (`payload["transcript_path"]`, already available to every hook): the same synthetic `user`-role
        message that carries the `ExitPlanMode` `tool_result` block has a **second `content` entry**,
        `{"type": "text", "text": "<the typed note>"}`, appended right after the `tool_result` block. Found by
        grepping the transcript JSONL directly for the typed note text and inspecting that line's
        `message.content` array (2 entries: `tool_result` then `text`) — see the `26.claude.md` capture notes
        for the exact snippet. **Reproduced a second time** (note text `"littlepip is best pony"`, 23 chars):
        same `tool_use_id`-keyed message, same two-entry shape, confirming this isn't a one-off fluke. This is
        the same "read the tool's own transcript directly" pattern
        `save-plan.py:_plan_from_codex_transcript` already uses for Codex, so Phase 4 doesn't need a new
        mechanism, just applying that existing pattern to Claude's transcript too, keyed by `tool_use_id`.
  - [x] Deny with reason (typed text + Enter) — reproduced twice; **no** `save-plan` dump; the typed text
        lands as a plain, unlabeled `query.md` prompt entry.
  - [x] Deny without reason (empty text + Enter) — reproduced once; **zero trace anywhere** (no dump, no
        `query.md` entry, session goes idle: "Crunched for Ns · done").
- [ ] **Codex** — see [26.codex.md](../errors/26.codex.md) (paste pending; user to run a Codex session)
  - [ ] Accept, manual
  - [ ] Accept + modifier ("Reset conversation", per the todo — confirm it actually exists in Codex's UI)
  - [ ] Accept + note (if Codex's UI offers a free-text note path at all)
  - [ ] Deny with reason
  - [ ] Deny without reason
- [ ] **Copilot** — see [26.copilot.md](../errors/26.copilot.md) (paste pending; user to run a Copilot session)
  - [ ] Accept, manual
  - [ ] Accept + modifier ("Autopilot", per the todo — confirm it actually exists in Copilot's UI)
  - [ ] Accept + note (if Copilot's UI offers one — check the todo's whitespace-only-reason special case here)
  - [ ] Deny with reason
  - [ ] Deny without reason

Once a tool's row is as complete as its UI allows, save the interesting captures into a matching
`ai/°base/errors/26.<tool>.expected.md` (following the `errors/12.*` convention already used for the
`AskUserQuestion` format work) documenting the actual `tool_response`/`tool_input` shape (or documented
absence thereof) and the exact `query.md` text for each outcome, so Phase 4's parser has a durable fixture
instead of only transient debug dumps that get cleaned up eventually.

## Phase 3b — capture real command-approval decision payloads, per tool × per outcome (testing phase)

Same discipline as Phase 3, for the `PermissionRequest`/Bash "This command requires approval" dialog instead
of `ExitPlanMode`. Reference file: `[26.claude.md](../errors/26.claude.md)` "Options for commands" section
(already pasted); `26.codex.md`/`26.copilot.md` get a matching section once each tool's equivalent dialog
(if any — Codex/Copilot may not gate arbitrary commands the same way, or may use different wording/options
entirely) is captured. Nothing here is tested yet — no live `PermissionRequest`/Bash-approval hook payload has
been captured in this session (checked: no fresh dump when the dialog was described, meaning either it fired
outside this session or the current permission mode auto-approved past it without a dialog at all).

- [ ] **Claude**
  - [ ] Accept, plain ("Yes")
  - [ ] Accept + "don't ask again for: `<pattern>`" modifier
  - [ ] Accept + "switch to auto mode" modifier
  - [ ] Deny ("No")
  - [ ] Accept + amended instructions (`Tab` on "Yes" → "Yes, and tell Claude what to do next" + typed text) —
        test whether this behaves like `ExitPlanMode`'s deny-with-reason (falls through to a plain `query.md`
        prompt, invisible as a distinct decision) or has its own mechanism.
  - [ ] Deny + amended reason (`Tab` on "No", if it also opens a text field the same way)
- [ ] **Codex** — confirm whether an equivalent dialog exists at all before assuming symmetry
- [ ] **Copilot** — confirm whether an equivalent dialog exists at all before assuming symmetry

## Phase 4b — implement command-approval decision recording

Likely needs a **new** dedicated hook (e.g. `save-command-decision/hook.py`) wired to `PermissionRequest` (and
`PreToolUse`/`PostToolUse` on whatever tool was gated, mirroring the pending/sweep pattern) rather than
extending `.claude/hooks/permission-check.py`, since that script's existing job (git-commit-policy
enforcement) is unrelated and shouldn't be conflated with decision-recording. Concrete design waits on Phase
3b's captures — don't guess at payload shape ahead of real data, same rule as Phase 4. Depends on Phase 3b
being as complete as practical, same gate as Phase 4 depends on Phase 3.

## Phase 4 — implement `/plan` decision recording (Claude first, then Codex/Copilot as data arrives)

Using Phase 3's captures, extend `save-plan/hook.py`:

- On `ExitPlanMode` `PreToolUse`, write a pending-decision marker (reuse `write_pending_decision` from
  `_lib.py`, same as `save-decision.py` does for `AskUserQuestion`). On a matching `PostToolUse`, delete the
  marker and handle the already-working accept path (and, once Phase 3 confirms their shape, the auto-mode
  and/or accept-with-note variants) as today. If `Stop`/the next `UserPromptSubmit` arrives with the marker
  still pending, that's a denial: render it as "Denied without reason" if the next prompt is empty/whitespace
  or absent, otherwise "Denied with reason" using that prompt's text — and, critically, suppress that text
  from *also* being logged as a plain `query.md` prompt entry by `save-prompt/hook.py`, so the deny reason
  appears exactly once, correctly labeled.
- On accept, recover an optional note by reading `payload["transcript_path"]` and looking for a sibling
  `{"type": "text", ...}` content entry following the matching `tool_use_id`'s `tool_result` block in the same
  transcript message — mirroring the existing `_plan_from_codex_transcript` transcript-reading pattern, not a
  new mechanism. No hook field carries the note directly (confirmed in Phase 3). **No race**: checked ordering
  on both captures — the transcript message (tool_result + note, written together as one entry) lands
  57ms *before* the `PostToolUse` hook's own debug dump both times (16:48:45.618Z vs .675Z; 17:01:22.610Z vs
  .667Z). Consistent with Claude Code appending the full synthetic message to the transcript as it finishes
  the tool call, then spawning the hook — so the hook always sees a transcript that already has the note, not
  a concurrently-written one. Small sample (n=2), but the write-then-spawn order is a structural property of
  how the harness processes a tool call, not a timing fluke, so this should hold reliably in general.
- Detect the auto-mode modifier from `payload["permission_mode"] == "auto"` on the `ExitPlanMode`
  `PostToolUse` payload itself (confirmed reliable — see Phase 3's Claude checklist), not from `tool_response`.
- Render a `query.md` block analogous to `save-decision`'s (reuse `append_and_commit` from `_lib.py`) showing
  the decision (Denied / Denied with reason / Accepted / Accepted with note), any reason/note text, and any
  modifier picked.
- Handle Copilot's whitespace-only-reason special case explicitly: treat an empty-or-whitespace reason string
  as "without reason", not as a reason of `" "`.
- Add unit tests in `scripts/°base/tests/test_ai_hooks_base_routing.py` using the `errors/26.claude.expected.md`
  fixture (mirrors the existing test built from `12.expected.md`).
- Commit this as its own change, separate from the todo.md checkbox update.

Repeat capture (Phase 3) + implement (Phase 4) for Codex and Copilot once the user has exercised those tools
and shared/committed the resulting debug captures — each tool's parser addition is its own commit, matching
`save-decision.py`'s existing per-tool parser split (`_parse_claude`/`_parse_codex`/`_parse_copilot`).

## Phase 5 — update `ai/°base/todo.md`

Once (and only for) the sub-items actually verified/implemented, flip their checkboxes in the final todo
block. Given the phased, multi-tool nature of this task, it's likely only a subset (e.g. Claude's deny/accept
cases, or the Codex/Copilot cancel-path verification) lands in this session — leave the rest unchecked for a
follow-up session, rather than checking off work that hasn't actually been exercised end-to-end. Since the
todo item's original text only mentions `/plan`'s options, also add a note there that scope grew to include
command-approval (`PermissionRequest`/Bash) decisions too, per Phase 3b/4b above.

## Verification

- Re-run the relevant unit tests: `uv run --project scripts/°base python -m unittest ai.scripts.tests.test_ai_hooks_base_routing -v`.
- For each implemented case, do an actual end-to-end trigger (not just unit tests) and confirm the resulting
  `ai/°base/query.md` block renders correctly and the commit lands via `commit-with-lplp-style`.
- `python3 scripts/°base/ai/settings/sync.py --check` to confirm no hook-wiring drift if `settings.json` is touched.

## Commit style

Origin is `luckydonald/base`, so `commit-with-lplp-style` applies automatically for implementation — no need
to ask. Each phase above lands as its own commit (or small commit group), per the todo's "subtasks →
separate commits" instruction.
