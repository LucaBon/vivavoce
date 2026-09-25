"""The sentences for spoken media: «vai avanti di 30 secondi», «metti
l'audiolibro X», «riprendi il libro X», «capitolo successivo».

Its own module because ``intents.py`` is near the size ceiling and this is
the part that grows (T5.6). A mixin over :class:`router.Router`, like the other four: it reads
the router's aimed client, its guard and its yes/no offer.

**One step, run before the transport block** (see ``IntentTable._route``).
«avanti» and «indietro» already mean next and previous track, so a jump that
reached that block would skip the chapter instead of thirty seconds of it.
The patterns demand a unit of time, which is what keeps a bare «avanti»
skipping as it always has.

**Books only when there are books.** With no ``--library`` the router holds
no catalogue and this step does not look at the sentence at all: a household
without audiobooks keeps every answer it had, «metti l'audiolibro X»
included (a search for it, as any other title).
"""

from __future__ import annotations

import re

import actions
from conversation import cannot
from messages import msg
from parsing import _minutes_of
from player.composite import LENGTH_TOLERANCE
from player.errors import PlayerError

#: «mezzo minuto», "half a minute", «eine halbe Minute», «une demi-minute»,
#: «medio minuto»: thirty seconds. Half a *second* is not a jump anybody
#: means, and is asked again rather than read as thirty.
_HALF = ("mezzo", "mezza", "half", "halbe", "demi", "medio", "media")
#: «un paio di», "a couple of", «un par de», «ein paar»: two.
_PAIR = ("paio", "couple", "par", "paar")
#: The words that join the parts of a spoken number — «treinta y cinco»,
#: «vingt et un», "a couple of" — and add nothing to it. Dropped anywhere.
_CONJUNCTIONS = ("e", "y", "und", "et", "and", "of", "di", "de")
#: Articles, which are ALSO the word for one: «un minuto» is a minute, but in
#: «vingt et une» the «une» is the one of twenty-one. So they are dropped only
#: in front of an amount — never after a conjunction, where they count.
_ARTICLES = ("a", "an", "un", "uno", "una", "une", "ein", "eine", "einen")

#: How many books a spoken title is weighed against. The catalogue's own
#: ranking is only the tiebreaker: see :meth:`SpokenIntents._play_book`.
BOOK_CANDIDATES = 5

#: A chapter title that is only a number — «Capitolo 3», "Chapter 03",
#: «Track 3», «3» — which is what a folder of MP3s gets from its file names.
#: When the number is the chapter's own position it is said once, «capitolo 3
#: di 12», not «capitolo 3 di 12, "Capitolo 3"»; when it is not — a prologue
#: ahead of «Capitolo 1» — the title is information, and said.
_NUMBERED_ONLY = re.compile(
    r"^\W*(?:(?:chapter|capitolo|kapitel|chapitre|cap[ií]tulo|track|traccia"
    r"|part|parte|teil|partie)\W*)?(\d*)\W*$", re.I)

#: The spoken chapter moves, as ``(pattern key, step)``: 0 asks, ±1 moves.
_CHAPTER_STEPS = (("chapter_which", 0), ("chapter_next", 1),
                  ("chapter_prev", -1))


def _number(words):
    """Words -> int by the merged number tables, or None.

    The longest run of words that the tables know as one entry is read
    first, because French multiplies where the others add: «quatre-vingt-dix»
    is ninety, and summed a part at a time it was thirty-four. What is left
    after the longest entries is added up — «forty five», «quarante-cinq»,
    «treinta y un» — which is how all five languages say the rest.
    """
    total, i = 0, 0
    while i < len(words):
        for j in range(len(words), i, -1):
            span = words[i:j]
            value = next((v for v in (_minutes_of(" ".join(span)),
                                      _minutes_of("-".join(span)))
                          if v is not None), None)
            if value is not None:
                total += value
                i = j
                break
        else:
            if words[i] in _CONJUNCTIONS and 0 < i < len(words) - 1:
                i += 1  # «vingt ET une»: joins, adds nothing
                continue
            return None
    return total


def _count(words):
    """A spoken amount of one or more words -> int, or None when any word of
    it is not part of a number."""
    if any(w in _PAIR for w in words):
        rest = [w for w in words if w not in _PAIR]
        ok = all(w in _CONJUNCTIONS or w in _ARTICLES for w in rest)
        return 2 if ok else None
    return _number(words) if words else None


