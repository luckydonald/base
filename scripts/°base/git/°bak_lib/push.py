"""Push `bak/*` tags to the backup repo as namespaced tags, then optionally delete them locally and on origin.

Remote tag: bak/+/<host/owner/repo>/+/<tag|branch>/<on-empty|no-empty|-rebased->/+/<original name>
"""
from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from urllib.parse import urlsplit

from .settings import BackupTags

EMPTY: str = "430d07f279ab28a56977fe1b0c6200f6b2710a11"  # EmptyAAS/empty `init`
EMPTY_URL: str = "https://github.com/EmptyAAS/empty"
SEP: str = "+"
IDENT: dict[str, str] = {"GIT_COMMITTER_NAME": "Lucky Lucy", "GIT_COMMITTER_EMAIL": "2.2026._.code@luckydonald.de"}
URL_RE: str = r"^[\w.+-]+://"
SCP_RE: str = r"^(?:[^@/]+@)?([^:/]+):(.+)$"  # git@github.com:o/r.git


def git(repo: Path | str, *args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["git", "-C", str(repo), *args], text=True, capture_output=True, check=check)
# end def


def normalize_url(url: str) -> str:
    """Compare-key of a remote: no scheme, credentials, port or `.git`, lowercase host. Local paths are resolved."""
    if re.match(URL_RE, url):
        parts = urlsplit(url)
        host, path = (parts.hostname or "").lower(), parts.path
    elif m := re.match(SCP_RE, url):
        host, path = m.group(1).lower(), m.group(2)
    else:
        host, path = "", str(Path(url).resolve())
    # end if
    path = re.sub(r"\.git$", "", path.strip("/"))
    return f"{host}/{path}" if host else f"/{path}"
# end def


def url_path(url: str, repo: Path) -> str:
    """Turn a remote URL into `host/owner/repo` for the tag namespace."""
    home_git = Path.home() / "git"
    if re.match(URL_RE, url):
        parts = urlsplit(url)
        host, path = parts.hostname or "", parts.path  # hostname drops user:pw@ and :port
    elif m := re.match(SCP_RE, url):
        host, path = m.group(1), m.group(2)
    else:
        resolved = repo.resolve()
        host, path = "local", str(resolved.relative_to(home_git)) if resolved.is_relative_to(home_git) else repo.name
    # end if
    path = re.sub(r"\.git$", "", path.strip("/"))
    out = "/".join(p for p in [host, path] if p)
    out = re.sub(r"[^A-Za-z0-9._/+-]", "_", out)
    return "/".join(("_" + c if c.startswith(".") else re.sub(r"\.lock$", "_lock", c)) for c in out.split("/") if c)
# end def


def origin_name(repo: Path) -> str | None:
    remotes = git(repo, "remote").stdout.split()
    return "origin" if "origin" in remotes else None
# end def


def origin_url(repo: Path) -> str:
    name = origin_name(repo)
    if name is None:
        remotes = git(repo, "remote").stdout.split()
        name = remotes[0] if remotes else None
    # end if
    return git(repo, "remote", "get-url", name).stdout.strip() if name else ""
# end def


def has_object(repo: Path, sha: str) -> bool:
    return git(repo, "cat-file", "-e", f"{sha}^{{commit}}", check=False).returncode == 0
# end def


def has_empty(repo: Path, bak_repo: str, dry: bool) -> bool:
    """Whether the empty commit object is usable for the `-rebased-` variant. Never fetches in a dry run."""
    if dry or has_object(repo, EMPTY):
        return True  # dry run: assume it can be fetched
    # end if
    git(repo, "fetch", "-q", "--no-tags", bak_repo, "refs/heads/mane", check=False)  # bak/mane == EMPTY
    if not has_object(repo, EMPTY):
        git(repo, "fetch", "-q", "--no-tags", EMPTY_URL, "init", check=False)  # hardcoded fallback
    # end if
    return has_object(repo, EMPTY)
# end def


def rebase_on_empty(repo: Path, sha: str) -> str | None:
    tmp = tempfile.mkdtemp(prefix="bakrebase-")
    try:
        git(repo, "worktree", "add", "--detach", "-q", tmp, sha)
        cfg = ["-c", "core.hooksPath=/dev/null", "-c", "filter.lfs.required=false",
               "-c", "filter.lfs.smudge=", "-c", "filter.lfs.process="]
        r = subprocess.run(["git", "-C", tmp, *cfg, "rebase", "--root", "--onto", EMPTY, "--rebase-merges"],
                           text=True, capture_output=True, env={**os.environ, **IDENT})
        if r.returncode != 0:
            subprocess.run(["git", "-C", tmp, "rebase", "--abort"], capture_output=True)
            print(f"  ! rebase onto empty failed, skipping -rebased- variant: {r.stderr.strip()[:200]}", file=sys.stderr)
            return None
        # end if
        return git(tmp, "rev-parse", "HEAD").stdout.strip()
    finally:
        git(repo, "worktree", "remove", "--force", tmp, check=False)
        shutil.rmtree(tmp, ignore_errors=True)
    # end try
