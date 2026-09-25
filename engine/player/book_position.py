"""Where a second of a book falls among its files, and the reverse.

A book reaches the speakers as a list of files, and everything a listener
says about it is in seconds of the *whole* book: a resume point, a chapter
start, the position saved back to Audiobookshelf. This is the arithmetic
between the two, with no state and no network — the part of
:mod:`player.composite` that can be read, and tested, on its own.
"""

from __future__ import annotations

import re
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


#: A chapter title that is only a number — «Capitolo 3», "Chapter 03",
#: «Track 3», «3» — which is what a folder of MP3s gets from its file names.
_NUMBERED_ONLY = re.compile(
    r"^\W*(?:(?:chapter|capitolo|kapitel|chapitre|cap[ií]tulo|track|traccia"
    r"|part|parte|teil|partie)\W*)?(\d*)\W*$", re.I)

#: A number in front of a chapter's title — «02 - Gli Dei», «2. Gli Dei»,
#: «Capitolo 2: Gli Dei» — as LibriVox's .m4b files carry them.
_NUMBER_PREFIX = re.compile(
    r"^\W*(?:(?:chapter|capitolo|kapitel|chapitre|cap[ií]tulo|track|traccia"
    r"|part|parte|teil|partie)\s*)?0*(\d+)\s*[-–—.:)]\s*(?=\S)", re.I)


def chapter_name(title: str, index: int) -> str:
    """What is worth saying of chapter ``index``'s ``title`` beside its
    number: «02 - Gli Dei» at position 2 is «Gli Dei», and «Capitolo 2» or
    «02» there is nothing at all — the number is said already. A number that
    is *not* the position (a «Prologo» first, then «Capitolo 1») is kept:
    then it is information."""
    title = (title or "").strip()
    prefix = _NUMBER_PREFIX.match(title)
    if prefix and int(prefix.group(1)) == index + 1:
        title = title[prefix.end():]
    numbered = _NUMBERED_ONLY.match(title)
    if numbered and (not numbered.group(1) or int(numbered.group(1)) == index + 1):
        return ""
    return title


def file_titles(book: Dict[str, Any]) -> List[Optional[str]]:
    """What the player's queue should call each of ``book``'s files before it
    has played them — the LMS reads a remote file's tags only then, and
    showed every chapter still to come as «Unknown».

    A file that *is* a chapter — one starts where the file starts, and none
    starts inside it — is called by that chapter's title, number and all
    («03 - Il Castaldo»: the queue has no other number). Any other file is
    the book and which file of how many («Le favole · 2/9»), or the book
    alone when it is one file: an .m4b named after its first chapter would
    be wrong for the other eight. Nothing, when the book has no title.
    """
    files, chapters = book.get("tracks") or [], book.get("chapters") or []
    title = book.get("title") or ""
    names: List[Optional[str]] = []
    start = 0.0
    for index, f in enumerate(files):
        duration = f.get("duration") or 0.0
        end = start + duration if duration else None
        own = [ch for ch in chapters
               if abs(ch["start"] - start) < BOUNDARY_SNAP and ch.get("title")]
        inside = [ch for ch in chapters if end is not None
                  and start + BOUNDARY_SNAP <= ch["start"] < end - BOUNDARY_SNAP]
        if own and not inside and end is not None:
            names.append(own[0]["title"])
        elif title:
            names.append(title if len(files) == 1
                         else f"{title} · {index + 1}/{len(files)}")
        else:
            names.append(None)
        start = end if end is not None else start
    return names
