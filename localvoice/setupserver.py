"""The page that comes up when there is nothing to control yet.

Startup used to end here. No LMS on the network, or no player switched on,
and ``main()`` printed a line and returned 1 — so the web app, which is the
only thing anyone in the house ever looks at, never came up at all. The
person who could have fixed it in ten seconds (turn the Squeezebox back on)
saw a phone that would not load a page, and the diagnosis sat in a terminal
on a machine in a cupboard.

So the server binds first and explains itself second. This module owns that
in-between state: it decides *what is missing* and keeps looking until
nothing is, while ``setuppage.py`` owns what a person sees while it does.
``serve_setup`` blocks until the household is controllable and returns
``(lms_url, players)`` for ``server.main`` to carry on with.
"""

from __future__ import annotations

import json
import re
import threading
import time
import urllib.parse

import webguard
from http.server import BaseHTTPRequestHandler
from httpbase import BoundedThreadingHTTPServer, RequestBase
from lms import LMSClient, LMSError
from setuppage import LMS_DOWN, NO_LMS, NO_PLAYER, setup_page

#: How often the background probe re-checks, in seconds. Fast enough that
#: switching a player on feels like it did something, slow enough that an LMS
#: which is simply off is not dialled at a rate anyone would call polling.
PROBE_INTERVAL = 3.0

#: How often the network is searched from scratch, in seconds. An order of
#: magnitude slower than PROBE_INTERVAL, and deliberately: probing a known
#: address is one short-lived connection, while discovery is a UDP broadcast
#: followed — inside Docker, always — by a unicast sweep of every subnet the
#: machine can see. Running that every few seconds would make the setup page
#: the noisiest thing on the LAN.
DISCOVER_INTERVAL = 30.0

#: Failed probes on a remembered address before it is given up on and the
#: network is searched again. Two, because one is a router still coming up
#: after a power cut — the case the address was remembered for.
STALE_AFTER = 2


#: What a host may be made of. Anything else typed into that box is a
#: sentence, not an address — and ``urlsplit`` will happily hand back
#: "not a url at all" as a hostname, which then becomes a request nobody can
#: explain. IPv6 comes through ``hostname`` with its brackets stripped, hence
#: the second alternative.
_HOSTNAME_RE = re.compile(r"\A(?:[A-Za-z0-9._-]+|[0-9A-Fa-f:]+)\Z")


def normalize_lms_url(raw: str) -> str:
    """A typed-in address as an LMS base URL, or ``""`` if it isn't one.

    People type ``192.168.1.50``, because that is what the sticker on the
    router says. Accept it: add the scheme, add the port LMS has always used,
    and drop a trailing slash so the result concatenates the way the client
    expects. Anything with a scheme that is not http(s) is refused rather than
    normalised — a ``file://`` in this field is a mistake, not shorthand.
    """
    text = (raw or "").strip()
    if not text:
        return ""
    if "://" not in text:
        text = "http://" + text
    try:
        parts = urllib.parse.urlsplit(text)
        host, port = parts.hostname, parts.port
    except ValueError:
        return ""  # a port that isn't a number
    if parts.scheme not in ("http", "https") or not host:
        return ""
    if not _HOSTNAME_RE.match(host):
        return ""
    if ":" in host:  # IPv6, and urlsplit took the brackets off
        host = f"[{host}]"
    return urllib.parse.urlunsplit(
        (parts.scheme, f"{host}:{port or 9000}", "", "", ""))


def probe(lms_url: str, timeout: float = 3.0):
    """``(ok, players)`` for one address — does an LMS answer, and with what.

    A short timeout on purpose: this runs on a loop while somebody watches a
    spinner, and the answer "not yet" is worth having quickly.
    """
    try:
        players = LMSClient(lms_url, "0", timeout=timeout).get_players()
    except (LMSError, ValueError):
        return False, []
    return True, players


