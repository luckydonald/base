# Extend `°reffiles_lib` mentions to support `#anchor`/`#Lxx`/`:line` fragments, rewritten inline (fenced ones summarized after the block)

## Context

`scripts/°base/ai/hooks/°reffiles_lib/` scans logged prompt/decision text for `@path/to/file` and `` `path/to/file` `` mentions and, since commit `e778a13`, appends one markdown summary block *after the whole entry* linking to any mention that resolves to a real file — mentions inside fenced code blocks are skipped entirely (never scanned), and the entry's own text is never otherwise touched.

Gaps, all confirmed with the user:

1. **No fragment support at all.** The regexes greedily swallow any `#anchor`, `#L123`, `:345`, or `:346-400` suffix as part of the "path", so `resolve_existing`'s `abspath.is_file()` check fails (no such literal file) and the mention is silently dropped.
2. **A real file's own name could legitimately contain `#`/`:`.** Rather than always assuming the first/any `#`/`:` starts a fragment, the resolver should try the *most conservative* interpretation first — the whole mention text as a literal filename — and only fall back to treating a suffix as a fragment if that literal file doesn't exist. This also handles the pathological "fragment on a fragment" case (`foo.ext:1234#245:123`) by trying each progressively-more-aggressive split until one resolves, and gives up (mention dropped, as today) if none do. This has to happen where filesystem access lives (`commit.py`), not in the pure-text `mentions.py`.
3. **Fragment *type* (line ref vs. heading anchor) is picked mechanically, not validated.** A fragment shaped like `#L123-456` is always treated as a line range, even in the vanishingly unlikely case the target document has an actual `<a name="L123-456">` or heading literally titled that. Confirmed acceptable — no heading/anchor validation is being added (already decided below), so this ambiguity is accepted as-is.
4. **Append-only was too broad.** `e778a13`'s carve-out (never rewrite the entry text, only append a trailing block) was meant to protect fenced code-block examples from being mangled — not ordinary prose. Ordinary mentions outside fences go back to being rewritten in place as markdown links.
5. **Fenced mentions still matter, just can't be rewritten in place.** A mention inside a ``` ``` ``` or `~~~` block must not have its raw text touched, but should still be picked up and listed — in a summary block placed *immediately after that specific code block*, reusing the pre-existing one-liner/`<details>` template (now fragment-aware), indented/quoted to match the fence's own nesting (plain whitespace indent under a list item, and/or markdown blockquote `>` nesting stacked on top of the template's own `>` lines — not just copied indent).

**Explicitly out of scope (separate future change, per user):** fence *detection* becoming aware of fence-delimiter length/character consistency (e.g. a 4-backtick fence escaping literal triple-backticks inside). Detection stays as permissive as today.

## Design

### Path/fragment splitting: try the most conservative interpretation first

Given a mention's raw text (after stripping trailing punctuation), build an **ordered list of `(path, fragment)` candidates**, most-conservative first:

1. The whole string, unsplit (`fragment=None`) — "maybe this is just a real file with a weird name."
2. One candidate per `#`/`:` position that could plausibly start a fragment, tried **rightmost first**, walking left — i.e. keep as much of the string as `path` as possible, only falling back to slicing off more once a shorter interpretation still doesn't exist.
   - Every `#` position is a plausible split point (heading anchors are free-form text, so anything after `#` is a legal fragment shape).
   - A `:` position is only a plausible split point if everything from `:` onward matches a line/line-range shape (`:\d+` or `:\d+-\d+`) — otherwise it's left alone (protects things like `https://...`-shaped tokens from ever being split there).
3. Any candidate whose `path` half doesn't contain `/` is discarded (keeps the existing "must look like a path" gate, just applied per-candidate instead of once).

`commit.py::resolve_existing` walks a mention's candidates **in that order** and keeps the first whose `path` resolves to a real file — this is the only place doing filesystem I/O, so it's the natural home for "does this shorter interpretation actually exist" logic. If none of a mention's candidates resolve, the mention is dropped entirely, same as an unresolved mention is today.

Example: `foo.ext:1234#245:123` → candidates tried in order: `("foo.ext:1234#245:123", None)`, `("foo.ext:1234#245", ":123")` (rightmost `:` — matches the line-shape), `("foo.ext:1234", "#245:123")` (the `#`) — the `:` right after `foo.ext` is *not* a candidate split point, since `:1234#245:123` doesn't match the line/line-range shape.

### Fragment → link-target anchor (once a `(path, fragment)` pair is chosen)

| Fragment shape | Kind | Link-target anchor appended |
|---|---|---|
| `#L123` / `#123` | line | `#L123` |
| `#L123-456` / `#123-456` / `#L123-L456` | line range | `#L123-L456` |
| `:345` | line (colon shorthand) | `#L345` |
| `:346-400` | line range (colon shorthand) | `#L346-L400` |
| anything else starting with `#` (e.g. `#some-title`) | heading anchor | verbatim, no validation |

GitHub-style range anchors were chosen because neither PyCharm nor VS Code resolve `#Lxx` as a jump target from a plain markdown link anyway — it's a documentation convention, and GitHub's is the most recognized one. The fragment's **display text** in the rendered link is always exactly what the user typed; only the **link target**'s anchor is normalized.

### Two rendering paths, decided by fence membership

- **Not inside a fence:** the raw mention text (`@path...` or `` `path...` ``, including surrounding backticks) is replaced *in place* with the rendered link.
- **Inside a fence:** the raw fenced text is left completely untouched. Every mention resolved inside that fence is listed in a summary block inserted as new line(s) immediately after that fence's closing delimiter line, every line prefixed with that fence's exact leading prefix (whitespace indent and/or blockquote `>` markers, verbatim) — reusing the pre-`e778a13`-removal single-line/`<details>` template, now fragment-aware. Multiple separate fenced blocks in the same entry each get their own trailing summary, right after their own closing fence.

### `scripts/°base/ai/hooks/°reffiles_lib/mentions.py`

- Add `_LINE_FRAGMENT_RE = re.compile(r"^#L?(\d+)(?:-L?(\d+))?$")` and `_COLON_FRAGMENT_RE = re.compile(r"^:(\d+)(?:-(\d+))?$")`.
- Add `anchor_target(fragment: str) -> str`: matches `_COLON_FRAGMENT_RE` then `_LINE_FRAGMENT_RE`, returns `#L{n}` / `#L{n}-L{m}`; otherwise returns `fragment` unchanged (heading passthrough).
- Add `_split_candidates(raw: str) -> list[tuple[str, str | None]]`:
  ```python
  def _split_candidates(raw: str) -> list[tuple[str, str | None]]:
      positions = [i for i, ch in enumerate(raw) if ch == "#"]
      positions += [i for i, ch in enumerate(raw) if ch == ":" and _COLON_FRAGMENT_RE.match(raw[i:])]
      candidates = [(raw, None)]
      for i in sorted(positions, reverse=True):
          candidates.append((raw[:i], raw[i:]))
      return [(path, frag) for path, frag in candidates if "/" in path]
  ```
- Generalize fence detection to also recognize a blockquote/indent prefix and capture it: `_FENCE_RE = re.compile(r"^([ \t>]*)(```|~~~)")`, matched against the *raw* line (the pattern already consumes leading spaces/tabs/`>`, so no `.lstrip()` needed). Group 1 is the fence's full prefix string, reused verbatim later.
- Rework `Mention` to carry candidates instead of a single resolved path/fragment, plus fence placement info:
  ```python
  @dataclass
  class Mention:
      line: int                             # 1-indexed line number of the match
      start: int                            # start offset of the full raw match within that line
      end: int                              # end offset of the full raw match within that line
      at: bool                              # True for @mention, False for backtick mention
      candidates: list[tuple[str, str | None]]  # ordered (path, fragment) options, most-conservative first
      suffix: str                           # trailing punctuation stripped off the match (re-appended after the link when rewriting inline)
      in_fence: bool                        # True if found inside a fenced code block
      fence_end_line: int | None = None     # that fence's closing delimiter line (set only when in_fence)
      fence_prefix: str | None = None       # that fence's leading prefix string, verbatim (set only when in_fence)
  ```
