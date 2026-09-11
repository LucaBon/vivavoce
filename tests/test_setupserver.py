"""The setup page: what happens when there is nothing to control yet.

The behaviour under test is the one startup used to get wrong. No LMS on the
network, or no player switched on, and the process returned 1 — so the web
app never came up, and the only diagnosis was a console line on a machine
nobody looks at. Everything here is about the server binding first and
explaining itself second, and about it going on looking so that switching the
hi-fi back on is the whole fix.
"""

import json
import threading
import urllib.error
import urllib.request

import pytest

import setuppage
import setupserver
from lms import LMSError
from player.registry import BACKENDS


class FakeProbe:
    """A scriptable stand-in for :func:`setupserver.probe`.

    ``answers`` maps an address to what a music server there would say: a list
    of players, or ``None`` for "nothing answers".

    The signature mirrors the real one, keyword arguments included: since the
    player layer, which backend is being asked (and with which token) is part
    of the question, and ``asked`` records it so a test can check the setup
    loop is talking to the system it was pointed at.
    """

    def __init__(self, answers=None):
        self.answers = answers or {}
        self.calls = []
        self.asked = []

    def __call__(self, url, timeout=3.0, *, backend="lms", token=None):
        self.calls.append(url)
        self.asked.append((backend, token))
        players = self.answers.get(url)
        return (False, []) if players is None else (True, players)


class Clock:
    """A monotonic clock the test moves by hand."""

    def __init__(self):
        self.t = 1000.0

    def __call__(self):
        return self.t

    def advance(self, seconds):
        self.t += seconds


SALA = [{"playerid": "aa:bb:cc:dd:ee:ff", "name": "Sala"}]


@pytest.fixture
def probe(monkeypatch):
    fake = FakeProbe()
    monkeypatch.setattr(setupserver, "probe", fake)
    return fake


# -- the address box -----------------------------------------------------------

@pytest.mark.parametrize("typed, expected", [
    # People type what the router's sticker says. Accept it.
    ("192.168.1.50", "http://192.168.1.50:9000"),
    ("  192.168.1.50  ", "http://192.168.1.50:9000"),
    ("http://192.168.1.50", "http://192.168.1.50:9000"),
    ("http://192.168.1.50:9002/", "http://192.168.1.50:9002"),
    ("https://lms.home:9000/material/", "https://lms.home:9000"),
    ("lms.local", "http://lms.local:9000"),
])
def test_typed_addresses_are_normalised(typed, expected):
    assert setupserver.normalize_lms_url(typed) == expected


@pytest.mark.parametrize("junk", ["", "   ", "file:///etc/passwd", "http://",
                                  "not a url at all", "ftp://x:9000"])
def test_junk_is_refused_rather_than_guessed_at(junk):
    # A scheme that is not http(s) is a mistake, not shorthand: normalising it
    # would point the client at something nobody meant.
    assert setupserver.normalize_lms_url(junk) == ""


# -- which of the three things is missing --------------------------------------

def test_no_address_at_all_reads_as_no_lms():
    r = setupserver._Resolution("", lambda: "")
    assert r.reason == setupserver.NO_LMS


def test_a_remembered_address_is_not_yet_a_working_one():
    # Believed in, never probed. Saying "no player" here would be a guess, and
    # it is the wrong one whenever the server is simply off.
    r = setupserver._Resolution("http://lms:9000", lambda: "")
    assert r.reason == setupserver.LMS_DOWN


def test_an_lms_that_answers_with_nothing_on_reads_as_no_player(probe):
    probe.answers["http://lms:9000"] = []
    r = setupserver._Resolution("http://lms:9000", lambda: "")
    r.sweep()
    assert r.reason == setupserver.NO_PLAYER
    assert not r.done.is_set()


def test_a_player_switched_on_finishes_it(probe):
    probe.answers["http://lms:9000"] = SALA
    r = setupserver._Resolution("http://lms:9000", lambda: "")
    r.sweep()
    assert r.done.is_set()
    assert r.players == SALA


def test_an_explicit_player_only_needs_the_lms_to_answer(probe):
    # --player names a device the household knows about; an empty player list
    # is then not this server's business to argue with.
    probe.answers["http://lms:9000"] = []
    r = setupserver._Resolution("http://lms:9000", lambda: "",
                                require_player=False)
    r.sweep()
    assert r.done.is_set()


