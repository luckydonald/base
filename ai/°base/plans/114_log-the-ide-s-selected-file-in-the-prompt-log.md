# Log the IDE's selected file in the prompt log

**Commit style:** Skill `/commit-with-lplp-style` is active — auto-commit following it for this implementation.

Todo: `todo:0b3a981b-3de7-4f89-aa1d-32471f137111`, project `base`, commit scope `[base]`.

## Context

`ai/°base/query.md` records every prompt, but not which file or lines the user had selected in the IDE when sending it.
That context is often what makes a terse prompt like "fix this" understandable.
The IDE integrations inject it into the submitted prompt text, so `save-prompt/hook.py` currently either logs the raw tags or never sees them.

## Findings

- The `UserPromptSubmit` payload has no selection field: only `session_id`, `transcript_path`, `cwd`, `prompt`, `permission_mode` and similar.
- No local transcript, debug dump or `query.md` contains an IDE tag sample, so the real format is unverified here.
- The hook already has `_xmlish_tag_text` and `_context_field_text` (`scripts/°base/ai/hooks/save-prompt/hook.py:471`) and a `PromptLogEntry` with `extra_paths`.
- Tests use `init_repo` and `run_hook` from `scripts/°base/tests/test_ai_hooks_base_routing.py`, as in `test_save_prompt_skip_commands.py`.

## Decision

Cover Claude and Codex.
Parse the formats those tools are known to use, and keep parsing tolerant, because a failed parse must never lose or alter the user's prompt.

- Claude: `<ide_opened_file>The user opened the file /abs/path in the IDE. …</ide_opened_file>` and `<ide_selection>The user selected the lines A to B from /abs/path:\n…</ide_selection>`.
- Codex: a `# Context from my IDE setup:` block with `## Active file: path` and `## Open tabs:`, followed by `## My request for Codex:` and the real prompt.

## Changes

1. `scripts/°base/ai/hooks/save-prompt/hook.py`
   - Add `_extract_ide_context(prompt, log_path) -> tuple[str, str]` returning the prompt without the IDE blocks and a rendered link line, or `(prompt, "")` when nothing matches.
   - Links are relative to `log_path.parent`, falling back to the absolute path when the file is outside the repo, and `#L190` or `#L190-200` for a line range.
   - Link label: `⧉ File \`todo.md\``, `⧉ File \`todo.md\`: 1 line selected`, `⧉ File \`todo.md\`: 10 lines selected`.
   - The title-attribute variants from the todo are not used, since GitHub and GitLab do not render `{title=…}` on Markdown links.
   - Open tabs are not logged, only the active file or the selection.
   - Call it for `claude` and `codex` before `PromptLogEntry` is built, and append the link line as a `> • …` quote line under the prompt.
   - Keep the selected text itself out of the log: the link is enough.
2. `ai/°base/query.md` rendering stays otherwise unchanged, so existing entries are not rewritten.
3. Debug aid: `dump_debug_payload` already runs for each prompt, so real samples will appear under `ai/°base/output/debug/` for later verification.
4. Tests: new `scripts/°base/tests/test_save_prompt_ide_context.py` covering
   - Claude selection of one line and of several lines,
   - Claude opened-file only,
   - Codex active file plus request,
   - a prompt without tags, unchanged,
   - a malformed tag, logged unchanged.
5. `ai/°base/AGENTS.md`: one sentence under the `save-prompt/hook.py` row that the IDE selection is logged as a link line.

## Verification

- `uv run --project scripts/°base python -m unittest discover -s scripts/°base/tests -v` stays green.
- Feed the hook a hand-built Claude and Codex payload from the scratchpad and read the resulting `query.md`.
- After the next IDE-sent prompt, compare the real debug payload against the assumed formats, and fix the parser if they differ.

## Open point

The formats above are from knowledge of the tools, not from a local sample, so the first real IDE prompt is the real test.
