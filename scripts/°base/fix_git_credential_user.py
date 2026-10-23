#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.14"
# dependencies = []
# ///
"""
Find out which git command makes a git credential manager pop up, and pin the username into that remote's URL.

Without a user in the URL, a credential manager with several accounts for one host can't pick one and asks every time.
This waits until a `git-credential-*` helper is running, walks up to the `git` command that started it,
shows the old and new remote URL plus the command to rewrite it, and asks before running it.

Usage:
    ./scripts/fix_git_credential_user.py
    GIT_USERNAME='your-username' ./scripts/fix_git_credential_user.py
"""
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import quote, urlsplit, urlunsplit
import os
import re
import shlex
import subprocess
import sys
import time


DEFAULT_GIT_USERNAME = "luckydonald"
POLL_INTERVAL_SECONDS = 0.25

CREDENTIAL_HELPER_RE = re.compile(r"^(?:\S*/)?git-credential-[\w-]+(?:\s|$)")
REMOTE_HELPER_RE = re.compile(r"(?:^|/)git-remote-https?\s+(?P<remote>\S+)\s+(?P<url>\S+)\s*$")
GIT_COMMAND_RE = re.compile(r"^(?:\S*/)?git(?:\s|$)")


@dataclass(frozen=True)
class Process:
    pid: int
    ppid: int
    args: str
# end class


@dataclass(frozen=True)
class RemoteTarget:
    """The remote a git command was talking to when the credential helper opened."""
    repo_dir: Path
    remote: str
    url_key: str
    old_url: str
# end class


def list_processes() -> dict[int, Process]:
    output = subprocess.run(
        ["ps", "-axo", "pid=,ppid=,args="],
        capture_output=True, text=True, check=True,
    ).stdout
    processes: dict[int, Process] = {}
    for line in output.splitlines():
        parts = line.split(None, 2)
        if len(parts) < 3:
            continue
        # end if
        processes[int(parts[0])] = Process(pid=int(parts[0]), ppid=int(parts[1]), args=parts[2])
    # end for
    return processes
# end def


def find_credential_helper(processes: dict[int, Process]) -> Process | None:
    for pid in sorted(processes):
        if CREDENTIAL_HELPER_RE.match(processes[pid].args):
            return processes[pid]
        # end if
    # end for
    return None
# end def


def ancestors(process: Process, processes: dict[int, Process]) -> list[Process]:
    """Parents of the process, nearest first."""
    chain: list[Process] = []
    seen = {process.pid}
    current = processes.get(process.ppid)
    while current is not None and current.pid not in seen:
        chain.append(current)
        seen.add(current.pid)
        current = processes.get(current.ppid)
    # end while
    return chain
# end def


def process_cwd(pid: int) -> Path | None:
    result = subprocess.run(
        ["lsof", "-a", "-d", "cwd", "-p", str(pid), "-Fn"],
        capture_output=True, text=True,
    )
    for line in result.stdout.splitlines():
        if line.startswith("n"):
            return Path(line[1:])
        # end if
    # end for
    return None
# end def


def git_working_dir(process: Process) -> Path | None:
    """The directory a `git` process works in: its `-C` options applied on top of its own cwd."""
    try:
        tokens = shlex.split(process.args)
    except ValueError:
        return None
    # end try
    directories: list[str] = []
    index = 1
    while index < len(tokens) and tokens[index].startswith("-"):
        if tokens[index] == "-C" and index + 1 < len(tokens):
            directories.append(tokens[index + 1])
            index += 2
        elif tokens[index] == "-c":
            index += 2
        else:
            index += 1
        # end if
    # end while
    current: Path | None = None
    if not directories or not Path(directories[0]).is_absolute():
        current = process_cwd(process.pid)
        if current is None:
            return None
        # end if
    # end if
    for directory in directories:
        current = Path(directory) if current is None else current / directory
    # end for
    return current if current is not None and current.is_dir() else None
# end def


def configured_url_key(repo_dir: Path, remote: str, url: str) -> str | None:
    """Which config key (`pushurl` or `url`) of the remote holds this exact URL."""
    for key in (f"remote.{remote}.pushurl", f"remote.{remote}.url"):
        result = subprocess.run(
            ["git", "-C", str(repo_dir), "config", "--get-all", key],
            capture_output=True, text=True,
        )
        if url in result.stdout.splitlines():
            return key
        # end if
    # end for
    return None
