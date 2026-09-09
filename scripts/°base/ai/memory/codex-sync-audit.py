#!/usr/bin/env python3
"""Find and resolve ad-hoc Codex notes claimed by more than one project.

This is the cleanup tool for data left over by the pre-registry
`record-codex-memory/hook.py` (hostname-keyed identity + no cross-project
ownership check): the same native note could get auto-imported into every
project whose tool call happened to fire the hook next. Report mode (the
default) is read-only and safe to run any time; `--fix` is explicit,
one-decision-at-a-time, and touches git state in whichever *other* project
repos are found on disk -- review each case before applying it.

Usage:
    python3 scripts/°base/ai/memory/codex-sync-audit.py
    python3 scripts/°base/ai/memory/codex-sync-audit.py --fix <note.md> --owner <project-key>
"""
from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path


def load_hook():
    hook = Path(__file__).resolve().parents[1] / "hooks" / "record-codex-memory" / "hook.py"
    spec = importlib.util.spec_from_file_location("record_codex_memory", hook)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {hook}")
    # end if
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module
# end def


def _read_json(path: Path) -> dict | None:
    if not path.is_file():
        return None
    # end if
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    # end try
    return data if isinstance(data, dict) else None
# end def


def _scope_root(resource_dir: Path) -> Path | None:
    scope = _read_json(resource_dir / "scope.json")
    if scope is None or not isinstance(scope.get("cwd"), str):
        return None
    # end if
    root = Path(scope["cwd"])
    return root if root.is_dir() else None
# end def


def collect_claims(hook, base_synced: Path) -> dict[str, list[dict]]:
    """identity -> list of {project, root, target, hash, resource_dir}."""
    claims: dict[str, list[dict]] = {}
    resources = base_synced / "resources"
    if not resources.is_dir():
        return claims
    # end if
    for resource_dir in sorted(p for p in resources.iterdir() if p.is_dir()):
        project = resource_dir.name
        root = _scope_root(resource_dir)
        raw = _read_json(resource_dir / ".codex-sync.json")
        if raw is None:
            continue
        # end if
        if raw.get("version") == 2:
            notes = raw.get("notes") if isinstance(raw.get("notes"), dict) else {}
            for identity, entry in notes.items():
                if not isinstance(entry, dict) or entry.get("status") != "assigned":
                    continue
                # end if
                claims.setdefault(identity, []).append({
                    "project": project, "root": root,
                    "target": entry.get("target"), "hash": entry.get("hash"),
                    "resource_dir": resource_dir,
                })
            # end for
        elif root is not None:
            # Old v1 shape: normalize just enough to report it, without
            # writing anything back (that's what --fix / migration are for).
            migrated = hook._migrate_v1_codex_sync(raw, root)
            for identity, entry in migrated["notes"].items():
                if entry.get("status") != "assigned":
                    continue
                # end if
                claims.setdefault(identity, []).append({
                    "project": project, "root": root,
                    "target": entry.get("target"), "hash": entry.get("hash"),
                    "resource_dir": resource_dir,
                })
            # end for
        # end if
    # end for
    return claims
# end def


def note_context(hook, base_synced: Path, identity: str) -> str:
    source = base_synced.parent / identity
    if not source.is_file():
        return ""
    # end if
    try:
        return hook.note_title(source)
    except OSError:
        return ""
    # end try
# end def


def report(hook, base_synced: Path) -> int:
    claims = collect_claims(hook, base_synced)
    duplicates = {identity: owners for identity, owners in claims.items() if len(owners) > 1}
    if not duplicates:
        print("No note is claimed by more than one project.")
        return 0
    # end if
    for identity, owners in sorted(duplicates.items()):
        title = note_context(hook, base_synced, identity)
        print(f"{identity}" + (f" -- {title}" if title else ""))
        for owner in owners:
            root = owner["root"] if owner["root"] is not None else "<repo not found on disk>"
            print(f"  - {owner['project']}  root={root}  target={owner['target']}")
        # end for
    # end for
    print(f"\n{len(duplicates)} note(s) claimed by more than one project.")
    print("Resolve one at a time: --fix <note.md> --owner <project-key>")
    return 1
# end def


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
    subprocess.run(["git", "add", "--all", "--", str(hook.project_memory_dir(root).relative_to(root))], cwd=root, check=True)
    subprocess.run(
        ["git", "commit", "--no-verify", "-m", f"ai: remove misassigned codex memory {memory_file.name}"],
        cwd=root, capture_output=True, text=True,
    )
# end def


def fix(hook, base_synced: Path, note: str, owner_key: str) -> int:
    identity = note if note.startswith("extensions/ad_hoc/") else f"extensions/ad_hoc/{Path(note).name}"
    claims = collect_claims(hook, base_synced)
    owners = claims.get(identity, [])
    if len(owners) < 2:
        print(f"{identity} is not claimed by more than one project; nothing to fix.", file=sys.stderr)
        return 1
    # end if
    by_key = {owner["project"]: owner for owner in owners}
    if owner_key not in by_key:
        print(f"{owner_key} is not among the current claimants: {sorted(by_key)}", file=sys.stderr)
        return 1
    # end if
    kept = by_key[owner_key]

    for project, owner in by_key.items():
        if project == owner_key:
            continue
        # end if
        if owner["root"] is None:
            print(f"skipping {project}: repo not found on disk (scope.json points elsewhere); remove its resource dir manually.", file=sys.stderr)
            continue
        # end if
        _remove_from_project(hook, owner["root"], owner["target"], identity)
        hook.memory_lib.unlink_path(owner["resource_dir"] / Path(owner["target"]).name)
        resource_sync_path = owner["resource_dir"] / hook.METADATA_NAME
        resource_sync = hook.read_codex_sync(resource_sync_path, owner["root"])
        if resource_sync["notes"].pop(identity, None) is not None:
            hook.write_codex_sync(resource_sync_path, resource_sync)
        # end if
        print(f"removed {identity} from {project} ({owner['root']})")
    # end for

    registry_path = base_synced / hook.REGISTRY_NAME
    registry = hook.read_registry(registry_path)
    registry["notes"][identity] = {
        "status": "assigned", "project": owner_key,
        "target": kept["target"], "hash": kept["hash"],
    }
    hook.write_registry(registry_path, registry)
    if kept["root"] is not None:
        hook._write_project_sync_views(base_synced.parent, kept["root"], registry)
    # end if
    print(f"kept {identity} assigned to {owner_key}")
    return 0
# end def


def main(argv: list[str] | None = None) -> int:
    args = argv if argv is not None else sys.argv[1:]
    hook = load_hook()
    base_synced = hook.codex_memory_dir()
    if base_synced is None:
        print("Codex memory directory is unavailable (no $CODEX_HOME).", file=sys.stderr)
        return 1
    # end if
    base_synced = base_synced / hook.BASE_SYNCED_DIR

    if "--fix" in args:
        index = args.index("--fix")
        if index + 1 >= len(args) or "--owner" not in args:
            print("Usage: codex-sync-audit.py --fix <note.md> --owner <project-key>", file=sys.stderr)
            return 2
        # end if
        note = args[index + 1]
        owner_index = args.index("--owner")
        if owner_index + 1 >= len(args):
            print("--owner requires a project key", file=sys.stderr)
            return 2
        # end if
        owner_key = args[owner_index + 1]
        return fix(hook, base_synced, note, owner_key)
    # end if
    return report(hook, base_synced)
# end def


if __name__ == "__main__":
    raise SystemExit(main())
# end if
