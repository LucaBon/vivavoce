"""What the engine asks a streaming service for: songs, albums, artists.

A mixin over ``LMSClient``, and one layer above ``lms_feed``: everything here
is a question in the engine's words — «i brani di» , «l'album» , «la playlist»
— answered by walking a feed with the primitives that module provides. The
favorites menu is here too: it is a catalogue of its own, flat, under a tag
that is always present rather than a plugin's.

Two files and not one because together they were 476 lines, and this repo's
own rule is 400 (``tests/test_packaging.py``). The seam is real, though: below
is how a feed is walked, here is what it is walked for.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from .lms_services import _split_text, find_uri


class LMSCatalog:
    """The catalogue half of :class:`~lms.LMSClient`'s streaming side."""

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
            url = (item.get("url") or preset.get("favorites_url")
                   or find_uri(item, self.service.uri_re))
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
            self._named({"id": it["id"]}, it.get("name"))
            for it in self.category_items(query, "Albums", count)
            if it.get("id")
        ]

    def find_album(self, query: str, count: int = 20) -> Optional[Dict[str, Any]]:
        cands = self.album_candidates(query, count)
        return cands[0] if cands else None

    def album_tracks(self, query: str, count: int = 50) -> Dict[str, Any]:
        """Return ``{'album': {...} | None, 'tracks': [{'url','title'}, ...]}``.

        A row carries ``item_id`` instead of ``url`` where the feed keeps the
        url one level down (Spotty), exactly as :meth:`artist_tracks` does:
        dropping those rows made every album on Spotify look empty, so «Time
        dall'album X» played the whole album instead.
        """
        album = self.find_album(query, count)
        if not album:
            return {"album": None, "tracks": []}
        tracks: List[Dict[str, Any]] = []
        for item in self._app_items(
            "0", str(count), f"item_id:{album['id']}", "want_url:1"
        ):
            if not item.get("isaudio"):
                continue
            url = item.get("url") or find_uri(item, self.service.uri_re)
            if url:
                tracks.append(self._named({"url": url}, item.get("name")))
            elif self.service.tracks_inline and item.get("id"):
                tracks.append(self._named({"item_id": item["id"]},
                                          item.get("name")))
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
