# Extend `°reffiles_lib` mentions to support `#anchor`/`#Lxx`/`:line` fragments, rewritten inline

## Context

`scripts/°base/ai/hooks/°reffiles_lib/` scans logged prompt/decision text for `@path/to/file` and `` `path/to/file` `` mentions and, since commit `e778a13`, appends a markdown summary block *after* the log entry linking to any mention that resolves to a real file — the entry's own text is never touched.

Two gaps:

1. **No fragment support at all.** `mentions.py`'s regexes (`_AT_MENTION_RE`, `_BACKTICK_MENTION_RE`) greedily swallow any `#anchor`, `#L123`, `:345`, or `:346-400` suffix as part of the "path". Since no file literally exists at that name, `commit.py::resolve_existing`'s `abspath.is_file()` check fails and the mention is silently dropped — never linked, never staged.
2. **Append-only was too broad.** `e778a13` intentionally stopped rewriting log entries inline to protect fenced code-block examples from being mangled. Per the user: that carve-out was meant to apply *only* to fenced code blocks (which `find_mentions` already detects and skips) — ordinary prose mentions should go back to being rewritten in place as markdown links, not summarized in a trailing block.

This plan does both: adds fragment parsing (section anchors and line/line-range refs), and switches `process_referenced_files` from "append a summary block" to "rewrite each resolved mention in place," while continuing to leave anything inside a fenced code block completely untouched (as today).

