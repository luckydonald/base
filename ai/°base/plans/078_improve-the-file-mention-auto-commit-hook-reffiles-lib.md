# Improve the file-mention auto-commit hook (°reffiles_lib)

## Context

`scripts/°base/ai/hooks/°reffiles_lib/` (implemented via plan 034, commit `fcfb7fb`) scans user prompt text for `@path/to/file` and `` `path/to/file` `` mentions and auto-stages/commits any that resolve to real files on disk. Three gaps surfaced while using it (see the live request logged at the tail of `ai/°base/query.md`):

1. **Coverage**: `handle_referenced_files()` is only ever called once, at the very tail of `save-prompt/hook.py`'s `main()` — i.e. only on the plain "user typed a prompt" path. `AskUserQuestion` answers (handled by `save-decision/hook.py`) and other logged interactions (queued commands, compact prompts, plan writes, command decisions) never get scanned, even though they're logged into the same kind of ai/ artifact files via the same shared primitive, `append_and_commit()` in `_lib.py`.
2. **Readability**: mentions are logged into `query.md` as plain text, with no link to the file. The user wants a summary of the mentioned, existing files appended to the log entry at write time — as markdown links — but only for files that actually exist (no dead links), and **not** for anything that appears inside a fenced ` ``` ` code block (example diffs, quoted snippets, etc. must not be treated as real mentions — this /plan request's own fenced diff example is exactly such a case).
3. **Safety**: the current commit logic force-adds (`git add -f`) any untracked mention path starting with `ai/`, bypassing `.gitignore` unconditionally "for AI artifacts." This is exactly the mechanism that could silently commit something like `ai/.env` if it were ever gitignored — the user deliberately avoided triggering this while testing it. The fix is to always respect `.gitignore`, with no `ai/`-prefix exception.

Confirmed approach for (1): centralize the mention-scan/linkify/auto-commit logic inside `append_and_commit()` itself (in `_lib.py`), the single function every logging hook (`save-prompt`, `save-decision`, `save-plan`, `save-command-decision`, `save-compact-prompt`, `compact_result.py`) already calls to write into an ai/ log file. This covers "other interactions" for good — no hook can forget to wire it in later — and naturally satisfies (2) as well, since it's the one place `content` is transformed immediately before being written to disk (not a re-parse after the fact).

## Implementation

### 1. Break the `_lib` ↔ `°reffiles_lib` import cycle

`°reffiles_lib/commit.py` currently does `from _lib import base_ai_commit_subject`. Once `_lib.py` needs to import `°reffiles_lib`, this becomes circular. Fix: have `commit.py` get `base_ai_commit_subject` the same way `_lib.py` itself does — `import_module("°commit_style_lib").base_ai_commit_subject` — instead of going through `_lib`. This removes the reverse dependency entirely so `_lib.py` can safely do `reffiles_lib = importlib.import_module("°reffiles_lib")`.

### 2. `°reffiles_lib/mentions.py` — line-aware matching that skips fenced code blocks

Keep `extract_candidate_paths()` exactly as-is (existing tests + backward compat; it's still used for the pure "does this prompt reference any path" case elsewhere). Add a new function that walks `content` line by line, tracking fenced-code-block state so example diffs/snippets are never treated as real mentions:

```python
@dataclass
class Mention:
    line: int       # 1-indexed line number within `content`
    display: str    # original text to show as the link label, e.g. "@src/other_file.py" or "`ai/some_file.md`"
    path: str       # candidate path used for filesystem resolution (same value extract_candidate_paths would produce)

_FENCE_RE = re.compile(r"^(```|~~~)")

def find_mentions(content: str) -> list[Mention]:
    """Like extract_candidate_paths, but per-line and fence-aware: skips any
    line inside a ``` or ~~~ fenced block (including the fence delimiter
    lines themselves), so example code/diffs are never mistaken for mentions."""
