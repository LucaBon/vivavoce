"""Misheard names, on the router's side: where a spoken turn meets the
names this household really has (docs/name-recognition-design.md).

Three moments, all of them hooks with no policy of their own — the injected
``names`` feature (``localvoice/pro/names.py``, Pro) decides everything:

* **before** a spoken turn is routed, a correction the household confirmed
  («when you hear "coming di eminem e johnny", I mean "Kamin di EMIN &
  JONY"») replaces what was heard (:meth:`NamesTurn._corrected`);
* **after** a spoken turn that played nothing, a known name that sounds like
  what was heard is tried once (:meth:`NamesTurn._rename`);
* **after** a written turn that played, right after a spoken one that asked
  for something alike, the reply offers "remember this"
  (:meth:`NamesTurn._offer_to_remember`).

Only spoken turns are ever changed: a typed name is spelt as meant. Every
change is said out loud («Ho sentito «camin».»), runs through the whole
router again — kid-safe, rooms, sources — and never costs the turn: a hook
that fails leaves the answer it would have had.

A mixin of :class:`Router`, like ``alternatives.py`` beside it, and for the
same reason: ``router.py`` keeps under its 400-line ceiling.
"""

from __future__ import annotations

from typing import List, Optional, Tuple

import actions
from conversation import OFFER
from lang import PACKS
from messages import msg
from parsing import clean_command
from player.protocols import supports

#: The ``kind`` of an answer that asks the user to choose from a numbered
#: list (``candidates.py``, ``matching._did_you_mean``): a question, not a play.
CHOICE_KINDS = ("list", "disambiguate")

#: How long after a spoken turn a written one can still be its correction.
#: Long enough to read the answer, open the keyboard and type a name; short
#: enough that tonight's request is not paired with this morning's.
CORRECTION_WINDOW = 90.0