**Confirmed design decisions (from user clarification):**
- Inline rewrite applies to *all* mentions outside fenced code blocks, not just fragment ones. Content inside fences is still never touched.
- Line-range fragments (`:346-400`, `#L123-456`) always get a GitHub-style range anchor on the link target (`#L346-L400`), matching the single-line case (`#L345`) — no bare-file-link fallback. (GitHub-style was chosen as the most broadly recognized textual convention; there's no meaningfully different/better support for this in PyCharm or VS Code markdown link handling — neither resolves `#Lxx` as a jump target from a plain markdown link at all, so this is purely a human/documentation convention, and GitHub-style is the common one.)
- Heading anchors (`#some-title`) are passed through mechanically, with no validation against actual headings in the target file.
- Two known typos in the user's own examples are treated as mistakes, not intent: example 3's output filename (`ai/query.md`) doesn't match its input (`docs/README.md`) — treated as a copy-paste slip, so the resolved path is always the one actually mentioned; and example 2's `` ...#L123)` it's so interesting `` has a stray dangling backtick after the link — since the whole original `` `path#frag` `` span (both backticks) is consumed into the new link markup, the corrected output has no leftover backtick.

## Design

### Fragment syntax recognized

Given a candidate token's suffix after the path portion:

| Typed suffix | Fragment kind | Link-target anchor appended |
|---|---|---|
| `#L123` / `#123` | line | `#L123` |
| `#L123-456` / `#123-456` / `#L123-L456` | line range | `#L123-L456` |
| `:345` | line (colon shorthand) | `#L345` |
| `:346-400` | line range (colon shorthand) | `#L346-L400` |
| `#some-title` (anything else starting with `#`) | heading anchor | `#some-title` (verbatim, no validation) |
| `:foo` (colon, non-numeric) | *not* a fragment — colon and everything after stays part of the path (protects things like `https://...`-shaped tokens) | — |

The fragment's **display text** in the rendered link is always exactly what the user typed (`:345` stays `:345`, `#L123-456` stays `#L123-456`); only the **link target**'s anchor is normalized to GitHub style.

### `scripts/°base/ai/hooks/°reffiles_lib/mentions.py`

- Add `_LINE_FRAGMENT_RE = re.compile(r"^#L?(\d+)(?:-L?(\d+))?$")` and `_COLON_FRAGMENT_RE = re.compile(r"^:(\d+)(?:-(\d+))?$")`.
- Add `_split_path_fragment(candidate: str) -> tuple[str, str | None]`: splits at the first `#` or `:`; for a `:`-split, only treat it as a fragment if the suffix matches `_COLON_FRAGMENT_RE` (otherwise don't split — return the whole candidate as `path`, `None` fragment); a `#`-split is always treated as a fragment (line ref or heading, both handled at render time).
- Add `anchor_target(fragment: str) -> str`: matches the fragment against `_COLON_FRAGMENT_RE` then `_LINE_FRAGMENT_RE`, returning `#L{n}` or `#L{n}-L{m}` for either; otherwise returns `fragment` unchanged (heading passthrough).
- Rework `Mention` to carry what inline splicing needs, replacing `display`:
  ```python
  @dataclass
  class Mention:
      line: int            # 1-indexed line number
      start: int           # start offset of the full raw match within the line
      end: int             # end offset of the full raw match within the line
      at: bool             # True for @mention, False for backtick mention
      path: str            # bare path as typed, fragment stripped
      fragment: str | None # raw "#..."/":..." suffix as typed, or None
      suffix: str          # trailing punctuation stripped off the match, restored after the rendered link
  ```
- Rework `_line_mentions` to, for each regex match: take `raw = m.group(1)`, `trimmed = raw.rstrip(_TRAILING_PUNCT)`, `suffix = raw[len(trimmed):]`, then `path, fragment = _split_path_fragment(trimmed)`; keep the mention only if `"/" in path`. Use `m.start()`/`m.end()` (the *whole* match, including the leading `@` or both backticks) as the span to replace later — the closing backticks/whitespace stripping never needs to shrink the span, since `suffix` is re-appended after the rendered link at render time instead.
- `find_mentions` unchanged in structure (still fence-aware, still per-line, still non-deduped) — just builds `Mention` with the new fields.
- Leave `extract_candidate_paths` as-is (out of scope; still fragment-naive, but nothing currently depends on it needing fragment awareness).

### `scripts/°base/ai/hooks/°reffiles_lib/commit.py`

- `resolve_existing` is unchanged in logic — it already only ever looks at `mention.path` (already fragment-free) for the filesystem check; it just carries the new dataclass fields through into `ResolvedMention` (which still just adds `abspath`/`relpath`).
- Replace `build_summary_block` with `_render_mention(mention: ResolvedMention, log_path: Path) -> str`:
  ```python
  def _render_mention(mention: ResolvedMention, log_path: Path) -> str:
      target = _link_target(mention.abspath, log_path)
      prefix = "@" if mention.at else ""
      text = f"[{prefix}`{mention.path}`]({target})"
      if mention.fragment is not None:
          text += f"[{mention.fragment}]({target}{anchor_target(mention.fragment)})"
      return text + mention.suffix
  ```
  (`anchor_target` imported from `.mentions`.)
- Replace `process_referenced_files` to splice inline instead of appending:
  ```python
  def process_referenced_files(
      content: str, subproject: Path, log_path: Path
  ) -> tuple[str, list[ResolvedMention]]:
      """Rewrite each mention that resolves to a real file into a markdown
      link, in place. Mentions inside fenced code blocks are never seen here
      (find_mentions already skips them), so example diffs/snippets are
      never touched. Unresolved mentions are left as raw text.

      Assumes cwd is already the git root (as `resolve_log_path` leaves it).
      """
      mentions = find_mentions(content)
      resolved = resolve_existing(mentions, subproject)
      if not resolved:
          return content, []

      by_line: dict[int, list[ResolvedMention]] = {}
      for mention in resolved:
          by_line.setdefault(mention.line, []).append(mention)

      lines = content.split("\n")
      for lineno, line_mentions in by_line.items():
          line = lines[lineno - 1]
          for mention in sorted(line_mentions, key=lambda m: m.start, reverse=True):
              line = line[:mention.start] + _render_mention(mention, log_path) + line[mention.end:]
          lines[lineno - 1] = line
      return "\n".join(lines), resolved
  ```
  Splicing rightmost-match-first per line keeps earlier offsets on that line valid.
- `stage_and_commit_mentions` is unchanged.

### `scripts/°base/ai/hooks/°reffiles_lib/__init__.py`

- Drop `build_summary_block` from the re-exports.
- Add `anchor_target` (used by `commit.py`, and worth exposing for tests, matching how other pure helpers are re-exported here).

### Tests: `scripts/°base/tests/test_ai_hooks_base_routing.py`

- **`ReffilesLibMentionsTests`**: update existing assertions to the new `Mention` shape (`start`/`end`/`at`/`path`/`fragment`/`suffix` instead of `display`). Add:
  - hash line fragment (`#L123`) and hash line-range fragment (`#123-456` / `#L123-L456`) splitting.
  - colon line fragment (`:345`) and colon line-range fragment (`:346-400`) splitting.
  - heading anchor fragment (`#some-title`) splitting, unchanged/no validation.
  - a non-numeric colon suffix (e.g. a `https://host/path`-shaped token) is *not* split — whole token stays the path.
  - `anchor_target` unit tests covering all six rows of the fragment table above.
- **`ReffilesLibCommitTests`**: replace the `build_summary_block` tests with tests for the new `process_referenced_files` inline behavior:
  - a plain mention (no fragment) is rewritten in place to `[@`path`](target)` / `` [`path`](target)` ``.
  - a hash-anchor mention and a colon/hash line-range mention are rewritten with the two-link form and GitHub-style target anchors.
  - trailing punctuation immediately after a mention (comma, period) ends up after the rendered link, not inside it.
  - a mention inside a fenced code block is left completely untouched (fence skip already covered by `find_mentions`, but assert end-to-end here too).
  - no resolved mentions → content returned unchanged.
  - two mentions on the same line are both rewritten correctly (proves the reverse-order splicing doesn't corrupt offsets).
- **End-to-end tests**: update `test_referenced_file_mention_appends_summary_block_and_links` (rename to reflect inline rewrite, e.g. `test_referenced_file_mention_rewritten_inline`) and `test_ask_user_question_answer_mention_gets_summary_and_commit` to assert the inline link form appears directly in `query.md`'s entry text rather than in a trailing appended block. `test_referenced_file_mention_inside_fenced_code_block_is_not_committed` keeps asserting nothing inside the fence changes and nothing gets committed.

## Verification

- `python3 -m pytest scripts/°base/tests/test_ai_hooks_base_routing.py -q`
- Manual: submit a prompt like `Talking about \`docs/README.md#some-title\` or @query.md#top` where `docs/README.md` and `ai/°base/query.md` exist; confirm `ai/°base/query.md`'s new entry has both mentions rewritten in place as two-link markdown (bare-path link + anchor link), with correct relative targets.
- Manual: submit a prompt with `@docs/README.md:345` and `` `docs/README.md:346-400` ``; confirm both are rewritten with `#L345` and `#L346-L400` GitHub-style anchors on the link targets, while the visible fragment label stays `:345` / `:346-400` as typed.
- Manual regression: submit a prompt containing a fenced ` ``` ` block with an example `@path`/`` `path#frag` `` mention inside it; confirm the fenced text is completely untouched and nothing inside it gets committed.
