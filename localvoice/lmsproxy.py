"""Reverse proxy for the LMS: what this server does not own, it forwards.

Material Skin — browsing, the queue, the covers — is a plugin on the music
server the household already runs, and the page has always linked to it.
Opening it *inside* the page needs it to arrive under **this** origin: the
page is HTTPS (a microphone on another device requires a secure context) and
the LMS is plain HTTP, so an ``<iframe>`` pointed straight at it is mixed
content and the browser blocks it without appeal. The artwork proxy in
``http_api.py`` exists for that exact reason, one ``<img>`` at a time; this is
the same idea for a whole application.

**Catch-all, not a prefix.** Material asks for ``/cometd``, ``/jsonrpc.js``,
``/music/``, ``/imageproxy/``, ``/plugins/`` and ``/settings/`` by absolute
path, so a rewritten prefix would break every one of them. Everything that
would otherwise reach the final 404 of ``do_GET``/``do_POST`` is offered here
first, and only what upstream cannot answer comes back as a miss.

**What is deliberately not here: any check on who is asking.** ``do_GET`` has
already been through the Host allow-list and ``do_POST`` through the
cross-site guard (``httpbase.RequestBase``), both before routing, so the
proxied requests inherit them for free — from the same-origin iframe
``Sec-Fetch-Site`` says ``same-origin`` and passes; from somebody else's page
it says ``cross-site`` and is refused. Nothing in ``webguard.py`` needed
touching, and nothing here may grow a second, weaker copy of it.

Not a general-purpose proxy either: the target is fixed at startup and the
request path is appended to it, so there is no way to ask this for a host of
your choosing.

What it does widen, and this is worth saying out loud: whatever the LMS
serves now also answers under *this* origin, so an HTML page that machine
hands out is same-origin with the app — and ``Sec-Fetch-Site: same-origin``
is the whole of this server's CSRF defence. Embedding Material Skin *is*
trusting the music server as much as the app itself; there is no version of
framing somebody's UI that does not. What the proxy does not add is a way to
reach a *different* machine: the target is a startup constant and nothing a
request can influence, and ``nosniff`` below at least stops a body being
executed as a type it did not claim.

Known limit: a response that stays open holds its handler thread for as long
as it lasts (``UPSTREAM_TIMEOUT`` bounds one socket operation, not a whole
reply). CometD's long poll is one per open Material tab, and audio streamed
through the panel is one per stream, against the 128-connection ceiling in
``httpbase.BoundedThreadingHTTPServer``. Fine for a household; it is not a
proxy to put in front of a hundred listeners.
"""

from __future__ import annotations

import urllib.error
import urllib.request
from urllib.parse import urlsplit

# CometD is long-polling: the LMS holds the connection open on purpose until
# it has something to say. A timeout of the size a normal request wants would
# turn Material's live now-playing into a stream of gateway errors.
UPSTREAM_TIMEOUT = 70

# Copied through in blocks rather than buffered: `_send()` takes a whole body,
# which is the wrong shape for a JS bundle, a cover or a track download.
BLOCK = 64 * 1024

# Request bodies here are JSON-RPC and CometD envelopes — a few KB. The
# ceiling exists only so an announced gigabyte is a refusal instead of a
# buffer, the same reasoning as httpbase.MAX_JSON_BYTES.
MAX_BODY = 4 * 1024 * 1024

# Forwarded upstream, lowercased. An allow-list, so nothing hop-by-hop
# (Connection, Transfer-Encoding, Upgrade) survives into a request we then
# re-frame ourselves. Cookie is in it because the LMS settings pages need it,
# and it is this origin's own cookie jar: same-origin, sent by the browser to
# us, meant for the server we are standing in front of.
REQUEST_HEADERS = frozenset({
    "accept", "accept-language", "authorization", "content-type", "cookie",
    "range", "if-none-match", "if-modified-since",
})

# Sent back, lowercased. WWW-Authenticate is in it because the LMS web
# interface can be password-protected, and a challenge stripped on the way
# back is a browser that never asks for the password and a panel that never
# loads, with nothing on screen to explain why.
#
# No Content-Encoding: the stdlib client announces ``Accept-Encoding:
# identity`` for us (pinned by a test — it is what makes this omission safe),
# so a body arrives uncompressed and a compression header would describe
# bytes we do not have.
RESPONSE_HEADERS = frozenset({
    "content-type", "content-length", "content-range", "content-disposition",
    "accept-ranges", "cache-control", "expires", "etag", "last-modified",
    "location", "set-cookie", "vary", "www-authenticate",
})

# Statuses that carry no body at all, whatever else the headers say.
NO_BODY = (204, 304)


def browse_path(material_url: str, lms_base_url: str) -> str:
    """The path to open in the page, or ``""`` when it cannot be opened there.

    Embedding is possible exactly when the UI we would open lives on the
    server we are already talking to — that is the one case where forwarding
    what this app does not own reaches the right machine. Point
    ``--material-url`` at anything else (another host, a Material behind its
    own proxy) and this answers ``""``: no reverse proxy, no in-page panel,
    and the page falls back to the external link it has always had.

    That is the whole escape hatch, and it costs ``server.py`` — sitting
    exactly on the repo's 400-line ceiling — not one line.
    """
    material, lms = urlsplit(material_url), urlsplit(lms_base_url)
    if material.netloc != lms.netloc:
        return ""
    return material.path or "/material/"


