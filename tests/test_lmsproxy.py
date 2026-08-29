"""The reverse proxy that puts Material Skin inside the page.

The page is HTTPS and the LMS is HTTP, so Material can only be framed if it
arrives under this origin (see ``localvoice/lmsproxy.py``). That makes this
server a gateway to the music server for everything it does not own itself,
which is a larger change than it looks — so what is pinned here is the shape
of it:

* the routes this server *does* own still win, ahead of the catch-all;
* what is forwarded arrives upstream intact — method, path, body, headers —
  and nothing hop-by-hop travels with it;
* what comes back is relayed, upstream's own errors and redirects included;
* an unreachable hi-fi is a 502 that says so, rather than a 404 that would
  read as "Material isn't installed";
* the cross-site guard and the Host allow-list still cover the proxied
  requests, without a second, weaker copy of either living in the proxy;
* pointed at a Material somewhere else, none of it happens at all.

The upstream is injected (``proxy_open``), like ``artwork_fetch`` before it:
nothing here touches the network.
"""

import http.client
import io
import urllib.error
import urllib.parse

import pytest

import lmsproxy

from conftest import ELSEWHERE_MATERIAL_URL, FakeUpstream, UpstreamResponse


@pytest.fixture
def upstream():
    return FakeUpstream()


@pytest.fixture
def proxied(live_server, upstream):
    """A server with Material Skin embedded, i.e. the proxy on."""
    return live_server(proxy_open=upstream)


def _raiser(exc):
    def handler(request):
        raise exc
    return handler


def raw_get(srv, path, headers=None):
    """One GET with exactly these headers and no redirect following — the
    client library's own helpfulness is what several of these tests are
    trying to see past."""
    parts = urllib.parse.urlsplit(srv.url)
    conn = http.client.HTTPConnection(parts.hostname, parts.port, timeout=5)
    try:
        conn.request("GET", path, headers=headers or {})
        resp = conn.getresponse()
        return resp.status, dict(resp.getheaders()), resp.read()
    finally:
        conn.close()


# -- our own routes come first -------------------------------------------------

@pytest.mark.parametrize("path", ["/", "/index.html", "/sw.js",
                                  "/static/js/app.js", "/nowplaying",
                                  "/manifest.webmanifest", "/kidsafe"])
def test_the_routes_this_server_owns_never_reach_upstream(proxied, upstream, path):
    # The catch-all is last on purpose. A Material asset called /nowplaying
    # would be a curiosity; our own page answering it as one would be a bug.
    assert proxied.get(path).status == 200
    assert upstream.requests == []


def test_a_missing_static_file_is_still_our_404(proxied, upstream):
    # /static/ is this app's own tree: a miss there is a miss, not something
    # to go asking the hi-fi about.
    assert proxied.try_get("/static/js/no-such-module.js").status == 404
    assert upstream.requests == []


# -- what reaches upstream -----------------------------------------------------

def test_an_unknown_path_is_forwarded_verbatim(proxied, upstream):
    proxied.get("/material/html/js/app.js?v=3")
    request = upstream.last
    assert request.full_url == "http://lms.local:9000/material/html/js/app.js?v=3"
    assert request.get_method() == "GET"


def test_a_post_carries_its_method_body_and_type(proxied, upstream):
    proxied.post_json("/jsonrpc.js", {"method": "slim.request"})
    request = upstream.last
    assert request.get_method() == "POST"
    assert b'"slim.request"' in request.data
    assert request.get_header("Content-type") == "application/json"


def test_the_long_poll_gets_a_long_timeout(proxied, upstream):
    # CometD holds the connection open on purpose; a timeout of the size an
    # ordinary request wants would turn Material's live now-playing into a
    # stream of gateway errors.
    proxied.post_json("/cometd", [{"channel": "/meta/connect"}])
    assert upstream.timeout >= 60


def test_hop_by_hop_headers_do_not_travel(proxied, upstream):
    raw_get(proxied, "/material/", {"Host": "127.0.0.1",
                                    "Connection": "keep-alive",
                                    "Accept": "text/html"})
    request = upstream.last
    assert request.get_header("Connection") is None
    assert request.get_header("Accept") == "text/html"


# -- what comes back -----------------------------------------------------------

def test_the_upstream_status_and_type_are_relayed(proxied):
    resp = proxied.get("/material/")
    assert resp.status == 200
    assert resp.headers["Content-Type"].startswith("text/html")
    assert b"Material" in resp.body


