"""TLS for the local web server.

The mic (Web Speech / getUserMedia) needs a secure context when the page is
opened from another device, so the server can wrap its socket with the
self-signed certificate ``tools/make_cert.py`` generates — and serve the
local CA next to it for the one-time install that turns the padlock green.
"""

from __future__ import annotations

import os
import socket
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
    """Serve this server over TLS, one handshake per connection thread.

    The obvious implementation — wrapping the *listening* socket once — is a
    trap, and it cost this server every phone on the LAN. ``SSLSocket.accept()``
    runs the handshake itself, in the accept loop, with no timeout: a single
    client that opens the socket and says nothing blocks that loop forever, and
    with it every other device. Browsers do exactly that all the time (they
    open speculative connections and abandon them), so the symptom was a page
    that loaded once and then hung or reset for good.

    So the listening socket stays plain and each accepted connection is wrapped
    in the worker thread that will serve it, bounded by the handler's own
    timeout. A stalled or hostile client now costs one thread — which the
    server already caps — instead of the whole server.
    """
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    ctx.load_cert_chain(cert_path, key_path)

    # One source of truth for "how long may a silent client hold a thread":
    # the same timeout the handler applies to a request that has connected.
    handshake_timeout = getattr(httpd.RequestHandlerClass, "timeout", None) or 30

    def finish_request(request, client_address) -> None:
        request.settimeout(handshake_timeout)
        # wrap_socket() takes the file descriptor over and detaches `request`,
        # so the caller's shutdown_request() can no longer close it — this
        # connection is ours to close.
        conn = ctx.wrap_socket(request, server_side=True)
        try:
            httpd.RequestHandlerClass(conn, client_address, httpd)
        finally:
            try:
                conn.shutdown(socket.SHUT_WR)
            except OSError:
                pass
            conn.close()

    # Bound to the instance rather than the class: wrap_server() is handed a
    # server that is already built, and may be any socketserver flavour.
    httpd.finish_request = finish_request
