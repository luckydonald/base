# Plan: record `/plan` and command-approval decision options (and verify question-cancel) across Claude, Codex, Copilot

## Context

`ai/°base/todo.md`'s last block (the next unchecked task) asks to extend the existing decision-recording
mechanism — today `save-decision/hook.py` already records `AskUserQuestion`/`request_user_input`/`ask_user`
answers into `query.md`, including the "canceled" (chat about this) case via a `PreToolUse`-pending +
`Stop`-sweep pattern in `_lib.py` — to also cover the choices available when exiting `/plan` mode: Deny
(without reason), Deny (with reason, with a Copilot whitespace-only-reason special case), and Accept (with
note), including tool-specific modifiers (clear context for Codex, Autopilot for Claude/Copilot).

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
but has only been exercised for Claude. This phase is verification, not new code, unless a real bug turns up.
**Not started** — despite the extensive Codex/Copilot work done for Phase 3/3b, nobody has yet exercised the
`AskUserQuestion` cancel path specifically for either tool (checked: no mention in `26.codex.md`/`26.copilot.md`,
no Codex/Copilot-glyph "Question canceled" block in `query.md`).

- [ ] Run a Codex session and trigger the equivalent "cancel without answering" flow on a
      `request_user_input` call; inspect `ai/°base/query.md` for a correctly rendered "Question canceled"
      block and `ai/°base/output/debug/*-save-decision.json` for the underlying payload shape.
- [ ] Same for a Copilot session, on its `ask_user` call.
- [ ] If either tool's payload shape breaks the existing `_parse_codex`/`_parse_copilot` parsers or the
      pending/sweep bookkeeping, fix `save-decision/hook.py` accordingly and add a regression test in
      `scripts/°base/tests/test_ai_hooks_base_routing.py` (existing `ExitPlanMode`/decision test patterns
      there are the template) using the captured payload as fixture data.
- [ ] Commit: if no bug found, a one-line update to `ai/°base/todo.md` documenting the verification. If a bug
      is found and fixed, that fix is its own commit before the todo update.

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
        same `tool_use_id`-keyed message, same two-entry shape, confirming this isn't a one-off fluke.
        **Generalized further** (see Phase 3b): the exact same `tool_result`+sibling-`text` shape showed up
        for a plain `Edit` call and an unrelated `Bash` call in this same session, *neither* of which went
        through any visible permission dialog — proving this is not an `ExitPlanMode`-specific "note" field at
        all, but a general Claude Code behavior: **any message sent while a tool call is in flight gets
        delivered attached to that tool's `tool_result`**, regardless of dialog type or whether one was even
        shown. `shift+tab`/`Tab`-amend are just one UI path that happens to trigger this same underlying
        mechanism. Phase 4 should therefore implement this as a general "recover interjected text for a given
        `tool_use_id`" utility (reusable across `save-plan.py` and the new Phase 4b command-decision hook),
        not ExitPlanMode-specific parsing — still the same "read the tool's own transcript directly" pattern
        `save-plan.py:_plan_from_codex_transcript` already uses for Codex, just generalized.
  - [x] Deny with reason (typed text + Enter) — reproduced twice; **no** `save-plan` dump; the typed text
        lands as a plain, unlabeled `query.md` prompt entry.
  - [x] Deny without reason (empty text + Enter) — reproduced once; **zero trace anywhere** (no dump, no
        `query.md` entry, session goes idle: "Crunched for Ns · done").
- [x] **Codex** — see [26.codex.md](../errors/26.codex.md) — no plan-exit choice carries text outside normal
      prompt logging.
  - [x] Accept, ordinary ("Yes, implement this plan") — exercised. The transcript contains only the plan item
        followed by task completion; hooks emit only `Stop`, with no `exit_plan_mode` / `ExitPlanMode`, note,
        or acceptance field.
  - [x] Accept + modifier ("Yes, clear context and implement") — not separately exercised: it is a non-text
        modifier and therefore out of scope. Do not infer a `context cleared` tag from a successor session.
  - [x] No, stay in Plan mode — acts as denial without reason. It returns to the normal prompt box and
        produced only `Stop`, followed by ordinary `UserPromptSubmit`; no `exit_plan_mode` / `ExitPlanMode`
        event fired.
  - [x] Accept + note / deny with reason — unavailable: Codex exposes no free-text path for either outcome.