def test_a_body_larger_than_one_block_arrives_whole(live_server, upstream):
    # Copied in 64 KB blocks rather than buffered whole: that loop is the only
    # thing between a 300 KB bundle and a truncated app.
    payload = b"x" * (300 * 1024)
    upstream.handler = lambda request: UpstreamResponse(
        200, [("Content-Type", "text/javascript"),
              ("Content-Length", str(len(payload)))], payload)
    resp = live_server(proxy_open=upstream).get("/material/html/js/bundle.js")
    assert resp.body == payload


def test_an_upstream_404_stays_a_404(live_server, upstream):
    upstream.handler = _raiser(urllib.error.HTTPError(
        "http://lms.local:9000/nope", 404, "Not Found",
        {"Content-Type": "text/html"}, io.BytesIO(b"<h1>404</h1>")))
    assert live_server(proxy_open=upstream).try_get("/nope").status == 404


def test_a_redirect_is_handed_to_the_browser_not_followed(live_server, upstream):
    # Material's own URLs are what the browser has to end up on; a redirect
    # resolved here would hide the destination from the frame.
    upstream.handler = _raiser(urllib.error.HTTPError(
        "http://lms.local:9000/material", 302, "Found",
        {"Location": "/material/", "Content-Length": "0"}, io.BytesIO(b"")))
    srv = live_server(proxy_open=upstream)
    status, headers, _ = raw_get(srv, "/material")
    assert status == 302
    assert headers["Location"] == "/material/"
    assert len(upstream.requests) == 1


def test_an_unreachable_music_server_is_a_502(live_server, upstream):
    # The one deliberate 5xx in this server, and the honest code: a 404 would
    # make "the plugin isn't installed" look like "the hi-fi is switched off".
    upstream.handler = _raiser(OSError("connection refused"))
    resp = live_server(proxy_open=upstream).try_get("/material/")
    assert resp.status == 502


def test_an_oversized_body_is_refused_instead_of_buffered(live_server, upstream,
                                                          monkeypatch):
    monkeypatch.setattr(lmsproxy, "MAX_BODY", 8)
    srv = live_server(proxy_open=upstream)
    resp = srv.try_post("/jsonrpc.js", b'{"method":"slim.request"}')
    assert resp.status == 413
    assert upstream.requests == []


# -- the guards the proxy inherits ---------------------------------------------

def test_a_cross_site_post_is_refused_before_it_is_forwarded(live_server, upstream):
    # There is no second copy of webguard in the proxy: do_POST runs the
    # cross-site guard ahead of every route, the proxied ones included.
    srv = live_server(proxy_open=upstream)
    resp = srv.try_post("/jsonrpc.js", b"{}",
                        headers={"Sec-Fetch-Site": "cross-site"})
    assert resp.status == 403
    assert upstream.requests == []


def test_a_rebound_host_is_refused_before_it_is_forwarded(live_server, upstream):
    srv = live_server(proxy_open=upstream)
    resp = srv.try_get("/material/", headers={"Host": "evil.example"})
    assert resp.status == 403
    assert upstream.requests == []


# -- switched off --------------------------------------------------------------

def test_material_elsewhere_leaves_the_server_exactly_as_it_was(live_server,
                                                                upstream):
    srv = live_server(material_url=ELSEWHERE_MATERIAL_URL, proxy_open=upstream)
    assert srv.try_get("/nope").status == 404
    assert srv.try_post_json("/jsonrpc.js", {}).status == 404
    assert upstream.requests == []


# -- what the page is told -----------------------------------------------------

def test_the_page_learns_where_to_browse(live_server):
    assert 'browse: "/material/"' in live_server().get("/").text


def test_the_page_gets_no_browse_path_when_material_is_elsewhere(live_server):
    page = live_server(material_url=ELSEWHERE_MATERIAL_URL).get("/").text
    assert 'browse: ""' in page
    # ...and the link itself is untouched, so it still opens in a new tab.
    assert ELSEWHERE_MATERIAL_URL in page


def test_the_browse_path_follows_material_url_rather_than_assuming_one(live_server):
    # --material-url may name a different path on the same LMS (the classic
    # skin, say); the panel opens that, not a hard-coded /material/.
    srv = live_server(material_url="http://lms.local:9000/classic/")
    assert 'browse: "/classic/"' in srv.get("/").text


def test_the_module_default_transport_is_used_when_none_is_injected(
        live_server, upstream, monkeypatch):
    # The injection point exists for the tests; the app still has to get a
    # working transport when nobody passes one.
    monkeypatch.setattr(lmsproxy, "_urlopen", upstream)
    srv = live_server(proxy_open=None)
    assert srv.get("/material/").status == 200
    assert upstream.requests
