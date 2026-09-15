"""MusicAssistant as a Vivavoce backend.

MusicAssistant is a server, not a Home Assistant integration: it indexes a
library, talks to TIDAL/Qobuz/Spotify, and drives players of its own —
including DLNA, Chromecast, Sonos and AirPlay. That last part is why this is
the backend worth having second. A dumb speaker needs someone to resolve a
request into a stream it can actually swallow, and MusicAssistant already is
that someone. Driving it gets every player it supports, without this project
learning SSDP, SOAP or protobuf.

The catalogue half lives in :mod:`player.ma_library`, the wire in
:mod:`player.ma_transport` and the registration in :mod:`player.ma_backend`.
What is left here is the device half — the controls that resolve nothing —
plus construction and the two re-aimings the engine leans on.

Every command name and argument name below was read off
``music-assistant/server`` on 2026-09-11.
"""

from __future__ import annotations

import copy
import time
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

from .ma_library import MusicAssistantLibrary
from .resilience import Resilient
from .silence import SilentServices
from .ma_transport import MusicAssistantError, Transport, post

#: How the three enqueue modes the engine speaks are spelled on the wire.
#: From ``QueueOption``: REPLACE empties the queue and starts at the top, ADD
#: appends, NEXT goes in after whatever is playing.
_QUEUE_OPTION = {"play": "replace", "add": "add", "insert": "next"}

#: MusicAssistant's playback states, as the engine's ``mode``. The engine
#: distinguishes three things and only three: playing, paused, and nothing.
_PLAYBACK_STATE = {"playing": "play", "paused": "pause", "idle": "stop"}

#: How long a player's queue id is trusted before being looked up again.
QUEUE_TTL = 30.0

#: Music providers that are the local library wearing a different hat. They
#: are real providers, but offering one as "a streaming service to play from"
#: would be offering the user their own files twice.
_LOCAL_PROVIDERS = ("filesystem", "filesystem_local", "filesystem_smb")


@dataclass(frozen=True)
class MAService:
    """One streaming service, as much of it as the engine actually reads.

    Much smaller than the LMS ``ServiceSpec``, because everything that one
    carries — a CLI tag, URI schemes, the localized names of menu nodes — is
    about navigating a plugin's menu tree, and there is no menu tree here.
    What survives is the one judgement that is about the *service* rather than
    about the server in front of it.
    """

    #: Provider domain as MusicAssistant spells it, or "" for "all of them".
    name: str = ""
    #: How it is said out loud.
    label: str = ""
    #: Whether "the search returned it first" is evidence of what was asked
    #: for. It is for a search that answers *nothing* when nothing matches.
    #: Spotify's search always answers — «zzzzqqqxyzzy» comes back with
    #: fourteen tracks — so there the top result is a guess presented as an
    #: answer. That is a fact about Spotify, not about which server is asking,
    #: which is why it is spelled the same way here as in ``lms.SERVICES``.
    trust_ranking: bool = True


def _service(name: Optional[str]) -> MAService:
    name = (name or "").strip().lower()
    return MAService(name=name, label=name.replace("_", " ").title() or "",
                     trust_ranking=name != "spotify")


