"""Minimal Lyrion/Logitech Media Server (LMS) JSON-RPC client.

Talks to the LMS/Daphile control interface at ``<base_url>/jsonrpc.js`` using
the ``slim.request`` method. The transport is injectable so the whole client
can be unit-tested without any network access (see ``tests/``).

This module is the client itself: the wire, the clone-per-service and
clone-per-player, the player list, and which exception a failure wears. What
that client can *do* lives in three mixins beside it, and each says why it is
a separate file:

* ``player/lms_feed.py`` — how a streaming plugin's app feed is walked at
  all: the three-level OPML navigation (TIDAL, Qobuz, Spotty), documented
  there because that is where it lives.
* ``player/lms_catalog.py`` — what it is walked *for*: songs, albums,
  artists, playlists, and the favorites menu that shares their shape.
* ``player/lms_library.py`` — the music on the disk, by stable numeric id.
* ``player/lms_transport.py`` — play/pause/volume/seek/queue, and the reading
  that says what is playing.
* ``player/lms_services.py`` — the service table and the URI helpers they all
  read.

The split happened when this file reached 1317 lines and was the only one
exempt from the repo's own 400-line rule. Every name that was importable from
``lms`` still is: the imports below re-export them on purpose.
"""

from __future__ import annotations

import copy
import re
from typing import Any, Callable, Dict, List, Optional, Tuple

from player.errors import (PlayerError, PlayerRefused, PlayerUnreachable,
                           never_delivered)
# The breaker and the per-turn budget moved to player/resilience.py when a
# second backend needed them. The three names beside Resilient are unused
# here and imported on purpose: they were part of this module's surface
# before the move, and tests/test_lms_resilience.py still reaches for them.
from player.silence import SilentServices
from player.resilience import (BREAKER_COOLDOWN, BREAKER_THRESHOLD,  # noqa: F401
                               Breaker as _Breaker, Resilient)
from player.lms_catalog import LMSCatalog
from player.lms_feed import LMSFeed
from player.lms_library import LMSLibrary
from player.lms_transport import LMSTransport
# Re-exported, not used here: these were module-level names of this file
# before the split, and `from lms import SERVICES` (and the rest) has to keep
# working — engine/player/lms_backend.py, the tests, and the ServiceSpec
# comments scattered through engine/ all speak of them as living here.
from player.lms_services import (SERVICES, ServiceSpec, find_tidal_uri,  # noqa: F401
                                 find_uri, service_of, uri_kind)

# A transport takes the JSON-RPC ``params`` (``[player_id, [cmd, ...]]``) and
# returns the parsed ``result`` object from the LMS response.
Transport = Callable[[list], Dict[str, Any]]


class LMSError(PlayerError):
    """Raised when the LMS server cannot be reached or returns garbage.

    A :class:`~player.errors.PlayerError`, so the engine catches it with
    every other backend's failure and still says the one thing it has
    always said about a hi-fi that is not answering.
    """


class LMSUnreachable(LMSError, PlayerUnreachable):
    """The LMS gave no answer (see :class:`~player.errors.PlayerUnreachable`)."""


class LMSRefused(LMSError, PlayerRefused):
    """The LMS answered with an error or with something that is not a result."""


#: A number with a sign: a relative step. «mixer volume +5», «playlist index
#: +1», «time -10» — each one moves from wherever the player is, so sending it
#: twice moves twice.
_RELATIVE_ARG = re.compile(r"^[+-]\d")

#: Queue verbs that append rather than replace. «playlist play» and
#: «playlistcontrol cmd:load» put the same thing on the queue however many
#: times they are sent; these add it again each time.
_APPENDING = frozenset({"add", "insert", "addtracks", "inserttracks",
                        "cmd:add", "cmd:insert"})


def _lms_repeat_safe(cmd: List[str]) -> bool:
    """Whether an LMS command does the same thing sent twice as sent once."""
    words = [str(w).lower() for w in cmd]
    if any(_RELATIVE_ARG.match(w) for w in words):
        return False
    if words[:1] == ["button"]:
        return False
    return not any(w in _APPENDING for w in words)



