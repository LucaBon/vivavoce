"""What is playing, and the commands that change it.

A mixin over ``LMSClient``, next to ``lms_feed`` and ``lms_library`` and named
like ``ma_transport`` on the MusicAssistant side, because it is the same job:
the verbs the engine speaks through ``PlayerTransport`` (play, pause, volume,
seek, the queue) and the reading that says what came of them.

Split out of ``engine/lms.py``; nothing moved changed.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from .lms_services import _as_float, _as_int


class LMSTransport:
    """The playback half of :class:`~lms.LMSClient`."""

    def now_playing_info(self) -> Optional[Dict[str, Any]]:
        """The queue head plus the transport ``mode`` (play/pause/stop), the
        queue position and the elapsed seconds.

        The mode matters: ``status - 1`` returns the current queue entry
        whatever the player is doing, so without it a stopped player answered
        "now playing X" about a song nobody could hear. Position and elapsed
        matter for the same reason one floor up: they are what tells a queue
        that is playing from one that is walking through itself failing every
        track (``engine/playback.py``). LMS spells the index as a string.

        ``connected`` is False only when LMS says so: a player it has not heard
        from takes a queue and plays none of it, and that silence belongs to
        the player, not to the service the queue came from.
        """
        res = self.command("status", "-", "1", "tags:aAlN")
        loop = res.get("playlist_loop") or []
        if not loop:
            return None
        item = loop[0]
        return {"title": item.get("title"), "artist": item.get("artist"),
                "mode": res.get("mode"), "index": _as_int(res.get("playlist_cur_index")),
                "elapsed": _as_float(res.get("time")),
                "connected": res.get("player_connected") is None
                or _as_int(res.get("player_connected")) != 0}

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