# -- going on looking ----------------------------------------------------------

def test_the_page_walks_itself_into_the_app_when_a_player_comes_on(probe):
    # The whole point: nobody types anything, they just switch the hi-fi on.
    probe.answers["http://lms:9000"] = []
    r = setupserver._Resolution("http://lms:9000", lambda: "")
    r.sweep()
    assert not r.done.is_set()
    probe.answers["http://lms:9000"] = SALA
    r.sweep()
    assert r.done.is_set()


def test_a_remembered_address_is_given_up_on_and_the_network_searched_again(probe):
    # A lease expired and the LMS moved. One miss is a router still booting,
    # which is the case the address was remembered for; after STALE_AFTER we
    # stop believing it, and the same sweep that gives up goes looking.
    probe.answers["http://old:9000"] = None
    probe.answers["http://new:9000"] = SALA
    r = setupserver._Resolution("http://old:9000", lambda: "http://new:9000",
                                discover_interval=0.0)
    for _ in range(setupserver.STALE_AFTER - 1):
        r.sweep()
        assert not r.done.is_set()
        assert r.lms_url == "http://old:9000"  # still worth another try
    r.sweep()
    assert r.done.is_set()
    assert r.lms_url == "http://new:9000"


def test_the_network_is_not_searched_while_a_known_address_may_still_come_back(
        probe):
    # The first miss must not send us hunting: an LMS mid-reboot answers the
    # next sweep, and rediscovery is expensive (broadcast, then a unicast
    # sweep of every subnet).
    probe.answers["http://old:9000"] = None
    discovered = []
    r = setupserver._Resolution("http://old:9000",
                                lambda: discovered.append(1) or "")
    r.sweep()
    assert discovered == []


def test_the_network_is_not_re_searched_on_every_round(probe):
    # Probing a known address is one short connection; discovery is a UDP
    # broadcast plus a unicast sweep of every subnet. Running the second at
    # the first's cadence would make the setup page the noisiest thing on the
    # LAN — and it runs for as long as the LMS stays missing, which can be
    # all night.
    clock = Clock()
    rounds = []
    r = setupserver._Resolution("", lambda: rounds.append(1) or "",
                                discover_interval=30.0, now=clock)
    for _ in range(20):
        r.sweep()
    assert rounds == [1]
    clock.advance(31)
    r.sweep()
    assert len(rounds) == 2


def test_a_configured_address_is_never_swapped_for_a_discovered_one(probe):
    # --lms is configuration. Searching the network for a server somebody has
    # already named is how you end up controlling the neighbour's hi-fi.
    probe.answers["http://pinned:9000"] = None
    discovered = []

    def discover():
        discovered.append(1)
        return "http://someone-elses:9000"

    r = setupserver._Resolution("http://pinned:9000", discover, pinned=True,
                                discover_interval=0.0)
    for _ in range(setupserver.STALE_AFTER + 3):
        r.sweep()
    assert r.lms_url == "http://pinned:9000"
    assert discovered == []


def test_a_probe_that_raises_does_not_stop_the_loop(monkeypatch):
    calls = []

    def exploding(url, timeout=3.0):
        calls.append(url)
        raise LMSError("boom")

    monkeypatch.setattr(setupserver, "probe", exploding)
    r = setupserver._Resolution("http://lms:9000", lambda: "")
    naps = []

    def sleep(seconds):
        naps.append(seconds)
        if len(naps) >= 3:
            r.done.set()

    setupserver._probe_loop(r, 3.0, sleep)
    assert len(calls) >= 3  # kept going rather than dying in the thread


# -- the HTTP surface ----------------------------------------------------------

@pytest.fixture
def setup_server(probe):
    """A live setup server on an ephemeral port; yields ``(base, resolution)``."""
    from httpbase import BoundedThreadingHTTPServer

    resolution = setupserver._Resolution("", lambda: "")
    httpd = BoundedThreadingHTTPServer(
        ("127.0.0.1", 0), setupserver.make_setup_handler(resolution))
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{httpd.server_address[1]}", resolution
    finally:
        httpd.shutdown()
        httpd.server_close()
        thread.join(timeout=5)


def _get(url):
    with urllib.request.urlopen(url, timeout=5) as resp:
        return resp.status, resp.read().decode("utf-8")


def _post(url, payload):
    req = urllib.request.Request(
        url, data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=5) as resp:
        return json.loads(resp.read().decode("utf-8"))


