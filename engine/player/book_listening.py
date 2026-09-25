"""The listening half of :class:`player.composite.Composite`: where each book
of ours is, saved to the catalogue and shown on the page (T5.6).

A mixin, as the Router's pieces are, because :mod:`player.composite` would
not fit under the size ceiling with it: the playing and the chapters stay
there, and this reads what they recorded — ``_locate``, ``chapter_at``,
``_books`` — without changing any of it but the last save.
"""

from __future__ import annotations

import contextlib
from typing import Any, Dict, List, Optional, Tuple

from .book_position import chapter_name
from .errors import PlayerError

#: Seconds a book must have moved since the last save to be saved again. A
#: paused hi-fi does not move, so it stops writing — and does not overwrite
#: the position of somebody listening on the phone meanwhile.
SAVE_STEP = 5.0


class Listening:
    """``save_progress``, ``players`` and ``now_playing`` for a Composite."""

    _playing: Dict[Any, Tuple[str, int, int]]
    _transports: Dict[Any, Any]
    _saved: Dict[Any, Tuple[Tuple[str, int, int], float]]
    _books: Dict[str, Dict[str, Any]]
    library: Any

    # -- progress (T5.6) -----------------------------------------------------
    def save_progress(self, transport: Any) -> Optional[float]:
        """Save where ``transport`` is in its book to the catalogue, and
        answer the position saved — or ``None`` when nothing was: no book of
        ours playing there (:meth:`chapter_at`'s checks, the same ones), a
        position that cannot be summed, a catalogue with no
        ``save_progress``, or a book that has not moved :data:`SAVE_STEP`
        since the last save.

        Called by the sampler, never by a sentence, so that *every*
        interruption is covered — music started from Material Skin included,
        which Vivavoce never hears about. Once the book is replaced, the
        checks fail and nothing more is written: the last save stays the
        last true position.
        """
        save = getattr(self.library, "save_progress", None)
        if save is None:
            return None
        with _background(transport), _background(self.library):
            found = self._locate(transport)
            if found is None:
                return None
            record, durations, head, elapsed = found
            if not all(durations[:head]):
                return None
            position = sum(durations[:head]) + elapsed
            key = _player_key(transport)
            last = self._saved.get(key)
            if (last is not None and last[0] is record
                    and abs(position - last[1]) < SAVE_STEP):
                return None
            total = sum(durations) if all(durations) else None
            _from_library(lambda item: save(item, position, total), record[0])
        self._saved[key] = (record, position)
        return position

    def players(self) -> List[Any]:
        """The transports a book of ours was last played on — the ones the
        progress sampler looks at."""
        return [self._transports[key] for key in list(self._playing)
                if key in self._transports]

    def now_playing(self, transport: Any) -> Optional[Dict[str, Any]]:
        """What the page's now-playing panel should show for ``transport``
        while it plays a book of ours: ``{"title", "author", "chapter",
        "chapters", "chapter_title", "cover"}`` — or ``None``, and the panel
        shows what the player says, as for any music.

        Needed because the player knows only the file: a remote URL with a
        chapter's tag in it, no book, no author, no picture. The same checks
        as the chapter commands decide it is ours (``chapter_at``), and the
        book is the one read when it started, not a request per poll.
        """
        where = self.chapter_at(transport)
        if where is None:
            return None
        book = self._books.get(where["item_id"]) or {}
        index = where["index"]
        get_cover = getattr(self.library, "cover_url", None)
        return {"title": book.get("title") or "",
                "author": book.get("author") or "",
                "chapter": index + 1, "chapters": len(where["chapters"]),
                "chapter_title": chapter_name(
                    where["chapters"][index].get("title") or "", index),
                "cover": get_cover(where["item_id"]) if get_cover else None}


def _background(client: Any):
    """``client.background()`` — calls that never count toward its breaker
    (``player/resilience.py``) — for a client that has it, and nothing for
    one that does not: probed, as the engine probes everything optional."""
    block = getattr(client, "background", None)
    return block() if block is not None else contextlib.nullcontext()


def _player_key(transport: Any) -> Any:
    """Which player a transport is aimed at, as :attr:`Composite._playing`
    is keyed: both clients carry ``player_id``, and one that does not is a
    single player anyway."""
    return getattr(transport, "player_id", None)


def _from_library(fetch, item_id: str) -> Any:
    """``fetch(item_id)``, a call to the catalogue, with any
    :class:`PlayerError` tagged ``from_library`` so a caller can still tell
    "the catalogue's own files are unreachable" from "the speakers playing
    them are" — the two get different replies (see
    ``intents_spoken._start_book``)."""
    try:
        return fetch(item_id)
    except PlayerError as exc:
        exc.from_library = True
        raise
