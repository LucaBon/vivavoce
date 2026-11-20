"""Le alternative del riconoscitore, provate finché una colpisce.

Web Speech ne restituisce diverse per lo stesso audio, ordinate dalla sua
preferita in giù, e quella preferita non è affatto sempre la migliore: il
motore it-IT storpia i nomi inglesi («Audioslave» → «sfigati») e spesso è
un'alternativa di rango più basso a trascriverli bene. Whisper invece ne dà
una sola, e questo modulo è il posto dove quella differenza si vede.

Vive a parte da ``router.py`` per la ragione per cui ne sono già usciti
``conversation.py``, ``intents.py`` e ``sources.py``: quel file ha un tetto di
400 righe (``tests/test_packaging.py``) e qui c'è una cucitura vera — tutto
ciò che riguarda *più letture dello stesso turno*, e niente che riguardi una
lettura sola. È un mixin di :class:`Router`, come gli altri tre.
"""

from __future__ import annotations

import actions
from conversation import Busy, OFFER, busy
from lang import PACKS
from messages import msg, set_lang
from parsing import _reportable, clean_command

#: The ``kind`` of an answer that asks the user to choose from a numbered
#: list (``candidates.py``, ``matching._did_you_mean``): a question, not a play.
CHOICE_KINDS = ("list", "disambiguate")


