# Flush pending plan/command denials before every git-committing hook

## Context

The `dd2c4bfe` bug (two "Plan denied" blocks bundled into one commit) happened because `record_claude_plan_rejections()` in `scripts/°base/ai/hooks/save-plan/hook.py` only runs from `save-prompt`'s `UserPromptSubmit` handler — the *next user message* — not from whatever hook fires in between. If the agent edits the plan and gets denied a second time before the user types anything, two denials pile up unrecorded and get flushed together.

Splitting the batched commit into one-commit-per-rejection (already done in this session) fixes the "bundled into one commit" symptom, but not the root ordering problem: the two denial commits still land *after* all the plan-edit commits made between them, instead of interleaved in the order things actually happened. The only real fix is to flush a pending denial as soon as *any* other git-committing hook is about to make its own commit — including `save-plan` itself, right before it commits the next plan revision.

Investigation (`scripts/°base/ai/hooks/save-command-decision/hook.py:78-115`) found the exact same "batch multiple rejections into one commit" bug already live there for denied `Bash`/`Write`/`Edit`/etc. calls (`CLAUDE_COMMAND_TOOLS`) — so this needs fixing in two places, not one, and the fix should be shared rather than duplicated a third time.

**Every** git-committing hook needs to run this "flush pending denials first" check, since a plan or command denial can be sitting unrecorded when any of them fires:
`save-plan`, `save-decision`, `save-command-decision`, `save-prompt`, `record-memory`, `record-codex-memory`, `save-compact-prompt` — confirmed via `grep -ln "append_and_commit\|commit" scripts/°base/ai/hooks/*/hook.py`.

### Efficiency

`_lib.py`'s `load_transcript_tool_events()` (`_lib.py:181-243`) currently re-reads and re-parses the *entire* transcript `.jsonl` file from disk on every call (`_iter_transcript_lines`, `_lib.py:164-178`), with no caching anywhere in the module. `save-command-decision` already does a full rescan on nearly every `PostToolUse` today, so this isn't a new problem, but making the same scan mandatory in ~7 hooks (several of which fire on nearly every tool call) meaningfully increases how often the full file gets re-parsed per session. Real transcripts observed on this machine run 300 KB–4.8 MB.

Since these transcripts are append-only for the life of a session, the right fix is a small **incremental, disk-backed cache** inside `load_transcript_tool_events()` itself (transparent to all existing callers — no call-site changes needed for the caching benefit):

