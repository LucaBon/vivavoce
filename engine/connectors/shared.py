"""The connectors every language shares — and the reason there is a "shared"
at all rather than four clean per-language sets.

A connector is the word that joins the parts of a spoken request: the filler
in front of a title («la canzone X»), the phrase that introduces an album
(«dall'album X»), the one that introduces an artist («di X», "by X"), and the
tails that are never an artist name however much they look like one.

They were one pile until French arrived. French's artist connector is «de»,
and ``parse_song_query`` scans right to left, so a shared «de» turned «la
canzone di Marinella di De André» into a search for a singer called «André».
Hence ``connectors/``: what one language adds, only that language matches.

What stays here is what is safe in every language, and that set is not empty
by accident. Three tests in the suite ask ``parse_song_query`` for an English
or a German split with no language set at all — «Comfortably Numb by Pink
Floyd» and «… von Pink Floyd» under Italian — and they are right to. The
recogniser's language and the phrasing routinely disagree, which is the same
fact that makes ``localvoice/parsing.py`` merge the number tables across every
pack. So a connector leaves this module only when sharing it costs something.

Each name below is the *inside* of an alternation; the registry in
``__init__.py`` wraps it. Every alternative carries its own trailing
whitespace, because not all of them want the same amount: French elides
(«d'Édith Piaf» has no space after the apostrophe) and «by» does.
"""

from __future__ import annotations

# Fillers a request opens with, before the name it is actually about.
LEAD_FILLER = (r"la\s+canzone|il\s+brano|la\s+traccia|il\s+pezzo|la\s+song"
               r"|the\s+song|d(?:as|en)\s+lied|d(?:er|en)\s+song"
               r"|das\s+st(?:ü|ue)ck|den\s+titel")

# Splits "titolo dall'album X" / "title from album X" into title + album.
ALBUM_SEP = (r"dall['’]?\s*album|dell['’]?\s*album|dal\s+disco"
             r"|dall['’]?\s*disco|from\s+(?:the\s+)?album"
             # German: «Time aus dem Album Dark Side», «vom Album …».
             r"|(?:aus|auf)\s+dem\s+album|vom\s+album|von\s+dem\s+album")

# Splits "titolo di/dei/degli X" / "title by X" into title + artist. Used only
# to *rank* results (the search still runs on the full text), so a mis-split —
# a title that itself contains "di" — degrades gracefully instead of breaking.
ARTIST_SEP = (r"dei\s+|degli\s+|delle\s+|della\s+|dell['’]\s*|del\s+|di\s+"
              r"|by\s+|von\s+")

# Tails that are never an artist name — the phrase just happens to contain a
# connector. Without this, "Ti amo di più" searched for a singer called
# «più», and "Stand By Me" for one called "Me".
NOT_AN_ARTIST = {
    "piu", "meno", "me", "te", "noi", "voi", "lui", "lei", "loro", "se",
    "you", "us", "it", "her", "him", "them", "myself", "yourself", "now",
    "here", "there", "one", "two", "all", "more", "less", "everyone",
    # German, where «von» is the connector: «Ein Teil von mir» must not go
    # looking for a singer called "mir".
    "mir", "dir", "uns", "euch", "ihm", "ihr", "ihnen", "mich", "dich",
    "sich", "hier", "dort", "jetzt", "allen", "alle", "einem", "einer",
    "keinem", "niemandem", "damals", "heute",
}
