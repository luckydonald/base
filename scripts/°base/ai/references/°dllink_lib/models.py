from __future__ import annotations

import dataclasses
from pathlib import Path
from typing import Callable, Iterator


class DownloadError(RuntimeError):
    pass


@dataclasses.dataclass(frozen=True)
class Response:
    url: str
    status: int
    content: bytes
    content_type: str = ""

    @property
    def text(self) -> str:
        return self.content.decode("utf-8", errors="replace")


@dataclasses.dataclass(frozen=True)
class DownloadPlan:
    source_url: str
    download_url: str
    output_path: Path
    convert_html: bool
    link_paths: tuple[Path, ...] = ()


@dataclasses.dataclass(frozen=True)
class DownloadResult:
    path: Path
    content: bytes
    downloaded_url: str
    archive_timestamp: str | None = None

    def __iter__(self) -> Iterator[Path | bytes]:
        yield self.path
        yield self.content
    # end def


Fetch = Callable[[str, str], Response]
