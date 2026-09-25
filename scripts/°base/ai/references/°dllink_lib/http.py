from __future__ import annotations

import gzip
import urllib.error
import urllib.request
import zlib

from .log import log
from .models import DownloadError, Response


USER_AGENT = "base-download-link/1.0"


def decode_content(content: bytes, content_encoding: str) -> bytes:
    encoding = content_encoding.lower().strip()
    if encoding == "gzip":
        return gzip.decompress(content)
    # end if
    if encoding == "deflate":
        return zlib.decompress(content)
    # end if
    return content
# end def


def fetch_url(url: str, method: str = "GET") -> Response:
    request = urllib.request.Request(
        url,
        method=method,
        headers={
            "User-Agent": USER_AGENT,
            "Accept": "text/markdown,text/html,application/json,text/plain,*/*",
        },
    )
    log(f"{method} {url}")
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            content = b"" if method == "HEAD" else decode_content(
                response.read(), response.headers.get("Content-Encoding", "")
            )
            final_url = response.geturl()
            if final_url != url:
                log(f"redirect: {url} -> {final_url}")
            # end if
            status = int(response.status)
            content_type = response.headers.get("Content-Type", "")
            log(f"<- {status} {content_type}".rstrip())
            return Response(
                url=final_url,
                status=status,
                content=content,
                content_type=content_type,
            )
    except urllib.error.HTTPError as exc:
        content = b"" if method == "HEAD" else decode_content(
            exc.read(), exc.headers.get("Content-Encoding", "")
        )
        exc.close()
        log(f"<- {int(exc.code)} (error)")
        return Response(
            url=url,
            status=int(exc.code),
            content=content,
            content_type=exc.headers.get("Content-Type", ""),
        )
    except urllib.error.URLError as exc:
        raise DownloadError(f"fetch failed for {url}: {exc}") from exc
