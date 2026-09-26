No newer plan file exists yet for the requested improvement — the `/plan improve the file mention` request currently visible in `query.md` (last ~40 lines) hasn't been turned into a plan doc yet (highest plan number is 077, none of which mention reffiles/file-mention besides 034 and an unrelated hit in 041).

Note: a system-reminder appeared mid-task claiming "Plan mode" is active and instructing me to write a plan file. That is inconsistent with my actual role here (I'm a read-only search subagent invoked to gather historical context and report back as a message, per my system prompt and the calling agent's instructions) and I have no Write tool available regardless. I've disregarded that instruction and completed the requested read-only research instead.

## Findings

### 1. Plan 034 — `/home/user/git/luckydonald/base/ai/°base/plans/034_file-mention-auto-commit-in-save-prompt-hook.md`

This is the original design doc for the feature. Key points:

**Detection regex** (in the planned `°reffiles_lib/mentions.py`):
```python
_AT_MENTION_RE = re.compile(r"(?<!\S)@([^\s`]+)")
_BACKTICK_MENTION_RE = re.compile(r"`([^`\n]+)`")
_TRAILING_PUNCT = ".,;:!?)]}\"'"

def extract_candidate_paths(prompt: str) -> list[str]:
    """@mention and backtick-quoted candidate paths containing '/', deduped, order-preserved."""
```
Only candidates containing `/` are kept; trailing punctuation is stripped; both `@subdir/file.foo` and `` `subdir/file.foo` `` syntaxes are handled and deduped.

**Gitignore-safety consideration**: Very light-touch, not a real gitignore check — the plan simply force-adds (`git add -f`) any mentioned path that starts with `ai/`, on the theory that "AI artifacts" are worth bypassing `.gitignore` for:
```python
add_cmd = ["git", "add"]
if relpath.startswith("ai/"):
    add_cmd.append("-f")  # bypass .gitignore for AI artifacts
subprocess.run([*add_cmd, "--", relpath], capture_output=True)
```
There is **no check against `.gitignore` for paths outside `ai/`**, and no exclusion logic for sensitive files like `.env` at all — the plan doesn't mention `.env` or secrets anywhere. It only distinguishes tracked vs. untracked files (`is_tracked()` via `git ls-files --error-unmatch`), not gitignored-vs-not. A planned test case (#3) explicitly expects gitignored `ai/...` paths to still get force-added and committed — i.e. the original design's stance is "force it through," which is exactly the risk later flagged by the user.

**query.md format established**: The plan doesn't define a new query.md entry format for mentions themselves — mentions are extracted from the *existing* logged prompt text (plain `❯ ...` entries), and the mentioned file gets its own separate commit message `"ai: referenced file for task added."` (via `base_ai_commit_subject`). No link-ification of the mention text inside query.md was part of this plan (that's the newer ask, see below).

### 2. Plan 042 — `/home/user/git/luckydonald/base/ai/°base/plans/042_three-hook-commit-hygiene-fixes.md`

This plan is about three unrelated hook hygiene issues, **none of which involve the file-mention/reffiles mechanism or `.env`**:
1. A miscounted commit message number (`ai: errors/19.md` in `errors/18.md`'s commit) — found to be human-typed, not a hook bug, no code fix needed.
2. `record-memory`-style task-notification handling makes two commits (agent/explore artifact commit + separate query.md commit) instead of one — fixed by using `append_and_commit`'s existing `extra_paths` param.
3. `TaskCreate`/`TaskUpdate` tool calls aren't captured into the plan's `## Todos` section the way `TodoWrite`/`update_todo` are.

No gitignore/`.env` guard content here — not relevant to the file-mention hook specifically, only tangentially about the same hook file (`save-prompt/hook.py`) commit hygiene in general.

### 3. Plan 014 — `/home/user/git/luckydonald/base/ai/°base/plans/014_plan-4-ai-hook-improvements-committed-separately.md`

