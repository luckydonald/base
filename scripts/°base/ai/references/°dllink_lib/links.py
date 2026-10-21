from __future__ import annotations

import os
from pathlib import Path

from .models import DownloadError


def write_symlink(target: Path, link: Path) -> None:
    """Create `link` as a relative soft symlink to `target`, replacing an older file or symlink."""
    if link.is_dir() and not link.is_symlink():
        raise DownloadError(f"refusing to replace directory with symlink: {link}")
    # end if
    link.parent.mkdir(parents=True, exist_ok=True)
    if link.is_symlink() or link.exists():
        link.unlink()
    # end if
    relative = os.path.relpath(target.resolve(), link.parent.resolve())
    link.symlink_to(relative)
# end def