def seek_seconds(amount: str, unit: str, plus: str = ""):
    """``(amount, unit)`` as said -> seconds, or ``None`` when the amount is
    not a number anybody could have meant. ``plus`` is the «e mezzo» / "and
    a half" that may follow the unit: half of one more of it.

    A half inside the amount is the same thing said before the unit — "one
    and a half minutes", «zweieinhalb» aside — and a half on its own («mezzo
    minuto», "half a minute») is thirty seconds. Half of a second is not a
    jump anybody means, and is asked again.
    """
    words = [w for w in re.split(r"[\s-]+", (amount or "").strip().lower()) if w]
    minutes = (unit or "").lower().startswith("min")
    half = next((i for i, w in enumerate(words) if w in _HALF), None)
    if half is not None:
        if not minutes or plus or any(w not in _ARTICLES for w in words[half + 1:]):
            return None
        whole = words[:half]
        while whole and whole[-1] in _CONJUNCTIONS + _ARTICLES:
            whole = whole[:-1]  # "one AND A half"
        if not whole or all(w in _ARTICLES for w in whole):
            return 30
        n = _count(whole)
        return n * 60 + 30 if n else None
    n = _count(words)
    if not n:
        return None
    seconds = n * 60 if minutes else n
    if plus:
        if not minutes:
            return None
        seconds += 30
    return seconds


