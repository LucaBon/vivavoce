"""Minimal Lyrion/Logitech Media Server (LMS) JSON-RPC client.

Talks to the LMS/Daphile control interface at ``<base_url>/jsonrpc.js`` using the
``slim.request`` method. The transport is injectable so the whole client can be
unit-tested without any network access (see ``tests/``).

Streaming search & playback (app feeds)
---------------------------------------
Streaming plugins (TIDAL, Qobuz, Spotify) expose an LMS *app feed* — an OPML tree browsed
via the ``items`` command; results come back under the ``loop_loop`` key. Which
feed a client instance talks to is set by its ``ServiceSpec`` (see ``SERVICES``).
Searching is a three-level navigation:

1. Home menu ``["<tag>","items",0,N]`` contains a node of ``type == "search"``.
2. Enter it with ``item_id:<searchNodeId>`` + ``search:<term>`` -> category nodes
   ``Everything / Playlists / Artists / Albums / Songs`` (each with its own id).
3. Enter a category's id -> the actual items.

Item shapes (confirmed live for TIDAL, tag ``tidal``, plugin
``michaelherger/lms-plugin-tidal``):

* Song  -> ``{"type":"audio","isaudio":1,"url":"tidal://55391466.flc", ...}``  (play the url)
* Album/Playlist -> ``{"type":"playlist","isaudio":1,"hasitems":1, ...}`` (no url;
  play via ``["<tag>","playlist","play","item_id:<id>"]``)
* Artist -> ``{"type":"outline","hasitems":1, ...}`` (browsable; played the same way)

Qobuz (tag ``qobuz``, plugin ``LMS-Community/plugin-Qobuz`` 3.7.0) follows the
same pattern and is verified live too (2026-07-14); its quirks — nested search
node, "Releases" category, " (Hi-Res)" title tag, "Artist - Album" text line —
are captured in ``SERVICES["qobuz"]``.

Spotify (tag ``spotty``) is verified live too (2026-08-28) and does **not**
follow the pattern above: no Songs category, tracks listed beside the category
links, no url on a track, and title/artist/album packed into one name. It needs
Spotify Premium — Spotty plays through Spotify Connect — and its search never
answers "nothing", which is why ``trust_ranking`` exists. See the comment on
``SERVICES["spotify"]``.

Category names are matched against the per-service alias tables; adjust if your
LMS UI language changes them.
"""

from __future__ import annotations

import copy
import re
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Tuple

# A transport takes the JSON-RPC ``params`` (``[player_id, [cmd, ...]]``) and
# returns the parsed ``result`` object from the LMS response.
Transport = Callable[[list], Dict[str, Any]]


def _uri_re(schemes: Tuple[str, ...]) -> "re.Pattern":
    """URI regex for a service's scheme(s): entity forms (``album:ID`` etc.) or
    the bare-track form ``<digits>.<ext>`` (e.g. ``tidal://55391466.flc``)."""
    alt = "|".join(re.escape(s) for s in schemes)
    return re.compile(
        rf"(?:{alt})://(?:(?:track|album|artist|playlist|mix):[^\s\"']+|\d+\.[A-Za-z0-9]+)",
        re.IGNORECASE,
    )


@dataclass(frozen=True)
class ServiceSpec:
    """Everything service-specific about an LMS streaming app feed."""

    name: str                    # registry key as spoken: "tidal" / "spotify"
    tag: str                     # CLI tag: cmd[0] of ["<tag>","items",...]
                                 # (not always the name: "spotify" -> "spotty")
    schemes: Tuple[str, ...]     # URL scheme(s) the plugin's tracks use
    category_aliases: Dict[str, tuple]  # canonical -> names the plugin may show
    artist_children: Tuple[str, ...]    # playable child nodes under an artist
    # How the name is spelled when a reply says it out loud: "qobuz" is a
    # config key, «Qobuz» is what the user hears. It lives here because the
    # registry is where a service is described, and two modules now need it —
    # the source tag on a play confirmation and the engine's own "that service
    # is not connected".
    label: str = ""
    # Some plugins (Qobuz) nest the search node one level down: home shows a
    # plain "Search" link whose CHILD is the ``type == "search"`` node. These
    # are the (lowercased) home-menu names worth entering to look for it.
    search_parents: Tuple[str, ...] = ()
    # Display noise the plugin appends to track titles (e.g. Qobuz's
    # " (Hi-Res)" quality tag and " [E]" parental marker), stripped before
    # scoring/confirmation so «Comfortably Numb» matches exactly.
    title_noise_re: Any = None
    # When the menu-mode text's 2nd line is "Artist<sep>Album" (Qobuz) rather
    # than just the artist (TIDAL), split on this to keep the artist part.
    artist_line_sep: Optional[str] = None
    # Spotty does not put songs in a category. Its search node answers with the
    # category links (Artists/Albums/Playlists/...) and the matching *tracks as
    # their siblings*, flagged ``isaudio``, with title/artist/album packed into
    # one ``name`` and no url at all. Two flags describe that shape:
    #   tracks_inline   read tracks from the search node's own children rather
    #                   than from a "Songs" category, which does not exist
    #   track_name_re   splits that one name; groups: title, artist, album
    tracks_inline: bool = False
    track_name_re: Any = None
    # The same packaging on an album row, which carries no " from " part:
    # "Brothers In Arms (Remastered 1996) by Dire Straits".
    album_name_re: Any = None
    # An artist's child nodes are rendered in the LMS UI language, exactly like
    # the search categories above — and unlike them, they used to be matched
    # exactly and case-sensitively against the English names in
    # ``artist_children``, so a plugin showing «Brani» made every artist
    # unplayable and said "non posso riprodurre" about a catalogue that had the
    # music. Canonical name -> the spellings a plugin may show; a canonical
    # name that is also a search category falls back to ``category_aliases``,
    # since it is the same word in the same language. Matching is
    # case-insensitive either way.
    #
    # Deliberately empty for the names that are NOT also categories ("Top
    # Tracks", "Artist Mix"): their localized spellings have not been read off
    # a live plugin, and guessing them here would be indistinguishable from
    # having verified them. ``tools/probe_lms.py`` prints the verbatim names —
    # that is where the entries come from.
    artist_child_aliases: Dict[str, tuple] = field(default_factory=dict)
    # Whether "no title matched, so play the top result" is a safe fallback.
    # It is for a search that answers *nothing* when nothing matches, which is
    # what TIDAL and Qobuz do — there, the top result being returned at all is
    # itself evidence. Spotify's search always answers: «zzzzqqqxyzzy» comes
    # back with fourteen tracks, and trusting the ranking there means playing a
    # song nobody asked for, in silence, which is the one thing this product
    # promises not to do. Off for such a service: say it was not found.
    trust_ranking: bool = True
    uri_re: Any = field(init=False, default=None, repr=False, compare=False)

    def __post_init__(self):
        object.__setattr__(self, "uri_re", _uri_re(self.schemes))