def _same_origin_location(value: str, base: str) -> str:
    """An upstream redirect to itself, rewritten to a path under this origin.

    ``http://lms.local:9000/material/`` is the ordinary shape of a
    trailing-slash redirect, and relaying it verbatim would send the frame
    straight back to plain HTTP — the mixed-content block this whole module
    exists to get around. As a path it stays here. A Location pointing
    anywhere else is left exactly as it is: that one really is somewhere else.
    """
    if value == base:
        return "/"
    return value[len(base):] if value.startswith(base + "/") else value


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    """Hand a redirect back to the browser instead of following it.

    Material's own URLs are what the browser must end up on; a redirect
    resolved here would hide the destination from it and desynchronise the
    address bar of the frame. Returning ``None`` makes urllib raise the
    response as an ``HTTPError``, which ``_proxy`` relays like any other.
    """

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


_OPENER = urllib.request.build_opener(_NoRedirect)


def _urlopen(request, timeout):
    return _OPENER.open(request, timeout=timeout)


def proxy_routes(target_base: str, enabled, opener=None):
    """A mixin whose ``_proxy()`` forwards anything to ``target_base``.

    ``enabled`` is truthy exactly when the UI we would open lives on the
    server we are already talking to (``http_api`` passes the browse path).
    Falsy, the mixin is inert: ``_proxy()`` answers ``False`` without reading
    or sending anything, and every caller falls back to the 404 it sent
    before. That is the escape hatch for ``--material-url`` pointed elsewhere.

    ``opener`` is the upstream transport, injectable the way ``artwork_fetch``
    is on ``make_handler`` — which is what keeps every test in this repo off
    the network.
    """
    base = (target_base or "").rstrip("/")
    opener = opener or _urlopen

    class ProxyRoutes:
        """Mixed into ``Handler``; see ``http_api.make_handler``."""

        def _proxy(self) -> bool:
            """True when this request was answered from upstream (or refused
            on its way there); False when the proxy is off or has no business
            with the path, and the caller should 404 as it always did."""
            if not enabled or not self.path.startswith("/"):
                # An absolute-form request line ("GET http://elsewhere/") is
                # what a client asks a *forward* proxy; this is not one.
                return False
            if self.command == "GET" and self._reject_cross_site():
                # do_POST runs this ahead of every route; do_GET deliberately
                # does not, because for the routes this server owns a GET is
                # safe to trigger cross-site — the answer cannot be read. That
                # reasoning stops at the proxy: the LMS classic interface acts
                # on GET (`/status.html?p0=power&p1=0`), so a cross-site GET
                # arriving here is a command, not a read. Worse, it would be a
                # NEW way in: an https:// page cannot touch the plain-HTTP LMS
                # at all today, and this origin would hand it the trip.
                return True
            if (self.headers.get("Transfer-Encoding") or "").strip():
                # content_length() cannot size a chunked body, so it would
                # read as 0 and the bytes would stay in the buffer for the
                # NEXT request on this keep-alive connection to be parsed out
                # of — the desync the drain loops in httpbase exist to avoid.
                self.close_connection = True
                self._send(411, "length required", "text/plain")
                return True
            body = self._proxy_body()
            if body is False:
                return True                    # already refused, see below
            request = urllib.request.Request(base + self.path, data=body,
                                             method=self.command)
            for name, value in self.headers.items():
                if name.lower() in REQUEST_HEADERS:
                    request.add_header(name, value)
            try:
                response = opener(request, UPSTREAM_TIMEOUT)
            except urllib.error.HTTPError as err:
                # An upstream 404, 304 or redirect is an answer, not a fault.
                response = err
            except Exception:
                # The one deliberate 5xx in this server, and it is the honest
                # code: the "never a 5xx" promise is about the JSON routes the
                # page leans on, and a gateway that cannot reach its upstream
                # *is* a gateway error. Dressing it as a 404 would make "the
                # plugin isn't installed" indistinguishable from "the hi-fi is
                # switched off", which are different rooms to walk to.
                self._send(502, "music server unreachable", "text/plain")
                return True
            try:
                self._relay(response)
            finally:
                response.close()
            return True

        def _proxy_body(self):
            """The body to forward: ``bytes`` (or ``None`` on a bodyless GET),
            or ``False`` when the request was already refused for size."""
            declared = self.content_length()
            if declared > MAX_BODY:
                while declared > 0:            # drain, or keep-alive desyncs
                    chunk = self.rfile.read(min(declared, BLOCK))
                    if not chunk:
                        break
                    declared -= len(chunk)
                self._send(413, "body too large", "text/plain")
                return False
            if declared:
                return self.rfile.read(declared)
            # A POST still needs an (empty) body or urllib sends no
            # Content-Length and the LMS waits for one that never comes.
            return None if self.command == "GET" else b""

        def _relay(self, response):
            """Copy status, the allowed headers and the body back to the
            client, in blocks."""
            status = getattr(response, "status", None) or response.code
            self.send_response(status)
            has_length = False
            for name, value in response.headers.items():
                if name.lower() not in RESPONSE_HEADERS:
                    continue
                has_length = has_length or name.lower() == "content-length"
                if name.lower() == "location":
                    value = _same_origin_location(value, base)
                self.send_header(name, value)
            # Upstream's own type, but never a guess past it: this origin now
            # serves whatever the music server hands out, and sniffing is one
            # way a body becomes a document it never claimed to be. The
            # artwork proxy says the same thing one image at a time.
            self.send_header("X-Content-Type-Options", "nosniff")
            bodyless = status in NO_BODY
            if not has_length and not bodyless:
                # HTTP/1.1 with no length has to be delimited by the close
                # instead. Every other response this server sends carries a
                # Content-Length — that is what makes keep-alive safe here
                # (httpbase.RequestBase.protocol_version) — so this is the one
                # place that has to say otherwise. send_header notices the
                # value and sets close_connection itself.
                self.send_header("Connection", "close")
            self.end_headers()
            if bodyless:
                return
            while True:
                block = response.read(BLOCK)
                if not block:
                    break
                self.wfile.write(block)

    return ProxyRoutes
