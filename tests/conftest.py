"""Shared test fixtures.

Adds the ``engine/`` directory to ``sys.path`` so tests can import ``lms`` and
``actions`` directly, and provides a scriptable fake transport that mimics the
LMS JSON-RPC server without any network access.

Also hosts the shared HTTP scaffolding (:func:`live_server`) used by every test
that exercises the real web handler, and the doubles those tests share.
"""

import json
import os
import sys
import threading
import urllib.error
import urllib.request

import pytest

ROOT = os.path.dirname(os.path.dirname(__file__))
ENGINE_DIR = os.path.join(ROOT, "engine")
LOCALVOICE_DIR = os.path.join(ROOT, "localvoice")
sys.path.insert(0, ENGINE_DIR)
sys.path.insert(0, LOCALVOICE_DIR)

import httpbase  # noqa: E402
import server  # noqa: E402
from lms import LMSClient, LMSError  # noqa: E402
from messages import set_lang  # noqa: E402


class FakeTransport:
    """Records every call and returns canned results keyed by command name.

    Usage::

        t = FakeTransport()
        t.responses["search"] = {"tracks_loop": [...]}
        t.raise_on.add("pause")   # simulate a server error for one command
    """

    def __init__(self):
        self.calls = []  # list of (player_id, [cmd, arg, ...])
        self.responses = {}
        self.raise_on = set()

    def __call__(self, params):
        player, cmd = params[0], params[1]
        self.calls.append((player, list(cmd)))
        name = cmd[0]
        if name in self.raise_on:
            raise LMSError(f"simulated failure for {name}")
        result = self.responses.get(name, {})
        return result(cmd) if callable(result) else result

    # -- convenience assertions -------------------------------------------
    def last_call(self):
        return self.calls[-1]

    def commands(self):
        """All issued commands as lists, e.g. ['pause', '1']."""
        return [cmd for _player, cmd in self.calls]


@pytest.fixture
def transport():
    return FakeTransport()


@pytest.fixture
def make_feed():
    """Factory for a fake streaming app-feed handler (3-level OPML navigation).

    Simulates a real plugin (TIDAL, Qobuz — the handler never looks at the
    feed tag, so key it under any service): home menu exposes a 'search' node;
    entering it with ``search:`` returns category nodes; entering a category id
    returns its items; and ``["<tag>","playlist","play",...]`` is the container
    play action.

    Wire it up with::

        transport.responses["tidal"] = make_feed(
            categories={"Songs": "S", "Artists": "A"},
            items={"S": [{"isaudio": 1, "url": "tidal://42.flc", "name": "Time"}]},
        )
    """

    def factory(search_node="7", categories=None, items=None):
        categories = categories or {}
        items = items or {}

        def handler(cmd):
            if len(cmd) > 1 and cmd[1] == "playlist":  # play_browse_item action
                return {}
            params = cmd[2:]
            item_id = None
            has_search = False
            for part in params:
                if part.startswith("item_id:"):
                    item_id = part[len("item_id:") :]
                elif part.startswith("search:"):
                    has_search = True
            if item_id is None:  # home menu -> search node
                return {"loop_loop": [{"id": search_node, "type": "search", "name": "Search"}]}
            if has_search:  # search node -> category list
                return {"loop_loop": [{"name": n, "id": i} for n, i in categories.items()]}
            return {"loop_loop": items.get(item_id, [])}  # category -> items

        return handler

    return factory


@pytest.fixture
def make_tidal(make_feed):
    """Backward-compatible alias for :func:`make_feed`."""
    return make_feed


@pytest.fixture
def lms(transport):
    return LMSClient(
        base_url="http://lms.local:9000",
        player_id="aa:bb:cc:dd:ee:ff",
        transport=transport,
    )


@pytest.fixture
def qobuz(transport):
    """An LMSClient bound to the Qobuz service, same fake transport."""
    return LMSClient(
        base_url="http://lms.local:9000",
        player_id="aa:bb:cc:dd:ee:ff",
        transport=transport,
        service="qobuz",
    )


# -- language isolation --------------------------------------------------------
# ``messages.set_lang()`` mutates process-global state, so a test that speaks
# English would otherwise leak English replies into every test that runs after
# it — an order-dependent failure that only shows up when the suite is
# reordered. Reset once, centrally, instead of per-module.

@pytest.fixture(autouse=True)
def reset_lang():
    yield
    set_lang("it")


# -- live HTTP server ----------------------------------------------------------
# The handler in ``localvoice/server.py`` is only reachable over HTTP: its
# routing table, JSON contracts and "never a 5xx" guarantees live in
# ``do_GET``/``do_POST``, not in any importable function. These helpers run the
# real handler on an ephemeral port so tests can exercise that stack for real.

DEFAULT_MATERIAL_URL = "http://lms.local:9000/material/"

# Material Skin on a host that is NOT the LMS we talk to. That switches the
# reverse proxy and the in-page panel off (see http_api.make_handler), which
# is the shape this server had before either existed: a path it does not own
# is a 404 and nothing is forwarded anywhere.
ELSEWHERE_MATERIAL_URL = "http://other.local:9000/material/"


def _no_upstream(request, timeout):
    """The proxy's transport for every test that did not ask for one.

    The proxy is on by default here (the fake LMS and DEFAULT_MATERIAL_URL
    share a host), so without this an unrouted path in any test would go and
    resolve ``lms.local`` for real — and no test in this repo touches the
    network. Tests about the proxy inject their own; everyone else gets an
    unreachable hi-fi, i.e. a 502, instantly.
    """
    raise OSError("no upstream in tests")