# end def


def find_remote_target(helper: Process, processes: dict[int, Process]) -> RemoteTarget:
    chain = ancestors(helper, processes)
    remote_match = next(
        (match for match in (REMOTE_HELPER_RE.search(p.args) for p in chain) if match),
        None,
    )
    if remote_match is None:
        raise LookupError("No `git-remote-https <remote> <url>` process above the credential helper, so there is no remote to fix.")
    # end if
    remote, url = remote_match["remote"], remote_match["url"]
    if remote == url:
        raise LookupError(f"Git was given the URL {url} directly instead of a remote name, so there is no remote to rewrite.")
    # end if
    git_process = next((p for p in chain if GIT_COMMAND_RE.match(p.args)), None)
    if git_process is None:
        raise LookupError("No `git` command found above the credential helper.")
    # end if
    repo_dir = git_working_dir(git_process)
    if repo_dir is None:
        raise LookupError(f"Could not work out the repository directory from: {git_process.args}")
    # end if
    url_key = configured_url_key(repo_dir, remote, url)
    if url_key is None:
        raise LookupError(
            f"{url} is not configured for remote {remote!r} in {repo_dir}, "
            "perhaps it comes from an `url.<base>.insteadOf` rule."
        )
    # end if
    return RemoteTarget(repo_dir=repo_dir, remote=remote, url_key=url_key, old_url=url)
# end def


def url_with_username(url: str, username: str) -> str | None:
    """The URL with the user added, or None if it isn't an http(s) URL without a user."""
    parts = urlsplit(url)
    if parts.scheme not in ("http", "https") or "@" in parts.netloc:
        return None
    # end if
    return urlunsplit(parts._replace(netloc=f"{quote(username, safe='')}@{parts.netloc}"))
# end def


def set_url_command(target: RemoteTarget, new_url: str) -> list[str]:
    command = ["git", "-C", str(target.repo_dir), "remote", "set-url"]
    if target.url_key.endswith(".pushurl"):
        command.append("--push")
    # end if
    return [*command, target.remote, new_url]
# end def


def confirm() -> bool:
    answer = input("Confirm? [Y/n] ").strip().lower()
    return answer in ("", "y", "yes")
# end def


def main() -> int:
    from_environment = "GIT_USERNAME" in os.environ and os.environ["GIT_USERNAME"] != ""
    username = os.environ["GIT_USERNAME"] if from_environment else DEFAULT_GIT_USERNAME
    print(f"GIT_USERNAME: {username} ({'from environment' if from_environment else 'default'})")
    print(f"Set another one with: GIT_USERNAME='your-username' {sys.argv[0]}")

    announced = False
    helper: Process | None = None
    processes: dict[int, Process] = {}
    while helper is None:
        processes = list_processes()
        helper = find_credential_helper(processes)
        if helper is None:
            if not announced:
                print("Waiting for a git credential helper to open (Ctrl-C to abort) ...")
                announced = True
            # end if
            time.sleep(POLL_INTERVAL_SECONDS)
        # end if
    # end while
    print(f"Found credential helper: [{helper.pid}] {helper.args}")

    try:
        target = find_remote_target(helper, processes)
    except LookupError as error:
        print(f"Error: {error}", file=sys.stderr)
        return 1
    # end try

    new_url = url_with_username(target.old_url, username)
    if new_url is None:
        existing_user = urlsplit(target.old_url).username
        if existing_user is not None:
            print(f"Nothing to change: {target.old_url} already names the user {existing_user!r}.")
            print("The prompt is not caused by a missing user, so check which account the credential manager offers for it.")
        else:
            print(f"Nothing to change: {target.old_url} is not an http(s) URL.")
        # end if
        return 0
    # end if
    command = set_url_command(target, new_url)
    print()
    print(f"Repository: {target.repo_dir}")
    print(f"Old URL:    {target.old_url}")
    print(f"New URL:    {new_url}")
    print(f"Command:    {shlex.join(command)}")
    if not confirm():
        print("Aborted, nothing changed.")
        return 1
    # end if
    subprocess.run(command, check=True)
    print(f"Done. Answer the open credential prompt as {username}; later runs use the new URL.")
    return 0
# end def


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        raise SystemExit(130)
    # end try
# end if
