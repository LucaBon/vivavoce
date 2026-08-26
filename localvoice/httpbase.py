"""Request plumbing shared by every route: replies, bodies, and the
cross-site gate.

Split out of ``http_api.py``, which had grown past the 400-line ceiling the
repo sets itself (see ``tests/test_packaging.py``). The seam is the one
between *how a request is read and answered* and *what each route does*:
nothing here knows about players, licenses or the blocklist, and everything
here is what keeps the "never a 5xx" promise — a body that is bounded before
it is read, a Content-Length that can't raise, a refusal that still drains
the connection.

``RequestBase`` is a mixin over ``BaseHTTPRequestHandler``; ``http_api``
supplies the ``host_policy`` class attribute when it builds the handler.
"""

from __future__ import annotations

import json
import socket
import threading
from http.server import ThreadingHTTPServer

import webguard

# A spoken command is a few hundred bytes; the JSON routes take a body at all
# only to carry one. 64 KB is a wide margin and turns an upload bomb into a
# refusal instead of a buffer.
MAX_JSON_BYTES = 64 * 1024

# A LAN client that opens a connection and then goes quiet — or announces a
# Content-Length it never sends — used to pin a thread for good: there was no
# timeout anywhere, and the thread pool is unbounded (see server.py). Thirty
# seconds is far more than any real request here needs.
REQUEST_TIMEOUT = 30


class RequestBase:
    """Reply helpers, guarded body reads, and the cross-site refusal."""

    # HTTP/1.1, so a browser reuses one connection instead of paying a fresh
    # TCP+TLS handshake per request. The wake word streams ~12 chunks a second
    # per phone; on a Pi those handshakes cost more CPU than the detection did.
    # Every response this app sends carries a Content-Length, which is what
    # makes keep-alive safe here.
    protocol_version = "HTTP/1.1"
    # socketserver applies this to the connection socket: a half-open or
    # silent client releases its thread instead of holding it forever.
    timeout = REQUEST_TIMEOUT
    # Set by make_handler: which Host values this server acts on.
    host_policy = None

    def _send(self, code, body, ctype="application/json"):
        data = body.encode("utf-8") if isinstance(body, str) else body
        self.send_response(code)
        self.send_header("Content-Type", f"{ctype}; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _query_params(self) -> dict:
        """The request's query string, parsed once (``?a=1&b=2`` ->
        ``{"a": ["1"], "b": ["2"]}``)."""
        from urllib.parse import parse_qs, urlparse
        return parse_qs(urlparse(self.path).query)

    def content_length(self, cap=None) -> int:
        """The declared body length, sanitised.

        A missing, negative or non-numeric ``Content-Length`` reads as 0
        rather than raising: ``int("abc")`` used to escape uncaught and
        drop the connection with no response at all, which is exactly the
        5xx-shaped failure this module promises never to produce. A
        ``cap`` clamps the value, so an announced gigabyte is read as at
        most ``cap`` bytes.
        """
        try:
            length = int(self.headers.get("Content-Length", 0) or 0)
        except (TypeError, ValueError):
            return 0
        if length < 0:
            return 0
        return min(length, cap) if cap is not None else length

    def _read_json_object(self) -> dict:
        """The POST body as a JSON object, or ``{}`` on anything else —
        absent body, malformed JSON, *or* valid JSON that isn't an
        object (``null``, a number, a list, a bare string). That last
        case is not a ``ValueError``: ``json.loads`` happily returns it,
        and a bare ``.get()`` on it would raise ``AttributeError`` —
        uncaught, that drops the connection with no response, breaking
        this module's own "never a 5xx" guarantee.

        Bounded at MAX_JSON_BYTES, and whatever is left over is drained:
        with keep-alive on, an unread remainder desynchronises the
        connection and the *next* request on it fails too.
        """
        declared = self.content_length()
        length = min(declared, MAX_JSON_BYTES)
        raw = self.rfile.read(length) if length else b"{}"
        remaining = declared - length
        while remaining > 0:                       # drain the excess
            chunk = self.rfile.read(min(remaining, 65536))
            if not chunk:
                break
            remaining -= len(chunk)
        if declared > MAX_JSON_BYTES:
            return {}
        try:
            payload = json.loads(raw.decode("utf-8"))
        except (ValueError, UnicodeDecodeError):
            return {}
        return payload if isinstance(payload, dict) else {}

    # -- cross-site protection -----------------------------------------
    # There is no auth here by design (LAN only, no accounts), which makes
    # every POST a CSRF target: any page open on a phone on the same
    # network could fire /player (volume 100), /command, or /kidsafe
    # "enable" with a PIN of its own choosing — locking the parent out of
    # the feature meant to protect their child. Three cheap checks close
    # it; see webguard.py for what each one is for.
    def _reject_cross_site(self) -> bool:
        """True (and a 403 already sent) when this request must not act."""
        reason = webguard.cross_site_reason(
            self.headers, self.host_policy,
            require_json=self.path.split("?", 1)[0] in webguard.JSON_ROUTES)
        if reason is None:
            return False
        # Drain first: a refusal that leaves the body unread desynchronises
        # a keep-alive connection.
        declared = self.content_length()
        while declared > 0:
            chunk = self.rfile.read(min(declared, 65536))
            if not chunk:
                break
            declared -= len(chunk)
        self._send(403, json.dumps({"ok": False, "error": reason}))
        return True


# How many connections may be open at once. ThreadingHTTPServer spawns one
# thread per connection with no ceiling: a client opening connections and
# going quiet used to grow that without limit (each thread also had no socket
# timeout — see REQUEST_TIMEOUT above).
#
# The number counts CONNECTIONS, not requests: with keep-alive on, a browser
# holds several open per origin and each occupies its thread until it goes
# idle for REQUEST_TIMEOUT. 128 is therefore roughly twenty devices at once,
# which no household reaches, while still being a ceiling — the point is that
# an attacker cannot make it unbounded, not that it is small.
MAX_CONCURRENT_REQUESTS = 128


class BoundedThreadingHTTPServer(ThreadingHTTPServer):
    """ThreadingHTTPServer with a ceiling on concurrent request threads.

    Over the ceiling the connection is closed rather than queued: this is a
    LAN app talking to a browser that will retry, and a queue that grows is
    the same unbounded resource by another name.
    """

    max_workers = MAX_CONCURRENT_REQUESTS

    def __init__(self, *args, **kwargs):
        self._slots = threading.BoundedSemaphore(self.max_workers)
        super().__init__(*args, **kwargs)

    def process_request(self, request, client_address):
        # Acquire before the thread is spawned, release when its body ends
        # (process_request_thread below) — so the count tracks live handlers,
        # not connections accepted.
        if not self._slots.acquire(blocking=False):
            self.shutdown_request(request)
            return
        try:
            super().process_request(request, client_address)
        except BaseException:
            self._slots.release()
            raise

    def process_request_thread(self, request, client_address):
        try:
            super().process_request_thread(request, client_address)
        finally:
            self._slots.release()

    def handle_error(self, request, client_address):
        """A dropped connection is not an error worth a traceback.

        With keep-alive on (see RequestBase.protocol_version) the server holds
        connections open, so every phone that locks its screen or walks out of
        Wi-Fi range ends one abruptly — and the stdlib default prints a full
        stack trace for each, to a console this app otherwise keeps silent.
        Anything else still gets reported.
        """
        import sys
        if isinstance(sys.exc_info()[1], (ConnectionError, TimeoutError,
                                          socket.timeout)):
            return
        super().handle_error(request, client_address)