- Rework `_line_mentions(line) -> list[tuple[int, int, bool, list[tuple[str, str | None]], str]]`: for each `_AT_MENTION_RE`/`_BACKTICK_MENTION_RE` match, `raw = m.group(1)`, `trimmed = raw.rstrip(_TRAILING_PUNCT)`, `suffix = raw[len(trimmed):]`, `candidates = _split_candidates(trimmed)`; keep the match only if `candidates` is non-empty. Span is `m.start()`/`m.end()` (the whole match, including `@`/backticks).
- Rework `find_mentions` to **not** skip fenced lines when scanning — it still toggles fence state via `_FENCE_RE`, but now collects matches found while a fence is open into a `fence_pending` list; when that fence's closing delimiter is hit, stamps every pending mention with `fence_end_line` (the closing line's number) and `fence_prefix` (captured when that fence opened), then flushes them into the result list. An unterminated trailing fence's pending mentions are simply dropped (no closing line to anchor them to).
- Leave `extract_candidate_paths` as-is (unused by any real caller today; out of scope).

### `scripts/°base/ai/hooks/°reffiles_lib/commit.py`

- Rework `resolve_existing` to walk each mention's `candidates` in order and stop at the first that resolves to a real file, producing a `ResolvedMention` with the **concrete, chosen** `path`/`fragment` (no longer a list):
  ```python
  @dataclass
  class ResolvedMention:
      line: int
      start: int
      end: int
      at: bool
      suffix: str
      in_fence: bool
      fence_end_line: int | None
      fence_prefix: str | None
      path: str
      fragment: str | None
      abspath: Path
      relpath: str

  def resolve_existing(mentions: list[Mention], subproject: Path) -> list[ResolvedMention]:
      resolved: list[ResolvedMention] = []
      for mention in mentions:
          for path, fragment in mention.candidates:
              abspath = (subproject / path).resolve()
              if not abspath.is_file():
                  continue
              try:
                  relpath = str(abspath.relative_to(Path.cwd()))
              except ValueError:
                  continue  # outside the repo -- try the next candidate
              resolved.append(ResolvedMention(
                  line=mention.line, start=mention.start, end=mention.end, at=mention.at,
                  suffix=mention.suffix, in_fence=mention.in_fence,
                  fence_end_line=mention.fence_end_line, fence_prefix=mention.fence_prefix,
                  path=path, fragment=fragment, abspath=abspath, relpath=relpath,
              ))
              break
      return resolved
  ```
  (`ResolvedMention` no longer subclasses `Mention` via inherited `path`/`fragment` fields, since those are now single resolved values rather than a list — it's defined standalone with the fields above.)
- Add `_mention_link(mention: ResolvedMention, log_path: Path) -> str` — the pure "what does this mention's markdown look like" builder, used by both rendering paths:
  ```python
  def _mention_link(mention: ResolvedMention, log_path: Path) -> str:
      target = _link_target(mention.abspath, log_path)
      prefix = "@" if mention.at else ""
      text = f"[{prefix}`{mention.path}`]({target})"
      if mention.fragment is not None:
          text += f"[{mention.fragment}]({target}{anchor_target(mention.fragment)})"
      return text
  ```
- Replace `build_summary_block` with `_fence_summary_lines(mentions: list[ResolvedMention], log_path: Path, width: int) -> list[str]`, reusing today's single-vs-multiple template (one-liner `> _Mentioned file at line \`NNN\`:_ [...]` for exactly one; `<details><summary>` block for more than one), `[...]` built via `_mention_link`. Returns bare (unprefixed) lines — the fence's `fence_prefix` is applied by the caller, keeping this function about content, not placement.
- Replace `process_referenced_files`:
  1. `mentions = find_mentions(content)`; `resolved = resolve_existing(mentions, subproject)`; if empty, return `(content, [])` unchanged.
  2. Split into `inline = [m for m in resolved if not m.in_fence]` and `fenced = [m for m in resolved if m.in_fence]`.
  3. `lines = content.split("\n")`. For `inline`, group by `line`; for each line, splice mentions **rightmost `start` first** (keeps earlier offsets on that line valid): `line[:m.start] + _mention_link(m, log_path) + m.suffix + line[m.end:]`.
  4. `width = len(str(len(lines)))` (computed once, from the original line count, reused by every fenced summary block for consistent padding).
  5. For `fenced`, group by `(fence_end_line, fence_prefix)`. For each group, build the template body via `_fence_summary_lines`, prefix every line (including its blank separator lines) with that group's `fence_prefix` verbatim, and insert via `lines[fence_end_line:fence_end_line] = new_lines`. Process fence groups **in descending order of `fence_end_line`** so earlier insertions don't shift the target index of a group still to be processed.
  6. Return `("\n".join(lines), resolved)`.
- `stage_and_commit_mentions` unchanged.

### `scripts/°base/ai/hooks/°reffiles_lib/__init__.py`

- Drop `build_summary_block` from the re-exports.
- Add `anchor_target` to the re-exports (pure helper, worth testing directly).

### Tests: `scripts/°base/tests/test_ai_hooks_base_routing.py`

- **`ReffilesLibMentionsTests`**: update existing assertions to the new `Mention`/candidates shape. Add:
  - `_split_candidates`: whole-string-first ordering; rightmost-delimiter-first fallback order; a non-numeric colon suffix never becomes a split point; the `foo.ext:1234#245` and `foo.ext:1234#245:123` examples from the plan, asserting the exact candidate list and order.
  - hash line fragment / hash line-range fragment / colon line fragment / colon line-range fragment / heading anchor fragment, each as the *chosen* resolved fragment once combined with `resolve_existing` in a fixture where only one candidate's path exists on disk.
  - `find_mentions` now finds mentions inside a fenced block (reversing "skipped entirely") and stamps `fence_end_line`/`fence_prefix` correctly; non-fenced mentions have `in_fence=False`.
  - a fence indented under a list item asserts `fence_prefix` equals that indentation; a fence nested inside a blockquote asserts `fence_prefix` captures the `>`/`> >` prefix.
  - an unterminated fence contributes no mentions.
  - `anchor_target` unit tests covering every row of the fragment table above.
- **`ReffilesLibCommitTests`**: replace the `build_summary_block` tests with:
  - `resolve_existing` picks the most-conservative candidate that exists: a fixture with a literal file named `foo.ext:1234` (no such file needed for the `#245`-fragment interpretation) proves the "try whole string first" behavior; a fixture where only the split interpretation's path exists proves the fallback.
  - `_mention_link` for a plain mention, a hash-anchor mention, and a colon/hash line-range mention — correct two-link form and GitHub-style target anchors.
  - `process_referenced_files`: a non-fenced mention is rewritten in place; trailing punctuation ends up after the link; two mentions on the same line both rewrite correctly (proves reverse-order splicing doesn't corrupt offsets); no resolved mentions → content unchanged.
  - `process_referenced_files`: a mention inside a fenced block is not rewritten in place, but a summary block appears immediately after that fence's closing delimiter, lines prefixed by the fence's indent; same again nested in a blockquote (stacked `>` prefix); two separate fenced blocks each get their own trailing summary in the right place.
- **End-to-end tests**: update `test_referenced_file_mention_appends_summary_block_and_links` and `test_ask_user_question_answer_mention_gets_summary_and_commit` to assert the inline link form appears directly in `query.md`'s entry text. Update `test_referenced_file_mention_inside_fenced_code_block_is_not_committed` — the fenced text itself must still be untouched, but now assert a trailing summary block *does* appear right after that fence, linking to the file, and that the file still gets staged/committed.

## Verification

- `python3 -m pytest scripts/°base/tests/test_ai_hooks_base_routing.py -q`
- Manual: submit a prompt like `` Talking about `docs/README.md#some-title` or @query.md#top `` (both files exist); confirm both mentions are rewritten in place as two-link markdown with correct relative targets.
- Manual: submit `@docs/README.md:345` and `` `docs/README.md:346-400` ``; confirm `#L345` / `#L346-L400` GitHub-style target anchors while the visible fragment label stays as typed.
- Manual: submit a prompt with a fenced ` ``` ` block containing an example `@path/to/file#L10` mention, where that file exists; confirm the fenced text is untouched, but a summary block linking to it appears right after the closing fence.
- Manual: same, but the fenced block is indented under a `-` list item, and separately nested inside a `> ` blockquote; confirm the inserted summary lines are prefixed to match (list indent, stacked `>` for the blockquote case).
