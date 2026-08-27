"""Cross-site protection (``localvoice/webguard.py``) and the request-plumbing
limits in ``localvoice/httpbase.py``.

The app has no auth by design — LAN only, no accounts — so every POST would
otherwise be a CSRF target: a page open on any phone on the same Wi-Fi could
turn the volume to 100, or enable kid-safe with a PIN of its own choosing and
lock the parent out. Nothing here reads a reply cross-origin (the same-origin
policy already prevents that); the point is that the *action* must not happen.
"""

import json

import pytest

import webguard
from conftest import FakeLicense


@pytest.fixture
def srv(live_server):
    return live_server()


def _body(payload):
    return json.dumps(payload).encode("utf-8")


# -- the three checks, in isolation --------------------------------------------

class Headers(dict):
    """A case-insensitive header mapping, like ``self.headers``."""

    def get(self, key, default=None):
        for k, v in self.items():
            if k.lower() == key.lower():
                return v
        return default


ANY_HOST = "192.168.1.20:8730"


def reason(policy=None, require_json=False, **headers):
    headers.setdefault("Host", ANY_HOST)
    return webguard.cross_site_reason(
        Headers(headers), policy or webguard.HostPolicy(), require_json)


def test_a_plain_same_origin_post_is_allowed():
    assert reason(require_json=True,
                  **{"Content-Type": "application/json"}) is None


def test_a_simple_request_content_type_is_refused():
    # text/plain needs no preflight, so it is exactly what a cross-origin page
    # would use to fire a request it can't read the answer to.
    assert reason(require_json=True, **{"Content-Type": "text/plain"}) \
        == "content_type"
    assert reason(require_json=True,
                  **{"Content-Type": "application/x-www-form-urlencoded"}) \
        == "content_type"


def test_a_charset_parameter_does_not_break_the_content_type_check():
    assert reason(require_json=True,
                  **{"Content-Type": "application/json; charset=utf-8"}) is None


def test_an_origin_from_elsewhere_is_refused():
    assert reason(Origin="https://evil.example") == "cross_site"


def test_our_own_origin_is_allowed():
    assert reason(Origin="https://192.168.1.20:8730") is None


def test_sec_fetch_site_is_believed_when_present():
    assert reason(**{"Sec-Fetch-Site": "cross-site"}) == "cross_site"
    assert reason(**{"Sec-Fetch-Site": "same-origin"}) is None
    assert reason(**{"Sec-Fetch-Site": "none"}) is None   # typed in the bar


def test_a_public_name_in_host_is_refused_rebinding():
    # DNS rebinding survives both checks above: the attacker's own name
    # resolves to the LAN address, so Origin and Host agree — and both say
    # evil.example.
    assert reason(Host="evil.example", Origin="https://evil.example") \
        == "bad_host"


def test_ip_localhost_and_lan_names_are_accepted():
    for host in ("192.168.1.20:8730", "10.0.0.5", "[::1]:8730", "localhost",
                 "nas.local", "daphile.lan:8730"):
        assert reason(Host=host) is None, host


def test_an_explicit_allow_list_admits_a_real_name():
    policy = webguard.HostPolicy(["vivavoce.example.com"])
    assert webguard.cross_site_reason(
        Headers({"Host": "vivavoce.example.com"}), policy) is None


def test_parse_hosts_splits_and_trims():
    assert webguard.parse_hosts(" a.example , b.example ") == \
        ["a.example", "b.example"]
    assert webguard.parse_hosts(None) == []


# -- through the real server ---------------------------------------------------

def test_a_cross_origin_post_never_reaches_the_player(srv, transport):
    before = list(transport.calls)
    r = srv.try_post("/player", _body({"action": "volume", "value": 100}),
                     headers={"Origin": "https://evil.example"})
    assert r.status == 403
    assert r.json()["error"] == "cross_site"
    assert transport.calls == before   # nothing was sent to the LMS


