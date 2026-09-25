"""Where a second of a book falls among its files, and the reverse.

A book reaches the speakers as a list of files, and everything a listener
says about it is in seconds of the *whole* book: a resume point, a chapter
start, the position saved back to Audiobookshelf. This is the arithmetic
between the two, with no state and no network — the part of
:mod:`player.composite` that can be read, and tested, on its own.
"""

from __future__ import annotations

from typing import Any, Callable, Dict, List, Optional

#: Seconds by which the player's idea of a file's length may differ from the
#: catalogue's and still be the same file. Decoders round, and a VBR MP3
#: read from its header and from a scan disagree by a second or so; a song
#: put on since is minutes off (see :meth:`player.composite.Composite.chapter_at`).
LENGTH_TOLERANCE = 2.0

#: How far before a chapter's start still counts as inside it. A seek to a
#: chapter lands a hair early on some players, and «di che capitolo sono»
#: asked right after «capitolo successivo» must not name the one before.
CHAPTER_SLACK = 1.0

#: How long a seek is given to show up in the player's position, and how
#: often it is asked meanwhile (see :func:`seek_landed`).
SEEK_CHECK = 3.0
SEEK_POLL = 0.25

#: How close to a file boundary a chapter start is the boundary itself (see
#: ``chapter_point``).
BOUNDARY_SNAP = 0.5


def resume_point(files: List[Dict[str, Any]],
                 start: float) -> Optional[tuple]:
    """``(index, offset)`` of the file ``start`` seconds in falls inside, or
    ``None`` when a file's duration is unknown (``0.0``) and the search
    cannot be trusted past it — or when ``start`` lies past the end of a
    book whose every length is known: progress saved against other files,
    and seeking past the last one would play nothing at all."""
    elapsed = 0.0
    for index, f in enumerate(files):
        duration = f.get("duration") or 0.0
        if not duration and index < len(files) - 1:
            return None
        if start < elapsed + duration:
            return index, start - elapsed
        if index == len(files) - 1:
            return (index, start - elapsed) if not duration else None
        elapsed += duration
    return None


def chapter_point(files: List[Dict[str, Any]],
                  start: float) -> Optional[tuple]:
    """:func:`resume_point`, snapped to a file boundary within
    :data:`BOUNDARY_SNAP`: Audiobookshelf sums its chapter starts on its own,
    and a boundary it rounds differently from the track lengths is still the
    boundary — not a seek a player that cannot seek would be refused."""
    point = resume_point(files, start)
    if point is None:
        return None
    index, offset = point
    duration = files[index].get("duration") or 0.0
    if offset < BOUNDARY_SNAP:
        return index, 0.0
    if duration and duration - offset < BOUNDARY_SNAP and index + 1 < len(files):
        return index + 1, 0.0
    return index, offset


def file_chapters(durations: List[float]) -> List[Dict[str, Any]]:
    """One chapter per file. A start after a file of unknown length cannot
    be summed, and is ``None`` from there on."""
    chapters: List[Dict[str, Any]] = []
    elapsed: Optional[float] = 0.0
    for duration in durations:
        end = elapsed + duration if elapsed is not None and duration else None
        chapters.append({"start": elapsed, "end": end, "title": ""})
        elapsed = end
    return chapters


def seconds(value: Any) -> float:
    """A length or a position as the wire sent it -> float seconds; ``0.0``
    for one missing, or written as something that is not a number."""
    try:
        return float(value or 0.0)
    except (TypeError, ValueError):
        return 0.0


def seek_landed(elapsed: Callable[[], Any], target: float,
                now: Callable[[], float], sleep: Callable[[float], None]) -> bool:
    """Whether a player that accepted a seek to ``target`` seconds is there:
    ``elapsed()`` read back for up to :data:`SEEK_CHECK` seconds.

    Found on the hi-fi, 2026-09-25: LMS 9 streaming an .m4b from
    Audiobookshelf says ``can_seek`` 1, takes the seek, and restarts the
    stream from 0 without an error anywhere. So the answer is read, not
    assumed. Costs nothing when the seek has landed by the first read; a
    player that never gets there costs the wait. An ``elapsed()`` of
    ``None`` — a player that does not say — is trusted.
    """
    deadline = now() + SEEK_CHECK
    while True:
        position = elapsed()
        if position is None or seconds(position) >= target - CHAPTER_SLACK:
            return True
        if now() >= deadline:
            return False
        sleep(SEEK_POLL)
