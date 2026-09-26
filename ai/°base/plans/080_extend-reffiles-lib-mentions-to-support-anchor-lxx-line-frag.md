# Extend `°reffiles_lib` mentions to support `#anchor`/`#Lxx`/`:line` fragments, rewritten inline (fenced ones summarized after the block)

## Context

`scripts/°base/ai/hooks/°reffiles_lib/` scans logged prompt/decision text for `@path/to/file` and `` `path/to/file` `` mentions and, since commit `e778a13`, appends one markdown summary block *after the whole entry* linking to any mention that resolves to a real file — mentions inside fenced code blocks are skipped entirely (never scanned), and the entry's own text is never otherwise touched.

Three gaps, all confirmed with the user:

1. **No fragment support at all.** `mentions.py`'s regexes (`_AT_MENTION_RE`, `_BACKTICK_MENTION_RE`) greedily swallow any `#anchor`, `#L123`, `:345`, or `:346-400` suffix as part of the "path". Since no file literally exists at that name, `commit.py::resolve_existing`'s `abspath.is_file()` check fails and the mention is silently dropped — never linked, never staged.
2. **Append-only was too broad.** `e778a13`'s carve-out (never rewrite the entry text, only append a trailing block) was meant to protect fenced code-block examples from being mangled — not ordinary prose. Ordinary mentions outside fences should go back to being rewritten in place as markdown links.
3. **Fenced mentions still matter, just can't be rewritten in place.** A mention inside a ``` ``` ``` or `~~~` block (e.g. an example diff) must not have its raw text touched, but it should still be picked up and listed — as a summary block placed *immediately after that specific code block* (not at the end of the whole entry), reusing the pre-existing one-liner/`<details>` template (now fragment-aware), and indented/quoted to match the fence's own nesting (plain whitespace indent under a list item, and/or markdown blockquote `>` nesting — stacking an extra quote level, not just copying the indent).

