"""German phrases for spoken media. See ``spoken_it.py`` for why these live
beside the pack, and why the direction is a lookahead — German needs it most:
«30 Sekunden zurück», «spul eine Minute vor», «spring zurück um 10 Sekunden»
put the separable particle wherever the sentence ends."""

from __future__ import annotations

from .base import c

_AMOUNT = r"(?P<n>\d+|[^\W\d_]+(?:[\s-]+[^\W\d_]+){0,3}?)"
_PLUS = r"(?P<plus>\s+und\s+(?:eine\s+)?halbe?)?"
_UNIT = r"(?P<unit>sekunden?|minuten?)"
_VERB = r"(?:spule?|springe?|gehe?|mach)"
_DIR = r"(?:vor(?:w[aä]rts)?|zur[uü]ck|nach\s+vorne|weiter)"
_BODY = (rf"(?:{_VERB}\s+)?(?:{_DIR}\s+)?(?:um\s+)?{_AMOUNT}[\s-]+{_UNIT}{_PLUS}"
         rf"(?:\s+{_DIR})?(?:\s+bitte)?\s*$")
_BACK = r"(?=.*\bzur[uü]ck\b)"

#: «Geschwindigkeit 1,5», «stell die Geschwindigkeit auf 1.5», «lies
#: schneller/langsamer», «schneller/langsamer vorlesen». Not gated on
#: is_play — see intents_spoken._route_spoken.
_NUM = r"\d+(?:[.,]\d+)?"
_SPEED_VALUE = rf"(?:stelle?\s+(?:die\s+)?geschwindigkeit\s+auf|geschwindigkeit)\s+{_NUM}"
_SPEED_WORD = r"(?:lies\s+)?(?:schneller|langsamer)(?:\s+vorlesen)?"

PATTERNS = {
    "speed": c(rf"^(?:{_SPEED_VALUE}|{_SPEED_WORD})\s*$"),
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
    # «weiter mit dem Hörbuch X», «setz das Hörbuch X fort»: the same lookup
    # as ``audiobook``, worded as a return rather than a start (T5.6). The
    # noun is required so a bare «weiter»/«fortsetzen» keeps meaning the
    # transport's own play/unpause.
    # «fort» is dropped only after «setz…»: a title may end in it («Sie
    # sind fort»), and «weiter mit» never takes one.
    "resume_book": c(r"^(?:weiter\s+mit\s+(?:dem\s+|meinem\s+)?"
                     r"(?:h(?:ö|oe|o)rbuch|buch)\s+(.+?)"
                     r"|setz(?:e)?\s+(?:das\s+|mein\s+)?"
                     r"(?:h(?:ö|oe|o)rbuch|buch)\s+(.+?)\s+fort)\s*$"),
    # Chapters (T5.6): «Kapitel» is in every one, so a bare «weiter» /
    # «zurück» keeps skipping the track. A near miss falls through to the
    # track skip, which on a one-file .m4b skips the book.
    "chapter_next": c(r"^(?:(?:(?:spring|springe|geh|gehe)\s+)?(?:zum\s+)?"
                      r"n(?:ä|ae|a)chste[snm]?\s+kapitel"
                      r"|(?:ein\s+)?kapitel\s+(?:weiter|vor))"
                      r"(?:,?\s+bitte)?\s*$"),
    "chapter_prev": c(r"^(?:(?:(?:spring|springe|geh|gehe)\s+)?(?:zum\s+)?"
                      r"vorherige[snm]?\s+kapitel"
                      r"|(?:ein\s+)?kapitel\s+zur(?:ü|ue|u)ck)"
                      r"(?:,?\s+bitte)?\s*$"),
    "chapter_which": c(r"^(?:(?:in|bei)\s+)?welche[sm]?\s+kapitel"
                       r"(?:\s+(?:ist\s+(?:das|es)|bin\s+ich|sind\s+wir|h(?:ö|oe|o)re\s+ich))?\s*$"),
}
