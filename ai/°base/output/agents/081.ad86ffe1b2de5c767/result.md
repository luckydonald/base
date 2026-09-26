# Report: `°reffiles_lib` (file-mention auto-commit hook)

Location: `/home/user/git/luckydonald/base/scripts/°base/ai/hooks/°reffiles_lib`

## 1. Directory structure / files (with line counts)

```
°reffiles_lib/
├── __init__.py     21 lines  — public re-export surface
├── mentions.py     68 lines  — pure text extraction of @/backtick mentions (regex, no filesystem/git access)
├── commit.py      128 lines  — resolves mentions to real files, builds markdown summary block, git add/commit
└── __pycache__/    (compiled bytecode only, ignore)
```

No sub-packages beyond `__pycache__`. Full paths:
- `/home/user/git/luckydonald/base/scripts/°base/ai/hooks/°reffiles_lib/__init__.py`
- `/home/user/git/luckydonald/base/scripts/°base/ai/hooks/°reffiles_lib/mentions.py`
- `/home/user/git/luckydonald/base/scripts/°base/ai/hooks/°reffiles_lib/commit.py`

## 2. Mention-detection regex logic (verbatim)

File: `mentions.py`, lines 1–68.

```python
"""Pure text extraction of file-path mentions from a prompt."""
from __future__ import annotations

import re
from dataclasses import dataclass

_AT_MENTION_RE = re.compile(r"(?<!\S)@([^\s`]+)")
_BACKTICK_MENTION_RE = re.compile(r"`([^`\n]+)`")
_TRAILING_PUNCT = ".,;:!?)]}\"'"
_FENCE_RE = re.compile(r"^(```|~~~)")


def extract_candidate_paths(prompt: str) -> list[str]:
    """@mention and backtick-quoted candidate paths containing '/', deduped, order-preserved."""
    seen: set[str] = set()
    out: list[str] = []
    for regex in (_AT_MENTION_RE, _BACKTICK_MENTION_RE):
        for m in regex.finditer(prompt):
            candidate = m.group(1).strip().rstrip(_TRAILING_PUNCT)
            if "/" in candidate and candidate not in seen:
                seen.add(candidate)
                out.append(candidate)
    return out


@dataclass
class Mention:
    line: int       # 1-indexed line number within the scanned text
    display: str    # original text to show as the link label, e.g. "@src/other_file.py" or "`ai/some_file.md`"
    path: str       # candidate path used for filesystem resolution


def _line_mentions(line: str) -> list[tuple[str, str]]:
    """(display, path) pairs for @mentions and backtick mentions on a single line."""
    found: list[tuple[str, str]] = []
    for m in _AT_MENTION_RE.finditer(line):
        path = m.group(1).strip().rstrip(_TRAILING_PUNCT)
        if "/" in path:
            found.append((f"@{path}", path))
    for m in _BACKTICK_MENTION_RE.finditer(line):
        raw = m.group(1)
        path = raw.strip().rstrip(_TRAILING_PUNCT)
        if "/" in path:
            found.append((f"`{raw}`", path))
    return found


def find_mentions(content: str) -> list[Mention]:
    """Like `extract_candidate_paths`, but per-line and fence-aware: skips any
    line inside a ``` or ~~~ fenced code block (including the fence delimiter
    lines themselves), so example diffs/snippets are never mistaken for real
    mentions.

    Unlike `extract_candidate_paths`, matches are not deduplicated -- each
    occurrence becomes its own `Mention` so a summary can list every line a
    file was referenced on.
    """
    mentions: list[Mention] = []
    in_fence = False
    for lineno, line in enumerate(content.split("\n"), start=1):
        if _FENCE_RE.match(line.lstrip()):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        for display, path in _line_mentions(line):
            mentions.append(Mention(line=lineno, display=display, path=path))
    return mentions