# How many non-track rows a ``tracks_inline`` feed puts before the tracks.
# Six on Spotty (Artists, Albums, Playlists, Podcasts, Podcast Episodes,
# Users); asking for a few more than that costs nothing and guards against the
# plugin adding a seventh.
_INLINE_HEADROOM = 10

# "1. So Far Away ..." — the position Spotty prefixes to album tracks.
_TRACK_NUMBER_RE = re.compile(r"^\d{1,3}\.\s+")

SERVICES: Dict[str, ServiceSpec] = {
    # Verified against a live LMS/Daphile (see module docstring).
    "tidal": ServiceSpec(
        name="tidal",
        tag="tidal",
        label="TIDAL",
        schemes=("tidal", "wimp"),  # wimp:// is the legacy TIDAL scheme
        category_aliases={
            "Songs": ("Songs", "Brani", "Canzoni", "Tracce"),
            "Albums": ("Albums", "Album"),
            "Artists": ("Artists", "Artisti"),
            "Playlists": ("Playlists", "Playlist"),
        },
        artist_children=("Top Tracks", "Artist Mix"),
    ),
    # Verified live against LMS 9.0.3 + plugin-Qobuz 3.7.0 (2026-07-14):
    # categories come back as Releases/Artists/Songs/Playlists, the search
    # node is nested under a "Search" link, tracks are ``qobuz://<id>.flac``,
    # titles carry " (Hi-Res)" and the artist line is "Artist - Album".
    "qobuz": ServiceSpec(
        name="qobuz",
        tag="qobuz",
        label="Qobuz",
        schemes=("qobuz",),
        category_aliases={
            "Songs": ("Songs", "Tracks", "Brani", "Canzoni", "Tracce"),
            "Albums": ("Releases", "Albums", "Album"),
            "Artists": ("Artists", "Artisti"),
            "Playlists": ("Playlists", "Playlist"),
        },
        artist_children=("Songs", "Top Tracks"),
        search_parents=("search", "cerca", "ricerca"),
        title_noise_re=re.compile(r"(?:\s*\(Hi-Res\)|\s*\[E\])+\s*$", re.IGNORECASE),
        artist_line_sep=" - ",
    ),
    # Spotify, through the Spotty plugin (``cmd`` is "spotty", not "spotify" —
    # the registry key is what a person says, the tag is what LMS answers to).
    #
    # Verified live against LMS 9.0.3 + Spotty (2026-08-28), and it turned out
    # not to follow the pattern the other two share. Three differences, each
    # read off the wire rather than assumed:
    #
    #  1. **there is no Songs category.** The search node answers with the
    #     category links — Artists, Albums, Playlists, Podcasts, Podcast
    #     Episodes, Users — and then the matching tracks as their *siblings*;
    #  2. **a track carries no url.** It is `{"id", "name", "isaudio": 1,
    #     "hasitems": 1}` and nothing else. The url lives one level down, as the
    #     name of its single ``type == "audio"`` child:
    #     ``spotify://track:01Txvu3dNthhldq8oR0Pae``. See ``track_url``;
    #  3. **title, artist and album are one string**, "T by A from B", where the
    #     other two feeds give a separate ``text`` line.
    #
    # It also needs Spotify Premium, which is not a detail: Spotty plays through
    # Spotify Connect, so on a free account its whole menu is one "credentials
    # missing" notice and every search here returns nothing.
    "spotify": ServiceSpec(
        name="spotify",
        tag="spotty",
        label="Spotify",
        schemes=("spotify",),
        # No "Songs": that is the whole point of ``tracks_inline`` below. The
        # four that are here were read off a live search.
        category_aliases={
            "Albums": ("Albums", "Album"),
            "Artists": ("Artists", "Artisti"),
            "Playlists": ("Playlists", "Playlist"),
            "Podcasts": ("Podcasts", "Podcast"),
        },
        # Read off a live artist node, whose children are: Albums, Singles &
        # EPs, Compilations, Top Tracks, Artist Radio, Related Artists, Follow
        # artist. Only the one we can play is listed — a speculative entry in
        # here would cost the table the thing that makes it worth reading.
        artist_children=("Top Tracks",),
        search_parents=("search", "cerca", "ricerca"),
        tracks_inline=True,
        trust_ranking=False,
        # "Money For Nothing by Dire Straits from The Best Of Dire Straits".
        # The title group is greedy on purpose: an artist almost never contains
        # " by " while a title routinely does, so «Killed by Death by Motorhead
        # from ...» has to give the last " by " to the split, not the first.
        track_name_re=re.compile(r"^(?P<title>.+) by (?P<artist>.+?) from "
                                 r"(?P<album>.+)$"),
        album_name_re=re.compile(r"^(?P<title>.+) by (?P<artist>.+)$"),
    ),
}

# All registered schemes, for service-independent URI classification.
_ANY_SCHEME = "|".join(
    re.escape(s) for spec in SERVICES.values() for s in spec.schemes
)

