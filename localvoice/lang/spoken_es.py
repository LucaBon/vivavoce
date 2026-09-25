"""Spanish phrases for spoken media. See ``spoken_it.py`` for why these live
beside the pack, and why the direction is a lookahead."""

from __future__ import annotations

from .base import c

_AMOUNT = r"(?P<n>\d+|[^\W\d_]+(?:[\s-]+[^\W\d_]+){0,3}?)"
_PLUS = r"(?P<plus>\s+y\s+medi[oa])?"
_UNIT = r"(?P<unit>segundos?|minutos?)"
_VERB = r"(?:adelanta|avanza|retrocede|atrasa|vuelve|rebobina|salta|ve)"
_DIR = r"(?:hacia\s+)?(?:adelante|delante|atr[aá]s)"
_BODY = (rf"(?:{_VERB}\s+)?(?:{_DIR}\s+)?(?:unos\s+)?{_AMOUNT}[\s-]+{_UNIT}{_PLUS}"
         rf"(?:\s+{_DIR})?(?:\s+por\s+favor)?\s*$")
_BACK_WORDS = r"(?:retroced\w*|atras\w*|atr[aá]s|rebobin\w*|vuelve)"

#: «velocidad 1.5», «pon la velocidad a 1.5», «lee más rápido/despacio»,
#: «más rápido/más despacio». Not gated on is_play — see
#: intents_spoken._route_spoken.
_NUM = r"\d+(?:[.,]\d+)?"
_SPEED_VALUE = rf"(?:pon(?:me)?(?:\s+la)?\s+velocidad(?:\s+a)?|velocidad)\s+{_NUM}"
_SPEED_WORD = r"(?:lee\s+)?m[aá]s\s+(?:r[aá]pido|despacio|lento)"

PATTERNS = {
    "speed": c(rf"^(?:{_SPEED_VALUE}|{_SPEED_WORD})\s*$"),
    "seek_back": c(rf"^(?=.*\b{_BACK_WORDS}(?!\w)){_BODY}"),
    "seek_fwd": c(rf"^(?!.*\b{_BACK_WORDS}(?!\w))"
                  rf"(?=.*\b(?:adelant\w*|avanz\w*|salta|delante)\b){_BODY}"),
    # «audiolibro» is the marker; «léeme el libro X» the other way.
    "audiobook": c(r"^(?:(?:(?:pon|ponme|reproduce|escucha|lee|l[eé]eme)\s+)?"
                   r"(?:el\s+|un\s+|mi\s+)?audiolibro"
                   r"|l[eé]eme\s+(?:el|un)\s+libro)\s+(.+)$"),
    # «reanuda el libro X», «continúa el audiolibro X»: the same lookup as
    # ``audiobook``, worded as a return rather than a start (T5.6). The noun
    # is required so a bare «reanuda»/«continúa»/«sigue» keeps meaning the
    # transport's own play/unpause.
    "resume_book": c(r"^(?:reanuda|contin[uú]a|sigue)\s+"
                     r"(?:el\s+|un\s+|mi\s+)?(?:audio)?libro\s+(.+)$"),
    # Chapters (T5.6): «capítulo» is in every one, so a bare «siguiente» /
    # «anterior» keeps skipping the track. A near miss falls through to the
    # track skip, which on a one-file .m4b skips the book.
    "chapter_next": c(r"^(?:(?:pasa|ve|salta|pon)(?:me)?\s+)?(?:al\s+|el\s+)?"
                      r"(?:(?:siguiente|pr[oó]ximo)\s+cap[ií]tulo|cap[ií]tulo\s+siguiente)"
                      r"(?:,?\s+por\s+favor)?\s*$"),
    "chapter_prev": c(r"^(?:(?:vuelve|volver|ve|pasa|pon)(?:me)?\s+)?(?:al\s+|el\s+)?"
                      r"cap[ií]tulo\s+anterior"
                      r"(?:,?\s+por\s+favor)?\s*$"),
    "chapter_which": c(r"^(?:en\s+)?(?:qu[eé]|cu[aá]l)\s+(?:es\s+el\s+)?cap[ií]tulo"
                       r"(?:\s+(?:estoy|estamos|es))?\s*$"),
}