def test_the_page_is_served_at_the_root(setup_server):
    base, _ = setup_server
    status, body = _get(base + "/")
    assert status == 200
    assert "Vivavoce" in body
    # Every reason the server can report has a sentence in the page, in both
    # languages: a state with no words for it is the failure being retold.
    for reason in (setupserver.NO_LMS, setupserver.LMS_DOWN,
                   setupserver.NO_PLAYER):
        assert body.count(f'"{reason}"') >= 2


def test_the_state_endpoint_says_what_is_missing(setup_server):
    base, _ = setup_server
    status, body = _get(base + "/setup")
    assert status == 200
    assert json.loads(body) == {"ready": False, "reason": setupserver.NO_LMS,
                                "lms": ""}


def test_a_typed_address_that_works_finishes_setup(setup_server, probe):
    base, resolution = setup_server
    probe.answers["http://192.168.1.50:9000"] = SALA
    out = _post(base + "/setup", {"lms": "192.168.1.50"})
    assert out["ok"] is True and out["ready"] is True
    assert resolution.lms_url == "http://192.168.1.50:9000"
    assert resolution.players == SALA


def test_a_typed_address_that_answers_with_no_player_moves_the_question_on(
        setup_server, probe):
    # Not "ok", but not nothing either: the household now has the shorter
    # conversation ("switch something on") instead of the longer one.
    base, resolution = setup_server
    probe.answers["http://192.168.1.50:9000"] = []
    out = _post(base + "/setup", {"lms": "192.168.1.50"})
    assert out["ok"] is False
    assert out["reason"] == setupserver.NO_PLAYER
    assert resolution.lms_url == "http://192.168.1.50:9000"


def test_a_typed_address_that_answers_to_nothing_is_reported_as_such(
        setup_server):
    base, _ = setup_server
    out = _post(base + "/setup", {"lms": "192.168.9.9"})
    assert out["ok"] is False
    assert out["reason"] == setupserver.NO_LMS


def test_nothing_else_is_served_here(setup_server):
    # There is no LMS behind this server yet, by definition — so no proxy, and
    # nothing that would make a half-configured app look configured.
    base, _ = setup_server
    for path in ("/api/v1/command", "/material/", "/jsonrpc.js", "/nowplaying"):
        with pytest.raises(urllib.error.HTTPError) as excinfo:
            _get(base + path)
        assert excinfo.value.code == 404


def test_the_cross_site_guard_still_applies(setup_server):
    # Same guard as every other POST in the app: a page somewhere else must
    # not be able to aim this server at an address of its choosing.
    base, _ = setup_server
    req = urllib.request.Request(
        base + "/setup", data=b'{"lms":"192.168.1.50"}',
        headers={"Content-Type": "application/json",
                 "Origin": "http://evil.example"}, method="POST")
    with pytest.raises(urllib.error.HTTPError) as excinfo:
        urllib.request.urlopen(req, timeout=5)
    assert excinfo.value.code == 403


# -- serve_setup ---------------------------------------------------------------

def test_the_network_is_never_searched_before_the_port_is_bound(probe):
    # A first-ever start has no address to probe, and searching for one is a
    # broadcast plus a unicast sweep of every subnet — half a minute during
    # which the port would not answer and nobody could be told anything. The
    # cheap half runs first; the search happens behind the page.
    searched = []
    r = setupserver._Resolution("", lambda: searched.append(1) or "")
    r.sweep(search=False)
    assert searched == []
    r.sweep()
    assert searched == [1]


def test_a_healthy_house_never_sees_the_page(probe, monkeypatch):
    # The usual start: look once, find everything, return without binding.
    probe.answers["http://lms:9000"] = SALA

    def unexpected(*args, **kwargs):
        raise AssertionError("must not bind a setup server when nothing is wrong")

    monkeypatch.setattr(setupserver, "BoundedThreadingHTTPServer", unexpected)
    lms_url, players = setupserver.serve_setup(
        "127.0.0.1", 0, "http://lms:9000", lambda: "", announce=lambda _l: None)
    assert (lms_url, players) == ("http://lms:9000", SALA)