- [x] **Copilot** — see [26.copilot.md](../errors/26.copilot.md); the complete captured menu is `1. Accept
      plan and build on default permissions`, `2. Accept plan and build on autopilot`, `3. Exit plan mode and
      I will prompt myself`, `4. Suggest changes`.
  - [x] Accept, manual (option 1) — selected during the live test; the plan proceeded with default permissions.
  - [x] Accept + modifier (option 2, "autopilot") — exercised. No `save-plan`-style hook payload fires for
        either option 1 or option 2 (no `ExitPlanMode`/`exit_plan_mode` tool event at all), but `events.jsonl`
        records a `session.mode_changed` event for both, and its `newMode` field cleanly distinguishes them:
        `"interactive"` for option 1 vs. `"autopilot"` for option 2 (`previousMode` is `"plan"` in both). See
        `26.copilot.md` for the exact captured events.
  - [x] Accept + note — no separate accept-with-note path appears in Copilot's captured menu. The only text
        entry point is option 4 ("Suggest changes"), which is a denial/change request rather than an accepted
        plan with an attached note.
  - [x] Deny with reason (option 4, "Suggest changes") — reproduced twice with typed text (`"This is the
        text box I meant..."`) and recorded the exact dialog in `26.copilot.md`. No `save-plan`-equivalent
        hook payload was captured for this plan-exit case, and the current session event-log search found no
        dedicated plan-decision record; therefore the typed text is documented as a UI capture, not claimed
        to be recoverable through the command-approval `permission.completed` mechanism.
  - [x] Exit without a reason (option 3, "Exit plan mode and I will prompt myself") — exercised. It is a
        mode switch, not a denial: `events.jsonl` records `session.mode_changed` from `"plan"` to
        `"interactive"`, and the `exit_plan_mode` post-tool hook result contains
        `sessionLog: "✅ Plan approved, exited plan mode (exit_only)"`. No typed reason, plan text, or
        `save-plan` decision payload is emitted. The `exit_only` marker distinguishes it from option 1,
        which also ends in interactive mode.

Once a tool's row is as complete as its UI allows, save the interesting captures into a matching
`ai/°base/errors/26.<tool>.expected.md` (following the `errors/12.*` convention already used for the
`AskUserQuestion` format work) documenting the actual `tool_response`/`tool_input` shape (or documented
absence thereof) and the exact `query.md` text for each outcome, so Phase 4's parser has a durable fixture
instead of only transient debug dumps that get cleaned up eventually.

## Phase 3b — capture real command-approval decision payloads, per tool × per outcome (testing phase)

