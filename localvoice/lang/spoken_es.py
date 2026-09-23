"""Spanish phrases for spoken media. See ``spoken_it.py`` for why these live
beside the pack, and why the direction is a lookahead."""

from __future__ import annotations

from .base import c

_AMOUNT = r"(?P<n>\d+|medio|un\s+par\s+de|[a-záéíóúñü]+)"
_UNIT = r"(?P<unit>segundos?|minutos?)"
_VERB = r"(?:adelanta|avanza|retrocede|atrasa|vuelve|rebobina|salta|ve)"
_DIR = r"(?:hacia\s+)?(?:adelante|delante|atr[aá]s)"
_BODY = (rf"(?:{_VERB}\s+)?(?:{_DIR}\s+)?(?:unos\s+)?{_AMOUNT}[\s-]+{_UNIT}"
         rf"(?:\s+{_DIR})?(?:\s+por\s+favor)?\s*$")
_BACK_WORDS = r"(?:retroced\w*|atras\w*|atr[aá]s|rebobin\w*|vuelve)"

PATTERNS = {
    "seek_back": c(rf"^(?=.*\b{_BACK_WORDS}(?!\w)){_BODY}"),
    "seek_fwd": c(rf"^(?!.*\b{_BACK_WORDS}(?!\w))"
                  rf"(?=.*\b(?:adelant\w*|avanz\w*|salta|delante)\b){_BODY}"),
    # «audiolibro» is the marker; «léeme el libro X» the other way.
    "audiobook": c(r"^(?:(?:(?:pon|ponme|reproduce|escucha|lee|l[eé]eme)\s+)?"
                   r"(?:el\s+|un\s+|mi\s+)?audiolibro"
                   r"|l[eé]eme\s+(?:el|un)\s+libro)\s+(.+)$"),
}
