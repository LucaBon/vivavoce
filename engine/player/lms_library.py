"""The local library: the music on the disk LMS is looking at.

A mixin over ``LMSClient``, and the counterpart of ``lms_feed``: same client,
the other half of what an LMS knows. These are core LMS commands with stable
numeric ids rather than the OPML navigation a streaming plugin needs, which is
why local playback is deterministic and the app feed is full of special cases.

Split out of ``engine/lms.py``; nothing moved changed.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from .lms_services import SERVICES, _with_extid, service_of


class LMSLibrary:
    """The local-library half of :class:`~lms.LMSClient`."""

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
        # can_play, not can_search: a row the plugin imported is audio that
        # plugin has to fetch, so an expired token silences it exactly like a
        # logged-out one.
        return None if self.for_service(name).can_play() else name

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

