"""TLS for the local web server.

The mic (Web Speech / getUserMedia) needs a secure context when the page is
opened from another device, so the server can wrap its socket with the
self-signed certificate ``tools/make_cert.py`` generates — and serve the
local CA next to it for the one-time install that turns the padlock green.
"""

from __future__ import annotations

import os
import ssl
from typing import Optional


def find_ca(cert_path: Optional[str]) -> Optional[str]:
    """The local CA (if make_cert created one) lives next to the certificate;
    the handler serves it as /ca.pem."""
    if not cert_path:
        return None
    candidate = os.path.join(os.path.dirname(os.path.abspath(cert_path)),
                             "ca.pem")
    return candidate if os.path.exists(candidate) else None


def wrap_server(httpd, cert_path: str, key_path: str) -> None:
    """Swap the server socket for its TLS twin (in place)."""
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    ctx.load_cert_chain(cert_path, key_path)
    httpd.socket = ctx.wrap_socket(httpd.socket, server_side=True)
