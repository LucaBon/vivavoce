"""German connectors.

«von» does two jobs, and ``parse_song_query`` runs the album step first for
exactly that reason: «Time von dem Album Dark Side» is split on the album
phrase before the artist step ever sees the «von».

It is also a preposition before a pronoun, so «Ein Teil von mir» must not go
looking for a singer called "mir" — the German half of what
``NOT_AN_ARTIST`` does for «più» and for «me».
"""

from __future__ import annotations

CODE = "de"

LEAD_FILLER = (r"d(?:as|en)\s+lied|d(?:er|en)\s+song"
               r"|das\s+st(?:ü|ue)ck|den\s+titel")

# «Time aus dem Album Dark Side», «vom Album …».
ALBUM_SEP = r"(?:aus|auf)\s+dem\s+album|vom\s+album|von\s+dem\s+album"

ARTIST_SEP = r"von\s+"

NOT_AN_ARTIST = {
    "mir", "dir", "uns", "euch", "ihm", "ihr", "ihnen", "mich", "dich",
    "sich", "hier", "dort", "jetzt", "allen", "alle", "einem", "einer",
    "keinem", "niemandem", "damals", "heute",
}
