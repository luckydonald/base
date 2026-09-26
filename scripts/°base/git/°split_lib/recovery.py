"""Crash-safe recovery logging for every mutating split.py subcommand.

Before any ref is touched, the caller snapshots the current state of every
ref an invocation could plausibly move, prints it, and appends it (with
ready-to-run undo commands) to `.rebase-recovery.tmp` in the repo root --
so recovery information survives even if the process is killed mid-run.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path

from . import branches, git_ops, sync_splits, sync_unclean

RECOVERY_FILENAME = ".rebase-recovery.tmp"
BACKUP_TAG_ROOT = "refs/tags/bak/split"

ABORT_COMMANDS = (
    "git rebase --abort || true",
    "git cherry-pick --abort || true",
    "git merge --abort || true",
)


def resolve_watched_refs(branch: str | None, main_branch: str, cwd: Path) -> list[str]:
    """Ref names a given invocation could plausibly touch, deduped, order preserved."""
    branches_to_cover = [branch] if branch is not None else sync_splits.discover_unclean_branches(cwd)

    refs: list[str] = [main_branch, branches.history_name(main_branch)]
    for base_branch in branches_to_cover:
        refs.extend(
            [
                base_branch,
                branches.unclean_name(base_branch),
                branches.history_name(base_branch),
                branches.history_fork_point_ref(base_branch),
                sync_unclean.clean_cursor_ref(base_branch),
                sync_unclean.history_cursor_ref(base_branch),
                sync_splits.forward_cursor_ref(base_branch, "clean"),
                sync_splits.forward_cursor_ref(base_branch, "history"),
            ]
        )

    seen: set[str] = set()
    deduped: list[str] = []
    for ref in refs:
        if ref not in seen:
            seen.add(ref)
            deduped.append(ref)
    return deduped


def snapshot(refs: list[str], cwd: Path) -> dict[str, str | None]:
    return {ref: git_ops.rev_parse(ref, cwd) for ref in refs}


def backup_split_refs(
    base_branch: str,
    cwd: Path,
    *,
    when: datetime | None = None,
) -> dict[str, str]:
    """Tag the existing clean, UNCLEAN, and history tips before a split run."""
    tips = {
        "clean": git_ops.rev_parse(base_branch, cwd),
        "UNCLEAN": git_ops.rev_parse(branches.unclean_name(base_branch), cwd),
        "history": git_ops.rev_parse(branches.history_name(base_branch), cwd),
    }
    existing_tips = {label: sha for label, sha in tips.items() if sha is not None}
    if not existing_tips:
        return {}
    # end if

    candidate = when or datetime.now()
    while True:
        timestamp = candidate.strftime("%Y-%m-%d_%H-%M-%S")
        reserved_tag_refs = {
            label: f"{BACKUP_TAG_ROOT}/{base_branch}/{timestamp}/{label}"
            for label in tips
        }
        tag_refs = {
            label: reserved_tag_refs[label]
            for label in existing_tips
        }
        if all(git_ops.rev_parse(tag_ref, cwd) is None for tag_ref in reserved_tag_refs.values()):
            break
        # end if
        candidate += timedelta(seconds=1)
    # end while

    git_ops.create_refs(
        {tag_refs[label]: sha for label, sha in existing_tips.items()},
        cwd,
    )
    return tag_refs
# end def


def full_ref(ref: str) -> str:
    return ref if ref.startswith("refs/") else f"refs/heads/{ref}"


def undo_command(ref: str, old_sha: str | None) -> str:
    full = full_ref(ref)
    if old_sha is None:
        return f"git update-ref -d '{full}' || true"
    return f"git update-ref '{full}' '{old_sha}'"


def format_recovery_entry(invocation: str, before: dict[str, str | None], timestamp: str) -> str:
    lines = [f"#### Run _{timestamp}_ `{invocation}`", ""]

    lines.append("Branch | Commit before")
    lines.append("------ | -------------")
    for ref, sha in before.items():
        lines.append(f"`{ref}` | `{sha if sha is not None else '(none)'}`")
    lines.append("")

    lines.append("```shell")
    lines.extend(ABORT_COMMANDS)
    for ref, sha in before.items():
        lines.append(undo_command(ref, sha))
    lines.append("```")

    return "\n".join(lines)


def format_after_summary(before: dict[str, str | None], after: dict[str, str | None]) -> str:
    lines = ["Branch | Commit before | Commit now", "------ | ------------- | ----------"]
    for ref in before:
        before_sha = before[ref]
        after_sha = after.get(ref)
        lines.append(
            f"`{ref}` | `{before_sha if before_sha is not None else '(none)'}` "
            f"| `{after_sha if after_sha is not None else '(none)'}`"
        )
    return "\n".join(lines)


def write_recovery_log(repo_root: Path, entry_markdown: str) -> None:
    path = repo_root / RECOVERY_FILENAME
    with path.open("a", encoding="utf-8") as handle:
        handle.write(entry_markdown)
        handle.write("\n\n")