- Cache file per transcript: `$TMPDIR/transcript-scan-cache-<sha1(transcript_path)[:16]>.json`, storing `{"offset": <bytes consumed>, "size": <file size at last read>, "pending_tool_uses": {id: [name, input]}, "events": {id: event}}`.
- On each call: stat the transcript file. If current size < cached `size` (truncated/rotated — shouldn't normally happen but be defensive), discard the cache and rescan from 0. Otherwise seek to `offset`, read only the newly appended bytes, parse complete lines only (keep any trailing partial line unconsumed — a writer may be mid-flush), merge new `tool_use`/`tool_result` pairs into `pending_tool_uses`/`events` using the exact same pairing logic already in `load_transcript_tool_events`, update `offset` to the end of the last fully-consumed line, and write the cache back atomically (write to a temp file + `os.replace`).
- On any cache read/parse failure (corrupt JSON, race with a concurrent hook process), silently fall back to a full rescan and rewrite the cache — self-healing, never a hard failure.
- Return the merged `events` dict, exactly as today.

This turns "N git-committing hooks × full re-parse" into "first hook this turn pays for a full parse (or the incremental delta since the last turn), every later hook this turn/session reads a small cache file and typically parses zero or a few new lines."

## Design

### 1. `scripts/°base/ai/hooks/_lib.py`
- Add the incremental cache described above inside `load_transcript_tool_events` (or a private helper it delegates to) — signature and return value unchanged.
- Add `render_decision_block(label: str, detail: str | None) -> str`: the "❯ {label}\n> line\n...\n\n" renderer. This is currently duplicated verbatim as `_render_decision_block` in `save-plan/hook.py` and `render_decision` in `save-command-decision/hook.py` — consolidate to one copy; both hooks import it for their own (non-rejection) rendering too.
- Add a small `RejectionSpec` (e.g. `NamedTuple`: `tool_names: frozenset[str]`, `state_file: Path`, `render: Callable[[dict], str]`, `commit_msg: str`) and two module-level instances:
  - `PLAN_REJECTION_SPEC` — `{"ExitPlanMode"}`, `save-plan-rejections-state.json`, a renderer matching today's `_render_claude_plan_rejection` (`"Plan denied:"` / `"Plan denied."`), `"ai: save plan decision"`.
  - `COMMAND_REJECTION_SPEC` — `CLAUDE_COMMAND_TOOLS` (`{"Bash", "shell", "unified_exec", "Write", "Edit", "Read", "apply_patch"}`), `save-command-decision-state.json`, a renderer matching today's command-denied label, `"ai: save command decision"`.
  - Centralizing both specs in `_lib.py` (rather than having hooks import from each other's hyphenated directories, which isn't a valid plain `import`) keeps every hook's call site to a single import.
- Add `flush_pending_rejections(payload: dict) -> None`: resolves `payload["transcript_path"]` (no-op if missing/empty, matching today's early return), calls `load_transcript_tool_events` once, then for **both** specs: filter unrecorded rejections from that single parsed map (reusing `find_tool_rejections`'s filtering logic, refactored to accept an already-parsed events dict so it doesn't reparse), and `append_and_commit` **one rejection at a time** (not batched — this is the actual ordering fix), saving that spec's state file after each individual commit so a mid-loop crash doesn't lose already-committed progress.

### 2. Call-site changes (one line each, at the top of `main()`, right after the existing `is_cross_tool_duplicate` guard and before the hook's own work)
Add `flush_pending_rejections(payload)` to:
- `save-plan/hook.py` — **new call**; this is the actual fix for the reported bug, since it means a pending denial commits before save-plan's own next plan-revision commit. Remove `record_claude_plan_rejections`/`_render_claude_plan_rejection`/`_REJECTIONS_STATE_FILE` (now redundant, replaced by the shared spec/flush).
- `save-command-decision/hook.py` — replace the batching rejection loop in `record_claude_decisions` (`hook.py:92-100`) with the shared flush; keep the local "Instructions for Tool" block (`hook.py:102-109`) as-is, just pointed at the consolidated `render_decision_block`.
- `save-decision/hook.py`, `save-prompt/hook.py` (replacing its existing narrower plan-only call), `record-memory/hook.py`, `record-codex-memory/hook.py`, `save-compact-prompt/hook.py`.

### 3. Tests
- `scripts/°base/tests/test_save_plan_decisions.py`: update the existing `test_two_pending_denials_get_two_separate_commits` test to invoke `save-plan`'s own hook (e.g. a `TodoWrite` or `Write` plan-revision event) between the two denials instead of `save-prompt`, asserting the denial commit lands *before* that hook's own commit — this is the actual regression test for the ordering fix, replacing the current save-prompt-only coverage.
- Add an equivalent test in a `save-command-decision` test file for the same batching bug there (two unrecorded command denials → two separate commits).
- Add a `_lib.py`-level test for the incremental cache: write a transcript, call `load_transcript_tool_events` twice with no new content (confirm identical result, ideally via a monkeypatched read-counter or by checking the cache file's `offset` doesn't change), then append more content and call again (confirm the new event is picked up).

## Verification
- `python3 -m unittest discover -s "scripts/°base/tests" -p "test_*.py"` — full suite green (already reconfirmed once after the first, narrower fix).
- `python3 -m unittest scripts.°base.tests.test_save_plan_decisions -v` and the new command-decision test file individually.
- `git status` / `git diff --stat` before committing — confirm only the intended hook files + test files are staged.