class AlternativeSweep:
    """I due giri sulle alternative, e il perché dell'ordine."""

    #: Come è arrivato il turno in corso: ``"voice"`` (microfono) o
    #: ``"typed"`` (casella di testo, API). Solo un turno detto può portarsi
    #: dietro gli errori del riconoscitore, quindi solo quello si corregge.
    turn_via = "typed"

    def _sweep(self, alts, source: str, lang: str, *, repair: bool):
        """Un giro sulle alternative. ``(risposta, primaria, incomprese)``.

        ``risposta`` è il turno risolto — un colpo, un gate o un'offerta — e
        ``None`` quando ogni alternativa ha mancato. ``incomprese`` sono le
        alternative che nessuna regola ha agganciato: le uniche su cui la
        riparazione del verbo possa cambiare qualcosa.
        """
        primary = None
        unmatched = []
        for alt in alts:
            speech = self.handle(alt, source, lang, repair=repair)
            # A result is a hit when it acted on the request, and ``.ok`` is
            # how it says so. The ``getattr`` default is a backstop for a
            # plain string, and nothing in this codebase returns one any more:
            # it used to, and the heuristic was wrong in both languages, not
            # just in English as it once claimed. «Per farlo in Cucina serve
            # Pro» does not start with "non", so a refusal was reported as a
            # hit — to the web app, and to ``/api/v1/command``'s ``ok``, which
            # is a promise made to callers who cannot read the sentence. Every
            # path now carries the flag; the default stays for an injected
            # action from outside the engine, and keeps the old reading so
            # such a caller sees no change.
            ok = getattr(speech, "ok", not speech.strip().lower().startswith("non "))
            if primary is None:
                primary = (speech, _reportable(alt), ok, self._unmatched)
            if self._unmatched:
                unmatched.append(alt)
            # A gate is the end of the turn even though it is not a hit. The
            # alternatives exist to find better *words*; a gate has already
            # said the words are not the problem — no licence, not the owner,
            # not for this listener — so trying the next one cannot change
            # the answer, and can do harm. «metti Beatles in salotto» on the
            # free tier is refused with the room named and the way out; its
            # second-best transcription is «metti Beatles», which names no
            # room, sails past the gate and starts the music in the kitchen.
            # The listener never hears the refusal. Same shape for kid-safe:
            # retry the blocked artist until one spelling slips through.
            #
            # An OFFER ends the turn for the same reason from the other side:
            # it asked a question, the answer is the next turn's, and routing
            # the second-best transcription over it would throw the question
            # away between asking it and reading it out.
            if not ok and getattr(speech, "kind", None) in (actions.GATE, OFFER):
                return self._payload(speech, alt, ok=False), primary, unmatched
            if ok:
                return self._payload(speech, alt, ok=True), primary, unmatched
        return None, primary, unmatched

    def _rename(self, payload, alts, source: str, lang: str):
        """A spoken turn that played nothing, tried once more with a name
        this household really has (Pro, docs/name-recognition-design.md §1.3).

        The recogniser writes «camin» for «Kamin»; the search finds three
        Occitan songs with «camin» in the title and asks which. The injected
        ``names`` feature knows «Kamin di EMIN & JONY» has been played here,
        and that it sounds exactly like what was heard: the sentence is
        rebuilt with that name and run through the whole router again —
        kid-safe, rooms, sources and all — and the answer says what was
        heard, so a wrong guess is never a silent one.

        Only where nothing was lost by trying: a spoken turn (a typed name is
        spelt as meant), that played nothing — a miss, a list to choose from,
        a "did you mean". Never over a play, a gate, or a system that is not
        answering. And not over a list that already holds the known name:
        that list asked a fair question, and the answer is the user's.
        """
        names = getattr(self, "names", None)
        if names is None or self.turn_via != "voice":
            return payload
        speech = payload["speech"] if payload is not None else None
        kind = getattr(speech, "kind", None)
        if speech is not None and kind not in CHOICE_KINDS + (OFFER,) and (
                getattr(speech, "ok", False) or kind is not None):
            return payload
        P = (PACKS.get(lang) or PACKS["it"]).PATTERNS
        heard = []
        for alt in alts:
            t = clean_command(alt)
            m = t and (P["generic_play"].search(t) or (
                "generic_play_suffix" in P and P["generic_play_suffix"].match(t)))
            if m:
                heard.append((t, m))
        if not heard:
            return payload
        try:
            found = names.rename([m.group(1).strip() for _t, m in heard], lang)
        except Exception:  # noqa: BLE001 — a guess is never worth the turn
            found = None
        if not found or _lists(speech, found):
            return payload
        t, m = heard[found["index"]]
        text = t[:m.start(1)] + found["text"] + t[m.end(1):]
        result = self.handle(text, source, lang)
        r_kind = getattr(result, "kind", None)
        ok = getattr(result, "ok", False)
        if not ok and r_kind != actions.GATE:
            return payload  # the known name did no better: keep the first answer
        if ok and r_kind is None:
            self._close_list()  # it played: the first answer's list is moot
        return self._payload(renamed_speech(m.group(1).strip(), result),
                             text, ok=ok)

    def _close_list(self) -> None:
        self.candidates = None
        self.cand_source = None
        self.cand_player = None
        self.cand_mode = "play"

    def _note_played(self, speech) -> None:
        """Tell the play history (Pro) what this turn started, if anything.

        A turn played something when it acted (``ok``), is not a list or a
        question (no ``kind``) and named what it played (``terms``): «pausa»
        names nothing, a numbered list has a kind. Typed turns count as much
        as spoken ones — a name somebody wrote is spelt right, which is
        exactly what the history is for. Never allowed to fail the turn: the
        music is already playing, and the answer must still be given.
        """
        names = getattr(self, "names", None)
        terms = list(getattr(speech, "terms", []))
        if (names is None or not getattr(speech, "ok", False)
                or getattr(speech, "kind", None) or not terms):
            return
        client = getattr(self._aim, "last", None) or self.lms
        try:
            names.note_played(client, terms)
        except Exception:  # noqa: BLE001 — a history entry is never worth a turn
            pass

    def _payload(self, speech, alt, *, ok: bool) -> dict:
        return {"speech": speech, "used": _reportable(alt), "ok": ok,
                "terms": list(getattr(speech, "terms", [])),
                "choices": self._choices(),
                "needs_choice": self._needs_choice(),
                "unmatched": False}

    def handle_many(self, alternatives, source: str = "tidal", lang: str = "it",
                    *, via: str = "typed") -> dict:
        """Try each speech-recognition alternative until one is a hit.

        Web Speech (it-IT) often mangles English names ('Audioslave' -> 'sfigati');
        a lower-ranked alternative frequently transcribes them better. Playback
        happens only on a hit, so trying a miss has no side effect. Returns
        ``{'speech', 'used'}`` where ``used`` is the alternative that was kept
        (the primary one if none matched).

        **Due giri, e l'ordine è il punto.** Il primo prova le alternative
        così come sono arrivate; solo se nessuna aggancia, il secondo rimette
        a posto il verbo mal sentito (``parsing.repair_play_verb``). Riparare
        già al primo giro sembrava equivalente e non lo è: la riparazione fa
        colpire alternative che prima mancavano, quindi una trascrizione
        **prima ma peggiore** vincerebbe su una **dopo ma migliore** — «Matti
        Creep» riparato batterebbe «metti Creepshow», che è la parola giusta.
        Sarebbe il contrario di ciò per cui questo metodo esiste, come dice la
        riga qui sopra: le alternative servono a trovare parole migliori.

        Il secondo giro ripassa **solo le alternative incomprese**. Una che
        aveva agganciato e non trovato nulla ha già speso la sua ricerca sul
        server musicale, e il verbo non c'entrava: rifarla costerebbe una
        seconda interrogazione identica dentro un budget di dieci secondi.
        """
        set_lang(lang)
        alts = [a for a in (alternatives or []) if (a or "").strip()]
        if not alts:
            return {"speech": msg("heard_nothing"), "used": "", "ok": False,
                    "terms": [], "choices": [], "needs_choice": False,
                    "unmatched": False}
        # Both rounds inside ONE turn: a sweep is one spoken turn, so another
        # request arriving between its alternatives would read the state
        # half-written (see Router.__init__) — and the ten seconds the sweep
        # is allowed are the ten seconds of that one turn, not ten per
        # alternative (see ConversationState._turn).
        try:
            with self._turn():
                # Inside the turn: two conversations never share a Router,
                # and within one the turn lock keeps this from being read
                # half-way through someone else's sentence.
                self.turn_via = via
                self._aim.last = None  # see ConversationState._aimed_at
                payload, primary, unmatched = self._sweep(alts, source, lang,
                                                          repair=False)
                if payload is None and unmatched:
                    payload, second, _ = self._sweep(unmatched, source, lang,
                                                     repair=True)
                    # La primaria resta quella del PRIMO giro: se anche il
                    # secondo fallisce, la frase da riportare è quella che
                    # l'utente ha detto, non una riscritta da noi.
                    if payload is None and primary is None:
                        primary = second
                payload = self._rename(payload, alts, source, lang)
        except Busy:
            return {"speech": busy(), "used": "", "ok": False, "terms": [],
                    "choices": [], "needs_choice": False, "unmatched": False}
        if payload is not None:
            self._note_played(payload["speech"])
            return payload
        return {"speech": primary[0], "used": primary[1], "ok": primary[2],
                "terms": list(getattr(primary[0], "terms", [])),
                "choices": self._choices(),
                "needs_choice": self._needs_choice(),
                "unmatched": primary[3]}


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
