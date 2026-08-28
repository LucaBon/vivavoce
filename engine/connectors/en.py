"""English connectors.

«by» is the whole of the artist side, and it is also an ordinary English word:
«Stand By Me» is a title and not a request for a singer called «Me». That is
what ``NOT_AN_ARTIST`` is for here — the English half of what «più» is to
Italian and «mir» to German.
"""

from __future__ import annotations

CODE = "en"

LEAD_FILLER = r"the\s+song"

ALBUM_SEP = r"from\s+(?:the\s+)?album"

ARTIST_SEP = r"by\s+"

NOT_AN_ARTIST = {
    "me", "you", "us", "it", "her", "him", "them", "myself", "yourself",
    "now", "here", "there", "one", "two", "all", "more", "less", "everyone",
}
