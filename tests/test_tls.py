"""HTTPS: one slow client must not be able to stop the server.

The obvious way to serve TLS from a ``socketserver`` — wrap the *listening*
socket once, at startup — puts the handshake inside ``SSLSocket.accept()``,
which is to say inside the accept loop, in the main thread, with no timeout.
That is what this server used to do, and the consequence was not subtle: one
client that opened a connection and said nothing wedged the whole server for
good, for every device in the house. Browsers produce such connections on
their own (they preconnect and then abandon), so in practice the page loaded
once and every later request hung or was reset.

These tests are the shape of that bug, not of its fix: they open connections
that never finish a handshake and then insist that an ordinary request still
gets an answer. Both of those fail against the wrapped listening socket — an
abandoned connection also stays queued behind the blocked accept(), which is
why in the field the server never recovered on its own.
"""

import http.client
import socket
import ssl
import subprocess
import sys
import threading
from http.server import BaseHTTPRequestHandler

import pytest

pytest.importorskip("cryptography",
                    reason="cryptography not installed (extra: tls)")

import tls  # noqa: E402
from httpbase import BoundedThreadingHTTPServer  # noqa: E402

from test_make_cert import ROOT  # noqa: E402


class _Hello(BaseHTTPRequestHandler):
    # Short, so a wedged accept loop shows up as a failure and not as a
    # test run that hangs until CI gives up.
    timeout = 5

    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-Length", "2")
        self.end_headers()
        self.wfile.write(b"ok")

    def log_message(self, *args):
        pass


@pytest.fixture(scope="module")
def certs(tmp_path_factory):
    """A real certificate from the real tool — 127.0.0.1 is among its SANs."""
    out = tmp_path_factory.mktemp("tls")
    proc = subprocess.run(
        [sys.executable, "tools/make_cert.py", "--out", str(out)],
        cwd=ROOT, capture_output=True, text=True)
    assert proc.returncode == 0, proc.stderr[-500:]
    return out / "cert.pem", out / "key.pem", out / "ca.pem"


@pytest.fixture
def https(certs):
    cert, key, _ca = certs
    httpd = BoundedThreadingHTTPServer(("127.0.0.1", 0), _Hello)
    tls.wrap_server(httpd, str(cert), str(key))
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    try:
        yield httpd.server_address[1]
    finally:
        httpd.shutdown()
        httpd.server_close()


@pytest.fixture
def get(https, certs):
    """A GET / over real TLS, verified against the real CA."""
    _cert, _key, ca = certs
    ctx = ssl.create_default_context(cafile=str(ca))

    def _get():
        conn = http.client.HTTPSConnection("127.0.0.1", https,
                                           context=ctx, timeout=5)
        try:
            conn.request("GET", "/")
            return conn.getresponse().status
        finally:
            conn.close()
    return _get


@pytest.fixture
def mute():
    """Connections that complete TCP and then say nothing at all."""
    opened = []

    def _mute(port, count=1):
        for _ in range(count):
            opened.append(socket.create_connection(("127.0.0.1", port),
                                                   timeout=5))
    yield _mute
    for sock in opened:
        sock.close()


def test_serves_over_tls_at_all(get):
    assert get() == 200


def test_a_silent_client_does_not_block_anyone(https, get, mute):
    mute(https)
    assert get() == 200


def test_a_crowd_of_silent_clients_does_not_either(https, get, mute):
    mute(https, count=6)
    assert get() == 200


def test_the_server_survives_a_failed_handshake(https, get):
    """Plain HTTP typed at the HTTPS port — the everyday handshake failure.

    This one is not a guard against the accept-loop bug (it passed under it
    too: socketserver catches the SSLError there and keeps looping). It is
    here for the other half of serving TLS — a failed handshake must cost its
    own connection and nothing more, and must not be reported as a crash.
    """
    conn = http.client.HTTPConnection("127.0.0.1", https, timeout=5)
    # The server drops it mid-handshake, which reaches the client either as a
    # closed connection or as an unparseable reply, depending on the timing.
    with pytest.raises((OSError, http.client.HTTPException)):
        conn.request("GET", "/")
        conn.getresponse()
    conn.close()
    assert get() == 200
