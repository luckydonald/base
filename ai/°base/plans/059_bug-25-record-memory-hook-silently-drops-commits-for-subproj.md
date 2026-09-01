# Bug 25 — `record-memory` hook silently drops commits for subproject-nested Claude sessions

## Context

In the `sticker_tag_bot` Claude Code session (`luckydonald/docker-tg-bot`, a subdirectory of the `DockerTgBot` monorepo), the assistant wrote and edited memory files through the normal auto-memory flow, but no corresponding commit ever landed in `sticker_tag_bot/ai/memory/`. The user copied that session's transcript into `ai/°base/errors/25.claude1.txt`, then turned on hook debug tracing and reproduced the same failure in a second session, captured as `ai/°base/errors/25.claude2.txt` (transcript) and, still only in the `sticker_tag_bot` working tree (not yet in this repo), as raw hook payloads under `sticker_tag_bot/ai/output/debug/20260901-110828_704139-save-prompt.json` through `...-110902_037992-SubagentStop.json`. This plan documents the root cause found from that evidence, fixes the underlying hook bug, preserves the raw debug evidence in this repo, and updates this repo's own memory index per a related request that arrived mid-session — enabling the `commit-with-lplp-style` skill for the whole implementation, per the user's instruction, so the resulting commits stay clean (stray `ai:` auto-commits folded in, not left standalone).

## Root cause

Claude Code's own auto-memory feature scopes the per-project memory directory by the **git repository root**, not by the directory Claude was actually launched from. Since `sticker_tag_bot` is a subdirectory inside the `DockerTgBot` git repo (not a repo of its own), every memory `Write`/`Edit` in that session landed under the *git-root*-encoded directory, `~/.claude/projects/-Users-user-Documents-programming-Python-DockerTgBot/memory/*.md` — confirmed several ways:

- Both `record-memory.json` debug dumps (`20260901-110843_540969`, `20260901-110853_512295`) show `tool_input.file_path` under the git-root-encoded path while `"cwd"` in the same payload is `/Users/user/Documents/programming/Python/DockerTgBot/sticker_tag_bot`.
- `2026-07-20-history-master-replay-guards.md`/`MEMORY.md` only exist (with today's mtime) under the git-root-encoded `~/.claude/projects/-Users-user-Documents-programming-Python-DockerTgBot/memory/`; the subproject-encoded `-DockerTgBot-sticker-tag-bot` project directory has no `memory/` subfolder at all, and never has.
- `~/.claude.json`'s `"projects"` registry has exactly one entry for this repo family — `/Users/user/Documents/programming/Python/DockerTgBot` — and no separate entry for `.../DockerTgBot/sticker_tag_bot`, even though that subdirectory has its own registered session-transcript folder. Checked across every other registered project in this environment too: none of them has a second, subdirectory-scoped registry entry either, so this looks like a general Claude Code behavior, not something specific to this one repo.

`scripts/°base/ai/hooks/record-memory/hook.py`'s `_memory_dirs()` computes its *source* watch directory differently: `_encoded_project_dir(subproject) / "memory"`, where `subproject = _subproject_root()` reads `CLAUDE_PROJECT_DIR` — the literal launch directory, `sticker_tag_bot`, confirmed by the `"cwd"` field in every debug payload. That encodes to `~/.claude/projects/-Users-user-Documents-programming-Python-DockerTgBot-sticker-tag-bot/memory`, a directory that has never existed. In `main()` (`record-memory/hook.py:406-417`), the `PostToolUse` handler for `Write`/`Edit` does:

```python
src_file = Path(raw).resolve()
try:
    rel = src_file.relative_to(src_dir.resolve())
except (OSError, ValueError):
    return 0
```

Since `src_file` sits under the git-root-encoded directory and `src_dir` sits under the subproject-encoded directory, `relative_to()` always raises `ValueError`. The hook catches it and returns `0` — a silent no-op: no hardlink into `sticker_tag_bot/ai/memory/`, no `git commit`, and no error surfaced anywhere in the transcript or hook output. This reproduced identically in both sessions, and is not specific to `sticker_tag_bot` — it affects any Claude Code session launched from a subdirectory of a larger repo rather than the repo root.

Two more supporting details from the same debug payloads:

- `save-plan.json` at the same two timestamps (`110853`, `110857`) carries byte-identical payloads to the paired `record-memory.json` files — both hooks receive the same `PostToolUse` event; `save-plan`'s own Write/ExitPlanMode/Stop-only logic (per `ai/°base/AGENTS.md`) presumably no-ops on the `Edit` tool the same way and is unrelated to this bug.
- `SubagentStop.json`'s `last_assistant_message: "commit this"` in the second session shows a delegated agent noticing the missing commit and trying to force one manually, after the automatic hook path silently failed.

## Fix — `scripts/°base/ai/hooks/record-memory/hook.py`

Rather than assume the source directory is *always* the git-root encoding (which could regress a genuine future case where Claude Code does register a subdirectory separately), watch **both** encodings — the launch directory (`CLAUDE_PROJECT_DIR`, today's only candidate) and the git repository root (the one actually confirmed above) — and treat either one as a valid source. The destination stays subproject-scoped exactly as it is today (`sticker_tag_bot/ai/memory/`, distinct from `DockerTgBot/ai/memory/`); only the *source* lookup needs the second candidate.

Split `_memory_dirs()` into two helpers:

```python
def _memory_src_dirs(subproject: Path, git_root: Path) -> list[Path]:
    """Directories Claude Code's own auto-memory might have written into for
    this session. Its `~/.claude.json` "projects" registry has no separate
    entry for a subdirectory of an already-registered repo (confirmed: no
    `~/.claude/projects/...-sticker-tag-bot/memory/` ever existed for the
    `sticker_tag_bot` subproject inside `DockerTgBot`, only the git-root-
    encoded one did — see ai/°base/errors/25.*), so a session launched
    inside a monorepo subproject reads/writes memory under the *repo
    root*'s encoded project dir. List the repo-root encoding first (the
    confirmed case) and the launch-dir encoding second, so either being
    populated still works, and the two collapse to one entry when
    subproject == git_root (the common, non-monorepo case)."""
    dirs: list[Path] = []
    for root in (git_root, subproject):
        d = _encoded_project_dir(root) / "memory"
        if d not in dirs:
            dirs.append(d)
    return dirs


def _memory_dst_dir(subproject: Path) -> Path:
    rel = "ai/°base/memory" if _is_inside_base_repo(subproject) else "ai/memory"
    return subproject / rel
```

Then thread `src_dirs: list[Path]` through `main()` in place of the old single `src_dir`:

- **`main()`**: compute `git_root = _git_root()` once up front (it already runs this check before doing anything else), pass it into `_memory_src_dirs(subproject, git_root)`.
- **`PostToolUse` / Bash `rm` branch**: try each directory in `src_dirs` when matching `target.parent`, instead of only `resolved_src_dir`.
- **`PostToolUse` / `Write`\|`Edit` branch**: try `src_file.relative_to(candidate.resolve())` against each candidate in order, using the first one that doesn't raise.
- **`SessionStart` branch**: call `_sync_all(candidate, dst_dir, dst_dir_rel)` once per directory in `src_dirs` that exists on disk, accumulating `changed` before the single `_commit(...)` call. `_sync_all`'s dst→src "recreate a missing Claude-side file" loop keeps writing into whichever `src_dir` it's called with, so call it with `src_dirs[0]` (the git-root encoding, the confirmed one) for that recreation role.

### New test

Add to `scripts/°base/tests/test_ai_hooks_base_routing.py`, alongside the existing `test_memory_posttooluse_write_with_underscore_in_project_path` (same file, same `run_hook`/`init_repo`/`_encode_project_path` helpers — no new test scaffolding needed):

```python
def test_memory_posttooluse_write_from_subproject_syncs_via_git_root_source(self):
    """A session launched inside a monorepo subdirectory (CLAUDE_PROJECT_DIR
    != git root) must still find memory written under Claude Code's
    git-root-encoded source dir -- see ai/°base/errors/25.*."""
    with tempfile.TemporaryDirectory() as tmp:
        repo = Path(tmp) / "DockerTgBot"
        subproject = repo / "sticker_tag_bot"
        home = Path(tmp) / "home"
        init_repo(repo, "https://github.com/luckydonald/docker-tg-bot.git")
        subproject.mkdir()

        encoded_root = _encode_project_path(repo.resolve())
        src_dir = home / ".claude" / "projects" / encoded_root / "memory"
        src_dir.mkdir(parents=True)
        src_file = src_dir / "tip.md"
        src_file.write_text("useful tip\n", encoding="utf-8")

        run_hook(
            repo,
            MEMORY_HOOK,
            {
                "hook_event_name": "PostToolUse",
                "tool_name": "Write",
                "tool_input": {"file_path": str(src_file)},
            },
            extra_env={"HOME": str(home), "CLAUDE_PROJECT_DIR": str(subproject)},
        )

        dst = subproject / "ai" / "memory" / "tip.md"
        self.assertTrue(dst.exists(), "memory file was not synced to repo")
        self.assertEqual(dst.read_text(encoding="utf-8"), "useful tip\n")
        self.assertEqual(last_subject(repo), "ai: record memory tip")
```

Run the full suite (not just this file) to confirm no regressions in the many other `MEMORY_HOOK` cases already in `test_ai_hooks_base_routing.py`:

```bash
uv run --project scripts/°base python -m unittest discover -s scripts/°base/tests -v
```

## Preserve the raw debug evidence in this repo

The eight hook debug payloads only exist locally in the `sticker_tag_bot` working tree — `ai/output/debug/` is gitignored there (`**/ai/output/debug/` in `.gitignore`), the same as it is in every consuming repo — so they need to be copied into this repo to survive. Mirror the original relative path (`ai/output/debug/`) nested under `ai/°base/`, keeping every filename unchanged:

- `sticker_tag_bot/ai/output/debug/20260901-110828_704139-save-prompt.json` → `ai/°base/ai/output/debug/20260901-110828_704139-save-prompt.json`
- `.../20260901-110843_540969-record-memory.json` → `ai/°base/ai/output/debug/20260901-110843_540969-record-memory.json`
- `.../20260901-110853_475017-save-plan.json` → `ai/°base/ai/output/debug/20260901-110853_475017-save-plan.json`
- `.../20260901-110853_512295-record-memory.json` → `ai/°base/ai/output/debug/20260901-110853_512295-record-memory.json`
- `.../20260901-110857_598746-save-plan.json` → `ai/°base/ai/output/debug/20260901-110857_598746-save-plan.json`
- `.../20260901-110857_635557-record-memory.json` → `ai/°base/ai/output/debug/20260901-110857_635557-record-memory.json`
- `.../20260901-110900_226449-save-plan.json` → `ai/°base/ai/output/debug/20260901-110900_226449-save-plan.json`
- `.../20260901-110902_037992-SubagentStop.json` → `ai/°base/ai/output/debug/20260901-110902_037992-SubagentStop.json`

That destination is itself gitignored too — `**/ai/output/debug/` matches anywhere in the tree, including nested under `ai/°base/` — confirmed with `git check-ignore -v`, so adding these needs `git add -f`, matching the original "force add" instruction.

## Execution checklist

Enable the `commit-with-lplp-style` skill for this implementation (this repo's origin is `luckydonald/base`, so it's already the assumed-yes default per `ai/°base/AGENTS.md`'s Plan mode section — the user has now also asked for it explicitly, including cleaning up stray auto-commits).

- [ ] Apply the `record-memory/hook.py` fix (`_memory_src_dirs`/`_memory_dst_dir` split, threaded through `main()`'s three branches).
- [ ] Add the new test to `test_ai_hooks_base_routing.py` and run the full test suite; fix forward if anything else in that file assumed the old single-`src_dir` shape.
- [ ] Commit the fix + test through the `commit-with-lplp-style` flow — expected message: `[base] scripts: ai: Run: Fixed record-memory hook dropping commits when the session launch dir differs from git root.`
- [ ] Copy the eight debug JSON files into `ai/°base/ai/output/debug/`, keeping their original filenames.
- [ ] `git add -f ai/°base/ai/output/debug/20260901-*.json`.
- [ ] Commit the copied evidence through the same `commit-with-lplp-style` flow, which will fold in the two existing "ai: referenced file for task added." commits (`557cf20a` for `25.claude1.txt`, `a97a50d3` for `25.claude2.txt`) — expected result: one clean commit containing `25.claude1.txt`, `25.claude2.txt`, and the eight debug JSON files, tagged/backed-up via `scripts/tag_backup.py` first per the skill's usual flow.
- [ ] Edit `/Users/user/.claude/projects/-Users-user-Documents-programming-Python-base/memory/MEMORY.md`, replacing:
  `- [History-master replay guards](2026-07-20-history-master-replay-guards.md) — TODO: summarize this file.`
  with:
  `- [History-master replay guards](2026-07-20-history-master-replay-guards.md) — git-plumbing pitfalls in \`°base\`'s history_master.py merge-replay (conflict paths, cherry-pick, hooks, diff parsing)`
  (the same one-line summary already used for the equivalent memory in the `DockerTgBot` project). This runs through the same (now-fixed, but unaffected either way since `base`'s own `CLAUDE_PROJECT_DIR` already equals its git root) `record-memory` hook and commits into `ai/°base/memory/MEMORY.md` on its own — a normal standalone "ai: record memory" commit, not one that needs folding.

## Verification

- `uv run --project scripts/°base python -m unittest discover -s scripts/°base/tests -v` passes, including the new test.
- `git log --oneline -6 --stat` in `base` shows: the hook-fix commit, the squashed evidence commit (with no leftover loose "referenced file" commits), and the memory-index commit — in some order — with nothing else stray in between.
- `git show` on the squashed evidence commit contains exactly `ai/°base/errors/25.claude1.txt`, `25.claude2.txt`, and the eight files under `ai/°base/ai/output/debug/`.
- `ai/°base/memory/MEMORY.md` (base repo, not `~/.claude`) shows the updated summary line.