Same discipline as Phase 3, for `PermissionRequest`-gated dialogs instead of `ExitPlanMode`. Reference file:
`[26.claude.md](../errors/26.claude.md)` "Options for commands" section (already pasted); `26.codex.md`/
`26.copilot.md` get a matching section once each tool's equivalent dialog (if any — Codex/Copilot may not gate
commands the same way, or may use different wording/options entirely) is captured. Per the user, only the
message-carrying outcomes (accept-with-instructions, deny-with-reason) are actually worth recording — the
plain modifiers (don't-ask-again, auto-mode) aren't pursued. Plain accept was tested as a control (see
checklist) and confirmed to leave **zero** hook trace whatsoever, worse than `ExitPlanMode`'s deny cases.

**Scope correction, then re-widened**: `PermissionRequest` isn't Bash-specific — `Write`, `Edit`, and even
`Read` (when the path is *outside* the working directory; `Read` inside the repo has been silently
auto-allowed all session, with no dialog at all) all trigger the same kind of approval dialog.
`permission-check.py`'s hook matcher is scoped to `Bash|shell|unified_exec` only (in `ai/settings/settings.json`),
so confirmed empirically: neither `Write`'s nor `Read`'s `PermissionRequest` ever reaches any of our hooks at
all — no debug dump appears for either, regardless of accept or deny. Widening that matcher to also cover
`Write`/`Edit`/`Read` is a `settings.json`/`sync.py` config change, not just a payload-parsing change — but
per the user it **is** in scope: the underlying goal of this whole effort is finding *every* path by which a
decision/message can bypass the normal `query.md` prompt-logging pathway, across every gated tool, not just
`Bash`/`ExitPlanMode`/`AskUserQuestion`. So Phase 4b should widen the matcher too, once captures below justify
the shape of what to record for each tool.

- [x] **Claude** — both message-carrying outcomes confirmed (deny-with-reason, accept-with-instructions); per
      the user, the plain modifiers (don't-ask-again, auto-mode) were never worth pursuing, so their checkboxes
      stay unchecked by design, not as missing work.
  - [x] Accept, plain ("Yes") — tested as a baseline/control, **before** the fix below existed. **Confirmed:
        zero hook trace of the `PermissionRequest` event or the decision at all**, at any level — not just
        unparsed like `ExitPlanMode` denial, but *never even dumped*: `.claude/hooks/permission-check.py` was
        the only hook wired to `PermissionRequest` for Bash and didn't call `dump_debug_payload`. The only
        artifact was the completely ordinary `Bash` `PostToolUse` dump (`{stdout, stderr, interrupted,
        isImage, noOutputExpected}`) — identical in shape to a command that never triggered any approval
        dialog at all. **Fixed in a separate commit** (`6b51e7b`, `[base] git hooks: ai: Run: Wired debug
        dumping into permission-check.py:`) — it now calls `dump_debug_payload(data, "permission-check")`
        right after parsing stdin, before any branching, matching every other hook's convention. Re-testing
        plain accept after this fix would now at least show the raw `PermissionRequest` payload shape, though
        per the user this variant isn't worth pursuing further beyond that plumbing fix.
        all. So plain accept is fundamentally unrecoverable from hooks as currently wired; would need
        `permission-check.py` itself extended to dump/record, not something read after the fact.
  - [ ] Accept + "don't ask again for: `<pattern>`" modifier — not pursuing, low value per the user.
  - [ ] Accept + "switch to auto mode" modifier — not pursuing, low value per the user.
  - [x] Deny + amended reason — reproduced 3 times (denying three different `Bash` commands with typed reasons).
        Now that `permission-check.py` dumps its payload (see the fix above), confirmed: the `PermissionRequest`
        event fires and is captured, but it carries **no `tool_use_id`** at all (matches the docs: `tool_name`
        + `tool_input` only, unlike `PreToolUse`). Crucially, this is a **third, different** pattern from both
        earlier ones: the deny reason isn't a sibling `text` block — it's embedded **directly inside the single
        `tool_result` content string** the model receives: `"The user doesn't want to proceed with this tool
        use... user said:\n<reason>"`. That message is what I (the model) see in-context; no hook ever
        observes it (no `PostToolUse` fires for a denied/never-executed command). Since `PermissionRequest` has
        no `tool_use_id`, correlating a denial to its originating request can't use the `tool_use_id`-keyed
        pending/sweep pattern as-is — Phase 4b will need a session-scoped FIFO-style pending queue instead
        (push on `PermissionRequest`, pop on the next matching tool's successful `PostToolUse`, whatever's left
        at `Stop` is a denial), since commands are processed sequentially within a session.
  - [x] Accept + amended instructions (`Tab` on "Yes" → "Yes, and tell Claude what to do next" + typed text) —
        **confirmed, reproduced 6 times across every tool type tried this session**: `ExitPlanMode` (×2, see
        above), `Edit`, `Bash` (×3, including once with multiline text — no truncation/escaping issues), and
        `Read` (outside-repo path). Every single time: the exact same sibling `{"type": "text", ...}` block
        appended after that call's `tool_result` in the transcript, recoverable only by reading
        `payload["transcript_path"]` and matching on `tool_use_id` — never a hook field, never a separate
        `UserPromptSubmit`. This is conclusively a universal Claude Code mechanism, not specific to any one
        dialog or tool. No further per-tool-type testing of this case is needed for Claude; the general
        recovery utility planned in Phase 4 covers all of it uniformly.
- [x] **Codex** — its `PermissionRequest` menu is fully captured in [26.codex.md](../errors/26.codex.md).
  - [x] Accept, plain (“Yes, proceed”) — the pre-execution `PermissionRequest` payload contains the session,
        turn, `tool_name: "Bash"`, command, description, and `permission_mode`, but no approval result, choice
        label, note, or modifier. A successful ordinary Bash `PostToolUse` follows after the command runs.
  - [x] Accept + allowlist modifier (“Yes, and don't ask again for commands that start with `<prefix>`”) —
        exercised. It has no text path outside the ordinary prompt flow, so its persisted prefix is not a
        `query.md` recording target.
  - [x] Deny / “tell Codex what to do differently” — selecting it emits the documented “Conversation
        interrupted” message and closes the command. It has no inline text input and no command `PostToolUse`;
        any explanation is entered afterward as an ordinary `UserPromptSubmit`, already recorded in `query.md`.
        Do not add a second command-decision entry for that text or try to infer an association from timing.
  - Conclusion: no Codex command-permission path carries text that bypasses normal prompt logging; do not add
        Codex support to the Phase 4b command-decision implementation.
- [x] **Copilot** — equivalent command-approval dialog captured in [26.copilot.md](../errors/26.copilot.md).
  Its `permissionRequest` hook payload uses camelCase (`hookName`, `toolName`, `toolInput`) and contains no
  typed denial reason. The reason is recoverable afterward from
  `~/.copilot/session-state/<session_id>/events.jsonl`: match a
  `permission.completed` event's `data.toolCallId` and
  `data.result.kind == "denied-interactively-by-user"`, then read `data.result.feedback`; correlate the
  same `toolCallId` to the earlier `permission.requested` event to recover `fullCommandText`.

## Phase 4b — implement command-approval decision recording

**Not started.** Phase 3b's captures now justify a concrete design: a **new** dedicated hook (e.g.
`save-command-decision/hook.py`) wired to `PermissionRequest` (and `PreToolUse`/`PostToolUse` on whatever tool
was gated) rather than extending `.claude/hooks/permission-check.py`, since that script's existing job
(git-commit-policy enforcement) is unrelated and shouldn't be conflated with decision-recording.

- [ ] Claude: implement the session-scoped FIFO pending-queue (push on `PermissionRequest` — it carries no
      `tool_use_id` to key on, unlike `PreToolUse` — pop on the next matching tool's successful `PostToolUse`;
      whatever's left at `Stop` is a denial-without-a-hook-visible-reason).
- [ ] Claude: recover a deny reason from the *next* tool result's embedded rejection text (`"...user said:\n
      <reason>"`) — a different extraction path than the accept-with-instructions sibling-`text`-block reader
      built in Phase 4, since deny embeds the reason directly in the single `tool_result` content string.
- [ ] Claude: reuse Phase 4's general "recover interjected text for a `tool_use_id`" utility for
      accept-with-instructions.
- [ ] Copilot: recover the completed denial from `~/.copilot/session-state/<id>/events.jsonl` after the
      `PermissionRequest` hook returns — match `permission.completed.data.toolCallId` back to the earlier
      `permission.requested.data.permissionRequest.toolCallId` for the command, and read
      `data.result.feedback` for the typed reason. A later `Stop`/`UserPromptSubmit` hook is the earliest
      reliable place to do this correlation; the initial permission hook cannot see the user's later input.
- [ ] Codex: explicitly **not** implementing — Phase 3b concluded no Codex command-permission path carries
      text that bypasses normal prompt logging (its "tell Codex what to do differently" text always lands as
      an ordinary, already-recorded `UserPromptSubmit`). Document this exclusion in code comments, don't
      silently omit it.
- [ ] Add unit tests using the `26.claude.md`/`26.copilot.md` capture notes as fixtures.
- [ ] Widen `permission-check.py`'s `PermissionRequest` matcher (via `ai/settings/settings.json` +
      `sync.py`) to also cover `Write`/`Edit`/`Read`, per the user's explicit scope call — only after the
      above Bash-based design is working, so the matcher change doesn't block on an unfinished mechanism.
- [ ] Commit as its own change, separate from the todo.md checkbox update.

## Phase 4 — implement `/plan` decision recording (Claude first, then Codex/Copilot as data arrives)

**Not started.** Using Phase 3's captures, extend `save-plan/hook.py`:

- [ ] Claude: on `ExitPlanMode` `PreToolUse`, write a pending-decision marker (reuse `write_pending_decision`
      from `_lib.py`, same as `save-decision.py` does for `AskUserQuestion`). On a matching `PostToolUse`,
      delete the marker and handle the already-working accept path as today. If `Stop`/the next
      `UserPromptSubmit` arrives with the marker still pending, that's a denial: render it as "Denied without
      reason" if the next prompt is empty/whitespace or absent, otherwise "Denied with reason" using that
      prompt's text — and, critically, suppress that text from *also* being logged as a plain `query.md`
      prompt entry by `save-prompt/hook.py`, so the deny reason appears exactly once, correctly labeled.
- [ ] Claude: add a general (not `ExitPlanMode`-specific) `_lib.py` helper to recover an optional note: read
      `payload["transcript_path"]`, find the message whose `tool_result` block matches the given
      `tool_use_id`, and return a sibling `{"type": "text", ...}` entry if present. Mirrors the existing
      `_plan_from_codex_transcript` transcript-reading pattern; share it with Phase 4b, which needs the exact
      same lookup. **No race** (checked): the transcript message lands ~57ms before the hook's own debug dump
      in both captures — Claude Code appends the full message before spawning the hook, so this is a
      structural guarantee, not a timing fluke.
- [ ] Claude: detect the auto-mode modifier from `payload["permission_mode"] == "auto"` on the `ExitPlanMode`
      `PostToolUse` payload itself (confirmed reliable — see Phase 3's Claude checklist), not from
      `tool_response`.
- [ ] Claude: render a `query.md` block analogous to `save-decision`'s (reuse `append_and_commit` from
      `_lib.py`) showing the decision (Denied / Denied with reason / Accepted / Accepted with note), any
      reason/note text, and any modifier picked.
- [ ] Codex: per Phase 3, no denial-reason or accept-note text path exists at all — implement only plain
      accept/deny-without-reason recording. Render `Plan accepted <kbd>context cleared</kbd>` **only** when
      the clear-context acceptance capture identifies an explicit, stable modifier in the same plan-exit event
      or its transcript; add a paired ordinary-acceptance fixture and a clear-context fixture asserting only
      the latter gets the tag. If the clear-context choice starts a fresh session with no such linking signal,
      record that absence in `errors/26.codex.md` and omit the tag rather than guessing from session turnover.
- [ ] Copilot: implement plain accept, accept+autopilot modifier (via `session.mode_changed`'s `newMode`
      field), and exit-without-reason (`exit_only` marker) recording — all confirmed recoverable per Phase 3.
- [ ] Copilot: deny-with-reason (option 4, "Suggest changes") is **not implementable yet** — Phase 3 found no
      hook payload and no session-event-log record for this specific plan-exit case (unlike the
      command-approval case, which *does* have `events.jsonl` recovery). Do not guess at a mechanism; leave
      this checkbox unchecked and documented rather than silently omitting it.
- [ ] Handle Copilot's whitespace-only-reason special case (from the original todo item) once/if a recovery
      path for the above is found — moot until then, but don't drop the requirement.
- [ ] Add unit tests in `scripts/°base/tests/test_ai_hooks_base_routing.py` using the `errors/26.claude.expected.md`
      fixture (mirrors the existing test built from `12.expected.md`), plus Codex/Copilot fixtures from their
      respective `26.<tool>.md` captures.
- [ ] Commit this as its own change, separate from the todo.md checkbox update.

Repeat capture (Phase 3) + implement (Phase 4) for Codex and Copilot once the user has exercised those tools
and shared/committed the resulting debug captures — each tool's parser addition is its own commit, matching
`save-decision.py`'s existing per-tool parser split (`_parse_claude`/`_parse_codex`/`_parse_copilot`).

## Phase 5 — update `ai/°base/todo.md`

**Not started** — checked directly: the original todo block (`ai/°base/todo.md`, "Record the other choosable
options of a /plan") is still fully unchecked, despite all of Phase 3/3b's research being done. Only flip a
checkbox once the corresponding Phase 4/4b implementation item above is actually done, not merely captured.

- [ ] Check off `Deny (without reason)` once Phase 4's Claude denial-without-reason handling lands.
- [ ] Check off `Deny (with reason)` once Phase 4's Claude denial-with-reason handling lands.
- [ ] Add the Copilot whitespace-only-reason special-case note once (if) a recovery path exists (see Phase 4).
- [ ] Check off `Accept (with note)` once Phase 4's Claude accept-with-note handling lands.
- [ ] Check off `Reset conversation history and implement — Codex` once Phase 4's Codex `context cleared`
      tagging lands.
- [ ] Check off `Use Autopilot ... — Claude, Copilot, (Codex?)` once Phase 4's Claude/Copilot autopilot-modifier
      handling lands (Codex has no autopilot-equivalent modifier per Phase 3 — resolve the `(Codex?)` in the
      todo text to "no").
- [ ] Add a note to the todo item that scope grew mid-session to include command-approval
      (`PermissionRequest`) decisions too, per Phase 3b/4b, since the original text only mentions `/plan`.

## Verification

- Re-run the relevant unit tests: `uv run --project scripts/°base python -m unittest ai.scripts.tests.test_ai_hooks_base_routing -v`.
- For each implemented case, do an actual end-to-end trigger (not just unit tests) and confirm the resulting
  `ai/°base/query.md` block renders correctly and the commit lands via `commit-with-lplp-style`.
- `python3 scripts/°base/ai/settings/sync.py --check` to confirm no hook-wiring drift if `settings.json` is touched.

## Commit style

Origin is `luckydonald/base`, so `commit-with-lplp-style` applies automatically for implementation — no need
to ask. Each phase above lands as its own commit (or small commit group), per the todo's "subtasks →
separate commits" instruction.
