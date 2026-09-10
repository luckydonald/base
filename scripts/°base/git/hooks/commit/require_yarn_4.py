#!/usr/bin/env python3
"""Enforce the repository-wide Yarn 4 commit policy."""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path, PurePosixPath
from typing import Any


SHARED_SETTINGS = PurePosixPath("ai/settings/settings.json")
LOCAL_SETTINGS = Path("ai/settings/settings.local.json")
YARN_VERSION = re.compile(r"^yarn@4\.\d+\.\d+(?:-[0-9A-Za-z.-]+)?(?:\+[0-9A-Za-z.-]+)?$")
YARN_RELEASE = re.compile(r"^yarn-4\.\d+\.\d+(?:-[0-9A-Za-z.-]+)?\.c?js$")
COMPETING_LOCKS = {"package-lock.json", "npm-shrinkwrap.json", "pnpm-lock.yaml"}


def run_git(*args: str) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        ["git", *args],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        detail = result.stderr.strip() or result.stdout.strip()
        raise RuntimeError(f"git {' '.join(args)} failed: {detail}")
    # end if
    return result
# end def


def index_paths() -> list[PurePosixPath]:
    output = run_git("ls-files", "-z").stdout
    return [PurePosixPath(raw) for raw in output.split("\0") if raw]
# end def


def index_text(path: PurePosixPath) -> str:
    return run_git("show", f":{path.as_posix()}").stdout
# end def


def parse_json_object(text: str, label: str) -> dict[str, Any]:
    try:
        value = json.loads(text)
    except json.JSONDecodeError as error:
        raise ValueError(f"{label} is not valid JSON: {error}") from error
    # end try
    if not isinstance(value, dict):
        raise ValueError(f"{label} must contain a JSON object.")
    # end if
    return value
# end def


def yarn_setting(data: dict[str, Any], label: str, local: bool) -> bool:
    pre_commit = data.get("pre_commit")
    if pre_commit is None:
        return True
    # end if
    if not isinstance(pre_commit, dict):
        raise ValueError(f"{label}: pre_commit must be an object.")
    # end if
    if "yarn@4" not in pre_commit:
        return True
    # end if
    if local:
        raise ValueError(
            f"{label}: pre_commit.yarn@4 is shared repository policy; "
            "move it to ai/settings/settings.json."
        )
    # end if
    setting = pre_commit["yarn@4"]
    if not isinstance(setting, dict):
        raise ValueError(f"{label}: pre_commit.yarn@4 must be an object.")
    # end if
    enabled = setting.get("enabled")
    if not isinstance(enabled, bool):
        raise ValueError(f"{label}: pre_commit.yarn@4.enabled must be a boolean.")
    # end if
    return enabled
# end def


def policy_enabled(paths: list[PurePosixPath], repo: Path) -> bool:
    enabled = True
    if SHARED_SETTINGS in paths:
        shared = parse_json_object(index_text(SHARED_SETTINGS), SHARED_SETTINGS.as_posix())
        enabled = yarn_setting(shared, SHARED_SETTINGS.as_posix(), local=False)
    # end if

    # now make sure the `settings.local.json` has no `'yarn@4': false` as we only accept the git-tracked one.
    local_path = repo / LOCAL_SETTINGS
    if local_path.is_file():
        local = parse_json_object(local_path.read_text(encoding="utf-8"), LOCAL_SETTINGS.as_posix())
        yarn_setting(local, LOCAL_SETTINGS.as_posix(), local=True)
    # end if
    return enabled
# end def


def has_component(path: PurePosixPath, component: str) -> bool:
    return component in path.parts
# end def


def node_signal(path: PurePosixPath) -> bool:
    if path.name in {
        "package.json",
        "yarn.lock",
        ".yarnrc",
        ".yarnrc.yml",
        *COMPETING_LOCKS,
    }:
        return True
    # end if
    return has_component(path, "node_modules") or (
        ".yarn" in path.parts and "releases" in path.parts
    )
# end def


def ignored_node_modules() -> list[str]:
    result = run_git(
        "ls-files",
        "--others",
        "--ignored",
        "--exclude-standard",
        "--directory",
        "-z",
    )
    paths = {
        PurePosixPath(raw).as_posix().rstrip("/")
        for raw in result.stdout.split("\0")
        if raw and has_component(PurePosixPath(raw), "node_modules")
    }
    return sorted(paths)
# end def


def covered_by_root(path: PurePosixPath, roots: list[PurePosixPath]) -> bool:
    for root in roots:
        if path == root or root in path.parents:
            return True
        # end if
    # end for
    return False
# end def


def lock_is_yarn_4(text: str) -> bool:
    return re.search(
        r"(?m)^__metadata:\s*$\n(?:^[ \t]+.*$\n)*?^[ \t]+version:\s*['\"]?8['\"]?\s*$",
        text,
    ) is not None