# end def


def ref_kind(repo: Path, name: str) -> str | None:
    if git(repo, "show-ref", "--verify", "-q", f"refs/tags/{name}", check=False).returncode == 0:
        return "tag"
    # end if
    if git(repo, "show-ref", "--verify", "-q", f"refs/heads/{name}", check=False).returncode == 0:
        return "branch"
    # end if
    return None
# end def


def push_ref(repo: Path, bak_repo: str, sha: str, ref: str) -> bool:
    result = git(repo, "push", "--force", "-q", bak_repo, f"{sha}:refs/tags/{ref}", check=False)
    if result.returncode != 0:
        print(f"  ! push failed for {ref}: {result.stderr.strip()[:200]}", file=sys.stderr)
    # end if
    return result.returncode == 0
# end def


def origin_tag_sha(repo: Path, remote: str, name: str) -> str | None:
    """Commit the tag `name` points to on `remote` (peeled for annotated tags), `None` if absent or unreachable."""
    result = git(repo, "ls-remote", "--tags", remote, f"refs/tags/{name}", f"refs/tags/{name}^{{}}", check=False)
    if result.returncode != 0:
        return None
    # end if
    shas: dict[str, str] = {}
    for line in result.stdout.splitlines():
        sha, _, ref = line.partition("\t")
        shas[ref] = sha
    # end for
    return shas.get(f"refs/tags/{name}^{{}}") or shas.get(f"refs/tags/{name}")
# end def


def delete_on_origin(repo: Path, name: str, sha: str, bak_repo: str, dry: bool) -> None:
    remote = origin_name(repo)
    if remote is None:
        print(f"  - {name}: no origin, not deleted there")
        return
    # end if
    if normalize_url(git(repo, "remote", "get-url", remote).stdout.strip()) == normalize_url(bak_repo):
        print(f"  - {name}: origin is the backup repo, not deleted there")
        return
    # end if
    if origin_tag_sha(repo, remote, name) != sha:
        print(f"  - {name}: origin has no such tag at {sha[:10]}, not deleted there")
        return
    # end if
    print(f"  {'DRY would delete' if dry else 'delete'} {name} on {remote}")
    if not dry and git(repo, "push", "-q", remote, f":refs/tags/{name}", check=False).returncode != 0:
        print(f"  ! could not delete {name} on {remote}", file=sys.stderr)
    # end if
# end def


def process(repo: Path, names: list[str], cfg: BackupTags, dry: bool) -> None:
    empty_ok = has_empty(repo, cfg.repo, dry)
    base = url_path(origin_url(repo), repo)
    if not names:
        names = git(repo, "tag", "--list", "bak/*").stdout.split()
    # end if
    for name in names:
        kind = ref_kind(repo, name)
        if kind is None:
            print(f"  - {name}: not found, skipped")
            continue
        # end if
        sha = git(repo, "rev-parse", f"{name}^{{commit}}").stdout.strip()
        prefix = f"bak/{SEP}/{base}/{SEP}/{kind}"
        # a missing empty object simply means "not an ancestor", so no fetch is needed here
        on_empty = git(repo, "merge-base", "--is-ancestor", EMPTY, sha, check=False).returncode == 0
        main_ref = f"{prefix}/{'on-empty' if on_empty else 'no-empty'}/{SEP}/{name}"
        jobs: list[tuple[str, str, bool]] = [(main_ref, sha, True)]  # (ref, sha, required)
        if not on_empty and empty_ok:
            rebased = "(would be rebased)" if dry else rebase_on_empty(repo, sha)
            if rebased:
                jobs.append((f"{prefix}/-rebased-/{SEP}/{name}", rebased, False))
            # end if
        # end if
        ok = True
        for ref, s, required in jobs:
            if git(repo, "check-ref-format", f"refs/tags/{ref}", check=False).returncode != 0:
                print(f"  ! invalid ref name, skipped: {ref}")
                ok = ok and not required
                continue
            # end if
            print(f"  {'DRY ' if dry else ''}{s[:10]} -> {ref}")
            if not dry:
                if not push_ref(repo, cfg.repo, s, ref) and required:
                    ok = False
                # end if
            # end if
        # end for
        if kind != "tag" or not ok:
            continue
        # end if
        if cfg.delete_origin:
            delete_on_origin(repo, name, sha, cfg.repo, dry)
        # end if
        if cfg.delete_local:
            print(f"  {'DRY would delete' if dry else 'delete'} {name} locally")
            if not dry:
                git(repo, "tag", "-d", name)
            # end if
        # end if
    # end for
# end def
