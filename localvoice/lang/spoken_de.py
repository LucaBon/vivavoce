"""German phrases for spoken media. See ``spoken_it.py`` for why these live
beside the pack, and why the direction is a lookahead — German needs it most:
«30 Sekunden zurück», «spul eine Minute vor», «spring zurück um 10 Sekunden»
put the separable particle wherever the sentence ends."""

from __future__ import annotations

from .base import c

_AMOUNT = r"(?P<n>\d+|eine?\s+halbe|ein\s+paar|[a-zäöüß]+)"
_UNIT = r"(?P<unit>sekunden?|minuten?)"
_VERB = r"(?:spule?|springe?|gehe?|mach)"
_DIR = r"(?:vor(?:w[aä]rts)?|zur[uü]ck|nach\s+vorne|weiter)"
_BODY = (rf"(?:{_VERB}\s+)?(?:{_DIR}\s+)?(?:um\s+)?{_AMOUNT}[\s-]+{_UNIT}"
         rf"(?:\s+{_DIR})?(?:\s+bitte)?\s*$")
_BACK = r"(?=.*\bzur[uü]ck\b)"

PATTERNS = {
    "seek_back": c(rf"^{_BACK}{_BODY}"),
    "seek_fwd": c(rf"^(?!.*\bzur[uü]ck\b)"
                  rf"(?=.*\b(?:vor(?:w[aä]rts)?|vorne|weiter|spule?|springe?)\b)"
                  rf"{_BODY}"),
    # «Hörbuch» is the marker; «lies mir das Buch X vor» the other way, with
    # its particle at the end — trimmed, like «ab» after «spiel … ab».
    "audiobook": c(r"^(?:(?:(?:spiele?|starte|lies(?:\s+mir)?)\s+)?"
                   r"(?:das\s+|ein\s+|mein\s+)?h(?:ö|oe|o)rbuch"
                   r"|lies\s+(?:mir\s+)?(?:das|ein)\s+buch)\s+(.+?)"
                   r"(?:\s+(?:vor|ab))?\s*$"),
}