# end def


def validate_package_manager(text: str, label: str) -> str | None:
    try:
        package = parse_json_object(text, label)
    except ValueError as error:
        return str(error)
    # end try
    manager = package.get("packageManager")
    if not isinstance(manager, str) or YARN_VERSION.fullmatch(manager) is None:
        return f'{label}: packageManager must be an exact Yarn 4 version such as "yarn@4.13.0".'
    # end if
    return None
# end def


def yarn_path_error(text: str, label: str) -> str | None:
    match = re.search(r"(?m)^\s*yarnPath\s*:\s*([^#\r\n]+)", text)
    if match is None:
        return None
    # end if
    raw = match.group(1).strip().strip("'\"")
    filename = PurePosixPath(raw).name
    if YARN_RELEASE.fullmatch(filename) is None:
        return f"{label}: yarnPath must reference an exact Yarn 4 release, not {raw!r}."
    # end if
    return None
# end def


def validate_index(paths: list[PurePosixPath]) -> list[str]:
    errors: list[str] = []
    path_set = set(paths)

    for path in paths:
        if path.name in COMPETING_LOCKS:
            errors.append(f"{path}: competing package-manager lockfile is not allowed by Yarn 4 policy.")
        # end if
        if path.name == ".yarnrc":
            errors.append(f"{path}: legacy .yarnrc is not supported; use .yarnrc.yml.")
        # end if
        if has_component(path, "node_modules"):
            errors.append(f"{path}: node_modules must never be tracked or committed.")
        # end if
        if ".yarn" in path.parts and "releases" in path.parts and path.name.startswith("yarn-"):
            if YARN_RELEASE.fullmatch(path.name) is None:
                errors.append(f"{path}: checked-in Yarn release must be an exact Yarn 4 .cjs file.")
            # end if
        # end if
    # end for

    lock_paths = [path for path in paths if path.name == "yarn.lock"]
    roots = sorted({path.parent for path in lock_paths}, key=lambda item: (len(item.parts), item.as_posix()))
    package_paths = [
        path
        for path in paths
        if path.name == "package.json" and not has_component(path, "node_modules")
    ]
    if not package_paths:
        errors.append("Node/Yarn artifacts exist, but no package.json is tracked.")
    # end if

    for lock_path in lock_paths:
        root = lock_path.parent
        package_path = root / "package.json"
        if package_path not in path_set:
            errors.append(f"{lock_path}: Yarn project root is missing {package_path}.")
        else:
            package_error = validate_package_manager(index_text(package_path), package_path.as_posix())
            if package_error is not None:
                errors.append(package_error)
            # end if
        # end if
        if not lock_is_yarn_4(index_text(lock_path)):
            errors.append(f"{lock_path}: expected a Yarn 4 lockfile with __metadata.version 8.")
        # end if
    # end for

    for package_path in package_paths:
        if not covered_by_root(package_path.parent, roots):
            errors.append(f"{package_path}: package manifest is not covered by a Yarn 4 project root.")
        # end if
    # end for

    for path in paths:
        if path.name == ".yarnrc.yml":
            error = yarn_path_error(index_text(path), path.as_posix())
            if error is not None:
                errors.append(error)
            # end if
        # end if
    # end for
    return errors
# end def


def main(argv: list[str] | None = None) -> int:
    args = argv if argv is not None else sys.argv[1:]
    if args:
        print("This hook does not accept filenames or arguments.", file=sys.stderr)
        return 2
    # end if

    try:
        repo = Path(run_git("rev-parse", "--show-toplevel").stdout.strip())
        paths = index_paths()
        enabled = policy_enabled(paths, repo)
        if not enabled:
            return 0
        # end if
        warnings = ignored_node_modules()
        signals = any(node_signal(path) for path in paths)
        if not signals and not warnings:
            return 0
        # end if
        errors = validate_index(paths) if signals else []
    except (OSError, RuntimeError, ValueError) as error:
        print(f"Yarn 4 pre-commit configuration error: {error}", file=sys.stderr)
        return 2
    # end try

    for path in warnings:
        print(f"warning: ignored local node_modules detected: {path}", file=sys.stderr)
    # end for
    if not errors:
        return 0
    # end if

    print("Yarn 4 pre-commit policy rejected this commit:", file=sys.stderr)
    for error in errors:
        print(f"  - {error}", file=sys.stderr)
    # end for
    print(
        "Use Corepack and the tracked packageManager version, then regenerate with "
        "`yarn install`. Disable only through tracked "
        "ai/settings/settings.json -> pre_commit.yarn@4.enabled=false.",
        file=sys.stderr,
    )
    return 1
# end def


if __name__ == "__main__":
    raise SystemExit(main())
