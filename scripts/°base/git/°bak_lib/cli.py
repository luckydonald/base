from __future__ import annotations

import argparse
import os
from pathlib import Path

from .push import process
from .settings import BackupTags, git_root, load_backup_tags


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(
        description="Push local `bak/*` tags to the backup repo from `backup_tags` settings, optionally deleting them afterwards.",
    )
    ap.add_argument("names", nargs="*", help="tags/branches to push (default: all local bak/* tags)")
    ap.add_argument("-C", dest="repo", default=".", help="the repository (default: current directory)")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--bak-repo", help="backup repo URL, overrides `backup_tags.repo`")
    ap.add_argument("--delete-local", action=argparse.BooleanOptionalAction, default=None)
    ap.add_argument("--delete-origin", action=argparse.BooleanOptionalAction, default=None)
    return ap
# end def


def main(argv: list[str] | None = None) -> int:
    a = build_parser().parse_args(argv)
    repo = git_root(Path(a.repo))
    cfg = load_backup_tags(repo, os.environ)
    cfg = BackupTags(
        repo=a.bak_repo or cfg.repo,
        delete_local=cfg.delete_local if a.delete_local is None else a.delete_local,
        delete_origin=cfg.delete_origin if a.delete_origin is None else a.delete_origin,
    )
    print(f"== {repo} -> {cfg.repo} (delete local: {cfg.delete_local}, origin: {cfg.delete_origin})")
    process(repo, a.names, cfg, a.dry_run)
    return 0
# end def