class LMSClient(LMSCatalog, LMSFeed, LMSLibrary, LMSTransport, Resilient,
                SilentServices):
    #: Every round trip this client makes fails as an LMSError, breaker
    #: and turn budget included (see player/resilience.py).
    error = LMSError
    unreachable = LMSUnreachable
    refused = LMSRefused

    #: How the music system in front of the listener is spelled when a reply
    #: names it out loud — «Apri le impostazioni di …». It lives on the client
    #: and not in the message catalogs for the reason ``service`` labels do
    #: (see ``player.protocols.system_label``): the five catalogs said "LMS"
    #: to every household, including the ones whose hi-fi is a MusicAssistant
    #: and has no LMS settings page to open.
    #:
    #: On the CLASS, where ``Backend.client`` stamps ``capabilities`` on the
    #: INSTANCE, and the asymmetry is deliberate: a client built by hand has a
    #: sensible answer for a capability already ("it can do everything"), and
    #: none for a label — without this the sentence would lose its subject in
    #: every test and in every program that embeds the engine.
    #: ``lms_backend.BACKEND`` reads its own label from here, so the two
    #: cannot drift.
    SYSTEM_LABEL = "Lyrion Music Server"

    def __init__(
        self,
        base_url: str,
        player_id: str,
        username: Optional[str] = None,
        password: Optional[str] = None,
        timeout: float = 8.0,
        transport: Optional[Transport] = None,
        service: str = "tidal",
    ) -> None:
        if not base_url:
            raise ValueError("base_url is required")
        if not player_id:
            raise ValueError("player_id is required")
        if service not in SERVICES:
            raise ValueError(
                f"unknown service {service!r} (available: {', '.join(SERVICES)})"
            )
        self.base_url = base_url.rstrip("/")
        self.player_id = player_id
        self.username = username
        self.password = password
        self.service = SERVICES[service]
        self._transport: Transport = transport or self._http_transport
        # service tag -> (search node id or None, when it expires). A dict, so
        # the shallow copies for_service()/for_player() hand out SHARE it:
        # "is Qobuz logged in" is a fact about the server, not about which
        # clone asked. See search_node_id.
        self._search_nodes: Dict[str, Tuple[Optional[str], float]] = {}
        # "this service plays nothing today", shared between the clones for the
        # same reason (player/silence.py).
        self._init_silence()
        # timeout, breaker and per-turn budget, all shared with every other
        # backend. The breaker is deliberately a mutable object the shallow
        # copies of for_service()/for_player() SHARE, like the search-node
        # cache above and for the same reason.
        self._init_resilience(timeout)

    def for_service(self, name: str) -> "LMSClient":
        """This client re-targeted at another streaming service. Returns a
        shallow copy sharing transport/base_url/player, so one configured
        client can serve every registered service."""
        spec = SERVICES.get(name)
        if spec is None:
            raise ValueError(
                f"unknown service {name!r} (available: {', '.join(SERVICES)})"
            )
        if spec is self.service:
            return self
        clone = copy.copy(self)
        clone.service = spec
        return clone

    def for_player(self, player_id: Optional[str]) -> "LMSClient":
        """This client re-targeted at another player (multi-room). Returns a
        shallow copy sharing transport/base_url/service, so one configured
        client can command every player the LMS knows."""
        if not player_id or player_id == self.player_id:
            return self
        clone = copy.copy(self)
        clone.player_id = player_id
        return clone

    # -- low level ---------------------------------------------------------
    def _rpc(self, player: str, cmd: List[Any]) -> Dict[str, Any]:
        result = self._guarded([player, [str(c) for c in cmd]])
        if not isinstance(result, dict):
            raise LMSRefused(f"Unexpected LMS result type: {type(result)!r}")
        return result

    def _repeat_safe(self, request) -> bool:
        return _lms_repeat_safe(request[1])

    def command(self, *cmd: Any) -> Dict[str, Any]:
        """Run a command scoped to the configured player."""
        return self._rpc(self.player_id, list(cmd))

    def server_command(self, *cmd: Any) -> Dict[str, Any]:
        """Run a server-wide command (player id ``-``)."""
        return self._rpc("-", list(cmd))

    def _http_transport(self, params: list) -> Dict[str, Any]:
        import base64
        import http.client
        import json
        import urllib.error
        import urllib.request

        payload = json.dumps(
            {"id": 1, "method": "slim.request", "params": params}
        ).encode("utf-8")
        req = urllib.request.Request(
            self.base_url + "/jsonrpc.js",
            data=payload,
            headers={"Content-Type": "application/json"},
        )
        if self.username:
            token = base64.b64encode(
                f"{self.username}:{self.password or ''}".encode("utf-8")
            ).decode("ascii")
            req.add_header("Authorization", "Basic " + token)
        try:
            with urllib.request.urlopen(req, timeout=self._call_timeout()) as resp:
                body = json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            # An answer: a wrong password, a server error. Not silence, so
            # neither the retry nor the breaker has any business with it.
            raise LMSRefused(f"LMS answered {exc.code}: {exc.reason}") from exc
        except ValueError as exc:
            raise LMSRefused(f"LMS sent something that is not JSON: {exc}") from exc
        except (urllib.error.URLError, OSError,
                http.client.HTTPException) as exc:
            # http.client.HTTPException is NOT an OSError: an LMS restarted
            # mid-response raised BadStatusLine/IncompleteRead straight past
            # this handler, and the caller's `except LMSError` never saw it —
            # the page got a traceback instead of the friendly message.
            raise LMSUnreachable(f"LMS request failed: {exc}",
                                 delivered=not never_delivered(exc)) from exc
        if not isinstance(body, dict) or "result" not in body:
            raise LMSRefused(f"Unexpected LMS response: {body!r}")
        return body["result"]

    # -- players -----------------------------------------------------------
    def get_players(self) -> List[Dict[str, Any]]:
        res = self.server_command("players", "0", "100")
        return res.get("players_loop", []) or []

    def installed_services(self) -> List[str]:
        """Registered services whose plugin shows up in the player's LMS apps
        menu. The loop key is read in both spellings LMS has used."""
        res = self.command("apps", "0", "100")
        loop = res.get("appss_loop") or res.get("apps_loop") or []
        tags = {a.get("cmd") for a in loop if a.get("cmd")}
        return [name for name, spec in SERVICES.items() if spec.tag in tags]

    def known_services(self) -> List[str]:
        """Every service this client can be aimed at, installed or not.

        A fixed table, unlike :meth:`installed_services`, and deliberately
        answered without asking the server: what this is for is telling a name
        somebody typed from a typo, and a startup flag should not have to wait
        on a round trip — nor be rejected because the round trip failed.
        """
        return list(SERVICES)