```

**Verbatim regex patterns (mentions.py:7–10):**
```
_AT_MENTION_RE       = re.compile(r"(?<!\S)@([^\s`]+)")
_BACKTICK_MENTION_RE = re.compile(r"`([^`\n]+)`")
_TRAILING_PUNCT      = ".,;:!?)]}\"'"
_FENCE_RE            = re.compile(r"^(```|~~~)")
```

### Fragment/anchor handling — none exists

There is **no** logic anywhere in this library that strips or recognizes `#anchor`, `#L123`, `:345`, or `:346-400` suffixes. I verified this both by reading the source (no `#`/`:`-splitting code anywhere in `mentions.py` or `commit.py`) and empirically:

```
@src/file.py#L10       -> captured path: "src/file.py#L10"
@src/file.py:345       -> captured path: "src/file.py:345"
@src/file.py:345-400   -> captured path: "src/file.py:345-400"
`src/file.py#L10`      -> captured path: "src/file.py#L10"
`src/file.py:345-400`  -> captured path: "src/file.py:345-400"
```

`_AT_MENTION_RE`'s character class `[^\s`]+` and `_BACKTICK_MENTION_RE`'s `[^`\n]+` both greedily swallow the `#`/`:` suffix as part of the "path" — neither regex nor `_TRAILING_PUNCT` stripping (which only trims a single trailing char like `.` `,` `)` etc., and `:` is even *in* that trailing-punct set but only strips if it's the very last character, e.g. `foo/bar:` → `foo/bar`, not `foo/bar:345` → `foo/bar`) does anything with mid-string `#`/`:` fragments.

Consequence downstream in `commit.py::resolve_existing` (line 42–59): `abspath = (subproject / mention.path).resolve()` then `if not abspath.is_file(): continue`. Since no real file exists literally named `file.py:345` or `file.py#L10`, `is_file()` returns `False` and the mention is **silently dropped** — it never becomes a `ResolvedMention`, never appears in the summary block, and the file never gets auto-staged/committed. So today's behavior is: **fails to parse/resolve, and silently ignores** any mention with such a suffix (not "strips" it, not "ignores gracefully with a warning" — it just never resolves).

## 3. Markdown link generation — exact function, full source

File: `commit.py`. Two functions matter here: `_link_target` (relative-path helper, also answers item 3 below) and `build_summary_block` (the actual `[text](link)` markdown generator), plus the orchestrating `process_referenced_files`.

```python
def _link_target(abspath: Path, log_path: Path) -> str:
    target = os.path.relpath(abspath, log_path.parent)
    return target if target.startswith("..") else f"./{target}"


def build_summary_block(resolved: list[ResolvedMention], log_path: Path, content: str) -> str | None:
    """A blockquote note to append after a log entry, linking to each existing
    mentioned file. `None` when there's nothing to mention."""
    if not resolved:
        return None

    width = len(str(content.count("\n") + 1))

    if len(resolved) == 1:
        mention = resolved[0]
        target = _link_target(mention.abspath, log_path)
        line_no = f"{mention.line:0{width}d}"
        return f"> _Mentioned file at line `{line_no}`:_ [{mention.display}]({target})"

    lines = ["> <details><summary><i>Mentioned files:</i></summary>", ">"]
    for mention in resolved:
        target = _link_target(mention.abspath, log_path)
        line_no = f"{mention.line:0{width}d}"
        lines.append(f"> - line `{line_no}`: [{mention.display}]({target})")
    lines.append(">")
    lines.append("> </details>")
    return "\n".join(lines)


def process_referenced_files(
    content: str, subproject: Path, log_path: Path
) -> tuple[str, list[ResolvedMention]]:
    """Append a summary of existing mentioned files to `content` (never
    rewriting it inline, so fenced code blocks and other formatting are left
    untouched) and return the resolved mentions to stage/commit.

    Assumes cwd is already the git root (as `resolve_log_path` leaves it).
    """
    mentions = find_mentions(content)
    resolved = resolve_existing(mentions, subproject)
    block = build_summary_block(resolved, log_path, content)
    if block is None:
        return content, []
    return content.rstrip("\n") + "\n\n" + block + "\n\n", resolved
```

