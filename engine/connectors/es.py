"""Spanish connectors.

«de» is how Spanish names an artist («Malamente de Rosalía»), which makes this
the second module in the package to claim that word — French claimed it first,
and the reason the package came apart at all is that it was shared. Nothing is
shared now, so the two claims cost nothing: ``for_lang`` hands a Spanish
request the Spanish table and a French request the French one, and
``tests/test_connectors.py`` asserts «de Pink Floyd» splits in both and in
neither of the other three.

Longest first in ``ARTIST_SEP``, and it is not decoration: ``parse_song_query``
takes the LAST connector, so a bare `de\\s+` would eat the head of «de los» and
send «Himno de los Planetas» looking for a singer called "los Planetas".
connectors/it.py records the same lesson for «dell'».
"""

from __future__ import annotations

CODE = "es"

LEAD_FILLER = r"la\s+canci[oó]n|el\s+tema|la\s+pista|el\s+corte"

ALBUM_SEP = (r"del\s+[aá]lbum|en\s+el\s+[aá]lbum|del\s+disco"
             r"|de\s+el\s+[aá]lbum")

# Longest first — see the module docstring. «por» is deliberately absent:
# Spanish names a performer with «de», and «por» in a title is «Por Ti Volaré»
# far more often than it is an attribution.
ARTIST_SEP = r"de\s+la\s+|de\s+los\s+|de\s+las\s+|del\s+|de\s+"

# Tails that are never an artist name — the phrase just happens to end in a
# connector. «La Chica de Ayer» must not go looking for a singer called
# «ayer», and «Acuérdate de Mí» for one called «mí»: what «più» does to
# Italian, «me» to English, «mir» to German and «vivre» to French, and rather
# more of it here, because «de» is the whole of the Spanish artist side.
#
# Written normalized (no accents, no apostrophes), because that is the form
# ``_normalize`` hands the lookup — so «mí» is "mi" and «él» is "el". The
# guard reads the WHOLE tail, so it holds only where the tail is the pronoun
# or the adverb alone: «Antes de Que Cuente Diez» still splits, and that is
# the same limit every language in this package has.
NOT_AN_ARTIST = {
    "mi", "ti", "el", "ella", "ellos", "ellas", "nosotros", "vosotros",
    "ustedes", "uno", "una", "si", "aqui", "alli", "ahi", "eso", "esto",
    "aquello", "nada", "todo", "todos", "nadie", "alguien",
    "siempre", "nunca", "ahora", "manana", "ayer", "antes", "despues",
    "mas", "menos", "verdad", "nuevo",
    "vivir", "amar", "sonar", "volver", "morir", "querer", "ti misma",
    "ti mismo", "mi misma", "mi mismo",
}
