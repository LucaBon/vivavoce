"""Italian phrases for spoken media — the relative seek and the audiobooks.

Beside the pack rather than in it: ``it.py`` would have room, but German's
does not (``tests/test_packaging.py`` holds every file under 400 lines), and
five languages with the same three keys belong in five files of the same
shape. The registry in ``__init__.py`` folds these into the pack's
``PATTERNS``, so the router sees one table and the key-parity test covers
them like any other.

**The direction is a lookahead, not a branch.** «vai avanti di 30 secondi»,
«avanti di 30 secondi», «30 secondi avanti», «salta 30 secondi»: the words
come in any order around the one thing that never moves — a number and a unit
of time. So both patterns share one body and differ only in what the sentence
has to contain somewhere. Two branches would need two capture groups per
name, which Python refuses.

**Why the unit is required.** «avanti» and «indietro» are already ``next`` and
``prev``, and this step runs first. A bare «avanti» must keep skipping the
track, so nothing here matches without «secondi» or «minuti».
"""

from __future__ import annotations

from .base import c

_AMOUNT = r"(?P<n>\d+|[^\W\d_]+(?:[\s-]+[^\W\d_]+){0,3}?)"
_PLUS = r"(?P<plus>\s+e\s+mezz[oa])?"
_UNIT = r"(?P<unit>second[oi]|minut[oi])"
_VERB = r"(?:vai|va|torna|salta|spostati|sposta|manda|portati|porta|riavvolgi|avanza)"
_DIR = r"(?:in\s+)?(?:avanti|indietro)"
_BODY = (rf"(?:{_VERB}\s+)?(?:{_DIR}\s+)?(?:di\s+)?{_AMOUNT}[\s-]+{_UNIT}{_PLUS}"
         rf"(?:\s+{_DIR})?(?:\s+(?:per\s+favore|grazie))?\s*$")
_BACK = r"(?=.*\b(?:indietro|riavvolgi)\b)"

#: «metti a velocità 1.2», «velocità 1,5», «leggi più veloce/lento», «più
#: veloce/più lento». Not gated on is_play — see intents_spoken._route_spoken.
_NUM = r"\d+(?:[.,]\d+)?"
_SPEED_VALUE = rf"(?:metti(?:\s+la)?(?:\s+a)?\s+velocit[aà]|velocit[aà])\s+{_NUM}"
_SPEED_WORD = r"(?:leggi(?:mi)?\s+)?pi[uù]\s+(?:veloce|lento)"

PATTERNS = {
    "speed": c(rf"^(?:{_SPEED_VALUE}|{_SPEED_WORD})\s*$"),
    "seek_back": c(rf"^{_BACK}{_BODY}"),
    "seek_fwd": c(rf"^(?!.*\b(?:indietro|riavvolgi)\b)"
                  rf"(?=.*\b(?:avanti|salta|avanza)\b){_BODY}"),
    # A marker a song title never carries: «audiolibro», or «leggi il
    # libro». Never «metti il libro X» — *Il libro della giungla* is a record.
    "audiobook": c(r"^(?:(?:(?:metti|mettimi|riproduci|fai\s+partire|ascolta"
                   r"|voglio\s+ascoltare|leggi|leggimi)\s+)?"
                   r"(?:l['’]\s*|un\s+|il\s+mio\s+)?audiolibro"
                   r"|(?:leggi|leggimi)\s+(?:il|un)\s+libro)\s+(.+)$"),
    # «riprendi il libro X», «riprendi l'audiolibro X», «continua il libro
    # X»: the same lookup as ``audiobook``, worded as a return rather than a
    # start (T5.6) — resuming is what «riprendi» already does for a book,
    # so this is only another name for it. The noun is required so a bare
    # «riprendi» keeps meaning the transport's own play/unpause.
    "resume_book": c(r"^(?:riprendi|continua)\s+"
                     r"(?:l['’]\s*|il\s+mio\s+|il\s+|un\s+)?"
                     r"(?:audiolibro|libro)\s+(.+)$"),
    # Chapters (T5.6): the noun «capitolo» is in every one, so a bare
    # «avanti»/«indietro»/«prossimo» keeps skipping the track.
    "chapter_next": c(r"^(?:(?:(?:vai|passa|salta|metti)\s+(?:al\s+|il\s+)?)?"
                      r"(?:prossimo\s+capitolo|capitolo\s+(?:successivo|seguente|dopo))"
                      r"|salta\s+(?:questo\s+|il\s+)?capitolo"
                      r"|avanti\s+(?:di\s+)?un\s+capitolo)\s*$"),
    "chapter_prev": c(r"^(?:(?:(?:vai|torna|passa|metti)\s+(?:al\s+|il\s+)?)?"
                      r"capitolo\s+(?:precedente|prima)"
                      r"|(?:torna\s+|vai\s+)?indietro\s+(?:di\s+)?un\s+capitolo)\s*$"),
    "chapter_which": c(r"^(?:(?:a|di|in)\s+)?(?:che|quale)\s+capitolo"
                       r"(?:\s+(?:sono|siamo|[eè]|sto\s+ascoltando|sono\s+arrivat[oa]))?\s*$"),
}