(`commit.py` lines 62–105.) The markdown link `[{display}]({target})` is produced inline inside `build_summary_block` — `display` comes straight from `Mention.display` (`"@path"` or `` "`raw-text`" `` including the original backticked text), and `target` from `_link_target`.

## 4. Relative-path helper (item 3)

`_link_target(abspath: Path, log_path: Path) -> str` — `/home/user/git/luckydonald/base/scripts/°base/ai/hooks/°reffiles_lib/commit.py:62–64`:

```python
def _link_target(abspath: Path, log_path: Path) -> str:
    target = os.path.relpath(abspath, log_path.parent)
    return target if target.startswith("..") else f"./{target}"
```

This is the only relative-path computation helper in the lib. It uses stdlib `os.path.relpath(abspath, log_path.parent)` (relative to the directory the log file — e.g. `ai/query.md` — lives in), then normalizes: if the result already climbs out (`..`), leave it as-is (e.g. `../sub/file.txt`); otherwise prefix with `./` (e.g. `./some_file.md`). This is exactly what produces the `../docs/README.md`-style output. It has no separate module — it lives directly in `commit.py`, called from both branches of `build_summary_block`.

## 5. Existing tests

All tests live in one file: `/home/user/git/luckydonald/base/scripts/°base/tests/test_ai_hooks_base_routing.py`. Two dedicated `unittest.TestCase` classes exercise this lib directly (imported via `importlib.import_module("°reffiles_lib.mentions")` / `"°reffiles_lib.commit"`, same pattern as `°split_lib`), plus several end-to-end tests exercise it through the full hook pipeline.

**`ReffilesLibMentionsTests`** (lines 2544–2609) — unit tests for `mentions.py`:
- `test_extracts_at_mention_and_backtick_path` (2555) — basic `@path` + `` `path` `` extraction.
- `test_strips_trailing_punctuation` (2562) — trailing `,`/`.`/`)` stripped.
- `test_ignores_non_path_tokens` (2569) — tokens without `/` (e.g. `@someone`, `` `just_a_word` ``) are ignored.
- `test_dedupes_repeated_mentions` (2573) — `extract_candidate_paths` dedupes.
- `test_find_mentions_reports_display_and_line` (2577) — `find_mentions` returns correct `line`/`display`/`path`.
- `test_find_mentions_skips_fenced_code_block` (2585) — mentions inside a ``` ```diff ``` fence are skipped, ones outside are kept, with correct line numbers.
- `test_find_mentions_skips_indented_fence_under_list_item` (2600) — fence indented under a markdown list item (`  ```diff`) is still detected via `line.lstrip()`.

None of these tests cover `#anchor`/`:line` suffixes — this edge case is entirely untested, confirming it's an unaddressed gap.

**`ReffilesLibCommitTests`** (lines 2612–2668) — unit tests for `commit.py`'s `build_summary_block` (pure string/path logic, no git/filesystem):
- `test_single_mention_uses_one_liner` (2630) — exact one-liner output format.
- `test_multiple_mentions_uses_details_block` (2639) — `<details>` block format, verifies both `./` and `../` target styles simultaneously.
- `test_no_resolved_mentions_returns_none` (2656).
- `test_padding_width_scales_with_entry_line_count` (2659) — line-number zero-padding scales with total content line count.