class NamesTurn:
    """The three hooks, and the bookkeeping the third one needs."""

    #: The spoken turn a written one may be correcting: what it asked to play
    #: (one entry per alternative), when, and in which language.
    _last_voice: Optional[Tuple[List[str], float, str]] = None

    # -- before: a confirmed correction ---------------------------------------

    def _corrected(self, alts, source: str, lang: str):
        """The turn's answer when a confirmed correction covers what was
        heard, else None and the turn is routed as usual. A correction that
        finds nothing (the record has left the library) falls back to the
        usual routing too: a rule the user wrote is not a reason to fail."""
        names = getattr(self, "names", None)
        if names is None or self.turn_via != "voice":
            return None
        heard = _play_requests(alts, lang)
        if not heard:
            return None
        try:
            found = names.correct([m.group(1).strip() for _t, m in heard], lang)
        except Exception:  # noqa: BLE001 — a rule is never worth the turn
            found = None
        if not found:
            return None
        return self._try_instead(heard[found["index"]], found["text"],
                                 source, lang, keep=None)

    # -- after: a known name that sounds like it ---------------------------------

    def _rename(self, payload, alts, source: str, lang: str):
        """A spoken turn that played nothing, tried once more with a name
        this household really has (Pro, docs/name-recognition-design.md §1.3).

        The recogniser writes «camin» for «Kamin»; the search finds three
        Occitan songs with «camin» in the title and asks which. The injected
        ``names`` feature knows «Kamin» has been played here, and that it
        sounds exactly like what was heard: the sentence is rebuilt with
        that name and run through the whole router again.

        Only where nothing was lost by trying: a spoken turn that played
        nothing — a miss, a list to choose from, a "did you mean". Never over
        a play, a gate, or a system that is not answering. And not over a
        list that already holds the known name: that list asked a fair
        question, and the answer is the user's.
        """
        names = getattr(self, "names", None)
        if names is None or self.turn_via != "voice":
            return payload
        speech = payload["speech"] if payload is not None else None
        kind = getattr(speech, "kind", None)
        if speech is not None and kind not in CHOICE_KINDS + (OFFER,) and (
                getattr(speech, "ok", False) or kind is not None):
            return payload
        heard = _play_requests(alts, lang)
        if not heard:
            return payload
        queries = [m.group(1).strip() for _t, m in heard]
        try:
            found = names.rename(queries, lang)
            if not found:  # phase 4: a name nobody here has played yet
                found = names.respell(queries, lang,
                                      search=self._probe_for(source))
        except Exception:  # noqa: BLE001 — a guess is never worth the turn
            found = None
        if not found or _lists(speech, found):
            return payload
        return self._try_instead(heard[found["index"]], found["text"],
                                 source, lang, keep=payload)

    def _probe_for(self, source: str):
        """A catalogue lookup for :meth:`Names.respell`: the tracks a query
        finds where this request would look — the library for ``local``,
        the streaming service for a service, both for ``auto`` — as
        ``[{"title", "artist"}]``. It searches; it never plays. The turn's
        deadline (``turn_deadline``) bounds it like every other call."""
        def probe(query: str):
            rows = []
            if source in ("auto", "local") and supports(self.lms, "local_library"):
                rows += self.lms.local_track_candidates(query, 10)
            if source != "local" and supports(self.lms, "search"):
                stream, _name, offline = self._streaming(source)
                if not offline:
                    rows += stream.search_tracks(query, 10)
            return [{"title": r.get("title"), "artist": r.get("artist")}
                    for r in rows if r.get("title")]
        return probe

    def _try_instead(self, heard, name: str, source: str, lang: str, *, keep):
        """Route the sentence ``heard`` with ``name`` in place of what was
        asked for. The answer, said after what was heard — or ``keep`` when
        the new sentence did no better (a plain miss)."""
        t, m = heard
        text = t[:m.start(1)] + name + t[m.end(1):]
        result = self.handle(text, source, lang)
        r_kind = getattr(result, "kind", None)
        ok = getattr(result, "ok", False)
        if not ok and r_kind != actions.GATE:
            return keep
        if ok and r_kind is None:
            self._close_list()  # it played: an earlier answer's list is moot
        return self._payload(renamed_speech(m.group(1).strip(), result),
                             text, ok=ok)

    def _close_list(self) -> None:
        self.candidates = None
        self.cand_source = None
        self.cand_player = None
        self.cand_mode = "play"

    # -- after: "remember this?" -------------------------------------------------

    def _offer_to_remember(self, payload, alts, lang: str, heard=None) -> None:
        """Note a spoken turn, or offer to remember the written one that
        corrected it.

        ``heard`` is what the page heard before the user corrected it in the
        text box (auto-send off): that transcript never reached the server as
        a turn of its own, so the page sends it along. Otherwise it is the
        last spoken turn on this conversation, if recent enough. The offer is
        ``payload["remember"]``, and it is only ever an offer: nothing is
        kept until somebody taps it (``POST /names``).
        """
        names = getattr(self, "names", None)
        if names is None:
            return
        now = self.now()
        if self.turn_via == "voice":
            self._last_voice = ([m.group(1).strip()
                                 for _t, m in _play_requests(alts, lang)],
                                now, lang)
            return
        speech = payload.get("speech") if payload else None
        if not (getattr(speech, "ok", False) and not getattr(speech, "kind", None)):
            return  # only a written turn that played is a correction
        if heard:
            said = [m.group(1).strip() for _t, m in _play_requests(heard, lang)]
        elif (self._last_voice and self._last_voice[2] == lang
              and now - self._last_voice[1] <= CORRECTION_WINDOW):
            said = self._last_voice[0]
        else:
            return
        meant = _play_requests([payload.get("used") or ""], lang)
        if not said or not meant:
            return
        try:
            offer = names.suggest(said, meant[0][1].group(1).strip(), lang)
        except Exception:  # noqa: BLE001
            offer = None
        if offer:
            payload["remember"] = dict(offer, lang=lang)
            self._last_voice = None  # offered once


def _play_requests(sentences, lang: str):
    """``[(sentence, match)]`` for each sentence that asks to play something
    («metti X»), where ``match.group(1)`` is the X. Only the generic verb:
    the album, playlist and artist phrases are not covered yet (see the
    design document's limits)."""
    P = (PACKS.get(lang) or PACKS["it"]).PATTERNS
    out = []
    for sentence in sentences or []:
        t = clean_command(sentence) if isinstance(sentence, str) else None
        m = t and (P["generic_play"].search(t) or (
            "generic_play_suffix" in P and P["generic_play_suffix"].match(t)))
        if m:
            out.append((t, m))
    return out


def _lists(speech, found) -> bool:
    """Whether the answer already being given lists the known name: same
    title, and same artist when both say one."""
    title = actions._normalize(found.get("title"))
    artist = actions._normalize(found.get("artist"))
    for cand in getattr(speech, "candidates", None) or []:
        c_title = actions._normalize(cand.get("title"))
        c_artist = actions._normalize(cand.get("artist"))
        if title and c_title == title and (not artist or not c_artist
                                           or c_artist == artist):
            return True
        if not title and artist and c_artist == artist:
            return True
    return False


def renamed_speech(heard: str, result):
    """``result``, said after what was heard: «Ho sentito «camin». Riproduco
    Kamin di EMIN & JONY.» Everything else the result carries stays, so the
    reply is read, tagged and offered exactly like the one it replaces."""
    return actions.ActionResult(
        msg("heard_as", heard=heard) + str(result),
        ok=getattr(result, "ok", False),
        candidates=getattr(result, "candidates", None),
        kind=getattr(result, "kind", None),
        terms=getattr(result, "terms", None),
        label=getattr(result, "label", None))
