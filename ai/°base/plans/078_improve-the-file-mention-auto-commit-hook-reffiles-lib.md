# Improve the file-mention auto-commit hook (°reffiles_lib)

## Context

`scripts/°base/ai/hooks/°reffiles_lib/` (implemented via plan 034, commit `fcfb7fb`) scans user prompt text for `@path/to/file` and `` `path/to/file` `` mentions and auto-stages/commits any that resolve to real files on disk. Three gaps surfaced while using it (see the live request logged at the tail of `ai/°base/query.md`):

1. **Coverage**: `handle_referenced_files()` is only ever called once, at the very tail of `save-prompt/hook.py`'s `main()` — i.e. only on the plain "user typed a prompt" path. `AskUserQuestion` answers (handled by `save-decision/hook.py`) and other logged interactions (queued commands, compact prompts, plan writes, command decisions) never get scanned, even though they're logged into the same kind of ai/ artifact files via the same shared primitive, `append_and_commit()` in `_lib.py`.
2. **Readability**: mentions are logged into `query.md` as plain text. The user wants the log entry itself, at write time, to become a markdown link to the mentioned file — but only when the file actually exists (no dead links).
3. **Safety**: the current commit logic force-adds (`git add -f`) any untracked mention path starting with `ai/`, bypassing `.gitignore` unconditionally "for AI artifacts." This is exactly the mechanism that could silently commit something like `ai/.env` if it were ever gitignored — the user deliberately avoided triggering this while testing it. The fix is to always respect `.gitignore`, with no `ai/`-prefix exception.

Confirmed approach for (1): centralize the mention-scan/linkify/auto-commit logic inside `append_and_commit()` itself (in `_lib.py`), the single function every logging hook (`save-prompt`, `save-decision`, `save-plan`, `save-command-decision`, `save-compact-prompt`, `compact_result.py`) already calls to write into an ai/ log file. This covers "other interactions" for good — no hook can forget to wire it in later — and naturally satisfies (2) as well, since it's the one place `content` is transformed immediately before being written to disk (not a re-parse after the fact).

## Implementation

### 1. Break the `_lib` ↔ `°reffiles_lib` import cycle

`°reffiles_lib/commit.py` currently does `from _lib import base_ai_commit_subject`. Once `_lib.py` needs to import `°reffiles_lib`, this becomes circular. Fix: have `commit.py` get `base_ai_commit_subject` the same way `_lib.py` itself does — `import_module("°commit_style_lib").base_ai_commit_subject` — instead of going through `_lib`. This removes the reverse dependency entirely so `_lib.py` can safely do `reffiles_lib = importlib.import_module("°reffiles_lib")`.

### 2. `°reffiles_lib/mentions.py` — add position-aware matching

Keep `extract_candidate_paths()` exactly as-is (existing tests + backward compat). Add a new function that also returns match spans and the exact original text to preserve, e.g.:

```python
@dataclass
class Mention:
    start: int      # offset in content where the linkable span begins
    end: int        # offset where it ends (excludes stripped trailing punctuation)
    display: str    # original text to keep inside the link, e.g. "@src/other_file.py" or "`ai/some_file.md`"
    path: str        # candidate path used for filesystem resolution (same value extract_candidate_paths would produce)

def find_mentions(content: str) -> list[Mention]: ...
```

