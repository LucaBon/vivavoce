"""The artwork proxy's upstream fetch: one cover, bounded.

Its own module because the cover URL is not ours to trust. It comes from
whatever a radio stream or a streaming plugin reported to the music server,
so it can point at something that is not an image, or at something that never
ends, and the fetch is where both are refused.
"""

from __future__ import annotations

import urllib.request

#: The largest cover the artwork proxy will hold in memory, in bytes. Covers
#: are tens of KB; the URL comes from whatever a radio or a plugin reported,
#: and a stream announced as a cover was read whole into RAM on every poll.
MAX_ARTWORK_BYTES = 5 * 1024 * 1024


def fetch(url: str, timeout: float = 5.0, *, urlopen=None):
    """GET ``url`` returning ``(content_type, bytes)`` — the artwork proxy's
    default transport (injectable in tests).

    The type is checked before a byte is read, and the body is read up to
    :data:`MAX_ARTWORK_BYTES` and no further: raising ``ValueError`` past
    either, which the caller answers with its usual 404.
    """
    urlopen = urlopen or urllib.request.urlopen
    with urlopen(url, timeout=timeout) as resp:
        ctype = resp.headers.get("Content-Type") or "image/jpeg"
        if not ctype.lower().startswith("image/"):
            raise ValueError(f"not an image: {ctype}")
        data = resp.read(MAX_ARTWORK_BYTES + 1)
        if len(data) > MAX_ARTWORK_BYTES:
            raise ValueError("artwork too large")
        return ctype, data