**End-to-end tests** (in `AiHooksBaseRoutingTests`-style class above, using the `run_hook` harness against a real temp git repo), lines 2318–2450:
- `test_referenced_file_mention_untracked_gets_own_commit` (2318) — untracked mentioned file gets its own auto-commit.
- `test_referenced_file_mention_tracked_only_staged` (2333) — already-tracked file just gets `git add`, no separate commit.
- `test_referenced_file_mention_gitignored_ai_path_not_committed` (2349) — regression test: gitignored `ai/`-prefixed paths are **not** force-added anymore (this was a prior bug/behavior removed).
- `test_referenced_file_mention_missing_file_ignored` (2370) — mention of a nonexistent path is a no-op.
- `test_referenced_file_mention_appends_summary_block_and_links` (2379) — verifies the `[@sub/file.txt](../sub/file.txt)` markdown link actually lands in `query.md`.
- `test_referenced_file_mention_inside_fenced_code_block_is_not_committed` (2395) — fenced example mentions aren't committed.
- `test_ask_user_question_answer_mention_gets_summary_and_commit` (2413) — mentions inside `AskUserQuestion` answers (routed through `save-decision`) also trigger the mechanism, since it's centralized in `append_and_commit()`.

## 6. File-by-file responsibility breakdown

- **`mentions.py`** — pure regex/text layer. No filesystem or git access. Defines the `Mention` dataclass and two extraction entry points: `extract_candidate_paths` (legacy/simple, deduped, whole-content) and `find_mentions` (line-aware, fence-skipping, non-deduped, used by the current pipeline). This is where any regex change to support `#anchor`/`:line` suffixes would go (`_AT_MENTION_RE`, `_BACKTICK_MENTION_RE`, `_line_mentions`, plus likely a new suffix-stripping step before the `/` check and before returning `path`).
- **`commit.py`** — resolution + rendering + git side effects layer:
  - `is_tracked` / `is_gitignored` — git status queries via `subprocess`.
  - `ResolvedMention` dataclass (extends `Mention` with `abspath`/`relpath`).
  - `resolve_existing` — turns raw `Mention`s into `ResolvedMention`s by checking the filesystem (`abspath.is_file()`) and computing the git-root-relative path. **This is where a suffix-aware fix would also need to reach** — either mentions.py strips the suffix before this runs, or this function needs to try stripping `#…`/`:…` before the `is_file()` check.
  - `_link_target` — relative-path computation for markdown link targets (item 3/4 above).
  - `build_summary_block` — renders the `[display](target)` markdown blockquote/details block (item 2 above).
  - `process_referenced_files` — orchestrates find → resolve → render → append (never rewrites original content, only appends).
  - `stage_and_commit_mentions` — the actual `git add` / `git commit --no-verify --only` side effects, respecting `.gitignore`, deduped by `relpath`.
- **`__init__.py`** — thin re-export surface (`build_summary_block`, `is_gitignored`, `is_tracked`, `process_referenced_files`, `resolve_existing`, `stage_and_commit_mentions`, `Mention`, `extract_candidate_paths`, `find_mentions`).
- **Caller**: `/home/user/git/luckydonald/base/scripts/°base/ai/hooks/_lib.py`, function `append_and_commit` (lines 484–523) — the single shared entry point every logging hook (`save-prompt`, `save-decision`, `save-plan`, `save-command-decision`, `save-compact-prompt`, `compact_result.py`) calls to write into an `ai/` log file. It does `reffiles_lib = import_module("°reffiles_lib")`, calls `process_referenced_files(content, _subproject_root(), log_path)` before writing the file, commits the log itself, then calls `stage_and_commit_mentions(resolved_mentions)` as the final step.

Historical context: this lib was introduced in commit `fcfb7fb` and reworked to its current shape (centralized in `append_and_commit`, fence-aware, gitignore-respecting) in commit `e778a13`, per plan `/home/user/git/luckydonald/base/ai/°base/plans/078_improve-the-file-mention-auto-commit-hook-reffiles-lib.md` (that plan document's proposed design matches the current source exactly — it's the historical spec for what's now implemented, not a pending TODO). Nothing in that plan or the current code addresses `#anchor`/`:line` fragment suffixes; that is a genuinely new gap for you to design a fix for.