# Backward-compatible alias (the TIDAL-only regex predates ServiceSpec).
_TIDAL_URI = SERVICES["tidal"].uri_re

# Scheme -> registry name, for the two places LMS names a service in a library
# row: the track url (``tidal://322955652.flc``) and the ``extid`` of a row
# imported from an online library (``tidal:album:322955651``, and for an artist
# a comma-separated list, ``qobuz:artist:6505891,tidal:artist:15694955``). Both
# spell the service the same way the registry does, which is why one map reads
# both.
_SERVICE_BY_SCHEME = {scheme: name
                      for name, spec in SERVICES.items()
                      for scheme in spec.schemes}


def service_of(uri: Optional[str]) -> Optional[str]:
    """The registry name behind a library row's url or ``extid``; None for a
    file on a disk, which needs nobody's permission to play."""
    if not uri:
        return None
    return _SERVICE_BY_SCHEME.get(str(uri).split(":", 1)[0].strip().lower())


def _with_extid(cand: Dict[str, Any], row: Dict[str, Any]) -> Dict[str, Any]:
    """``cand`` plus the row's ``extid``, and only when it has one — which is
    the same thing as saying the row was imported from an online library. A
    key that is present and empty would say something else, and every caller
    that compares whole candidate dicts would have to learn about it."""
    if row.get("extid"):
        cand["extid"] = row["extid"]
    return cand


def service_label(name: Optional[str]) -> str:
    """How a service is spelled when a reply says it out loud (``ServiceSpec.
    label``): 'qobuz' is a config key, «Qobuz» is what the user hears."""
    spec = SERVICES.get(name or "")
    return (spec.label if spec and spec.label else (name or ""))


class LMSError(Exception):
    """Raised when the LMS server cannot be reached or returns garbage."""


def find_uri(obj: Any, pattern: "re.Pattern") -> Optional[str]:
    """Recursively search a (possibly nested) OPML item for the first URI
    matching ``pattern``."""
    if isinstance(obj, str):
        match = pattern.search(obj)
        return match.group(0) if match else None
    if isinstance(obj, dict):
        for value in obj.values():
            uri = find_uri(value, pattern)
            if uri:
                return uri
    elif isinstance(obj, (list, tuple)):
        for value in obj:
            uri = find_uri(value, pattern)
            if uri:
                return uri
    return None


def find_tidal_uri(obj: Any) -> Optional[str]:
    """Recursively search a (possibly nested) OPML item for the first TIDAL URI."""
    return find_uri(obj, _TIDAL_URI)


def _split_text(text: Any) -> tuple:
    """Split a menu item's ``text`` ('Title\\nArtist') into (title, artist)."""
    if not text:
        return None, None
    lines = [p.strip() for p in str(text).split("\n") if p.strip()]
    if len(lines) >= 2:
        return lines[0], lines[1]
    return (lines[0] if lines else None), None


def uri_kind(uri: str) -> Optional[str]:
    """Classify a streaming URI (any registered service) as
    track/album/artist/playlist/mix."""
    match = re.match(
        rf"(?:{_ANY_SCHEME})://(track|album|artist|playlist|mix):", uri, re.IGNORECASE
    )
    if match:
        return match.group(1).lower()
    if re.match(rf"(?:{_ANY_SCHEME})://\d+\.[A-Za-z0-9]+$", uri, re.IGNORECASE):
        return "track"
    return None