def test_the_page_is_torn_down_once_the_house_is_controllable(probe):
    # Switch the player on from another thread; serve_setup returns by itself.
    probe.answers["http://lms:9000"] = []

    def turn_it_on():
        probe.answers["http://lms:9000"] = SALA

    threading.Timer(0.05, turn_it_on).start()
    lms_url, players = setupserver.serve_setup(
        "127.0.0.1", 0, "http://lms:9000", lambda: "", interval=0.02,
        sleep=lambda s: threading.Event().wait(s), announce=lambda _l: None)
    assert (lms_url, players) == ("http://lms:9000", SALA)


def test_the_console_is_told_where_the_page_is(probe):
    # The one line that still has to reach a terminal: the address to open.
    probe.answers["http://lms:9000"] = []
    said = []

    def turn_it_on():
        probe.answers["http://lms:9000"] = SALA

    threading.Timer(0.05, turn_it_on).start()
    setupserver.serve_setup("127.0.0.1", 0, "http://lms:9000", lambda: "",
                            interval=0.02,
                            sleep=lambda s: threading.Event().wait(s),
                            announce=said.append)
    assert len(said) == 1


# -- the page itself -----------------------------------------------------------

def test_the_page_carries_no_unrendered_placeholders():
    page = setuppage.setup_page()
    assert "__STRINGS__" not in page and "__POLL__" not in page
    assert str(setuppage.POLL_INTERVAL_MS) in page


def test_a_bare_address_is_completed_with_the_backends_own_port():
    # A bare IP completed with 9000 for a Music Assistant on 8095 produces an
    # address that looks right and answers nothing, which is worse than
    # refusing it: the household has no way to see what is wrong.
    assert setupserver.normalize_lms_url("192.168.1.50", 8095) == \
        "http://192.168.1.50:8095"
    assert setupserver.normalize_lms_url("192.168.1.50") == \
        "http://192.168.1.50:9000"
    # A port that was typed is never overridden.
    assert setupserver.normalize_lms_url("192.168.1.50:9999", 8095) == \
        "http://192.168.1.50:9999"


def test_the_setup_loop_asks_the_backend_it_was_pointed_at(probe):
    # The address box and the page copy are one half; the other is that the
    # probe behind them is talking to the system the user chose, with the
    # token they gave, rather than looking for an LMS that is not there.
    probe.answers["http://ma:8095"] = SALA
    setupserver.serve_setup("127.0.0.1", 0, "http://ma:8095", lambda: "",
                            backend="musicassistant", token="sekrit",
                            announce=lambda _l: None)
    assert probe.asked == [("musicassistant", "sekrit")]


KEYS = ("title", "hint_lms", "hint_down", "hint_player", "save", "looking",
        "bad", "found", "placeholder", "server", setupserver.NO_LMS,
        setupserver.LMS_DOWN, setupserver.NO_PLAYER)


@pytest.mark.parametrize("backend", sorted(BACKENDS))
def test_both_languages_answer_every_reason(backend):
    # A reason with no sentence renders an empty card, which is the original
    # failure ("something is wrong, good luck") wearing a stylesheet. Every
    # backend gets its own words, so every backend can lose one.
    words = setuppage.strings_for(backend)
    for lang in ("it", "en"):
        for key in KEYS:
            assert words[lang].get(key), f"{backend}/{lang}/{key}"


def test_a_backend_nobody_wrote_words_for_still_fills_the_card():
    # Vaguer, never blank: the generic copy names the system and says the same
    # things, so adding a backend cannot silently produce an empty page.
    words = setuppage.strings_for("newthing", label="New Thing")
    for lang in ("it", "en"):
        for key in KEYS:
            assert words[lang].get(key), f"{lang}/{key}"
        assert "New Thing" in words[lang]["bad"]


def test_the_page_never_tells_the_wrong_household_what_to_switch_on():
    # The bug this fixes: a Music Assistant household was told to switch on a
    # Squeezebox, which sends somebody looking for hardware they do not own.
    ma = setuppage.strings_for("musicassistant")
    assert "Squeezebox" not in ma["it"]["hint_player"]
    assert "Music Assistant" in ma["it"]["hint_player"]
    assert "8095" in ma["it"]["placeholder"]
    assert "Squeezebox" in setuppage.strings_for("lms")["it"]["hint_player"]


def test_the_page_is_built_for_the_backend_it_was_given():
    assert "8095" in setuppage.setup_page("musicassistant")
    assert "Music Assistant" in setuppage.setup_page("musicassistant")
    assert "Squeezebox" in setuppage.setup_page("lms")
