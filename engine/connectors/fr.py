"""French connectors — the language this package exists for.

«de» is how French names an artist («Ne me quitte pas de Jacques Brel»), and
it is also two letters that begin a great many names. Shared with every other
language it broke Italian outright: ``parse_song_query`` takes the LAST
connector, so «la canzone di Marinella di De André» split at the «De» and went
looking for a singer called «André». That is what ended the one shared pile,
and every language has answered for its own words since.

``d['’]`` carries ``\\s*`` rather than ``\\s+`` because elision leaves no space
behind: «d'Édith Piaf» is one word to a keyboard and two to a reader.
"""

from __future__ import annotations

CODE = "fr"

LEAD_FILLER = r"la\s+chanson|le\s+morceau|le\s+titre|la\s+piste"

ALBUM_SEP = (r"de\s+l['’]?\s*album|dans\s+l['’]?\s*album|sur\s+l['’]?\s*album"
             r"|du\s+disque|de\s+l['’]?\s*opus")

# Longest first: `de\s+` would otherwise eat the head of «de la» and hand the
# artist step "la Callas" as a title.
ARTIST_SEP = r"par\s+|d['’]\s*|des\s+|du\s+|de\s+"

# «Le Temps de Vivre» must not go looking for a singer called «vivre» — the
# French half of what ``NOT_AN_ARTIST`` does for «più» in it.py and «mir» in
# de.py. Written normalized (no accents, no apostrophes), because that is the
# form ``_normalize`` hands the lookup.
NOT_AN_ARTIST = {
    "moi", "toi", "lui", "elle", "nous", "vous", "eux", "elles", "soi",
    "ici", "la", "ca", "cela", "celui", "celle", "ceux", "rien", "tout",
    "tous", "personne", "quelquun", "toujours", "jamais", "maintenant",
    "demain", "hier", "plus", "moins", "vivre", "aimer", "rever", "partir",
    "toi meme", "nouveau", "trop", "peu", "loin", "pres",
}
