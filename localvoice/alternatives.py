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
from conversation import OFFER
from messages import msg, set_lang
from parsing import _reportable


class AlternativeSweep:
    """I due giri sulle alternative, e il perché dell'ordine."""

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

    def _payload(self, speech, alt, *, ok: bool) -> dict:
        return {"speech": speech, "used": _reportable(alt), "ok": ok,
                "terms": list(getattr(speech, "terms", [])),
                "choices": self._choices(),
                "needs_choice": self._needs_choice(),
                "unmatched": False}

    def handle_many(self, alternatives, source: str = "tidal", lang: str = "it") -> dict:
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
        payload, primary, unmatched = self._sweep(alts, source, lang,
                                                  repair=False)
        if payload is None and unmatched:
            payload, second, _ = self._sweep(unmatched, source, lang,
                                             repair=True)
            # La primaria resta quella del PRIMO giro: se anche il secondo
            # fallisce, la frase da riportare è quella che l'utente ha detto,
            # non una riscritta da noi.
            if payload is None and primary is None:
                primary = second
        if payload is not None:
            return payload
        return {"speech": primary[0], "used": primary[1], "ok": primary[2],
                "terms": list(getattr(primary[0], "terms", [])),
                "choices": self._choices(),
                "needs_choice": self._needs_choice(),
                "unmatched": primary[3]}
