"""French phrases for spoken media. See ``spoken_it.py`` for why these live
beside the pack, and why the direction is a lookahead."""

from __future__ import annotations

from .base import c

_AMOUNT = r"(?P<n>\d+|[^\W\d_]+(?:[\s-]+[^\W\d_]+){0,3}?)"
_PLUS = r"(?P<plus>\s+et\s+demie?)?"
_UNIT = r"(?P<unit>secondes?|minutes?)"
_VERB = (r"(?:avance|avancer|recule|reculer|reviens|revenir|retourne|va"
         r"|saute|rembobine)")
_DIR = r"(?:rapide|en\s+arri[eè]re|en\s+avant|plus\s+loin)"
_BODY = (rf"(?:{_VERB}\s+)?(?:{_DIR}\s+)?(?:de\s+|d['’]\s*)?{_AMOUNT}[\s-]+{_UNIT}{_PLUS}"
         rf"(?:\s+{_DIR})?(?:\s+(?:s['’]il\s+(?:te|vous)\s+pla[iî]t|merci))?\s*$")
_BACK_WORDS = r"(?:recul\w*|arri[eè]re|rembobin\w*|reviens|revenir|retourne)"

#: «vitesse 1.5», «mets la vitesse à 1.5», «lis plus vite/lentement», «plus
#: vite/plus lentement». Not gated on is_play — see
#: intents_spoken._route_spoken.
_NUM = r"\d+(?:[.,]\d+)?"
_SPEED_VALUE = rf"(?:mets(?:\s+la)?\s+vitesse(?:\s+[aà])?|vitesse)\s+{_NUM}"
_SPEED_WORD = r"(?:lis\s+)?plus\s+(?:vite|lentement)"

PATTERNS = {
    "speed": c(rf"^(?:{_SPEED_VALUE}|{_SPEED_WORD})\s*$"),
    "seek_back": c(rf"^(?=.*\b{_BACK_WORDS}\b){_BODY}"),
    "seek_fwd": c(rf"^(?!.*\b{_BACK_WORDS}\b)"
                  rf"(?=.*\b(?:avanc\w*|saute|en\s+avant|plus\s+loin)\b){_BODY}"),
    # «livre audio» is the marker; «lis-moi le livre X» the other way.
    "audiobook": c(r"^(?:(?:(?:mets|mettre|joue|lance|lis|[ée]coute)(?:[\s-]+moi)?\s+)?"
                   r"(?:le\s+|un\s+|mon\s+)?livre\s+audio"
                   r"|lis(?:[\s-]+moi)?\s+(?:le|un)\s+livre)\s+(.+)$"),
    # «reprends le livre audio X», «continue le livre X»: the same lookup as
    # ``audiobook``, worded as a return rather than a start (T5.6). The noun
    # is required so a bare «reprends»/«continue» keeps meaning the
    # transport's own play/unpause.
    "resume_book": c(r"^(?:reprends?|continue)\s+"
                     r"(?:le\s+|un\s+|mon\s+)?livre(?:\s+audio)?\s+(.+)$"),
    # Chapters (T5.6): «chapitre» is in every one, so a bare «suivant» /
    # «précédent» keeps skipping the track.
    "chapter_next": c(r"^(?:(?:passe|va|aller|saute|mets)(?:[\s-]+moi)?\s+au\s+)?"
                      r"(?:chapitre\s+suivant|prochain\s+chapitre)\s*$"),
    "chapter_prev": c(r"^(?:(?:reviens|retourne|va|passe|mets)(?:[\s-]+moi)?\s+au\s+)?"
                      r"chapitre\s+pr[ée]c[ée]dent\s*$"),
    "chapter_which": c(r"^(?:(?:[àa]|dans)\s+)?quel\s+chapitre"
                       r"(?:\s+(?:je\s+suis|suis[\s-]je|on\s+est|sommes[\s-]nous|c['’]\s*est))?\s*$"
                       r"|^c['’]\s*est\s+quel\s+chapitre\s*$"),
}