class Response:
    """One HTTP reply: status, headers, raw body — plus ``.json()``."""

    def __init__(self, status, headers, body):
        self.status = status
        self.headers = headers
        self.body = body

    def json(self):
        return json.loads(self.body)

    @property
    def text(self):
        return self.body.decode("utf-8")


class LiveServer:
    """A tiny HTTP client bound to one running handler.

    ``get``/``post`` raise ``HTTPError`` on a 4xx (the stdlib default, which
    existing tests assert on with ``pytest.raises``); ``try_get``/``try_post``
    return the error response instead, for tests that want to assert on a 404
    status directly.
    """

    def __init__(self, url):
        self.url = url

    # -- raw ------------------------------------------------------------------
    def get(self, path="/", timeout=5, headers=None):
        return self._open(
            urllib.request.Request(self.url + path, headers=headers or {}),
            timeout)

    def post(self, path, data=b"", content_type="application/json", timeout=5,
             headers=None):
        req = urllib.request.Request(
            self.url + path, data=data, method="POST",
            headers={"Content-Type": content_type, **(headers or {})})
        return self._open(req, timeout)

    def post_json(self, path, payload, timeout=5):
        return self.post(path, json.dumps(payload).encode("utf-8"),
                         timeout=timeout)

    # -- parsed-body shorthands, for the common "just assert on the JSON" case
    def json_get(self, path="/", timeout=5):
        return self.get(path, timeout).json()

    def json_post(self, path, payload, timeout=5):
        return self.post_json(path, payload, timeout).json()

    # -- non-raising variants -------------------------------------------------
    def try_get(self, path="/", timeout=5, headers=None):
        try:
            return self.get(path, timeout, headers)
        except urllib.error.HTTPError as exc:
            return Response(exc.code, dict(exc.headers), exc.read())

    def try_post(self, path, data=b"", content_type="application/json",
                 timeout=5, headers=None):
        try:
            return self.post(path, data, content_type, timeout, headers)
        except urllib.error.HTTPError as exc:
            return Response(exc.code, dict(exc.headers), exc.read())

    def try_post_json(self, path, payload, timeout=5):
        return self.try_post(path, json.dumps(payload).encode("utf-8"))

    @staticmethod
    def _open(req, timeout):
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return Response(resp.status, dict(resp.headers), resp.read())


@pytest.fixture
def live_server(lms):
    """Factory: the real ``make_handler`` stack on an ephemeral port.

    Every ``make_handler`` collaborator is overridable, so one fixture serves
    the artwork proxy, the ASR endpoints, kid-safe and multi-room alike::

        srv = live_server(kidsafe=KidSafe(...), license_mgr=FakeLicense())
        assert srv.get("/kidsafe?client=parent").json()["pro"] is True

    Servers started through the factory are shut down at teardown.
    """
    servers = []

    def start(client=None, material_url=DEFAULT_MATERIAL_URL,
              services=("tidal",), default_service="tidal", **kwargs):
        kwargs.setdefault("proxy_open", _no_upstream)
        handler = server.make_handler(client or lms, material_url,
                                      list(services), default_service,
                                      **kwargs)
        # The same server class the app runs (bounded threads, quiet on a
        # dropped connection) — a test stack that isn't it proves less.
        httpd = httpbase.BoundedThreadingHTTPServer(("127.0.0.1", 0), handler)
        threading.Thread(target=httpd.serve_forever, daemon=True).start()
        servers.append(httpd)
        return LiveServer(f"http://127.0.0.1:{httpd.server_address[1]}")

    yield start
    for httpd in servers:
        httpd.shutdown()


# -- shared doubles ------------------------------------------------------------
# Previously copy-pasted into each HTTP test module.

class UpstreamResponse:
    """What the reverse proxy's ``opener`` hands back.

    Just enough of an ``http.client`` response for ``lmsproxy`` to relay: a
    status, a header mapping it can iterate, and a body it reads in blocks.
    """

    def __init__(self, status=200, headers=(), body=b""):
        import email.message
        import io
        self.status = status
        self.headers = email.message.Message()
        pairs = headers.items() if hasattr(headers, "items") else headers
        for name, value in pairs:
            self.headers[name] = value
        self._body = io.BytesIO(body)
        self.closed = False

    def read(self, size=-1):
        return self._body.read(size)

    def close(self):
        self.closed = True


def material_page(request):
    """The default upstream: a small page, whatever was asked for."""
    return UpstreamResponse(200, [("Content-Type", "text/html; charset=utf-8")],
                            b"<!doctype html><title>Material</title><h1>Material</h1>")


class FakeUpstream:
    """A scriptable LMS behind the reverse proxy, recording every request.

    ``handler`` takes the ``urllib.request.Request`` and returns an
    :class:`UpstreamResponse` — or raises, which is how "the hi-fi is off"
    and "upstream said 404" are both written.
    """

    def __init__(self, handler=None):
        self.requests = []
        self.handler = handler or material_page

    def __call__(self, request, timeout):
        self.requests.append(request)
        self.timeout = timeout
        return self.handler(request)

    @property
    def last(self):
        return self.requests[-1]


class FakeLicense:
    """Just enough of ``LicenseManager`` for the Pro gates."""

    def __init__(self, pro=True):
        self.pro = pro

    def is_pro(self):
        return self.pro

    def status(self):
        return {"pro": self.pro}


class Clock:
    """A hand-wound clock for the time-dependent Pro features."""

    def __init__(self, t=1000.0):
        self.t = t

    def __call__(self):
        return self.t


@pytest.fixture
def clock():
    return Clock()
