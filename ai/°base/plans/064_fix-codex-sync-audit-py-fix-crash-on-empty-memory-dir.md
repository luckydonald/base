# Fix `codex-sync-audit.py --fix` crash on empty memory dir

## Context

`ai/°base/errors/25.txt` captures a crash of `scripts/°base/ai/memory/codex-sync-audit.py --fix`, the tool that resolves ad-hoc Codex notes claimed by more than one project. While removing the losing project's copy of a note, it crashes with:

```
subprocess.CalledProcessError: Command '['git', 'add', '--all', '--', 'ai/memory']' returned non-zero exit status 128.
```

(`fatal: pathspec 'ai/memory' did not match any files`)

It had already successfully processed several other projects (their "removed ... from ..." lines print before the traceback) before hitting one where this fails.

## Root cause

`_remove_from_project()` (`scripts/°base/ai/memory/codex-sync-audit.py:140-164`) always runs:

```python
subprocess.run(["git", "add", "--all", "--", str(hook.project_memory_dir(root).relative_to(root))], cwd=root, check=True)
```

`hook.memory_lib.unlink_path()` (confirmed via `°memory_lib/delete.py:28-30`) only unlinks the single note file — it never removes or prunes the parent directory. When the removed note was the *only* thing under that project's memory dir (e.g. it was untracked and nothing else lives there yet), the directory ends up empty: nothing in the working tree and nothing in the git index under that path. `git add --all -- <path>` then has literally nothing to match, so git exits 128 with "did not match any files" instead of silently no-op'ing, and `check=True` turns that into a crash — even though there's nothing wrong; there's just nothing left to stage.

This is a bug in the tool itself, not project-specific: it happens whenever a fix-removal empties a project's memory directory instead of just thinning it out.

## Fix

In `_remove_from_project()`, check whether there's anything to stage before calling `git add`, and skip the add+commit entirely when there isn't (nothing changed from git's perspective, so there's nothing to commit):

```python
def _remove_from_project(hook, root: Path, target: str, identity: str) -> None:
    memory_file = root / target
    hook.memory_lib.unlink_path(memory_file)
    for memory_dir in hook.project_memory_dirs(root):
        index = memory_dir / "MEMORY.md"
        if not index.is_file():
            continue
        # end if
        lines = index.read_text(encoding="utf-8").splitlines(keepends=True)
        kept = [line for line in lines if not hook._memory_md_references(line, memory_file.name)]
        if kept != lines:
            index.write_text("".join(kept), encoding="utf-8")
        # end if
    # end for
    sync_path = hook.project_memory_dir(root) / hook.METADATA_NAME
    data = hook.read_codex_sync(sync_path, root)
    if data["notes"].pop(identity, None) is not None:
        hook.write_codex_sync(sync_path, data)
    # end if

    memory_rel = str(hook.project_memory_dir(root).relative_to(root))
    status = subprocess.run(
        ["git", "status", "--porcelain", "--", memory_rel], cwd=root, capture_output=True, text=True, check=True,
    )
    if not status.stdout.strip():
        return
    # end if
    subprocess.run(["git", "add", "--all", "--", memory_rel], cwd=root, check=True)
    subprocess.run(
        ["git", "commit", "--no-verify", "-m", f"ai: remove misassigned codex memory {memory_file.name}"],
        cwd=root, capture_output=True, text=True,
    )
# end def
```

This is the only change needed — it's a self-contained fix in `scripts/°base/ai/memory/codex-sync-audit.py`.

## Error log file

`ai/°base/errors/25.txt` needs no change. Looking at the other numbered `.txt` error captures in that directory (`6.txt`, `7.txt`, `16.txt`, `17.txt`, `21.txt`, `22.txt`, `24.txt`), raw traceback logs like this one are kept as-is with no companion `N.expected.md` — that convention is only used for the `.md`-captured interactive/formatting bugs. `25.txt` is already committed and contains no data needing redaction, so it stays untouched.

## Verification

- Re-run `python3 scripts/°base/ai/memory/codex-sync-audit.py` (report mode, read-only) to confirm it still runs cleanly.
- Exercise the fixed code path directly: create a temp git repo with an untracked `ai/memory/<note>.md` and no `MEMORY.md`, call `_remove_from_project` (or invoke `--fix` against a synthetic duplicate-claim scenario) so the memory dir ends up empty, and confirm it now returns cleanly instead of raising `CalledProcessError`.
- Also confirm the previously-working case still works: a project where the memory dir still has other content left after removal should still get `git add`+`git commit`'d as before.
