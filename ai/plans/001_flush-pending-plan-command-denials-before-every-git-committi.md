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
- **Read is always lock-free and safe**: `os.replace` is an atomic rename at the filesystem level, so any reader either sees the fully-old file or the fully-new one — never a torn/partial mix, regardless of what's racing.
- **Write needs a cheap guard, not a lock held across the parse.** A process that reads the cache at offset O0, then gets preempted for a long time before it gets around to writing, must not blindly overwrite a cache that meanwhile advanced past its own computed offset while it was paused — that genuinely would erase already-discovered `pending_tool_uses`/`events` state that a slower re-reader wouldn't automatically recover if it trusted the cache's `size` field to mean "nothing changed, skip reparsing" (a plausible future optimization). So: writing the cache takes the same non-blocking `flock` primitive used everywhere else in this plan (`$TMPDIR/transcript-scan-cache-<hash>.json.lock`) — on `BlockingIOError`, skip persisting this round (the in-memory result computed by *this* call is still used normally by the caller; only the opportunistic cache write is skipped). If the lock is acquired, re-read the persisted `offset` under the lock: if it's already `>= our computed offset`, discard our write (someone else already has equal-or-newer state — no merge needed, just don't clobber); otherwise write our full computed state atomically (temp file + `os.replace`) and release the lock. This is a single integer comparison, not a partial-reslice reconciliation — cheap, and it fully closes the "paused writer regresses a newer cache" hole.
- On each call (independent of the lock above): stat the transcript file. If current size < cached `size` (truncated/rotated — shouldn't normally happen but be defensive), discard the cache and rescan from 0. Otherwise seek to `offset`, read only the newly appended bytes, parse complete lines only (keep any trailing partial line unconsumed — a writer may be mid-flush), merge new `tool_use`/`tool_result` pairs into `pending_tool_uses`/`events` using the exact same pairing logic already in `load_transcript_tool_events`, update `offset` to the end of the last fully-consumed line.
- `pending_tool_uses` here is purely the parser's own internal bookkeeping — a `tool_use` block seen with no matching `tool_result` yet, carried across incremental reads so it isn't lost between calls. It is **not** a work queue of anything to act on; nothing ever "processes" entries out of it except pairing them with their eventual `tool_result`. Don't confuse it with `flush_pending_rejections`'s "pending rejections," a completely different, user-facing concept (see below).
- On any cache read/parse failure (corrupt JSON, torn read), silently fall back to a full rescan and rewrite the cache — self-healing, never a hard failure.
- Return the merged `events` dict, exactly as today.

This turns "N git-committing hooks × full re-parse" into "first hook this turn pays for a full parse (or the incremental delta since the last turn), every later hook this turn/session reads a small cache file and typically parses zero or a few new lines."

### Where the real race is, and how it's already solved elsewhere in this codebase

The cache isn't the dangerous part — **the actual commit step is**: `flush_pending_rejections` doing load-recorded-ids → find-new-rejections → commit → save-recorded-ids. If two hook processes run concurrently for the same event (multiple hooks matched to one `PostToolUse`, for example) and both read the same "not yet recorded" state before either commits, both will try to commit the *same* rejection — a real duplicate-commit bug, unrelated to the cache.

`scripts/°base/ai/hooks/record-codex-memory/hook.py:600-606` already solves exactly this class of problem for its own state-sync work, and its approach is the right model here too:
```python
lock_path = repository / ".record-codex-memory.lock"
with lock_path.open("a", encoding="utf-8") as lock:
    try:
        fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        return 0
    ...
```
Non-blocking (`LOCK_NB`): a process that can't get the lock immediately doesn't wait — it just skips its own flush attempt this time and returns. No queue, no dedicated consumer process, no big serializing lock that would slow concurrent hooks down. `flush_pending_rejections` will reuse this exact pattern: one non-blocking `flock` per rejection-spec state file (e.g. `$TMPDIR/save-plan-rejections-state.json.lock`), held only around "read recorded ids → commit any new rejections one at a time → write recorded ids back" — never around the transcript parse, which (per above) doesn't need it.

**There is no separate queue or dedicated consumer of "pending rejections," and nothing is ever left half-handled.** Every single call to `flush_pending_rejections` that wins the lock does a *complete* pass: it finds **every** currently-unrecorded rejection in the transcript (not just "the one relevant to whatever tool call triggered this hook") and commits **all** of them, one commit each, before returning. The `already_recorded` id set is not a work queue with items waiting their turn — it's purely a dedupe marker so repeated scans across many hook calls don't recommit the same denial twice. So when a hook loses the lock race, it isn't "hoping someone else eventually gets to it" in some open-ended sense — it's skipping *because* whichever process currently holds the lock is, right now, clearing the entire backlog, not just one item. The only way a rejection could be delayed past the very next hook call is the vanishingly rare case where it appears in the transcript in the exact instant between the lock-holder finishing its scan and releasing the lock — and even then, the *next* git-committing hook (there is always one along within moments — that's the whole point of checking from every one of them instead of just `save-prompt`) will catch it on its own complete pass. Nothing about the transcript content itself is ever lost or overwritten by this — the source data (the denial reason text) lives in the immutable transcript file, not in any of these caches or state files, so a "slow" hook can never cause that text to go missing; at worst it delays *when* it gets committed to `query.md`, by one hook tick in the rarest case.

## Design

### 1. `scripts/°base/ai/hooks/_lib.py`
- Add the incremental cache described above inside `load_transcript_tool_events` (or a private helper it delegates to) — signature and return value unchanged.
- Add `render_decision_block(label: str, detail: str | None) -> str`: the "❯ {label}\n> line\n...\n\n" renderer. This is currently duplicated verbatim as `_render_decision_block` in `save-plan/hook.py` and `render_decision` in `save-command-decision/hook.py` — consolidate to one copy; both hooks import it for their own (non-rejection) rendering too.
- Add a small `RejectionSpec` (e.g. `NamedTuple`: `tool_names: frozenset[str]`, `state_file: Path`, `render: Callable[[dict], str]`, `commit_msg: str`) and two module-level instances:
  - `PLAN_REJECTION_SPEC` — `{"ExitPlanMode"}`, `save-plan-rejections-state.json`, a renderer matching today's `_render_claude_plan_rejection` (`"Plan denied:"` / `"Plan denied."`), `"ai: save plan decision"`.
  - `COMMAND_REJECTION_SPEC` — `CLAUDE_COMMAND_TOOLS` (`{"Bash", "shell", "unified_exec", "Write", "Edit", "Read", "apply_patch"}`), `save-command-decision-state.json`, a renderer matching today's command-denied label, `"ai: save command decision"`.
  - Centralizing both specs in `_lib.py` (rather than having hooks import from each other's hyphenated directories, which isn't a valid plain `import`) keeps every hook's call site to a single import.
- Add `flush_pending_rejections(payload: dict) -> None`: resolves `payload["transcript_path"]` (no-op if missing/empty, matching today's early return), calls `load_transcript_tool_events` once, then for **both** specs: try a non-blocking `fcntl.flock(LOCK_EX | LOCK_NB)` on that spec's own `<state_file>.lock`; on `BlockingIOError`, skip that spec this call (another process is already flushing it — no wait, no queue). Once the lock is held: filter unrecorded rejections from the already-parsed events map (reusing `find_tool_rejections`'s filtering logic, refactored to accept a parsed events dict so it doesn't reparse), and `append_and_commit` **one rejection at a time** (not batched — this is the actual ordering fix), saving that spec's state file after each individual commit so a mid-loop crash doesn't lose already-committed progress. Release the lock (context manager / `finally`) before returning.

### 2. Call-site changes (one line each, at the top of `main()`, right after the existing `is_cross_tool_duplicate` guard and before the hook's own work)
Add `flush_pending_rejections(payload)` to:
- `save-plan/hook.py` — **new call**; this is the actual fix for the reported bug, since it means a pending denial commits before save-plan's own next plan-revision commit. Remove `record_claude_plan_rejections`/`_render_claude_plan_rejection`/`_REJECTIONS_STATE_FILE` (now redundant, replaced by the shared spec/flush).
- `save-command-decision/hook.py` — replace the batching rejection loop in `record_claude_decisions` (`hook.py:92-100`) with the shared flush; keep the local "Instructions for Tool" block (`hook.py:102-109`) as-is, just pointed at the consolidated `render_decision_block`.
- `save-decision/hook.py`, `save-prompt/hook.py` (replacing its existing narrower plan-only call), `record-memory/hook.py`, `record-codex-memory/hook.py`, `save-compact-prompt/hook.py`.

### 3. Tests
- `scripts/°base/tests/test_save_plan_decisions.py`: update the existing `test_two_pending_denials_get_two_separate_commits` test to invoke `save-plan`'s own hook (e.g. a `TodoWrite` or `Write` plan-revision event) between the two denials instead of `save-prompt`, asserting the denial commit lands *before* that hook's own commit — this is the actual regression test for the ordering fix, replacing the current save-prompt-only coverage.
- Add an equivalent test in a `save-command-decision` test file for the same batching bug there (two unrecorded command denials → two separate commits).
- Add a `_lib.py`-level test for the incremental cache: write a transcript, call `load_transcript_tool_events` twice with no new content (confirm identical result, ideally via a monkeypatched read-counter or by checking the cache file's `offset` doesn't change), then append more content and call again (confirm the new event is picked up).
- Add a `_lib.py`-level test for `flush_pending_rejections`'s lock-skip behavior: pre-acquire the spec's lock file in the test (simulating a concurrent hook process already flushing it), call `flush_pending_rejections` with a pending unrecorded rejection present, and assert it returns without committing (no exception, no duplicate/attempted commit) — then release the lock and call again, asserting it now does commit.

## Verification
- `python3 -m unittest discover -s "scripts/°base/tests" -p "test_*.py"` — full suite green (already reconfirmed once after the first, narrower fix).
- `python3 -m unittest scripts.°base.tests.test_save_plan_decisions -v` and the new command-decision test file individually.
- `git status` / `git diff --stat` before committing — confirm only the intended hook files + test files are staged.