```

Fence detection: for each line, check `_FENCE_RE.match(line.lstrip())` (handles fences indented under a markdown list item, as in this very /plan request's diff example) and toggle an `in_fence` flag; skip mention-scanning entirely while `in_fence` is true (both the opening and closing fence lines are skipped too, since they can't contain a real mention). Non-fenced lines are scanned with the existing `_AT_MENTION_RE` / `_BACKTICK_MENTION_RE` (per line — the backtick regex already disallows embedded newlines, so per-line scanning is equivalent to the old whole-content scanning for real content). Unlike `extract_candidate_paths`, **do not dedupe** — each occurrence becomes its own `Mention` (needed so the summary list can show every `line NNN` a file was mentioned on); deduping for git purposes happens later, in `stage_and_commit_mentions`.

### 3. `°reffiles_lib/commit.py` — existing-file summary block + gitignore-safe commit

- Add `is_gitignored(relpath: str) -> bool` using `git check-ignore -q -- <relpath>` (returncode 0 ⇒ ignored).
- Replace `handle_referenced_files()` with:
  - `resolve_existing(mentions: list[Mention], subproject: Path) -> list[ResolvedMention]`: for each `Mention`, resolve `(subproject / mention.path).resolve()`, keep only when `abspath.is_file()`, and compute the git-root-relative path the same way the old `handle_referenced_files` did (`abspath.relative_to(Path.cwd())`, skipping on `ValueError` for anything outside the repo). `ResolvedMention` extends `Mention` with `abspath`/`relpath`.
  - `build_summary_block(resolved: list[ResolvedMention], log_path: Path) -> str | None`: `None` if `resolved` is empty. For each entry, the link target is `os.path.relpath(abspath, log_path.parent)`, prefixed with `./` unless it already starts with `..` (matches the user's example: a file next to `ai/query.md` → `./some_file.md`; one under `src/` → `../src/other_file.py`). Format:
    - **Exactly one** resolved mention → a single blockquote line:
      ```
      > _Mentioned file at line `124`:_ [{display}]({target})
      ```
    - **More than one** → a collapsible blockquote block, using an HTML `<i>` tag (not markdown `_..._`) inside `<summary>` since markdown emphasis syntax doesn't reliably render inside inline HTML:
      ```
      > <details><summary><i>Mentioned files:</i></summary>
      >
      > - line `002`: [{display}]({target})
      > - line `012`: [{display}]({target})
      >
      > </details>
      ```
      One `- line \`NNN\`: [...](...)` per resolved mention, in order of appearance, line numbers zero-padded to 3 digits (`f"{n:03d}"`).
  - `process_referenced_files(content: str, subproject: Path, log_path: Path) -> tuple[str, list[ResolvedMention]]`: `mentions = find_mentions(content)` → `resolved = resolve_existing(mentions, subproject)` → `block = build_summary_block(resolved, log_path)`. If `block is None`, return `(content, [])` unchanged. Otherwise return `(content.rstrip("\n") + "\n\n" + block + "\n\n", resolved)` — content itself is **never rewritten inline**, only appended to; this is what keeps fenced code blocks and any other original formatting untouched.
  - `stage_and_commit_mentions(resolved: list[ResolvedMention]) -> None`: dedupe `resolved` by `relpath` (first occurrence wins) before acting, then per unique file — if `is_tracked(relpath)`, just `git add` it (unchanged); otherwise, if `is_gitignored(relpath)`, skip it entirely (**no exception for `ai/`-prefixed paths** — this is the safety fix); otherwise `git add` + `git commit --no-verify --only <relpath> -m base_ai_commit_subject("ai: referenced file for task added.")` as today.
- Keep `is_tracked()` unchanged.

### 4. `_lib.py` — wire it into `append_and_commit()`

In `append_and_commit()` (line ~484), right after `snap = _staged_snapshot(relpath)` and before the file write:

```python
reffiles_lib = importlib.import_module("°reffiles_lib")  # lazy, avoids any load-order issues
content, resolved_mentions = reffiles_lib.process_referenced_files(content, _subproject_root(), log_path)
```

Write the (possibly summary-appended) `content` instead of the raw argument. After the existing commit + `_restore_staged` calls, add `reffiles_lib.stage_and_commit_mentions(resolved_mentions)` as the final step — same relative ordering as today (log gets committed first, then mentioned files get their own commit(s)).

### 5. `save-prompt/hook.py` — remove the now-redundant explicit call

Delete the tail call `reffiles_lib.handle_referenced_files(raw_prompt, _subproject_root())` (around line 1067) — this logic now runs automatically inside the `append_and_commit()` call that immediately precedes it (line 1060). Leaving both would double-process mentions (using the *pre-linkify* `raw_prompt`, against a query.md that already has the linkified text). Remove the now-unused top-of-file `reffiles_lib = importlib.import_module("°reffiles_lib")` import and `raw_prompt` capture from `hook.py` if nothing else in the file uses them after this change (check first).

### 6. Tests

- Extend `test_ai_hooks_base_routing.py`'s `ReffilesLibMentionsTests` area with unit tests for `find_mentions`: mentions inside a fenced ` ``` `/`~~~` block (including an indented one nested under a markdown list, mirroring this /plan request's own diff example) are skipped entirely; mentions outside fences are still found with correct line numbers.
- Unit tests for `build_summary_block`: single resolved mention → the `> _Mentioned file at line \`NNN\`:_ [...](...)]` one-liner; two or more → the `<details><summary><i>Mentioned files:</i></summary>` block with one `- line \`NNN\`: [...](...)` per mention and correct `./` vs `../` targets (both cases from the user's example); zero resolved mentions → `None` (content unchanged, nothing appended).
- Unit test for `is_gitignored` + the removed `ai/`-prefix exception: with a `.gitignore` rule covering an `ai/`-prefixed path, assert `stage_and_commit_mentions` does **not** stage/commit it (regression test for the incident this plan fixes).
- End-to-end test via the existing `run_hook` harness: submit a prompt mentioning an existing, untracked, non-ignored file (use `ai/.debug`, per the user's own suggestion, since it holds no secrets) through `save-prompt`; assert `query.md` gets the appended summary block and the file was committed.
- End-to-end test showing `save-decision`'s AskUserQuestion answer path now also triggers this (satisfies requirement 1): a synthetic decision payload whose rendered block mentions an existing file should get the summary block appended in `query.md` and the file committed, the same way a prompt would.

## Verification

- `python3 -m pytest scripts/°base/tests/test_ai_hooks_base_routing.py scripts/°base/tests/test_save_prompt_queued_commands.py -q`
- Manual: mention `ai/.debug` in a real prompt; confirm `ai/°base/query.md`'s new entry gets the appended blockquote link and `git log -1 -- ai/.debug` shows the new auto-commit.
- Manual: submit a prompt containing a fenced code block with an example `@path/or/`` `path`` `` mention inside it (like this very /plan request); confirm nothing inside the fence is treated as a mention (no summary block appended, nothing committed) for that fenced text.
- Manual regression check: mention a path that matches an existing `.gitignore` rule under `ai/`; confirm it is **not** staged or committed (this is the scenario that used to force-add).
