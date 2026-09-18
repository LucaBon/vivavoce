"""Italian connectors.

Italian is the default language, so this module is also what a request in a
language this package has never heard of falls back to — see ``for_lang``.

``dell['’]`` keeps a MANDATORY space, which is not a detail. While the tables
were one shared pile the whitespace lived outside the group and applied to
every alternative alike; moving it inside, written ``\\s*``, silently started
splitting elided Italian titles — «Il canto dell'amore» went looking for a
singer called «amore». Only French elides without a space, and it says so in
its own module.
"""

from __future__ import annotations

CODE = "it"

LEAD_FILLER = (r"la\s+canzone|il\s+brano|la\s+traccia|il\s+pezzo|la\s+song")

ALBUM_SEP = (r"dall['’]?\s*album|dell['’]?\s*album|dal\s+disco"
             r"|dall['’]?\s*disco")

# Longest first, and every alternative carries its own trailing whitespace.
ARTIST_SEP = (r"dei\s+|degli\s+|delle\s+|della\s+|dell['’]\s+|del\s+|di\s+")

# Tails that are never an artist name — the phrase just happens to end in a
# connector. Without this, «Ti amo di più» searched for a singer called «più».
NOT_AN_ARTIST = {
    "piu", "meno", "me", "te", "noi", "voi", "lui", "lei", "loro", "se",
}

# Words that may sit around a title in a pick and add nothing to it — the
# articles and the nouns ``LEAD_FILLER`` already strips off the front of a
# search. ``candidates.choose_by_name`` reads them and nothing else does: with
# a numbered list open, a title that merely OCCURS inside the request used to
# win it, so «metti Money for Nothing dei Dire Straits» played the «Money»
# that was on the list. The test is now what is LEFT once the title is taken
# out: filler, and the pick stands; anything with content in it, and the
# request was a new one.
#
# Written normalized (no accents, no apostrophes, elision split into its own
# token), because that is the form ``_normalize`` hands the lookup: «l'album»
# arrives as "l album".
PICK_FILLER = {
    "il", "lo", "la", "i", "gli", "le", "l", "un", "uno", "una",
    "canzone", "brano", "traccia", "pezzo", "song", "album", "disco",
    "playlist", "per", "favore", "grazie", "dai", "mi", "poi",
}
