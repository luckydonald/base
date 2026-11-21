"""Layered `backup_tags` settings: tracked, repo, local, then env vars."""
from __future__ import annotations

import json
import subprocess
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

DEFAULT_REPO: str = "https://luckydonald@github.com/luckydonald/bak.git"
SETTINGS_FILES: tuple[Path, ...] = (
    Path("ai/settings/settings.json"),
    Path("ai/settings/settings.repo.json"),
    Path("ai/settings/settings.local.json"),
)
ENV_PREFIX: str = "BACKUP_TAGS"
TRUE_WORDS: frozenset[str] = frozenset({"1", "true", "yes", "on"})
FALSE_WORDS: frozenset[str] = frozenset({"0", "false", "no", "off"})


@dataclass(frozen=True)
class BackupTags:
    repo: str = DEFAULT_REPO
    delete_local: bool = False
    delete_origin: bool = False
# end class


def git_root(cwd: Path) -> Path:
    result = subprocess.run(["git", "-C", str(cwd), "rev-parse", "--show-toplevel"], text=True, capture_output=True)
    return Path(result.stdout.strip()) if result.returncode == 0 and result.stdout.strip() else cwd
# end def


def parse_bool(value: str, source: str) -> bool:
    word = value.strip().lower()
    if word in TRUE_WORDS:
        return True
    # end if
    if word in FALSE_WORDS:
        return False
    # end if
    raise SystemExit(f"{source}: {value!r} is not a boolean (use true/false)")
# end def


def read_layer(path: Path) -> dict[str, Any]:
    """The `backup_tags` dict of one settings file; `{}` if the file or the key is missing."""
    if not path.is_file():
        return {}
    # end if
    try:
        data = json.loads(path.read_text())
    except (OSError, ValueError) as e:
        raise SystemExit(f"{path}: cannot read settings: {e}") from e
    # end try
    section = data.get("backup_tags") if isinstance(data, dict) else None
    if section is None:
        return {}
    # end if
    if not isinstance(section, dict):
        raise SystemExit(f"{path}: `backup_tags` must be an object")
    # end if
    repo, delete = section.get("repo"), section.get("delete_tags")
    if repo is not None and (not isinstance(repo, str) or not repo):
        raise SystemExit(f"{path}: `backup_tags.repo` must be a non-empty string")
    # end if
    if delete is not None:
        if not isinstance(delete, dict):
            raise SystemExit(f"{path}: `backup_tags.delete_tags` must be an object")
        # end if
        for key in ("local", "origin"):
            if delete.get(key) is not None and not isinstance(delete[key], bool):
                raise SystemExit(f"{path}: `backup_tags.delete_tags.{key}` must be a boolean")
            # end if
        # end for
    # end if
    return section
# end def


def read_env(env: Mapping[str, str]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    if env.get(f"{ENV_PREFIX}_REPO"):
        out["repo"] = env[f"{ENV_PREFIX}_REPO"]
    # end if
    delete: dict[str, bool] = {}
    for key in ("local", "origin"):
        name = f"{ENV_PREFIX}_DELETE_TAGS_{key.upper()}"
        if env.get(name, "").strip():
            delete[key] = parse_bool(env[name], name)
        # end if
    # end for
    if delete:
        out["delete_tags"] = delete
    # end if
    return out
# end def


def load_backup_tags(root: Path, env: Mapping[str, str]) -> BackupTags:
    """Merge defaults < settings.json < settings.repo.json < settings.local.json < env; each layer only overrides keys it sets."""
    repo, local, origin = DEFAULT_REPO, False, False
    for layer in [*(read_layer(root / f) for f in SETTINGS_FILES), read_env(env)]:
        repo = layer.get("repo") or repo
        delete = layer.get("delete_tags") or {}
        local = delete["local"] if delete.get("local") is not None else local
        origin = delete["origin"] if delete.get("origin") is not None else origin
    # end for
    return BackupTags(repo=repo, delete_local=local, delete_origin=origin)
# end def