class SpokenIntents:
    """The spoken-media step of the router (see the module docstring)."""

    books = None  # a player.composite.Composite, or None: no --library

    def _route_spoken(self, t: str, P: dict, is_play: bool):
        """The reply for a jump, a speed change or a book, or ``None`` when
        ``t`` is none of those and routing goes on."""
        # Ahead of the seek check below and not gated on is_play: «metti a
        # velocità 1.2» carries a play verb, unlike «vai avanti di 30
        # secondi». No backend can do this yet, so the answer is fixed —
        # no Capabilities flag, no transport call. A GATE, as every "this
        # system cannot" is (conversation.cannot): a second-best transcription
        # must not turn «più veloce» into a search that starts a song.
        if P["speed"].match(t):
            return actions.ActionResult(msg("no_speed"), ok=False,
                                        kind=actions.GATE)
        if not is_play:
            for key, sign in (("seek_back", -1), ("seek_fwd", 1)):
                m = P[key].match(t)
                if m:
                    seconds = seek_seconds(m.group("n"), m.group("unit"),
                                           m.group("plus"))
                    if seconds is None:
                        return actions.ActionResult(msg("ask_seek"), ok=False)
                    return (self._unable("seek", say="no_seek")
                            or actions.seek_relative(self.lms, sign * seconds))
        if self.books is not None:
            for key, step in _CHAPTER_STEPS:
                if P[key].match(t):
                    return self._chapter(step)
            m = P["audiobook"].match(t) or P["resume_book"].match(t)
            if m:
                # The first group that took part: German «resume_book» has
                # one per branch (see spoken_de).
                title = next(g for g in m.groups() if g is not None)
                return self._play_book(title.strip())
        return None

    def _play_book(self, query: str):
        guard = self._guard
        try:
            found = self.books.book_candidates(query, BOOK_CANDIDATES)
        except PlayerError:
            # The catalogue's own search, not the hi-fi: name it, so a
            # rebooting Audiobookshelf is not reported as the whole system
            # being down (the music, on the same speakers, still plays).
            return actions.unreachable(self.books.label)
        if guard is not None:
            # Blocked is not found: naming the book back to the child who
            # asked for it is the one thing a blocklist must not do. The
            # request is weighed too, as for music — the words asked for it.
            found = [b for b in found if not guard.blocks(
                query, b.get("title"), b.get("author"))]
        if not found:
            return actions.ActionResult(msg("no_book_found", title=query),
                                        ok=False)
        # The catalogue ranks by its own lights — author and series count
        # there as much as the title — so the words that were said decide,
        # and its order only breaks a tie. Otherwise an exact title in
        # second place was out of reach: the question named the first one,
        # and «no» ended the turn.
        scored = [(self._book_score(query, b), i, b) for i, b in enumerate(found)]
        score, _, book = min(scored, key=lambda s: (-s[0], s[1]))
        title, author = book.get("title"), book.get("author")
        # A book is hours long: starting the wrong one in silence is the
        # failure this product promises not to have. So a weak best match is
        # asked about, with the same yes/no every other doubt uses — and «sì»
        # plays it where the question was asked.
        if score < actions.CONFIDENT_SCORE:
            key = "book_did_you_mean_by" if author else "book_did_you_mean"
            return self._offer(msg(key, title=title, author=author),
                               lambda: self._start_book(book))
        return self._start_book(book)

    def _chapter(self, step: int):
        """«a che capitolo sono» (``step`` 0), or a move of ``step`` chapters
        through the book this player is playing (T5.6).

        Only a book Vivavoce itself started can be placed — the transport says
        which queue position is playing, never which file — so «no audiobook
        playing» covers a book started from Audiobookshelf's own app too, and
        says so («messo da me»). See ``Composite.chapter_at`` for how a queue
        changed since is told apart.
        """
        try:
            where = self.books.chapter_at(self.lms)
            if where is None:
                return actions.ActionResult(msg("no_book_playing"), ok=False)
            chapters, target = where["chapters"], where["index"] + step
            if not step:
                return actions.ActionResult(
                    _chapter_said("chapter_now", target, chapters), ok=True)
            if target < 0:
                return actions.ActionResult(msg("chapter_first"), ok=False)
            if target >= len(chapters):
                return actions.ActionResult(msg("chapter_last"), ok=False)
            chapter = chapters[target]
            reached = self.books.play_chapter(self.lms, where["item_id"],
                                              chapter)
        except ValueError:
            # The book's own files cannot place it (Composite.play_chapter):
            # not the player's fault, so not «this system cannot».
            return actions.ActionResult(msg("chapter_unplaceable"), ok=False)
        except PlayerError as exc:
            # As in _start_book: the catalogue named, the speakers not.
            service = self.books.label if getattr(exc, "from_library", False) else None
            return actions.unreachable(service)
        if reached is None:
            return cannot("no_seek_chapter")
        if reached < chapter["start"] - LENGTH_TOLERANCE:
            # The seek into the file failed after the file started: what
            # plays is that file from its start, and the reply must not
            # name a chapter the listener is not hearing.
            return actions.ActionResult(msg("chapter_file_start", n=target + 1),
                                        ok=True)
        return actions.ActionResult(
            _chapter_said("chapter_playing", target, chapters), ok=True)

    @staticmethod
    def _book_score(query: str, book: dict) -> float:
        """How well ``query`` names ``book``: by its title, or by its title
        and author together («lo hobbit di tolkien»)."""
        title, author = book.get("title"), book.get("author")
        return max(actions._score(query, title),
                   actions._score(query, f"{title} {author or ''}"))

    def _start_book(self, book: dict):
        title = book.get("title") or ""
        try:
            start = self.books.progress(book["id"]) or 0.0
        except PlayerError as exc:
            # Audiobookshelf owns this fact and nothing else does (T5.5), but
            # not knowing it must not cost the listener the book itself —
            # only the resume. Logged, not raised: the catalogue may just be
            # slow to answer, and its files are asked for next regardless.
            print(f"Audiobookshelf: non riesco a leggere il progresso di "
                  f"{title!r} ({exc}); riparto da capo.")
            start = 0.0
        try:
            queued, reached = self.books.play_from(self.lms, book["id"], start)
        except PlayerError as exc:
            # enqueue() makes two kinds of call: fetching the book's own
            # files (the catalogue) and sending them to the speakers (the
            # transport) — see Composite.play_from. Only the first is named;
            # a transport failure keeps the generic "the system", which is
            # the LMS/MusicAssistant player it was already about.
            service = self.books.label if getattr(exc, "from_library", False) else None
            return actions.unreachable(service)
        if not queued:
            return actions.ActionResult(msg("book_no_audio", title=title),
                                        ok=False)
        # What is said is where playback really begins, not where the
        # listener stopped: the two differ when a file's length is unknown or
        # the player cannot seek (see Composite.play_from). Under a minute in
        # is not worth announcing as a resume.
        if reached >= 60:
            return actions.ActionResult(
                msg("book_resumed", title=title, position=_position(reached)),
                ok=True, terms=[title])
        author = book.get("author")
        key = "book_playing_by" if author else "book_playing"
        return actions.ActionResult(msg(key, title=title, author=author),
                                    ok=True, terms=[title])


def _position(seconds: float) -> str:
    """How far into a book, in whole minutes, as a person says it: «un'ora e
    30 minuti», not «90 minuti»."""
    hours, minutes = divmod(int(seconds) // 60, 60)
    said_minutes = (msg("resume_one_minute") if minutes == 1
                    else msg("resume_minutes", n=minutes))
    if not hours:
        return said_minutes
    said_hours = (msg("resume_one_hour") if hours == 1
                  else msg("resume_hours", n=hours))
    if not minutes:
        return said_hours
    return msg("resume_hours_minutes", hours=said_hours, minutes=said_minutes)


def _chapter_said(key: str, index: int, chapters: list) -> str:
    """Chapter ``index`` of ``chapters`` as the reply ``key`` says it: by
    number, and by name too when it has one that is more than its number."""
    title = (chapters[index].get("title") or "").strip()
    numbered = _NUMBERED_ONLY.match(title)
    if title and not (numbered and (not numbered.group(1)
                                    or int(numbered.group(1)) == index + 1)):
        return msg(f"{key}_titled", n=index + 1, total=len(chapters), title=title)
    return msg(key, n=index + 1, total=len(chapters))