Reuse the same `_AT_MENTION_RE` / `_BACKTICK_MENTION_RE` / `_TRAILING_PUNCT` logic; for `@mentions` the span covers `@` + the stripped candidate only (trailing punctuation like `!` stays outside the span, matching the user's example); for backtick mentions the span is the whole `` `...` `` match.

### 3. `°reffiles_lib/commit.py` — linkify + gitignore-safe commit

- Add `is_gitignored(relpath: str) -> bool` using `git check-ignore -q -- <relpath>` (returncode 0 ⇒ ignored).
- Replace `handle_referenced_files()` with two functions used from `append_and_commit()`:
  - `process_referenced_files(content: str, subproject: Path, log_path: Path) -> tuple[str, list[Mention]]`: calls `find_mentions(content)`, resolves each candidate to an absolute path under `subproject`, keeps only the ones where `abspath.is_file()`. For each existing one, computes the git-root-relative path (unchanged resolution/`ValueError`-skip logic from the old `handle_referenced_files`) and a markdown link target *relative to `log_path.parent`* (`os.path.relpath`, prefixed with `./` unless it already starts with `..`, matching the user's exact example: `ai/some_file.md` mentioned from `ai/°base/query.md` → `./some_file.md`... actually relative to `ai/query.md` → `./some_file.md`; `@src/other_file.py` → `../src/other_file.py`). Replaces each existing mention's span with `[{display}]({target})`, processing matches in reverse offset order so earlier offsets stay valid. Returns the new content plus the resolved list (for staging). Mentions whose file doesn't exist are left untouched in the text and excluded from the returned list.
  - `stage_and_commit_mentions(mentions: list[ResolvedMention]) -> None`: for each resolved mention — if `is_tracked(relpath)`, just `git add` it (unchanged); otherwise, if `is_gitignored(relpath)`, skip it entirely (**no exception for `ai/`-prefixed paths** — this is the safety fix); otherwise `git add` + `git commit --no-verify --only <relpath> -m base_ai_commit_subject("ai: referenced file for task added.")` as today.
- Keep `is_tracked()` unchanged.

### 4. `_lib.py` — wire it into `append_and_commit()`

In `append_and_commit()` (line ~484), right after `snap = _staged_snapshot(relpath)` and before the file write:

```python
reffiles_lib = importlib.import_module("°reffiles_lib")  # lazy, avoids any load-order issues
content, mentions = reffiles_lib.process_referenced_files(content, _subproject_root(), log_path)
```

Write the (possibly linkified) `content` instead of the raw argument. After the existing commit + `_restore_staged` calls, add `reffiles_lib.stage_and_commit_mentions(mentions)` as the final step — same relative ordering as today (log gets committed first, then mentioned files get their own commit(s)).

### 5. `save-prompt/hook.py` — remove the now-redundant explicit call

Delete the tail call `reffiles_lib.handle_referenced_files(raw_prompt, _subproject_root())` (around line 1067) — this logic now runs automatically inside the `append_and_commit()` call that immediately precedes it (line 1060). Leaving both would double-process mentions (using the *pre-linkify* `raw_prompt`, against a query.md that already has the linkified text). Remove the now-unused top-of-file `reffiles_lib = importlib.import_module("°reffiles_lib")` import and `raw_prompt` capture from `hook.py` if nothing else in the file uses them after this change (check first).

### 6. Tests

- Extend `test_ai_hooks_base_routing.py`'s `ReffilesLibMentionsTests` area with unit tests for `find_mentions`/`process_referenced_files`: existing file → correct span replaced with `[display](relative/target)` (cover both the `./`-same-dir and `../`-sibling-dir cases from the user's example); non-existent file → left as plain text.
- Unit test for `is_gitignored` + the removed `ai/`-prefix exception: with a `.gitignore` rule covering an `ai/`-prefixed path, assert `stage_and_commit_mentions` does **not** stage/commit it (regression test for the incident this plan fixes).
- End-to-end test via the existing `run_hook` harness: submit a prompt mentioning an existing, untracked, non-ignored file (use `ai/.debug`, per the user's own suggestion, since it holds no secrets) through `save-prompt`; assert `query.md` contains the linked form and the file was committed.
- End-to-end test showing `save-decision`'s AskUserQuestion answer path now also triggers this (satisfies requirement 1): a synthetic decision payload whose rendered block mentions an existing file should get linkified in `query.md` and the file committed, the same way a prompt would.

## Verification

- `python3 -m pytest scripts/°base/tests/test_ai_hooks_base_routing.py scripts/°base/tests/test_save_prompt_queued_commands.py -q`
- Manual: mention `ai/.debug` in a real prompt; confirm `ai/°base/query.md`'s new entry shows it as a markdown link and `git log -1 -- ai/.debug` shows the new auto-commit.
- Manual regression check: mention a path that matches an existing `.gitignore` rule under `ai/`; confirm it is **not** staged or committed (this is the scenario that used to force-add).
