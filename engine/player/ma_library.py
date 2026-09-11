"""The catalogue half of the MusicAssistant client.

Split from the transport half for the reason ``tests/test_packaging.py`` has
been saying about ``engine/lms.py`` since before this backend existed —
*"transport, search and queue in one client"*. A device and a catalogue are
two jobs, :mod:`player.protocols` says so, and the new backend gets to be born
the right shape instead of being split later.

Two things make this far shorter than its LMS counterpart, and both are
MusicAssistant giving back what LMS made us earn:

* **One search command.** ``music/search`` takes the media types wanted and
  the providers to ask, and answers with typed lists. There is no menu tree to
  walk, no per-plugin category names to alias, no localized "Songs" to
  recognise. The three-level OPML navigation that fills half of ``lms.py`` has
  no equivalent here because it has no purpose here.
* **Everything is a URI.** ``play_media`` takes ``tidal://track/123`` or
  ``library://album/7`` directly, so a candidate's id, a track's playable URL
  and a browse item's handle are all the same string. Where LMS needs
  ``item_id`` plus a plugin tag plus a second round trip to turn a search hit
  into something playable, here the search hit already is it.

Command names and argument names were read off ``music-assistant/server`` on
2026-09-11 rather than remembered.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

#: Which key of a ``SearchResults`` holds which media type.
_RESULT_KEY = {"track": "tracks", "album": "albums", "artist": "artists",
               "playlist": "playlists", "radio": "radio"}

#: Ask only the library, not the streaming providers. The special provider
#: name is MusicAssistant's own — see the docstring of ``music/search``.
LIBRARY = "library"


def _name_of(item: Any) -> str:
    return (item or {}).get("name") or ""


def _first_artist(item: Dict[str, Any]) -> Optional[str]:
    """The artist to say out loud for a track.

    MusicAssistant carries every credited artist; the engine's shape has room
    for one, and the one it wants is the one a person would name. That is the
    first, which is how MusicAssistant orders them.
    """
    for artist in item.get("artists") or ():
        name = _name_of(artist)
        if name:
            return name
    return None


def _track(item: Dict[str, Any]) -> Dict[str, Any]:
    """One search hit as the engine's track shape.

    ``url`` rather than ``item_id``: a MusicAssistant URI is playable as it
    stands, so the engine never has to come back and ask what it resolves to.
    """
    track = {"url": item.get("uri"), "title": _name_of(item)}
    artist = _first_artist(item)
    if artist:
        track["artist"] = artist
    album = _name_of(item.get("album"))
    if album:
        track["album"] = album
    return track


def _container(item: Dict[str, Any]) -> Dict[str, Any]:
    """An album, artist or playlist as the engine's candidate shape.

    ``item_id`` and ``provider`` ride along because the per-type listings
    (``artist_tracks``, ``album_tracks``) are addressed by the pair rather than
    by the URI, and the engine hands a candidate back to us unchanged.
    """
    return {"id": item.get("uri"), "title": _name_of(item),
            "item_id": item.get("item_id"), "provider": item.get("provider")}


class MusicAssistantLibrary:
    """Search and browse, for :class:`~player.musicassistant.MusicAssistantClient`.

    A mixin rather than a class of its own: it needs ``_call`` and the
    ``provider`` the client is currently aimed at, and separating those would
    buy an indirection nobody reads.
    """

    # -- searching ---------------------------------------------------------
    def _search(self, query: str, media_type: str, count: int,
                providers: Optional[List[str]] = None) -> List[Dict[str, Any]]:
        if not (query or "").strip():
            return []
        results = self._call("music/search", search_query=query,
                             media_types=[media_type], limit=count,
                             providers=providers or self._providers()) or {}
        return list(results.get(_RESULT_KEY[media_type]) or [])

    def _providers(self) -> Optional[List[str]]:
        """The providers a search should ask, or None for "all of them".

        ``for_service`` narrows this to one, which is what makes «mettilo da
        Qobuz» mean something here. Unaimed, the answer is None and
        MusicAssistant searches the library and every provider at once — which
        is the behaviour that makes it worth using.
        """
        return [self.service.name] if self.service.name else None

    def search_tracks(self, query: str, count: int = 20) -> List[Dict[str, Any]]:
        return [_track(t) for t in self._search(query, "track", count)]

    def track_url(self, item_id: str) -> Optional[str]:
        """A MusicAssistant URI is already playable, so this is the identity.

        It exists because the engine calls it for a search hit that carried an
        id and no url — a shape only the Spotify plugin on LMS produces.
        """
        return item_id

    def album_candidates(self, query: str, count: int = 20) -> List[Dict[str, Any]]:
        return [_container(a) for a in self._search(query, "album", count)]

    def find_album(self, query: str, count: int = 20) -> Optional[Dict[str, Any]]:
        found = self.album_candidates(query, count)
        return found[0] if found else None

    def album_tracks(self, query: str, count: int = 50) -> Dict[str, Any]:
        album = self.find_album(query, count)
        if not album:
            return {"album": None, "tracks": []}
        rows = self._call("music/albums/album_tracks", item_id=album["item_id"],
                          provider_instance_id_or_domain=album["provider"]) or []
        return {"album": album, "tracks": [_track(t) for t in rows[:count]]}

    def artist_candidates(self, query: str, count: int = 20) -> List[Dict[str, Any]]:
        return [_container(a) for a in self._search(query, "artist", count)]

    def find_artist(self, query: str, count: int = 20) -> Optional[Dict[str, Any]]:
        found = self.artist_candidates(query, count)
        return found[0] if found else None

    def artist_tracks(self, artist: Dict[str, Any],
                      count: int = 20) -> List[Dict[str, Any]]:
        rows = self._call("music/artists/artist_tracks",
                          item_id=artist.get("item_id"),
                          provider_instance_id_or_domain=artist.get("provider")) or []
        return [_track(t) for t in rows[:count]]

    def artist_top_tracks(self, query: str, count: int = 20) -> Dict[str, Any]:
        artist = self.find_artist(query, count)
        if not artist:
            return {"artist": None, "tracks": []}
        rows = self._call("music/artists/top_tracks", item_id=artist["item_id"],
                          provider_instance_id_or_domain=artist["provider"]) or []
        return {"artist": artist, "tracks": [_track(t) for t in rows[:count]]}

    def playlist_candidates(self, query: str, count: int = 20) -> List[Dict[str, Any]]:
        return [_container(p) for p in self._search(query, "playlist", count)]

    def find_playlist(self, query: str, count: int = 20) -> Optional[Dict[str, Any]]:
        found = self.playlist_candidates(query, count)
        return found[0] if found else None

    # -- the local library -------------------------------------------------
    # ``<type>/library_items`` rather than a search restricted to the library:
    # it is the command MusicAssistant means for this, it sorts by name rather
    # than by relevance, and it does not consult a single streaming provider.
    def _library_items(self, media_type: str, query: Optional[str],
                       count: int) -> List[Dict[str, Any]]:
        return list(self._call(f"music/{media_type}s/library_items",
                               search=query, limit=count) or [])

    def local_album_candidates(self, query: str, count: int = 10) -> List[Dict[str, Any]]:
        return [_container(a) for a in self._library_items("album", query, count)]

    def local_artist_candidates(self, query: str, count: int = 10) -> List[Dict[str, Any]]:
        return [_container(a) for a in self._library_items("artist", query, count)]

    def local_track_candidates(self, query: str, count: int = 10) -> List[Dict[str, Any]]:
        return [_track(t) for t in self._library_items("track", query, count)]

    def find_local_album(self, query: str, count: int = 10) -> Optional[Dict[str, Any]]:
        found = self.local_album_candidates(query, count)
        return found[0] if found else None

    def find_local_artist(self, query: str, count: int = 10) -> Optional[Dict[str, Any]]:
        found = self.local_artist_candidates(query, count)
        return found[0] if found else None

    def find_local_track(self, query: str, count: int = 10) -> Optional[Dict[str, Any]]:
        found = self.local_track_candidates(query, count)
        return found[0] if found else None

    def local_albums_by_artist(self, query: str, count: int = 50) -> Dict[str, Any]:
        artist = self.find_local_artist(query)
        if not artist:
            return {"artist": None, "albums": []}
        rows = self._call("music/artists/artist_albums", item_id=artist["item_id"],
                          provider_instance_id_or_domain=artist["provider"]) or []
        return {"artist": artist, "albums": [_container(a) for a in rows[:count]]}

    def local_genres(self, count: int = 200) -> List[Dict[str, Any]]:
        # Genres are addressed by their numeric library id, not by a URI:
        # ``music/genres/tracks`` wants ``item_id``. So this is the one
        # candidate shape here whose "id" is not a URI.
        return [{"id": g.get("item_id"), "title": _name_of(g)}
                for g in self._library_items("genre", None, count)]

    def local_years(self, count: int = 200) -> List[int]:
        """Always empty: MusicAssistant does not index a library by year.

        Declared ``years=False`` in the backend's capabilities, so nothing
        should reach this. It answers rather than raising because the mood
        code asks first and falls through to a streaming playlist when the
        list is empty, which is the right outcome and costs nothing here.
        """
        return []

    def blocking_service(self, candidate: Dict[str, Any],
                         kind: str) -> Optional[str]:
        """Always None: this problem is one MusicAssistant does not have.

        On LMS a library row can be an index entry for a TIDAL track, playable
        only while that plugin is logged in — so the engine has to probe before
        offering it. MusicAssistant resolves a URI to a provider that can
        actually stream it at play time, and leaves unplayable items out of the
        listing, so there is nothing here to warn about.
        """
        return None

    # -- playing by catalogue id ------------------------------------------
    # A URI is a URI: an album, an artist, a playlist and a track all enqueue
    # the same way, which is why these twelve names are twelve one-liners
    # rather than four families of special cases.
    def play_browse_item(self, item_id: str) -> Any:
        return self._enqueue(item_id, "play")

    def add_browse_item(self, item_id: str) -> Any:
        return self._enqueue(item_id, "add")

    def insert_browse_item(self, item_id: str) -> Any:
        return self._enqueue(item_id, "insert")

    play_local_album = play_local_artist = play_local_track = play_browse_item
    add_local_album = add_local_artist = add_local_track = add_browse_item
    insert_local_album = insert_local_artist = insert_local_track = insert_browse_item

    def play_local_genre(self, genre_id: Any) -> Any:
        rows = self._call("music/genres/tracks", item_id=genre_id) or []
        return self.play_tracks([_track(t) for t in rows])

    # -- favourites --------------------------------------------------------
    def favorites_items(self, count: int = 50,
                        query: Optional[str] = None) -> List[Dict[str, Any]]:
        """Saved radio stations and playlists, newest listing first.

        ``name`` and not ``title``: this is the one candidate shape the engine
        reads by that key (``actions.play_favorites``), and it is the LMS
        favourites shape rather than a choice made here.
        """
        items = []
        for media_type in ("radio", "playlist"):
            rows = self._call(f"music/{media_type}s/library_items",
                              favorite=True, search=query, limit=count) or []
            items += [{"id": r.get("uri"), "name": _name_of(r)} for r in rows]
        return items[:count]

    def favorites_playlist_play(self, item_id: str) -> Any:
        return self._enqueue(item_id, "play")