class MusicAssistantClient(Resilient, MusicAssistantLibrary, SilentServices):
    """One MusicAssistant server, aimed at one of its players.

    Shaped deliberately like ``LMSClient``, down to the injectable transport
    and the two shallow-copy re-aimings, because the engine hands the two
    objects to the same functions and a reader comparing them should be able
    to see one difference at a time.
    """

    #: Every round trip fails as this, breaker and turn budget included.
    error = MusicAssistantError

    def __init__(
        self,
        base_url: str,
        player_id: str,
        token: str = "",
        timeout: float = 8.0,
        transport: Optional[Transport] = None,
        service: str = "",
    ) -> None:
        if not base_url:
            raise ValueError("base_url is required")
        if not player_id:
            raise ValueError("player_id is required")
        self.base_url = base_url.rstrip("/")
        self.player_id = player_id
        self.token = token
        self.service = _service(service)
        self._transport: Transport = transport or self._http_transport
        # player id -> (queue id, when it expires). A dict, so the shallow
        # copies handed out by for_player()/for_service() SHARE it: which
        # queue a player is on is a fact about the server, not about which
        # clone asked. Same reasoning as LMSClient._search_nodes.
        self._queues: Dict[str, Tuple[str, float]] = {}
        # "this provider plays nothing today", shared between the clones like
        # the queues above (player/silence.py).
        self._init_silence()
        self._init_resilience(timeout)

    # -- re-aiming ---------------------------------------------------------
    def for_service(self, name: str) -> "MusicAssistantClient":
        """This client, restricted to one music provider.

        No registry to validate against, unlike LMS: a provider domain is
        whatever the user has configured, and MusicAssistant is the only thing
        that can say which those are (see :meth:`installed_services`).
        """
        service = _service(name)
        if service == self.service:
            return self
        clone = copy.copy(self)
        clone.service = service
        return clone

    def for_player(self, player_id: Optional[str]) -> "MusicAssistantClient":
        """This client, aimed at another player (multi-room)."""
        if not player_id or player_id == self.player_id:
            return self
        clone = copy.copy(self)
        clone.player_id = player_id
        return clone

    # -- low level ---------------------------------------------------------
    def _http_transport(self, request: Dict[str, Any]) -> Any:
        return post(self.base_url, self.token, request, self._call_timeout())

    def _call(self, command: str, **args: Any) -> Any:
        """One command, behind the breaker and the turn budget.

        Arguments that are ``None`` are dropped rather than sent: every
        optional argument on the server has a default worth having, and
        spelling it ``null`` overrides it with nothing.
        """
        return self._guarded({
            "command": command,
            "args": {k: v for k, v in args.items() if v is not None},
        })

    def _queue_id(self) -> str:
        """The queue this player is really on.

        Not always its own: a player synced into a group plays the group's
        queue, and sending ``player_queues/clear`` to the member would clear a
        queue nobody is listening to. Asking costs one round trip, so the
        answer is kept for :data:`QUEUE_TTL` — long enough to spend once per
        turn rather than once per command.
        """
        cached = self._queues.get(self.player_id)
        if cached is not None and cached[1] > time.monotonic():
            return cached[0]
        queue = self._call("player_queues/get_active_queue",
                           player_id=self.player_id) or {}
        queue_id = queue.get("queue_id") or self.player_id
        self._queues[self.player_id] = (queue_id, time.monotonic() + QUEUE_TTL)
        return queue_id

    def _enqueue(self, media: Any, mode: str = "play") -> Any:
        return self._call("player_queues/play_media", queue_id=self._queue_id(),
                          media=media, option=_QUEUE_OPTION[mode])

    # -- transport ---------------------------------------------------------
    # Every players/cmd/* takes a player_id and redirects itself to the active
    # queue, so these need no queue lookup.
    def pause(self) -> Any:
        return self._call("players/cmd/pause", player_id=self.player_id)

    def resume(self) -> Any:
        return self._call("players/cmd/play", player_id=self.player_id)

    def next_track(self) -> Any:
        return self._call("players/cmd/next", player_id=self.player_id)

    def previous_track(self) -> Any:
        return self._call("players/cmd/previous", player_id=self.player_id)

    def volume(self, delta: int) -> Any:
        """One notch up or down.

        The engine asks in notches of its own (``transport.VOLUME_STEP``);
        MusicAssistant has a step per player, configured by whoever set the
        player up. Its step wins, because it is the one that suits the
        amplifier. So the sign is honoured and the size is not.
        """
        command = "volume_up" if delta >= 0 else "volume_down"
        return self._call(f"players/cmd/{command}", player_id=self.player_id)

    def volume_set(self, value: int) -> Any:
        return self._call("players/cmd/volume_set", player_id=self.player_id,
                          volume_level=max(0, min(100, int(value))))

    def seek(self, seconds: float) -> Any:
        return self._call("players/cmd/seek", player_id=self.player_id,
                          position=int(seconds))

    def sleep(self, seconds: int) -> Any:
        """Arm the server's own sleep timer; ``0`` cancels it."""
        if seconds and int(seconds) > 0:
            return self._call("players/sleep_timer/set",
                              player_id=self.player_id, seconds=int(seconds))
        return self._call("players/sleep_timer/clear", player_id=self.player_id)

    # -- the queue ---------------------------------------------------------
    def clear_queue(self) -> Any:
        return self._call("player_queues/clear", queue_id=self._queue_id())

    def queue_upcoming(self, limit: int = 5) -> List[Dict[str, Any]]:
        queue_id = self._queue_id()
        queue = self._call("player_queues/get", queue_id=queue_id) or {}
        index = queue.get("current_index")
        offset = 0 if index is None else int(index) + 1
        rows = self._call("player_queues/items", queue_id=queue_id,
                          limit=limit, offset=offset) or []
        return [_queue_entry(row) for row in rows]

    # -- what is playing ---------------------------------------------------
    def now_playing_info(self) -> Optional[Dict[str, Any]]:
        queue = self._call("player_queues/get",
                           queue_id=self._queue_id()) or {}
        item = queue.get("current_item")
        if not item:
            return None
        info = _queue_entry(item)
        info["mode"] = _PLAYBACK_STATE.get(queue.get("state"), "stop")
        # Position and elapsed: what tells a queue that is playing from one
        # walking through itself failing every track (engine/playback.py).
        info["index"] = queue.get("current_index") or 0
        info["elapsed"] = queue.get("elapsed_time") or 0
        return info

    def status_info(self) -> Dict[str, Any]:
        queue = self._call("player_queues/get",
                           queue_id=self._queue_id()) or {}
        player = self._call("players/get", player_id=self.player_id) or {}
        item = queue.get("current_item") or {}
        media = item.get("media_item") or {}
        entry = _queue_entry(item) if item else {}
        return {
            "mode": _PLAYBACK_STATE.get(queue.get("state"), "stop"),
            "title": entry.get("title"),
            "artist": entry.get("artist"),
            "album": (media.get("album") or {}).get("name"),
            "duration": item.get("duration"),
            "elapsed": queue.get("elapsed_time"),
            "artwork": self._artwork(item.get("image")),
            "volume": player.get("volume_level"),
        }

    def _artwork(self, image: Optional[Dict[str, Any]]) -> Optional[str]:
        """An absolute URL for the cover, or None.

        Two shapes, both documented on ``MediaItemImage``: an image the
        provider serves publicly carries its own URL, and everything else is
        fetched back through this server's image proxy. Absolute either way,
        which is what ``http_api._send_artwork`` wants — it only prefixes a
        base URL onto a path that has no scheme.
        """
        if not image:
            return None
        if image.get("remotely_accessible") and image.get("path"):
            return image["path"]
        if image.get("proxy_id"):
            return f"{self.base_url}/imageproxy/{image['proxy_id']}"
        return None

    # -- starting something ------------------------------------------------
    def play_url(self, url: str) -> Any:
        return self._enqueue(url, "play")

    def add_url(self, url: str) -> Any:
        return self._enqueue(url, "add")

    def insert_url(self, url: str) -> Any:
        return self._enqueue(url, "insert")

    def play_tracks(self, tracks: List[Any]) -> None:
        """Replace the queue with several tracks. One call, not one per track:
        play_media takes a list, and enqueuing them one at a time would race
        the first one starting."""
        urls = [t.get("url") for t in tracks
                if isinstance(t, dict) and t.get("url")]
        if urls:
            self._enqueue(urls, "play")

    # -- which player, which service --------------------------------------
    def get_players(self) -> List[Dict[str, Any]]:
        """Every player, in the shape the rest of the app reads.

        ``playerid`` and not ``player_id``: that spelling is the LMS one, and
        it reaches the web page, the ``/players`` endpoint and the multi-room
        room matcher. Renaming it is a change to a published API, not to this
        backend, so the translation happens here.
        """
        rows = self._call("players/all") or []
        return [{"playerid": p.get("player_id"), "name": p.get("name"),
                 "connected": p.get("available", True)} for p in rows]

    def _music_providers(self, *, switched_on: bool) -> List[str]:
        """The streaming music providers this server is configured with."""
        configs = self._call("config/providers", provider_type="music") or []
        found = []
        for config in configs:
            domain = config.get("domain")
            if not domain or (switched_on and not config.get("enabled", True)):
                continue
            if domain in _LOCAL_PROVIDERS or domain in found:
                continue
            found.append(domain)
        return found

    def installed_services(self) -> List[str]:
        """The music providers configured and switched on, streaming only."""
        return self._music_providers(switched_on=True)

    def known_services(self) -> List[str]:
        """Every service this client can be aimed at, switched on or not.

        No fixed table to answer from, unlike LMS — a provider domain is
        whatever this server was set up with. Switched OFF still counts, and
        that is the whole difference from :meth:`installed_services`: this
        answers "is this a name you know", and a provider being
        re-authenticated this morning is not a name somebody mistyped.
        """
        return self._music_providers(switched_on=False)

    def can_search(self) -> bool:
        """Whether the service this client is aimed at will answer.

        Unaimed, the answer is yes and means something stronger than it does
        on LMS: MusicAssistant searches the library even with no streaming
        provider connected at all, so there is always something to ask.
        """
        if not self.service.name:
            return True
        return self.service.name in self.installed_services()


def _queue_entry(item: Dict[str, Any]) -> Dict[str, Any]:
    """A queue item as ``{"title", "artist"}``.

    ``media_item`` first: a queue item's own ``name`` is a display line that
    can already read "Artist - Title", and repeating the artist inside the
    title is exactly the kind of thing a spoken reply cannot hide.
    """
    media = item.get("media_item") or {}
    title = media.get("name") or item.get("name")
    entry: Dict[str, Any] = {"title": title}
    for artist in media.get("artists") or ():
        if artist.get("name"):
            entry["artist"] = artist["name"]
            break
    return entry
