"""The web assets the server ships: the page, the PWA shell, static/ on disk.

Everything here answers "what bytes for this path?"; the HTTP routing that
calls it lives in ``http_api.py``. Two serving policies on purpose:

* re-read per request (the page, ``static/``): an edit lands with a refresh,
  no server restart. Negligible cost on a home LAN.
* read once at import (``STATIC``): the PWA shell files, which change only
  with the code itself.
"""

from __future__ import annotations

import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))


def index_html() -> str:
    with open(os.path.join(HERE, "index.html"), encoding="utf-8") as f:
        return f.read()


def index_page(*, material_url: str, services, service_labels, langs,
               version: str, browse) -> str:
    """``index.html`` with every server-side placeholder filled in.

    ``json.dumps`` for all but the Material URL, which is an href: the rest
    land inside the page's inline config script and have to arrive as JS
    literals — a quoted string, an array, an object — rather than as bare
    text. A token left unfilled is a SyntaxError that kills that script and
    takes the source selector with it, which is why
    ``test_index_leaves_no_placeholder_behind`` exists.
    """
    page = index_html()
    for token, value in (
            ("__MATERIAL_URL__", material_url),
            ("__SERVICES__", json.dumps(list(services))),
            ("__SERVICE_LABELS__", json.dumps(service_labels)),
            ("__LANGS__", json.dumps(langs)),
            ("__VERSION__", json.dumps(version)),
            ("__BROWSE__", json.dumps(browse))):
        page = page.replace(token, value)
    return page


def _read_bytes(name: str) -> bytes:
    with open(os.path.join(HERE, name), "rb") as f:
        return f.read()


STATIC = {
    "/manifest.webmanifest": (_read_bytes("manifest.webmanifest"),
                              "application/manifest+json"),
    "/sw.js": (_read_bytes("sw.js"), "text/javascript"),
    "/icon-192.png": (_read_bytes("icon-192.png"), "image/png"),
    "/icon-512.png": (_read_bytes("icon-512.png"), "image/png"),
}

# La UI vive in localvoice/static/ (moduli ES + CSS). Solo estensioni note:
# il resto è un 404.
STATIC_DIR = os.path.join(HERE, "static")
STATIC_TYPES = {".js": "text/javascript", ".css": "text/css",
                ".png": "image/png", ".svg": "image/svg+xml"}


def static_file(url_path: str):
    """``(bytes, content_type)`` for a ``/static/...`` URL, or ``None`` when
    the path escapes the static dir, has an unknown extension or is missing."""
    relative = os.path.normpath(url_path.lstrip("/"))
    full = os.path.normpath(os.path.join(HERE, relative))
    if not full.startswith(STATIC_DIR + os.sep):
        return None
    ctype = STATIC_TYPES.get(os.path.splitext(full)[1].lower())
    if not ctype:
        return None
    try:
        with open(full, "rb") as f:
            return f.read(), ctype
    except OSError:
        return None