class LMSClient:
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
        self.timeout = timeout
        self.service = SERVICES[service]
        self._transport: Transport = transport or self._http_transport
        # service tag -> (search node id or None, when it expires). A dict, so
        # the shallow copies for_service()/for_player() hand out SHARE it:
        # "is Qobuz logged in" is a fact about the server, not about which
        # clone asked. See search_node_id.
        self._search_nodes: Dict[str, Tuple[Optional[str], float]] = {}

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
        result = self._transport([player, [str(c) for c in cmd]])
        if not isinstance(result, dict):
            raise LMSError(f"Unexpected LMS result type: {type(result)!r}")
        return result

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
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                body = json.loads(resp.read().decode("utf-8"))
        except (urllib.error.URLError, OSError, ValueError,
                http.client.HTTPException) as exc:
            # http.client.HTTPException is NOT an OSError: an LMS restarted
            # mid-response raised BadStatusLine/IncompleteRead straight past
            # this handler, and the caller's `except LMSError` never saw it —
            # the page got a traceback instead of the friendly message.
            raise LMSError(f"LMS request failed: {exc}") from exc
        if not isinstance(body, dict) or "result" not in body:
            raise LMSError(f"Unexpected LMS response: {body!r}")
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

    # -- streaming app-feed browse/search (TIDAL, Qobuz, ...) --------------
    def _app_items(self, *params: Any) -> List[Dict[str, Any]]:
        res = self.command(self.service.tag, "items", *params)
        return res.get("loop_loop") or res.get("item_loop") or []

    #: How long a search-node lookup is trusted. It buys two things at once:
    #: the extra round-trip ``can_search`` would otherwise add to every
    #: streaming request (the search path asks for the same node moments
    #: later), and a bound on how long a plugin that has just been logged in
    #: keeps being reported as offline. Short enough that authenticating in
    #: LMS and speaking the next sentence works without restarting the app.
    SEARCH_NODE_TTL = 30.0

    def search_node_id(self) -> Optional[str]:
        """Id of the plugin's search node (type == 'search'), or None when the
        plugin has none to give — which is what an unauthenticated service
        looks like from here: a TIDAL that is logged out answers its whole
        menu with one 'Please go to Settings/Advanced/TIDAL' textarea.

        Memoized per service for ``SEARCH_NODE_TTL`` seconds (see there)."""
        cached = self._search_nodes.get(self.service.tag)
        if cached is not None and cached[1] > time.monotonic():
            return cached[0]
        node = self._find_search_node()
        self._search_nodes[self.service.tag] = (
            node, time.monotonic() + self.SEARCH_NODE_TTL)
        return node

    def can_search(self) -> bool:
        """Whether this service can answer a search at all — i.e. whether the
        plugin is installed AND logged in. False is the difference between
        "your music isn't there" and "nobody was asked", and the router needs
        it to tell those two apart before it reports a miss."""
        try:
            return self.search_node_id() is not None
        except LMSError:
            return False

    def _find_search_node(self) -> Optional[str]:
        """The uncached lookup behind :meth:`search_node_id`.

        TIDAL exposes the node right in the home menu; Qobuz nests it one
        level down (home 'Search' link -> 'New search'), so when the home menu
        has none we enter the ``search_parents`` nodes and look again."""
        items = self._app_items("0", "50")
        for item in items:
            if item.get("type") == "search":
                return item.get("id")
        for item in items:
            name = (item.get("name") or "").strip().lower()
            if item.get("id") and item.get("hasitems") and name in self.service.search_parents:
                for child in self._app_items("0", "50", f"item_id:{item['id']}"):
                    if child.get("type") == "search":
                        return child.get("id")
        return None

    def search_categories(self, query: str, count: int = 30) -> Dict[str, str]:
        """Map of category name -> node id for a query (Songs, Artists, ...)."""
        node = self.search_node_id()
        if node is None:
            return {}
        items = self._app_items(
            "0", str(count), f"item_id:{node}", f"search:{query}"
        )
        return {it["name"]: it["id"] for it in items if it.get("name") and it.get("id")}

    # Canonical category -> accepted names as the plugin may localize them
    # (per-service table). We match by name (case-insensitive) trying each
    # alias, so search keeps working if the LMS UI language is switched.
    def _resolve_category(self, cats: Dict[str, str], canonical: str) -> Optional[str]:
        wanted = self.service.category_aliases.get(canonical, (canonical,))
        norm = {name.strip().lower(): cid for name, cid in cats.items()}
        for alias in wanted:
            cid = norm.get(alias.strip().lower())
            if cid:
                return cid
        return None

    def category_items(
        self, query: str, category: str, count: int = 20
    ) -> List[Dict[str, Any]]:
        cats = self.search_categories(query, count)
        node_id = self._resolve_category(cats, category)
        if not node_id:
            return []
        return self._app_items("0", str(count), f"item_id:{node_id}", "want_url:1")

    def _clean_name(self, name: Optional[str]) -> Optional[str]:
        """Strip a feed's display packaging from an item name.

        Spotty writes the same "T by A from B" into *album* listings as into
        search results, and prefixes album tracks with "1. ". Nothing plays by
        these strings — ranking absorbs the extra words — but they are read
        back aloud, and «Metto "1. So Far Away - Remastered 1996 by Dire
        Straits from Brothers In Arms"» is not a sentence to say to somebody.
        Services with no ``track_name_re`` are untouched.
        """
        if not name:
            return name
        cleaned = _TRACK_NUMBER_RE.sub("", name.strip())
        # Track form first ("T by A from B"), then the album form ("T by A"),
        # which is the same sentence with the tail missing. Order matters: the
        # album pattern would happily eat a track name and keep "T by A" as the
        # title.
        for pattern in (self.service.track_name_re, self.service.album_name_re):
            if pattern is None:
                continue
            match = pattern.match(cleaned)
            if match:
                return match.group("title").strip() or name
        return cleaned or name

    def _inline_tracks(self, query: str, count: int) -> List[Dict[str, Any]]:
        """Tracks for feeds that list them beside the category links, not under
        a Songs category (Spotty).

        Deliberately does NOT resolve each url: that costs one round trip per
        track, and of twenty results at most one is ever played. The item id
        travels instead, and ``track_url`` turns the chosen one into a url.
        """
        node = self.search_node_id()
        if node is None:
            return []
        # The category links (Artists, Albums, Playlists, Podcasts, Podcast
        # Episodes, Users) are the first rows and they count against the
        # quantity asked for: a plain ``count`` of 20 came back as 14 tracks
        # every time, which would hand Spotify a shortlist a third smaller than
        # the one TIDAL and Qobuz get for the same request. Ask for the links
        # too, then keep ``count`` tracks.
        out: List[Dict[str, Any]] = []
        for item in self._app_items("0", str(count + _INLINE_HEADROOM),
                                    f"item_id:{node}", f"search:{query}"):
            if len(out) >= count:
                break
            if not item.get("isaudio") or not item.get("id"):
                continue
            name = (item.get("name") or "").strip()
            title, artist, album = name, None, None
            pattern = self.service.track_name_re
            match = pattern.match(name) if (pattern and name) else None
            if match:
                title = match.group("title").strip() or name
                artist = (match.group("artist") or "").strip() or None
                album = (match.group("album") or "").strip() or None
            track = {"item_id": item["id"], "title": title}
            if artist:
                track["artist"] = artist
            # The album is kept although nothing plays by it, because the
            # kid-safe guard checks every name field of a resolved item
            # (guard.ITEM_NAME_FIELDS) and this is the only feed that hands one
            # over. Dropping it would mean a blocked album whose tracks are not
            # themselves blocked still plays.
            if album:
                track["album"] = album
            out.append(track)
        return out

    def track_url(self, item_id: str) -> Optional[str]:
        """The play url of a browseable track node, fetched on demand.

        Spotty's search results carry no url; entering a track yields a single
        ``type == "audio"`` child carrying it (in ``text`` and in
        ``presetParams.favorites_url`` — verified live 2026-08-28, and note it
        has no ``name`` at all under ``menu:1``).

        Three conditions, not one. The child must *be* audio, and the uri must
        classify as a **track**: the service scheme alone also matches
        ``spotify://album:`` and ``spotify://artist:``, and Spotty does ship
        "go to album"/"go to artist" actions on this node. Returning one of
        those would hand ``play_url`` a whole album for a request for one song
        — quietly, which is the failure mode this file works hardest to avoid.
        """
        for child in self._app_items("0", "5", f"item_id:{item_id}", "menu:1"):
            if child.get("type") != "audio":
                continue
            preset = child.get("presetParams") or {}
            for value in (child.get("url"), preset.get("favorites_url"),
                          child.get("text"), child.get("name")):
                if not isinstance(value, str):
                    continue
                found = self.service.uri_re.search(value)
                if found and uri_kind(found.group(0)) == "track":
                    return found.group(0)
        return None

    def search_tracks(self, query: str, count: int = 20) -> List[Dict[str, Any]]:
        """Return playable tracks ``[{'url', 'title'[, 'artist']}, ...]`` for a query.

        Uses the Songs category in **menu mode** (``menu:1``): each item carries the
        artist as the 2nd line of ``text`` ('Title\\nArtist') and the play URL under
        ``presetParams.favorites_url`` — the plain ``want_url`` mode strips both to a
        bare title. Falls back to ``name``/``url``/``artist`` keys so the simulated
        transport in tests still works.

        Spotty answers a different shape and takes the branch below: no Songs
        category, tracks inline as siblings of the category links, and no url on
        the item — see ``SERVICES["spotify"]`` and ``_inline_tracks``."""
        if self.service.tracks_inline:
            return self._inline_tracks(query, count)
        cats = self.search_categories(query, count)
        node = self._resolve_category(cats, "Songs")
        if not node:
            return []
        out: List[Dict[str, Any]] = []
        for item in self._app_items("0", str(count), f"item_id:{node}", "menu:1"):
            if item.get("isaudio") == 0:
                continue
            preset = item.get("presetParams") or {}
            url = item.get("url") or preset.get("favorites_url") or find_uri(item, self.service.uri_re)
            if not url:
                continue
            title, artist = _split_text(item.get("text"))
            title = title or item.get("name")
            artist = artist or item.get("artist")
            if title and self.service.title_noise_re is not None:
                title = self.service.title_noise_re.sub("", title).strip() or title
            if artist and self.service.artist_line_sep:
                # e.g. Qobuz: "Pink Floyd - The Wall (Remastered)" -> "Pink Floyd"
                artist = artist.split(self.service.artist_line_sep, 1)[0].strip() or artist
            track = {"url": url, "title": title}
            if artist:
                track["artist"] = artist
            out.append(track)
        return out

    def playlist_candidates(self, query: str, count: int = 20) -> List[Dict[str, Any]]:
        return [
            {"id": it["id"], "title": it.get("name")}
            for it in self.category_items(query, "Playlists", count)
            if it.get("id")
        ]

    def find_playlist(self, query: str, count: int = 20) -> Optional[Dict[str, Any]]:
        cands = self.playlist_candidates(query, count)
        return cands[0] if cands else None

    def album_candidates(self, query: str, count: int = 20) -> List[Dict[str, Any]]:
        """All album matches for a query, in the service's relevance order. The
        caller scores these against the request (edition words like 'Live In
        Berlin' surface the right edition)."""
        return [
            {"id": it["id"], "title": self._clean_name(it.get("name"))}
            for it in self.category_items(query, "Albums", count)
            if it.get("id")
        ]

    def find_album(self, query: str, count: int = 20) -> Optional[Dict[str, Any]]:
        cands = self.album_candidates(query, count)
        return cands[0] if cands else None

    def album_tracks(self, query: str, count: int = 50) -> Dict[str, Any]:
        """Return ``{'album': {...} | None, 'tracks': [{'url','title'}, ...]}``."""
        album = self.find_album(query, count)
        if not album:
            return {"album": None, "tracks": []}
        tracks: List[Dict[str, Any]] = []
        for item in self._app_items(
            "0", str(count), f"item_id:{album['id']}", "want_url:1"
        ):
            url = item.get("url") or find_uri(item, self.service.uri_re)
            if item.get("isaudio") and url:
                tracks.append({"url": url,
                               "title": self._clean_name(item.get("name"))})
        return {"album": album, "tracks": tracks}

    def artist_candidates(self, query: str, count: int = 20) -> List[Dict[str, Any]]:
        """All artist matches for a query, in the service's relevance order.

        The counterpart of :meth:`album_candidates` and
        :meth:`playlist_candidates`, and it exists for the same reason: the
        caller scores these against the request rather than trusting the first
        row. ``find_artist`` did trust it, and for TIDAL and Qobuz nothing
        downstream checked the name either.
        """
        return [
            {"id": it["id"], "title": self._clean_name(it.get("name"))}
            for it in self.category_items(query, "Artists", count)
            if it.get("id")
        ]

    def find_artist(self, query: str, count: int = 20) -> Optional[Dict[str, Any]]:
        cands = self.artist_candidates(query, count)
        return cands[0] if cands else None

    def _artist_child_id(self, by_name: Dict[str, str],
                         canonical: str) -> Optional[str]:
        """The node id for one of ``artist_children``, by any name the plugin
        may show it under — see ``ServiceSpec.artist_child_aliases``."""
        aliases = self.service.artist_child_aliases.get(
            canonical, self.service.category_aliases.get(canonical, (canonical,)))
        for alias in aliases:
            node_id = by_name.get(alias.strip().lower())
            if node_id:
                return node_id
        return None

    # Artist "outline" nodes are NOT directly playable (verified live on TIDAL:
    # playing them is a no-op). Their music lives in child nodes; we drill the
    # first available of the service's ``artist_children`` to playable URLs.
    def artist_tracks(self, artist: Dict[str, Any],
                      count: int = 20) -> List[Dict[str, Any]]:
        """The playable rows under an already-resolved artist node.

        A row carries ``url`` where the feed hands one over, and ``item_id``
        where it does not: Spotty's tracks are ``{"id", "name", "isaudio"}``
        with the url one level down (see :meth:`track_url`), and dropping them
        for want of a url is why an artist on Spotify came back unplayable
        while its songs were right there. ``play_tracks`` resolves an id when —
        and only when — it is about to queue that track.
        """
        children = self._app_items(
            "0", str(count), f"item_id:{artist['id']}", "want_url:1"
        )
        by_name = {c["name"].strip().lower(): c["id"]
                   for c in children if c.get("name") and c.get("id")}
        tracks: List[Dict[str, Any]] = []
        for child_name in self.service.artist_children:
            node_id = self._artist_child_id(by_name, child_name)
            if not node_id:
                continue
            for item in self._app_items(
                "0", str(count), f"item_id:{node_id}", "want_url:1"
            ):
                if not item.get("isaudio"):
                    continue
                url = item.get("url") or find_uri(item, self.service.uri_re)
                title = self._clean_name(item.get("name"))
                if url:
                    tracks.append({"url": url, "title": title})
                elif self.service.tracks_inline and item.get("id"):
                    tracks.append({"item_id": item["id"], "title": title})
            if tracks:
                break
        return tracks

    def artist_top_tracks(
        self, query: str, count: int = 20
    ) -> Dict[str, Any]:
        """Return ``{'artist': {...} | None, 'tracks': [{'url','title'}, ...]}``."""
        artist = self.find_artist(query, count)
        if not artist:
            return {"artist": None, "tracks": []}
        return {"artist": artist, "tracks": self.artist_tracks(artist, count)}

    # -- local library (Music Folder / USB drive) -------------------------
    # Uses LMS core commands with stable numeric ids (verified live), so local
    # playback is fully deterministic — unlike the TIDAL app-feed navigation.
    # LMS ``search:`` is a loose keyword search across fields; it can return
    # loosely-related rows. So we return all candidates and let the caller score
    # them against the query (title + artist) instead of trusting the first row.
    #
    # ``tags:E`` (albums, artists) and ``tags:u`` (titles) are what tell a row
    # that lives on a disk apart from one a streaming plugin IMPORTED into the
    # library — see :meth:`blocking_service`, which is the whole reason they
    # are asked for.
    def local_artist_candidates(self, query: str, count: int = 10) -> List[Dict[str, Any]]:
        loop = self.server_command(
            "artists", "0", str(count), f"search:{query}", "tags:E"
        ).get("artists_loop") or []
        return [_with_extid({"id": a["id"], "title": a.get("artist")}, a)
                for a in loop if a.get("id") is not None]

    def find_local_artist(self, query: str, count: int = 10) -> Optional[Dict[str, Any]]:
        cands = self.local_artist_candidates(query, count)
        return cands[0] if cands else None

    def local_album_candidates(self, query: str, count: int = 10) -> List[Dict[str, Any]]:
        loop = self.server_command(
            "albums", "0", str(count), f"search:{query}", "tags:laE"
        ).get("albums_loop") or []
        return [
            _with_extid(
                {"id": a["id"], "title": a.get("album"), "artist": a.get("artist")},
                a)
            for a in loop if a.get("id") is not None
        ]

    def find_local_album(self, query: str, count: int = 10) -> Optional[Dict[str, Any]]:
        cands = self.local_album_candidates(query, count)
        return cands[0] if cands else None

    def local_track_candidates(self, query: str, count: int = 10) -> List[Dict[str, Any]]:
        loop = self.server_command(
            "titles", "0", str(count), f"search:{query}", "tags:au"
        ).get("titles_loop") or []
        out: List[Dict[str, Any]] = []
        for a in loop:
            if a.get("id") is None:
                continue
            cand = {"id": a["id"], "title": a.get("title")}
            if a.get("url"):
                cand["url"] = a["url"]
            if a.get("artist"):
                cand["artist"] = a["artist"]
            out.append(cand)
        return out

    def find_local_track(self, query: str, count: int = 10) -> Optional[Dict[str, Any]]:
        cands = self.local_track_candidates(query, count)
        return cands[0] if cands else None

    #: How many tracks are read to decide whether an imported album or artist
    #: can play. One would do — every track of an imported album comes from the
    #: same plugin — but a handful costs the same single round trip and covers
    #: an artist whose rows came from two different services.
    IMPORT_PROBE_TRACKS = 20

    def blocking_service(self, candidate: Dict[str, Any],
                         kind: str) -> Optional[str]:
        """The disconnected service a local-library row's audio comes from, or
        None when the row can play right now.

        A streaming plugin imports its favourites INTO the LMS library: the
        rows look local — they answer ``artists``/``albums``/``titles``, they
        have library ids, ``playlistcontrol`` queues them without complaint —
        but the audio is still ``tidal://322955652.flc``, and with the plugin
        logged out not one second of it plays. That is what happened here: an
        artist request loaded ten imported tracks, LMS accepted the command,
        the app said "playing", the player walked the whole queue failing every
        track and stopped in silence. ``can_search`` (see there) had covered
        only the other half of it — SEARCHING a logged-out plugin.

        A row with no ``extid`` is a file on a disk and is answered without
        asking anybody anything, which is nearly every row in nearly every
        library. An imported album or artist costs one ``titles`` query,
        because the ``extid`` says which services know the row and only the
        track urls say which one it will actually stream from: this artist's
        extid named both Qobuz and TIDAL while every track in the library was
        TIDAL's.
        """
        if kind == "track":
            return self._offline_service(candidate.get("url"))
        if not candidate.get("extid"):
            return None
        loop = self.server_command(
            "titles", "0", str(self.IMPORT_PROBE_TRACKS),
            f"{kind}_id:{candidate['id']}", "tags:u"
        ).get("titles_loop") or []
        blocked = None
        for track in loop:
            offline = self._offline_service(track.get("url"))
            if offline is None:
                return None  # one playable track is enough to keep the row
            blocked = blocked or offline
        # No tracks came back: an empty album plays nothing either way, and
        # inventing a verdict out of silence is how a working library starts
        # losing rows. Say nothing is blocking it and let the play be a no-op.
        return blocked

    def _offline_service(self, uri: Optional[str]) -> Optional[str]:
        """The service ``uri`` needs, when that service cannot answer today."""
        name = service_of(uri)
        if name is None or name not in SERVICES:
            return None
        return None if self.for_service(name).can_search() else name

    def local_albums_by_artist(self, query: str, count: int = 50) -> Dict[str, Any]:
        artist = self.find_local_artist(query)
        if not artist:
            return {"artist": None, "albums": []}
        loop = self.server_command(
            "albums", "0", str(count), f"artist_id:{artist['id']}", "tags:la"
        ).get("albums_loop") or []
        albums = [{"id": a["id"], "title": a.get("album")} for a in loop if a.get("id")]
        return {"artist": artist, "albums": albums}

    # Genres are the one piece of library metadata a mood can be resolved
    # against without asking anyone's taste (see engine/moods.py): LMS has
    # tagged every track with one already, and the ids are stable like the
    # rest of the local-library commands.
    def local_genres(self, count: int = 200) -> List[Dict[str, Any]]:
        loop = self.server_command(
            "genres", "0", str(count)
        ).get("genres_loop") or []
        return [{"id": g["id"], "title": g.get("genre")}
                for g in loop if g.get("id") is not None]

    # The other axis LMS tags every track with, and the reason a decade is a
    # mood at all (see engine/moods.py). Two things about `years` are not like
    # `genres` and are easy to get wrong: the response loop is keyed by
    # ``year``, not by ``id`` — the year is its own identifier — and
    # ``hasAlbums:1`` is what keeps years that only stray singles live in out
    # of the list. Nothing anywhere in the CLI accepts a range, so callers ask
    # for one year at a time.
    def local_years(self, count: int = 200) -> List[int]:
        loop = self.server_command(
            "years", "0", str(count), "hasAlbums:1"
        ).get("years_loop") or []
        years = []
        for entry in loop:
            try:
                years.append(int(entry.get("year")))
            except (AttributeError, TypeError, ValueError):
                continue
        return years

    # ``sort:random`` is documented as relevant exactly when genre_id, artist_id
    # or year is supplied, and it is scoped to this one call — unlike
    # `playlist shuffle 1`, which is the player's standing preference. It sorts
    # ALBUMS, not tracks, so it is not a true shuffle; see engine/moods.py.
    def play_local_year(self, year: Any) -> Dict[str, Any]:
        return self.command("playlistcontrol", "cmd:load", f"year:{year}",
                            "sort:random")

    def play_local_genre(self, genre_id: Any) -> Dict[str, Any]:
        return self.command("playlistcontrol", "cmd:load",
                            f"genre_id:{genre_id}", "sort:random")

    def play_local_artist(self, artist_id: Any) -> Dict[str, Any]:
        return self.command("playlistcontrol", "cmd:load", f"artist_id:{artist_id}")

    def play_local_album(self, album_id: Any) -> Dict[str, Any]:
        return self.command("playlistcontrol", "cmd:load", f"album_id:{album_id}")

    def play_local_track(self, track_id: Any) -> Dict[str, Any]:
        return self.command("playlistcontrol", "cmd:load", f"track_id:{track_id}")

    def add_local_album(self, album_id: Any) -> Dict[str, Any]:
        return self.command("playlistcontrol", "cmd:add", f"album_id:{album_id}")

    def insert_local_album(self, album_id: Any) -> Dict[str, Any]:
        return self.command("playlistcontrol", "cmd:insert", f"album_id:{album_id}")

    def add_local_artist(self, artist_id: Any) -> Dict[str, Any]:
        return self.command("playlistcontrol", "cmd:add", f"artist_id:{artist_id}")

    def insert_local_artist(self, artist_id: Any) -> Dict[str, Any]:
        return self.command("playlistcontrol", "cmd:insert", f"artist_id:{artist_id}")

    def add_local_track(self, track_id: Any) -> Dict[str, Any]:
        return self.command("playlistcontrol", "cmd:add", f"track_id:{track_id}")

    def insert_local_track(self, track_id: Any) -> Dict[str, Any]:
        return self.command("playlistcontrol", "cmd:insert", f"track_id:{track_id}")

    def now_playing_info(self) -> Optional[Dict[str, Any]]:
        """The queue head plus the transport ``mode`` (play/pause/stop).

        The mode matters: ``status - 1`` returns the current queue entry
        whatever the player is doing, so without it a stopped player answered
        "now playing X" about a song nobody could hear.
        """
        res = self.command("status", "-", "1", "tags:aAlN")
        loop = res.get("playlist_loop") or []
        if not loop:
            return None
        item = loop[0]
        return {"title": item.get("title"), "artist": item.get("artist"),
                "mode": res.get("mode")}

    def status_info(self) -> Dict[str, Any]:
        """Player status for the web now-playing panel.

        Returns mode (play/pause/stop), current track metadata, elapsed and
        total seconds, and where the artwork lives: ``artwork`` is either an
        LMS-relative path (local tracks: ``/music/<coverid>/cover.jpg``) or
        the absolute URL the streaming plugin reported (``artwork_url``).
        """
        res = self.command("status", "-", "1", "tags:aAlKcdJ")
        loop = res.get("playlist_loop") or []
        item = loop[0] if loop else {}

        # LMS reports a muted player as a negative "mixer volume".
        raw_volume = res.get("mixer volume")
        try:
            volume = max(0, min(100, int(float(raw_volume))))
        except (TypeError, ValueError):
            volume = None

        artwork = item.get("artwork_url")
        if artwork and not artwork.startswith(("http://", "https://", "/")):
            artwork = "/" + artwork  # LMS a volte omette lo slash iniziale
        if not artwork:
            cover_id = item.get("coverid") or item.get("artwork_track_id")
            if cover_id:
                artwork = f"/music/{cover_id}/cover.jpg"
            elif item:
                # Fallback: la copertina del brano corrente del player, che
                # l'LMS sa risolvere sia per tracce locali sia in streaming.
                artwork = f"/music/current/cover.jpg?player={self.player_id}"

        def _num(value: Any) -> Optional[float]:
            try:
                return float(value)
            except (TypeError, ValueError):
                return None

        return {
            "mode": res.get("mode") or "stop",
            "title": item.get("title"),
            "artist": item.get("artist"),
            "album": item.get("album"),
            "duration": _num(item.get("duration") or res.get("duration")),
            "elapsed": _num(res.get("time")),
            "artwork": artwork,
            "volume": volume,
        }

    # -- playback / controls ----------------------------------------------
    def play_url(self, url: str) -> Dict[str, Any]:
        """Play a direct URL (e.g. a track ``tidal://<id>.flc``) on the player."""
        return self.command("playlist", "play", url)

    def play_browse_item(self, item_id: str) -> Dict[str, Any]:
        """Play a browseable app-feed node (album/playlist) by its OPML id."""
        return self.command(self.service.tag, "playlist", "play", f"item_id:{item_id}")

    def add_url(self, url: str) -> Dict[str, Any]:
        return self.command("playlist", "add", url)

    def insert_url(self, url: str) -> Dict[str, Any]:
        """Queue a track to play right after the current one ("play next")."""
        return self.command("playlist", "insert", url)

    def add_browse_item(self, item_id: str) -> Dict[str, Any]:
        """Queue a browseable app-feed node (album/playlist) at the end."""
        return self.command(self.service.tag, "playlist", "add", f"item_id:{item_id}")

    def insert_browse_item(self, item_id: str) -> Dict[str, Any]:
        """Queue a browseable app-feed node to play right after the current one."""
        return self.command(self.service.tag, "playlist", "insert", f"item_id:{item_id}")

    def _entry_url(self, entry: Any) -> Optional[str]:
        """The play url of a :meth:`artist_tracks` row (or of a bare url)."""
        if isinstance(entry, str):
            return entry
        url = entry.get("url")
        if url:
            return url
        item_id = entry.get("item_id")
        return self.track_url(item_id) if item_id else None

    def play_tracks(self, tracks: List[Any]) -> None:
        """Play the first playable entry (replacing the queue) then enqueue the
        rest. An entry is a url, or a row from :meth:`artist_tracks` — which
        may carry ``item_id`` instead of ``url``. Ids are resolved one at a
        time, in order, so the music starts after a single extra round trip
        rather than after all twenty."""
        started = False
        for entry in tracks or []:
            url = self._entry_url(entry)
            if not url:
                continue
            if started:
                self.add_url(url)
            else:
                self.play_url(url)
                started = True

    def pause(self) -> Dict[str, Any]:
        return self.command("pause", "1")

    def resume(self) -> Dict[str, Any]:
        return self.command("pause", "0")

    def next_track(self) -> Dict[str, Any]:
        return self.command("playlist", "index", "+1")

    def previous_track(self) -> Dict[str, Any]:
        return self.command("playlist", "index", "-1")

    def volume(self, delta: int) -> Dict[str, Any]:
        sign = "+" if delta >= 0 else "-"
        return self.command("mixer", "volume", f"{sign}{abs(int(delta))}")

    def volume_set(self, value: int) -> Dict[str, Any]:
        """Set the player volume to an absolute 0-100 level."""
        return self.command("mixer", "volume", str(max(0, min(100, int(value)))))

    def sleep(self, seconds: int) -> Dict[str, Any]:
        """Stop playback after ``seconds`` (LMS native sleep timer); 0 cancels."""
        return self.command("sleep", str(max(0, int(seconds))))

    def seek(self, seconds: float) -> Dict[str, Any]:
        """Jump to an absolute position (seconds) in the current track."""
        return self.command("time", str(max(0, int(seconds))))

    def clear_queue(self) -> Dict[str, Any]:
        """Empty the play queue and stop playback."""
        return self.command("playlist", "clear")

    def queue_upcoming(self, limit: int = 5) -> List[Dict[str, Any]]:
        """Up to ``limit`` tracks queued after the currently playing one, in
        play order.

        ``status - N tags:a`` is documented to start the listing at the
        current song (``playlist_loop[0]`` is the now-playing track, the LMS
        convention already relied on by :meth:`now_playing_info`/
        :meth:`status_info`); the rest of the loop is what plays next.
        """
        res = self.command("status", "-", str(max(0, limit) + 1), "tags:a")
        loop = res.get("playlist_loop") or []
        return [
            {"title": t.get("title"), "artist": t.get("artist")}
            for t in loop[1 : limit + 1] if t.get("title")
        ]

    # -- favorites (core LMS feature, not a plugin) ------------------------
    # Same OPML shape as a streaming app feed (see the module docstring), but
    # under the always-present "favorites" tag rather than a service's — and
    # flat, not the search-node/category/items 3-level dance TIDAL/Qobuz need:
    # ``search:`` filters the top-level list directly.
    def favorites_items(self, count: int = 50,
                        query: Optional[str] = None) -> List[Dict[str, Any]]:
        """The user's saved favorites (server-wide, not per-player), optionally
        filtered by ``query``. Each item carries at least ``id`` and ``name``
        when playable; folders (no ``id``... actually folders have an id too
        but no ``isaudio``) are included as-is — callers filter for ``id``."""
        params = ["0", str(count), "want_url:1"]
        if query:
            params.append(f"search:{query}")
        res = self.server_command("favorites", "items", *params)
        return res.get("loop_loop") or res.get("item_loop") or []

    def favorites_playlist_play(self, item_id: str) -> Dict[str, Any]:
        """Play a favorite by its (dotted) id. If it isn't itself playable but
        contains playable sub-items (a folder), LMS plays those instead."""
        return self.command("favorites", "playlist", "play", f"item_id:{item_id}")