def test_a_simple_request_post_never_reaches_the_router(srv, transport):
    before = list(transport.calls)
    r = srv.try_post("/command", _body({"text": "metti Time"}),
                     content_type="text/plain")
    assert r.status == 403
    assert r.json()["error"] == "content_type"
    assert transport.calls == before


def test_kidsafe_cannot_be_enabled_from_another_page(live_server, tmp_path,
                                                     clock):
    from pro.kidsafe import KidSafe
    kidsafe = KidSafe(str(tmp_path), FakeLicense(pro=True), now=clock)
    srv = live_server(kidsafe=kidsafe, license_mgr=FakeLicense(pro=True))
    r = srv.try_post("/kidsafe",
                     _body({"action": "enable", "pin": "666666",
                            "client": "attacker"}),
                     headers={"Origin": "https://evil.example"})
    assert r.status == 403
    assert kidsafe.enabled() is False   # the parent is not locked out
    assert kidsafe.has_pin() is False


def test_the_page_itself_still_works(srv):
    # Everything above must not have broken the ordinary case.
    assert srv.json_post("/command", {"text": "pausa"})["speech"] == "In pausa."


# -- body limits ---------------------------------------------------------------

def test_an_oversized_json_body_is_refused_not_buffered(srv):
    huge = _body({"text": "x" * 200_000})
    assert len(huge) > 64 * 1024
    # Refused as "no usable payload" rather than parsed: the reply is the
    # ordinary "I didn't hear anything", not a crash and not a 5xx.
    assert srv.json_post("/command", json.loads(huge))["ok"] is False


def test_a_bogus_content_length_gets_an_answer_not_a_dropped_connection(srv):
    import socket
    host, port = srv.url.rsplit(":", 1)
    sock = socket.create_connection(("127.0.0.1", int(port)), timeout=5)
    sock.sendall(b"POST /command HTTP/1.1\r\n"
                 b"Host: 127.0.0.1\r\n"
                 b"Content-Type: application/json\r\n"
                 b"Connection: close\r\n"
                 b"Content-Length: not-a-number\r\n\r\n")
    sock.settimeout(5)
    head = sock.recv(64)
    sock.close()
    assert head.startswith(b"HTTP/1.1 200"), head


def test_responses_are_keep_alive(srv):
    # protocol_version = HTTP/1.1: the wake word posts ~12 chunks a second per
    # phone, and each one used to be a fresh TCP+TLS handshake.
    assert srv.get("/tls").headers.get("Connection", "").lower() != "close"


# -- reads, and the one attack that can read them -------------------------------

def test_a_rebound_host_cannot_read_the_household_state(srv):
    # Checks 1 and 2 rest on "cross-site, the answer can't be read". DNS
    # rebinding is exactly the case where it can: the attacker's own name
    # resolves to this LAN address, so their page is same-origin with us.
    # do_GET never consulted the allow-list that check exists for, so every
    # readable route answered it — the license and its key, the players in
    # the house, the kid-safe state, what is playing right now.
    for path in ("/license", "/players", "/kidsafe?client=x", "/nowplaying",
                 "/tls", "/"):
        r = srv.try_get(path, headers={"Host": "evil.example"})
        assert r.status == 403, f"{path} answered a rebound host"
        assert r.json()["error"] == "bad_host"


def test_ordinary_reads_still_work(srv):
    # The allow-list admits IP literals and LAN names; nothing here may make
    # the app harder to open than it was.
    assert srv.get("/").status == 200                      # Host: 127.0.0.1:port
    assert srv.try_get("/tls", headers={"Host": "vivavoce.local"}).status == 200
    assert srv.try_get("/license",
                       headers={"Host": "localhost:8730"}).status == 200


def test_an_allowed_name_can_read_too(live_server):
    srv = live_server(allowed_hosts=["hifi.example.com"])
    assert srv.try_get("/tls",
                       headers={"Host": "hifi.example.com"}).status == 200
