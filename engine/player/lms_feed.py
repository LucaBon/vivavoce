"""Browsing and searching a streaming plugin's app feed.

A mixin over ``LMSClient``: every method here goes through
``self.command``/``self._app_items`` and reads ``self.service``, both of which
the client owns. It catches ``self.error`` rather than ``LMSError`` for the
same reason — which exception class a failure wears belongs to whoever
composes the mixin (``player/resilience.py``).

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
LMS UI language changes them."""

from __future__ import annotations

import time
from typing import Any, Dict, List, Optional

from .lms_services import _INLINE_HEADROOM, _TRACK_NUMBER_RE, uri_kind


class LMSFeed:
    """The app-feed half of :class:`~lms.LMSClient` (see the module docstring)."""

    # -- streaming app-feed browse/search (TIDAL, Qobuz, ...) --------------
    def _app_items(self, *params: Any) -> List[Dict[str, Any]]:
        res = self.command(self.service.tag, "items", *params)
        return res.get("loop_loop") or res.get("item_loop") or []

    #: How long a *found* search node is trusted. It buys the extra round-trip
    #: ``can_search`` would otherwise add to every streaming request: the
    #: search path asks for the same node moments later.
    SEARCH_NODE_TTL = 30.0

    #: How long a *missing* one is. Deliberately much shorter, because the two
    #: answers are not worth the same. A found node saves a round trip that is
    #: about to happen anyway; a missing one saves nothing — the caller gives
    #: up rather than asking again — and costs the household the one thing the
    #: cache should never cost them: logging TIDAL into LMS, coming straight
    #: back, and being told for another half-minute that it is logged out.
    #: A couple of seconds still collapses the duplicate lookups inside one
    #: turn, which is all the saving there ever was on this side.
    SEARCH_NODE_MISS_TTL = 2.0

    def search_node_id(self) -> Optional[str]:
        """Id of the plugin's search node (type == 'search'), or None when the
        plugin has none to give — which is what an unauthenticated service
        looks like from here: a TIDAL that is logged out answers its whole
        menu with one 'Please go to Settings/Advanced/TIDAL' textarea.

        Memoized per service, asymmetrically: see the two TTLs above."""
        cached = self._search_nodes.get(self.service.tag)
        if cached is not None and cached[1] > time.monotonic():
            return cached[0]
        node = self._find_search_node()
        ttl = self.SEARCH_NODE_TTL if node else self.SEARCH_NODE_MISS_TTL
        self._search_nodes[self.service.tag] = (node, time.monotonic() + ttl)
        return node

    def _forget_search_node(self) -> None:
        """Drop the memoized node for this service, so the next call looks
        again.

        Called when a search *through* that node comes back with nothing at
        all — not no results, no categories: the node is not behaving like a
        search node any more, which is what a plugin logged out since we
        looked at it looks like from here. Without this the client keeps
        aiming a stale id at a service that has stopped answering for as long
        as the TTL, and reports the miss as "nothing found" rather than "not
        connected" — the one distinction ``can_search`` exists to make.

        A genuinely empty answer costs one extra round trip next time. That is
        the whole price, and it is only ever paid on the path that already
        failed.
        """
        self._search_nodes.pop(self.service.tag, None)

    def can_search(self) -> bool:
        """Whether this service can answer a search at all — i.e. whether the
        plugin is installed AND logged in. False is the difference between
        "your music isn't there" and "nobody was asked", and the router needs
        it to tell those two apart before it reports a miss."""
        try:
            return self.search_node_id() is not None
        except self.error:      # il tipo lo decide chi compone il mixin
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
        if not items:
            self._forget_search_node()
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
        return self._name_parts(name)[0]

    def _name_parts(self, name: Optional[str]) -> tuple:
        """``(title, artist)`` out of a feed's packaged name.

        The artist is what :meth:`_clean_name` throws away, and it is the one
        thing kid-safe needs from an album row: «The Marshall Mathers LP by
        Eminem» cleaned to its title is an album nobody can tell is Eminem's.
        ``artist`` is None wherever the name carried none.
        """
        if not name:
            return name, None
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
                artist = (match.group("artist") or "").strip() or None
                return match.group("title").strip() or name, artist
        return cleaned or name, None

    def _named(self, row: Dict[str, Any], name: Optional[str]) -> Dict[str, Any]:
        """``row`` with the title and, when the name carried one, the artist."""
        title, artist = self._name_parts(name)
        row["title"] = title
        if artist:
            row["artist"] = artist
        return row

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

