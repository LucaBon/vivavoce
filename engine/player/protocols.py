"""What the engine needs from a music system, split in two.

``engine/`` has never imported ``LMSClient``. It imports the error type and
calls methods on whatever object it was handed — ``matching.py`` says so out
loud: *"this module's contract is 'any object with the same methods', not 'an
LMSClient'"*. These protocols are that sentence written down, so a second
backend can be checked against it instead of discovering it by crashing.

**Why two and not one.** ``LMSClient`` does two unrelated jobs. It works the
transport controls — pause, volume, skip, the queue — which every target in
the world can do, from a Squeezebox to a Chromecast. And it searches a
catalogue, which a DLNA speaker cannot do at all: there is nothing in a pair
of powered speakers that knows who recorded «Comfortably Numb». Folding both
into one interface would mean every dumb device pretending to a library it has
not got. So: :class:`PlayerTransport` is what a *device* does,
:class:`MusicLibrary` is what a *catalogue* does, and a backend implements one
or both. LMS and MusicAssistant implement both.

**What is not here yet, and why.** Pairing a catalogue with somebody else's
speakers — a DLNA renderer, a Chromecast, a bare ``media_player`` — is the
obvious use of a split like this, and it does not work today. The engine
starts an album with ``play_browse_item(id)`` and a library record with
``play_local_album(id)``, and an id is a thing only the catalogue understands:
handed to a catalogue that is also a whole music system, it starts the music
on *that* system's own player rather than on the speakers being aimed at. A
composite would need a way to turn an id into playable URLs — one method, on
:class:`MusicLibrary` — and no backend in the tree needs it, so it has not
been invented on their behalf. Until then a household with dumb speakers is
served by pointing Vivavoce at MusicAssistant, which drives DLNA, Chromecast,
Sonos and AirPlay itself.

Nothing inherits from these. Backends stay duck-typed exactly as they are
today; the protocols are for the type checker and for
``tests/test_player_protocol.py``, which is where a backend that quietly
forgot a method gets caught.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional

try:  # pragma: no cover - typing only
    from typing import Protocol, runtime_checkable
except ImportError:  # pragma: no cover - Python 3.7 and older
    Protocol = object  # type: ignore[assignment]

    def runtime_checkable(cls):  # type: ignore[misc]
        return cls


@dataclass(frozen=True)
class Capabilities:
    """What a backend can actually do, declared rather than discovered.

    The engine asks before it offers. A speaker with no catalogue should
    answer «questo lettore non sa cercare» — a sentence the user can act on —
    rather than raise ``AttributeError`` three frames down and apologise with
    the generic "hi-fi not answering", which would be a lie.

    Declaring a capability is a promise that the matching methods exist:
    ``tests/test_player_protocol.py`` checks every backend against its own
    declaration, so the two cannot drift.
    """

    #: Free-text search over a catalogue (``search_tracks`` and friends).
    search: bool = False
    #: The ``local_*`` family: a library of files this system has indexed.
    local_library: bool = False
    #: Saved favourites and radio stations.
    favorites: bool = False
    #: Browse the local library by genre / by year.
    genres: bool = False
    years: bool = False
    #: Playback keyed by a catalogue id rather than a URL
    #: (``play_browse_item`` and the ``*_local_*`` family).
    browse_items: bool = False
    #: Several streaming services behind one system, switchable per request
    #: (``for_service`` / ``can_search`` / ``can_play`` /
    #: ``note_playback_failure`` / ``forget_playback_failure`` /
    #: ``installed_services``).
    services: bool = False
    #: A sleep timer the server itself owns.
    sleep_timer: bool = False
    #: Seek within the current track.
    seek: bool = False
    #: More than one player, addressable by id (``for_player`` / ``get_players``).
    multi_player: bool = False
    #: Cover art reachable from the status call.
    artwork: bool = False


@runtime_checkable
class PlayerTransport(Protocol):
    """A thing that makes noise: the controls that resolve nothing.

    Every method here acts on the player in front of it and needs no search,
    no candidates and no library — which is exactly what separates them from
    :class:`MusicLibrary`. ``engine/transport.py`` is built on this set alone.

    Implementations also carry a ``player_id`` attribute naming the player
    they are aimed at. It is not declared below because a protocol with data
    members behaves differently across the Python versions this project
    supports; ``tests/test_player_protocol.py`` checks for it directly.
    """

    # -- transport ---------------------------------------------------------
    def pause(self) -> Any: ...
    def resume(self) -> Any: ...
    def next_track(self) -> Any: ...
    def previous_track(self) -> Any: ...

    def volume(self, delta: int) -> Any:
        """Nudge the volume by ``delta`` notches of the 0-100 scale."""

    def volume_set(self, value: int) -> Any: ...
    def seek(self, seconds: float) -> Any: ...

    def sleep(self, seconds: int) -> Any:
        """Stop playback after ``seconds``; ``0`` cancels an armed timer."""

    # -- the queue ---------------------------------------------------------
    def clear_queue(self) -> Any: ...

    def queue_upcoming(self, limit: int = 5) -> List[Dict[str, Any]]:
        """The next few tracks after the current one, as
        ``{"title", "artist"}`` dicts."""

    # -- what is playing ---------------------------------------------------
    def now_playing_info(self) -> Optional[Dict[str, Any]]:
        """``{"title", "artist", "mode", "index", "elapsed"}`` for the queue
        head, or None.

        ``mode`` is ``"play"``, ``"pause"`` or ``"stop"`` — a stopped player
        must not be reported as playing whatever the queue head happens to be.
        ``index`` is the queue position (0 for the track a play just started)
        and ``elapsed`` the seconds played of it; together they are how
        ``engine/playback.py`` tells a queue that is playing from one walking
        through itself failing every track.
        """

    def status_info(self) -> Dict[str, Any]:
        """The fuller picture the web page shows: ``mode``, ``title``,
        ``artist``, ``album``, ``duration``, ``elapsed``, ``artwork``,
        ``volume``."""

    # -- starting something ------------------------------------------------
    def play_url(self, url: str) -> Any:
        """Replace the queue with ``url`` and start it."""

    def add_url(self, url: str) -> Any:
        """Append ``url`` to the end of the queue."""

    def insert_url(self, url: str) -> Any:
        """Queue ``url`` right after the current track."""

    def play_tracks(self, tracks: List[Any]) -> None:
        """Replace the queue with several tracks and start it."""

    # -- which player ------------------------------------------------------
    def get_players(self) -> List[Dict[str, Any]]:
        """Every player this system knows, as ``{"playerid", "name",
        "connected"}`` dicts."""

    def for_player(self, player_id: Optional[str]) -> "PlayerTransport":
        """This client, re-aimed at another player. Returns ``self`` when the
        id is empty or already the current one, so a caller never has to
        check."""


@runtime_checkable
class MusicLibrary(Protocol):
    """A thing that knows what music exists, and where.

    This is the half a dumb speaker has not got, and the half the product is
    actually about: everything here exists so that «metti Comfortably Numb dei
    Pink Floyd» can start *that* record rather than the first search hit.

    Only the search surface is declared here — see the note at the end of the
    class for what is governed by :class:`Capabilities` instead.

    Implementations also carry a ``service`` attribute describing the
    streaming service in play; ``matching._trusts_ranking`` reads
    ``service.trust_ranking`` through two ``getattr`` calls precisely so that a
    backend without the concept costs nothing.
    """

    # -- searching ---------------------------------------------------------
    def search_tracks(self, query: str, count: int = 20) -> List[Dict[str, Any]]:
        """Tracks matching ``query``, in the catalogue's own relevance order.

        Order matters and must not be re-sorted: ``actions._resolve_song``
        treats "the catalogue put it first" as evidence, but only for a search
        that answers *nothing* when nothing matches.
        """

    def track_url(self, item_id: str) -> Optional[str]:
        """The playable URL for a search result that carried only an id."""

    def album_candidates(self, query: str, count: int = 20) -> List[Dict[str, Any]]: ...
    def find_album(self, query: str, count: int = 20) -> Optional[Dict[str, Any]]: ...

    def album_tracks(self, query: str, count: int = 50) -> Dict[str, Any]:
        """``{"album": {...} | None, "tracks": [...]}``."""

    def artist_candidates(self, query: str, count: int = 20) -> List[Dict[str, Any]]: ...
    def find_artist(self, query: str, count: int = 20) -> Optional[Dict[str, Any]]: ...
    def artist_tracks(self, artist: Dict[str, Any], count: int = 20) -> List[Dict[str, Any]]: ...

    def artist_top_tracks(self, query: str, count: int = 20) -> Dict[str, Any]:
        """``{"artist": {...} | None, "tracks": [...]}``."""

    def playlist_candidates(self, query: str, count: int = 20) -> List[Dict[str, Any]]: ...
    def find_playlist(self, query: str, count: int = 20) -> Optional[Dict[str, Any]]: ...

    # -- beyond here, ask Capabilities first -------------------------------
    # The members below are NOT declared on this protocol, deliberately. Each
    # belongs to a capability a backend may not have, and a protocol that
    # demanded all of them would make "searches a catalogue" and "indexes a
    # library by year" the same claim. MusicAssistant, for instance, does
    # everything here except years — there is no year listing in it to have.
    #
    # They are still part of the contract; what governs them is
    # :class:`Capabilities` rather than this class, and
    # ``tests/test_player_protocol.py`` holds a backend to whichever ones it
    # declares:
    #
    #   local_library  local_{album,artist,track}_candidates,
    #                  find_local_{album,artist,track}, local_albums_by_artist,
    #                  blocking_service
    #   genres         local_genres, play_local_genre
    #   years          local_years, play_local_year
    #   browse_items   {play,add,insert}_browse_item and the matching
    #                  {play,add,insert}_local_{album,artist,track} family
    #   favorites      favorites_items, favorites_playlist_play
    #   services       installed_services, can_search, can_play,
    #                  note_playback_failure, forget_playback_failure,
    #                  for_service
    #
    # Three of those families are reached through
    # ``getattr(client, f"{mode}_...")`` in ``actions`` and ``library``, so
    # their NAMES are load-bearing: a generic ``enqueue(mode=...)`` would not
    # be found.