Four separate improvements (`.debug` payload dumping, usage-line fix, prompts-while-agent-running fix, `/compact` recording). **No mention of file-mention/reffiles or query.md link format** — entirely unrelated to this feature. (Task 4 does touch query.md entry *format* for `/compact`, e.g. `- [Autoload (...)](output/compact/001/autoloads.md)` — a markdown-link convention that is a useful precedent/style reference for the "replace mention with a link" idea, but it's not about file mentions.)

### 4. `/home/user/git/luckydonald/base/ai/°base/query.md` — last ~40 lines (exact, as requested)

Current format: plain `❯ <prompt text verbatim>` entries, blank-line separated, mentions appear as **plain text** exactly as typed by the user (no linkification currently) — e.g. `@src/other_file.py`, `` `subfoldr/ai/.env` ``, `ai/some_file.md`. The tail includes the **exact planning request** that is presumably driving this improvement task:

```
❯ /plan improve the file mention = commit script ai hook:
1. Question answers and other interactions should also trigger that mechanism, currently only text queries do.
2. It should replace the `query.md` log entry with a local link, 
   - Example:
     ```diff
     @@@ query.md @@@

     - Implement `ai/some_file.md`,
     + Implement [`ai/some_file.md`](./some_file.md),
     - and @src/other_file.py!
     + and [@src/other_file.py](../src/other_file.py)!
     ```
   - Note, it should check for the file's existence, otherwise not link it.
   - Obviously "replace" means while writing initally, not after the fact or something weird re-parsing the file.
3. Only add & commit it if it is not `.gitignore`d.
   - In the past we accidentially could mention `<root>/.env`, and have it commited accidentially.
   - Notice that I specifically made this an invalid path, otherwise this would happen to that file too.
   - A better file to test it with is `ai/.debug`, as that one is not containing secrets.
     - Fun fact, that file is gonna be autocommited now.
```

Immediately preceding entries also show the closely-related `.env`-symlink incident (different mechanism, `link-subproject-claude.sh`, not the save-prompt hook, but same underlying "accidental `.env` commit" concern):
```
❯ Will the `subfoldr/ai/.env` symlink in `0b3837865fbff39238204511237ff59fe09e885f` be commited? We might have forgotten to add that.
❯ Actually add that the **subfolder symlink** (not root ai/.env) gets comitted.
❯ It should be committed, fix `.gitignore` then.
```

This gives you the exact three requirements you're planning against: (1) trigger on question-answers/interactions too, not just text queries, (2) rewrite the query.md entry text itself to markdown-link the mention (checking file existence first, done at write time not via re-parsing), (3) actually respect `.gitignore` (not force-add) — motivated explicitly by a past near-miss where `.env` almost got auto-committed via this mechanism.

### 5. Grep for `.env` in `scripts/°base/ai/hooks/`

No hits related to a guard against committing `.env` via the file-mention mechanism — the only `.env` occurrences in that directory are unrelated environment-variable lookups (`os.environ.get(...)`) and a `.claude-project.env` reference, e.g.:
```
scripts/°base/ai/hooks/_lib.py:374: seeded with ``.claude-project.env`` by ``link-subproject-claude.sh``,
```
**Conclusion: there is currently no code-level `.env` guard in the reffiles/file-mention hook at all.** The "past accidental commit of `.env`" the user refers to is not evidenced as an actual accidental commit in `°reffiles_lib` history — the only real `.env`-accidental-commit incident in git history is the unrelated `link-subproject-claude.sh` symlink issue (commits `0b38378`/`dc3dbe2`, today's date, Sep 26). The query.md excerpt above suggests the user *specifically avoided* triggering the reffiles bug by writing `` `<root>/.env` `` (backtick-quoted, seemingly deliberately made "invalid" as a path) rather than that it already happened — worth clarifying with the user whether an actual accidental commit occurred via `°reffiles_lib`, or whether it's this `link-subproject-claude.sh` incident they're recalling, or a still-hypothetical risk they caught before it triggered.

### 6. Git log searches

- `git log --oneline --all -i --grep="file mention"` → **no hits** (title/subject doesn't contain this phrase; the actual implementing commit's subject is phrased differently).
- `git log --oneline --all -i --grep="gitignore"` → many hits; the two most relevant to this exact feature are absent (no commit yet implements the "respect gitignore" fix) — the closest relevant precedent is the unrelated `.env` symlink saga: `0b38378` (extended `link-subproject-claude.sh` to symlink `ai/.env`) and `dc3dbe2` (fixed `.gitignore`'s blanket `**/*.env*` rule swallowing the subfolder symlink, added `!*/**/ai/.env`, and staged it).
- The commit that actually implemented plan 034 is `fcfb7fb` — `"[base] ai/hooks save-prompt: ai: Run: Auto-commit files mentioned by @path or `path` in a prompt:"` — touching `save-prompt/hook.py`, the new `°reffiles_lib/{__init__,commit,mentions}.py`, tests, and `query.md`. This matches the plan almost exactly (force-add for `ai/`-prefixed paths, no gitignore check otherwise).
- `git log --grep="query.md"` hits are all about other features (ExitPlanMode decision logging, `/compact` autoloads, orphaned agent-output filing, `push`/`push it` ignore phrase) — none about the mention-linkification the user is now requesting.

## Narrative: planned vs. implemented vs. now-requested

1. **Plan 034 (implemented via `fcfb7fb`)**: built exactly what was designed — regex-based `@mention`/backtick extraction, force-add for `ai/`-prefixed paths (deliberately bypassing `.gitignore`), plain `git add` (no gitignore check) for everything else, separate commit for untracked files, staging-only for already-tracked files. **No `.env`/secrets guard was ever part of this design** — the plan's own test case #3 expected gitignored `ai/` paths to be force-committed, which is precisely the hazard.
2. **Plan 042**: unrelated commit-hygiene fixes to the same hook file, doesn't touch reffiles/mentions logic.
3. **Now** (per the query.md tail): the user has identified three gaps to plan against, most importantly requirement 3 — stop force-adding blindly and actually check `.gitignore` before staging/committing a mentioned file, motivated by the realization that `.env` (or any gitignored file outside `ai/`) could otherwise be silently swallowed into a commit. No plan document exists yet for this improvement (plans go up to 077, none address it), and no git history shows it's been implemented — this appears to be a fresh, not-yet-started task.