**Explicitly out of scope (separate future change, per user):** making fence *detection* aware of fence-delimiter length/character consistency (e.g. a 4-backtick fence used to escape literal triple-backticks inside). Detection stays exactly as permissive as today (any line starting with `` ``` `` or `~~~`, after stripping quote/indent prefix, toggles fence state).

## Design

### Fragment syntax recognized (same as before)

| Typed suffix | Fragment kind | Link-target anchor appended |
|---|---|---|
| `#L123` / `#123` | line | `#L123` |
| `#L123-456` / `#123-456` / `#L123-L456` | line range | `#L123-L456` |
| `:345` | line (colon shorthand) | `#L345` |
| `:346-400` | line range (colon shorthand) | `#L346-L400` |
| `#some-title` (anything else starting with `#`) | heading anchor | `#some-title` (verbatim, no validation) |
| `:foo` (colon, non-numeric) | *not* a fragment — stays part of the path (protects things like `https://...`-shaped tokens) | — |

GitHub-style range anchors were chosen because neither PyCharm nor VS Code resolve `#Lxx` as a jump target from a plain markdown link anyway — it's a documentation convention, and GitHub's is the most recognized one. Fragment **display text** is always exactly what the user typed; only the **link target**'s anchor is normalized.

### Two rendering paths, decided by fence membership

- **Not inside a fence:** the raw mention text (`@path...` or `` `path...` ``, including surrounding backticks) is replaced *in place* with the rendered link.
- **Inside a fence:** the raw fenced text is left completely untouched. Instead, every mention found inside that fence is listed in a summary block inserted as new line(s) immediately after that fence's closing delimiter line, prefixed on every line with that fence's exact leading prefix (whitespace indent *and/or* blockquote `>` markers, verbatim) — reusing the pre-`e778a13`-removal single-line/`<details>` template, now with fragment-aware two-link rendering. Multiple separate fenced blocks in the same entry each get their own trailing summary, right after their own closing fence.

### `scripts/°base/ai/hooks/°reffiles_lib/mentions.py`

- Add `_LINE_FRAGMENT_RE = re.compile(r"^#L?(\d+)(?:-L?(\d+))?$")` and `_COLON_FRAGMENT_RE = re.compile(r"^:(\d+)(?:-(\d+))?$")`.
- Add `_split_path_fragment(candidate: str) -> tuple[str, str | None]`: splits at the first `#` or `:`; a `:`-split only counts as a fragment if it matches `_COLON_FRAGMENT_RE` (otherwise don't split, whole thing stays `path`); a `#`-split always counts as a fragment (line ref or heading, disambiguated later at render time).
- Add `anchor_target(fragment: str) -> str`: matches `_COLON_FRAGMENT_RE` then `_LINE_FRAGMENT_RE`, returns `#L{n}` / `#L{n}-L{m}`; otherwise returns `fragment` unchanged (heading passthrough).
- Generalize fence detection to also recognize a blockquote/indent prefix and capture it: `_FENCE_RE = re.compile(r"^([ \t>]*)(```|~~~)")`, matched against the *raw* line (no `.lstrip()` needed — the pattern already consumes leading spaces/tabs/`>`). Group 1 is the fence's full prefix string, reused verbatim later.
- Rework `Mention` to carry what both rendering paths need:
  ```python
  @dataclass
  class Mention:
      line: int                     # 1-indexed line number of the match itself
      start: int                    # start offset of the full raw match within that line
      end: int                      # end offset of the full raw match within that line
      at: bool                      # True for @mention, False for backtick mention
      path: str                     # bare path as typed, fragment stripped
      fragment: str | None          # raw "#..."/":..." suffix as typed, or None
      suffix: str                   # trailing punctuation stripped off the match (re-appended after the link when rewriting inline)
      in_fence: bool                # True if this mention was found inside a fenced code block
      fence_end_line: int | None    # 1-indexed line of that fence's closing delimiter (set only when in_fence)
      fence_prefix: str | None      # that fence's leading prefix string, verbatim (set only when in_fence)
  ```
- Rework `_line_mentions(line) -> list[tuple[int, int, bool, str, str | None, str]]` (start, end, at, path, fragment, suffix) using `m.start()`/`m.end()` for the *whole* regex match (including the `@`/backticks), and the same trailing-punctuation-stripping → fragment-splitting pipeline as `extract_candidate_paths` today.
- Rework `find_mentions` to **not** skip fenced lines when scanning — it still toggles fence state via `_FENCE_RE`, but now: while a fence is open, collect matches into a `fence_pending` list instead of discarding them; when the closing delimiter for that fence is hit, stamp every pending mention with `fence_end_line` (the closing line's number) and `fence_prefix` (the prefix captured when that fence opened), then flush them into the result list. An unterminated trailing fence's pending mentions are simply dropped (no closing line to anchor them to — same as being silently ignored today).
- Leave `extract_candidate_paths` as-is (unused by any real caller today; out of scope).

### `scripts/°base/ai/hooks/°reffiles_lib/commit.py`

- `resolve_existing` unchanged in logic (still resolves only `mention.path`, fragment-free); `ResolvedMention` just carries the new `Mention` fields through via dataclass inheritance, unchanged otherwise.
- Add `_mention_link(mention: ResolvedMention, log_path: Path) -> str` — the pure "what does this mention's markdown look like" builder, used by both rendering paths (no `suffix` here — that's only meaningful for the inline path):
  ```python
  def _mention_link(mention: ResolvedMention, log_path: Path) -> str:
      target = _link_target(mention.abspath, log_path)
      prefix = "@" if mention.at else ""
      text = f"[{prefix}`{mention.path}`]({target})"
      if mention.fragment is not None:
          text += f"[{mention.fragment}]({target}{anchor_target(mention.fragment)})"
      return text
  ```
- Replace `build_summary_block` with `_fence_summary_lines(mentions: list[ResolvedMention], log_path: Path, width: int) -> list[str]`, reusing the exact single-vs-multiple template from today's `build_summary_block` (one-liner `> _Mentioned file at line \`NNN\`:_ [...]` for exactly one; `<details><summary>` block for more than one) but with `[...]` built via `_mention_link`. This returns bare (unprefixed) lines; the fence's own `fence_prefix` is applied by the caller so this function stays about content, not placement.
- Replace `process_referenced_files` to do both things:
  1. Split `resolve_existing(...)` results into `inline = [m for m in resolved if not m.in_fence]` and `fenced = [m for m in resolved if m.in_fence]`.
  2. For `inline`: group by `line`, and for each line splice mentions in place, **rightmost `start` first** (so earlier offsets on that line stay valid): `line[:m.start] + _mention_link(m, log_path) + m.suffix + line[m.end:]`.
  3. For `fenced`: group by `(fence_end_line, fence_prefix)` (a `dict` keeps this simple since a `str` key component is fine). For each group, build the template body via `_fence_summary_lines`, prefix every line (including the blank separator lines the template already uses) with that group's `fence_prefix` verbatim, and insert the resulting lines into the line list right after index `fence_end_line` (0-indexed slice-insert: `lines[fence_end_line:fence_end_line] = new_lines`). Process fence groups **in descending order of `fence_end_line`** so inserting into the list doesn't shift the target index of a fence group still to be processed.
  4. Line-number padding width (`width = len(str(len(lines)))`, i.e. total line count) is computed once, up front, from the original content — reused for both the inline case (not currently padded — inline rendering has no line-number text at all, only the fenced summary uses `width`) and every fenced summary block, for visual consistency across blocks.
  5. Return `("\n".join(lines), resolved)`; if `resolved` is empty, return `(content, [])` unchanged, same as today.
- `stage_and_commit_mentions` unchanged.

### `scripts/°base/ai/hooks/°reffiles_lib/__init__.py`

- Drop `build_summary_block` from the re-exports; nothing named `_fence_summary_lines`/`_mention_link` needs to be public (module-private helpers, matching `_link_target`'s existing visibility).
- Add `anchor_target` to the re-exports (pure helper, worth testing directly, matching how other small helpers here are exposed).

### Tests: `scripts/°base/tests/test_ai_hooks_base_routing.py`

- **`ReffilesLibMentionsTests`**: update existing assertions to the new `Mention` shape. Add:
  - hash line fragment (`#L123`) and hash line-range fragment (`#123-456` / `#L123-L456`) splitting.
  - colon line fragment (`:345`) and colon line-range fragment (`:346-400`) splitting.
  - heading anchor fragment (`#some-title`) splitting, unvalidated.
  - a non-numeric colon suffix (e.g. a `https://host/path`-shaped token) is *not* split.
  - `find_mentions` now **does** find mentions inside a fenced block (reversing the old "skipped entirely" test) and stamps them with the correct `fence_end_line` and `fence_prefix`; mentions outside fences have `in_fence=False`.
  - a fence indented under a list item (existing test, `test_find_mentions_skips_indented_fence_under_list_item` → rename/repurpose) now asserts `fence_prefix` equals that indentation.
  - a fence nested inside a markdown blockquote (`> ` prefix) is detected, with `fence_prefix` capturing the `> ` (or nested `> > `) prefix.
  - an unterminated fence (no closing delimiter) contributes no mentions.
  - `anchor_target` unit tests covering all six rows of the fragment table above.
- **`ReffilesLibCommitTests`**: replace the `build_summary_block` tests with:
  - `_mention_link` (or via `process_referenced_files`) for a plain mention (no fragment), a hash-anchor mention, and a colon/hash line-range mention — asserting correct two-link form and GitHub-style target anchors.
  - `process_referenced_files`: a non-fenced mention is rewritten in place; trailing punctuation ends up after the link, not inside it; two mentions on the same line are both rewritten correctly (proves reverse-order splicing doesn't corrupt offsets); no resolved mentions → content unchanged.
  - `process_referenced_files`: a mention inside a fenced block is **not** rewritten in place, but a summary block appears immediately after that fence's closing delimiter, with lines prefixed by the fence's indent.
  - Same, but the fence is nested in a blockquote: the inserted summary lines carry the blockquote's `>` prefix stacked in front of the template's own `>` lines (nested blockquote).
  - Two separate fenced blocks in the same content each get their own trailing summary in the right place.
- **End-to-end tests**: update `test_referenced_file_mention_appends_summary_block_and_links` and `test_ask_user_question_answer_mention_gets_summary_and_commit` to assert the inline link form appears directly in `query.md`'s entry text. Update `test_referenced_file_mention_inside_fenced_code_block_is_not_committed` — the fenced example text itself must still be untouched, but now assert a trailing summary block *does* appear right after that fence, linking to the file (previously this test asserted nothing happened at all for fenced mentions — that assumption changes here), and that the file still gets staged/committed like any other resolved mention.

## Verification

- `python3 -m pytest scripts/°base/tests/test_ai_hooks_base_routing.py -q`
- Manual: submit a prompt like `` Talking about `docs/README.md#some-title` or @query.md#top `` (both files exist); confirm `ai/°base/query.md`'s new entry has both mentions rewritten in place as two-link markdown, with correct relative targets.
- Manual: submit `@docs/README.md:345` and `` `docs/README.md:346-400` ``; confirm both get `#L345` / `#L346-L400` GitHub-style target anchors while the visible fragment label stays as typed.
- Manual: submit a prompt with a fenced ` ``` ` block containing an example `@path/to/file#L10` mention, where that file exists; confirm the fenced text is untouched, but a summary block linking to it appears right after the closing fence.
- Manual: same, but the fenced block is indented under a `-` list item, and separately nested inside a `> ` blockquote; confirm the inserted summary lines are prefixed to match (list indent, and stacked `>` for the blockquote case) so they render as part of the same list item / blockquote rather than breaking out of it.