class _Resolution:
    """What the setup server is waiting for, and what it has found so far.

    Three states, and they are three different sentences to say to somebody:
    no address at all, an address that does not answer, and an LMS answering
    with nothing switched on. Collapsing them into "not working" was the old
    behaviour and it is what sent people to a terminal.

    Guarded by a lock because two threads write it: the background probe and
    whichever request thread the household typed an address into.
    """

    def __init__(self, lms_url: str, discover, pinned: bool = False,
                 require_player: bool = True,
                 discover_interval: float = DISCOVER_INTERVAL,
                 now=time.monotonic):
        self.lock = threading.Lock()
        self.discover = discover
        self.discover_interval = discover_interval
        self.now = now
        self.discover_after = 0.0
        # ``pinned`` is --lms / PREFIX_LMS: configuration, not a guess. A
        # remembered or discovered address is given up on when it stops
        # answering (the old cache did the same); a configured one never is,
        # because searching the network for a server somebody has already
        # named is how you end up controlling the neighbour's.
        self.pinned = pinned
        self.require_player = require_player
        self.lms_url = lms_url
        self.players: list = []
        # Whether the address above has actually answered, as opposed to
        # merely being believed in. A remembered address starts unconfirmed:
        # until something replies we do not know which of the two things is
        # wrong, and the page must not guess.
        self.confirmed = False
        self.misses = 0
        self.done = threading.Event()

    @property
    def reason(self) -> str:
        if not self.lms_url:
            return NO_LMS
        return NO_PLAYER if self.confirmed else LMS_DOWN

    def state(self) -> dict:
        with self.lock:
            return {"ready": self.done.is_set(), "reason": self.reason,
                    "lms": self.lms_url}

    def offer(self, lms_url: str) -> bool:
        """Try one address. True when it leaves the house controllable."""
        ok, players = probe(lms_url)
        with self.lock:
            if not ok:
                if lms_url == self.lms_url:
                    self.confirmed = False
                    self.misses += 1
                    if not self.pinned and self.misses >= STALE_AFTER:
                        # Back to searching, and say so: an address that has
                        # stopped answering twice is more likely to have moved
                        # (a new DHCP lease) than to be coming back.
                        self.lms_url = ""
                return False
            # An LMS that answers is worth keeping even with nothing switched
            # on: it moves the page from "find the server" to "switch
            # something on", which is the shorter of the two conversations.
            self.lms_url = lms_url
            self.players = players
            self.confirmed = True
            self.misses = 0
            enough = bool(players) or not self.require_player
        if enough:
            self.done.set()
        return enough

    def sweep(self, search: bool = True) -> None:
        """One round of looking, from wherever we currently are.

        ``search=False`` does the cheap half only — probe the address we
        believe in, if any. That is what runs before the port is bound: an
        address that answers means there is nothing to explain and no page to
        serve, and finding that out costs one short connection. Searching the
        network does not, so it happens after the page exists, where somebody
        can watch it happen instead of watching a terminal.
        """
        with self.lock:
            known = self.lms_url
        if known and self.offer(known):
            return
        with self.lock:
            still_known = self.lms_url
        if still_known:
            return  # keep trying the address we have rather than the network
        if not search or self.now() < self.discover_after:
            return  # searched recently; see DISCOVER_INTERVAL
        self.discover_after = self.now() + self.discover_interval
        found = self.discover()
        if found:
            self.offer(found)


def _probe_loop(resolution: _Resolution, interval: float, sleep) -> None:
    while not resolution.done.is_set():
        try:
            resolution.sweep()
        except Exception:
            pass  # a probe that raises is a probe that found nothing
        if resolution.done.is_set():
            break
        sleep(interval)


def make_setup_handler(resolution: _Resolution, allowed_hosts=None):
    page = setup_page()

    class SetupHandler(RequestBase, BaseHTTPRequestHandler):
        host_policy = webguard.HostPolicy(allowed_hosts)

        def do_GET(self):
            if self._reject_bad_host():
                return
            if self.path == "/setup":
                self._send(200, json.dumps(resolution.state()))
            elif self.path.split("?", 1)[0] in ("/", "/index.html"):
                self._send(200, page, "text/html")
            else:
                # Everything else 404s rather than being proxied anywhere:
                # there is no LMS behind this server yet, by definition.
                self._send(404, "not found", "text/plain")

        def do_POST(self):
            if self._reject_cross_site():
                return
            if self.path.split("?", 1)[0] != "/setup":
                self._send(404, '{"ok":false}')
                return
            url = normalize_lms_url(self._read_json_object().get("lms") or "")
            ok = resolution.offer(url) if url else False
            state = resolution.state()
            state["ok"] = ok
            self._send(200, json.dumps(state))

        def log_message(self, *args):  # keep the console quiet
            pass

    return SetupHandler


def serve_setup(host: str, port: int, lms_url: str, discover, *,
                pinned: bool = False, require_player: bool = True,
                allowed_hosts=None, wrap=None, interval: float = PROBE_INTERVAL,
                discover_interval: float = DISCOVER_INTERVAL,
                sleep=time.sleep, announce=print):
    """Serve the setup page until the household is controllable.

    Returns ``(lms_url, players)`` — an LMS that answers and at least one
    player switched on — for ``server.main`` to build the real app with.
    ``discover`` is called (repeatedly) only while no address is known;
    ``wrap`` is handed the server to put TLS on it, so the setup page is
    reached at the same scheme and port as the app that replaces it.
    """
    resolution = _Resolution(lms_url, discover, pinned=pinned,
                             require_player=require_player,
                             discover_interval=discover_interval)
    # Look once before binding anything — but only the cheap half. A house
    # that is already fine (the usual restart: a remembered address, a player
    # left on) is found in one short connection and never sees a setup page.
    # A network search is the other order of magnitude and belongs after the
    # page exists, so a first-ever start shows "looking…" instead of an
    # unresponsive port for half a minute.
    resolution.sweep(search=False)
    if resolution.done.is_set():
        return resolution.lms_url, resolution.players

    httpd = BoundedThreadingHTTPServer(
        (host, port), make_setup_handler(resolution, allowed_hosts))
    if wrap:
        wrap(httpd)
    prober = threading.Thread(
        target=_probe_loop, args=(resolution, interval, sleep), daemon=True)
    prober.start()
    waiter = threading.Thread(
        target=lambda: (resolution.done.wait(), httpd.shutdown()), daemon=True)
    waiter.start()
    announce("Apri l'indirizzo qui sopra: la pagina dice cosa manca e va "
             "avanti da sola appena lo trova.")
    try:
        httpd.serve_forever()
    finally:
        httpd.server_close()
    return resolution.lms_url, resolution.players
