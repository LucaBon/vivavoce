"""The sentences for spoken media: «vai avanti di 30 secondi», «metti
l'audiolibro X».

Its own module because ``intents.py`` is near the size ceiling and this is
the part that will grow — chapters, speed and «riprendi il libro» come next
(T5.6). A mixin over :class:`router.Router`, like the other four: it reads
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

import actions
from messages import msg
from parsing import _minutes_of
from player.errors import PlayerError

#: «mezzo minuto», "half a minute", «eine halbe Minute», «une demi-minute»,
#: «medio minuto»: thirty seconds, whichever unit follows.
_HALF = ("mezzo", "mezza", "half", "halbe", "demi", "medio")
#: «un paio di», "a couple of", «un par de»: two.
_PAIR = ("paio", "couple", "par")

#: How many books a spoken title is weighed against. The first is the one the
#: catalogue ranked highest; the rest only have to lose to it.
BOOK_CANDIDATES = 5


def seek_seconds(amount: str, unit: str):
    """``(amount, unit)`` as said -> seconds, or ``None`` when the amount is
    not a number anybody could have meant."""
    words = (amount or "").strip().lower().split()
    if not words:
        return None
    if any(w in _HALF for w in words):
        return 30
    if any(w in _PAIR for w in words):
        n = 2
    else:
        n = _minutes_of(words[-1]) if len(words) == 1 else None
    if not n:
        return None
    return n * 60 if (unit or "").lower().startswith("min") else n


class SpokenIntents:
    """The spoken-media step of the router (see the module docstring)."""

    books = None  # a player.composite.Composite, or None: no --library

    def _route_spoken(self, t: str, P: dict, is_play: bool):
        """The reply for a jump or a book, or ``None`` when ``t`` is neither
        and routing goes on."""
        if not is_play:
            for key, sign in (("seek_back", -1), ("seek_fwd", 1)):
                m = P[key].match(t)
                if m:
                    seconds = seek_seconds(m.group("n"), m.group("unit"))
                    if seconds is None:
                        return actions.ActionResult(msg("ask_seek"), ok=False)
                    return (self._unable("seek", say="no_seek")
                            or actions.seek_relative(self.lms, sign * seconds))
        if self.books is not None:
            m = P["audiobook"].match(t)
            if m:
                return self._play_book(m.group(1).strip())
        return None

    def _play_book(self, query: str):
        guard = self._guard
        try:
            found = self.books.book_candidates(query, BOOK_CANDIDATES)
        except PlayerError:
            return actions.unreachable()
        if guard is not None:
            # Blocked is not found: naming the book back to the child who
            # asked for it is the one thing a blocklist must not do. The
            # request is weighed too, as for music — the words asked for it.
            found = [b for b in found if not guard.blocks(
                query, b.get("title"), b.get("author"))]
        if not found:
            return actions.ActionResult(msg("no_book_found", title=query),
                                        ok=False)
        book = found[0]
        # The catalogue ranks by its own lights, and a book is hours long:
        # starting the wrong one in silence is the failure this product
        # promises not to have. So a weak first match is asked about, with
        # the same yes/no every other doubt uses — and «sì» plays it where
        # the question was asked.
        title, author = book.get("title"), book.get("author")
        score = max(actions._score(query, title),
                    actions._score(query, f"{title} {author or ''}"))
        if score < actions.CONFIDENT_SCORE:
            key = "book_did_you_mean_by" if author else "book_did_you_mean"
            return self._offer(msg(key, title=title, author=author),
                lambda: self._start_book(book))
        return self._start_book(book)

    def _start_book(self, book: dict):
        title = book.get("title") or ""
        try:
            queued = self.books.enqueue(self.lms, book["id"], "play")
        except PlayerError:
            return actions.unreachable()
        if not queued:
            return actions.ActionResult(msg("book_no_audio", title=title),
                                        ok=False)
        author = book.get("author")
        key = "book_playing_by" if author else "book_playing"
        return actions.ActionResult(msg(key, title=title, author=author),
                                    ok=True, terms=[title])
