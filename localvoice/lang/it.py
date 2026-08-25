"""Italian language pack — the reference implementation of the contract in
``base.py``. Patterns moved verbatim from the pre-split router."""

from __future__ import annotations

from .base import c

CODE = "it"

# Web Speech transcribes a spoken position as a word ("tre"), not "3".
NUM_WORDS = {
    "uno": 1, "un": 1, "una": 1, "due": 2, "tre": 3, "quattro": 4, "cinque": 5,
    "sei": 6, "sette": 7, "otto": 8, "nove": 9, "dieci": 10,
}

# People answer a read-out list with "la seconda" at least as often as with
# the bare number (see the router for how ordinals are gated on an open list).
ORDINAL_WORDS = {
    "primo": 1, "prima": 1, "secondo": 2, "seconda": 2, "terzo": 3, "terza": 3,
    "quarto": 4, "quarta": 4, "quinto": 5, "quinta": 5, "sesto": 6, "sesta": 6,
    "settimo": 7, "settima": 7, "ottavo": 8, "ottava": 8, "nono": 9, "nona": 9,
    "decimo": 10, "decima": 10,
}

# Durations go beyond list positions: the sleep timer needs the spoken tens too
# («spegni tra trenta minuti»).
MINUTE_WORDS = dict(NUM_WORDS)
MINUTE_WORDS.update({
    "quindici": 15, "venti": 20, "trenta": 30, "quaranta": 40,
    "cinquanta": 50, "sessanta": 60, "novanta": 90,
})

# The tail of a sleep command ("spegni tra <tail>"), most specific first.
DURATIONS = (
    (c(r"^mezz\W?ora\b"), 30),
    (c(r"^(?:un|1)\W?\s*ora\b"), 60),
    (c(r"^(\d+|[a-zà-ù]+)\s*ore\b"), "hours"),
    (c(r"^(\d+|[a-zà-ù]+)\s*(?:minut\w*|min\b)"), "minutes"),
)

_LOCAL = r"(?:dalla mia musica|dal disco|in locale|dalla libreria)"

# One entry per routing step; the handle() flow is identical across languages.
# ``service`` is a template expanded per streaming service name.
PATTERNS = {
    "is_play": c(r"\b(?:metti|rimetti|riproduci|suona|fai\s+partire|voglio\s+ascoltare)\b"),
    "pause_explicit": c(r"\bin\s+pausa\b"),
    "pause": c(r"\b(pausa|ferma|stop)\b"),
    # Bare "play" always resumes, even though it is also a play verb.
    "resume_explicit": c(r"^play\s*$"),
    "resume": c(r"\b(riprendi|riparti|continua|play)\b"),
    "next": c(r"\b(success|prossim|avanti|salta)"),
    "prev": c(r"\b(precedent|indietro|torna)"),
    "vol_up": c(r"(alza|aumenta).{0,12}volume"),
    "vol_down": c(r"(abbassa|diminuisci).{0,12}volume"),
    # Loose forms that name no control: gated on is_play in the router, or
    # «metti Più Forte di Sempre» raised the volume instead of playing it.
    "vol_up_loose": c(r"pi[uù] forte"),
    "vol_down_loose": c(r"pi[uù] piano"),
    # Sleep timer: the captured tail must parse as a duration (see DURATIONS),
    # otherwise the phrase falls through to pause/play.
    # "pausa" belongs here too: «metti in pausa tra 30 minuti» used to reach
    # pause_explicit and pause immediately. The tail must still parse as a
    # duration, so a title can't be mistaken for a timer.
    "sleep": c(r"(?:spegni(?:ti)?|ferma(?:ti)?|stop|pausa)\b.{0,20}?"
               r"\b(?:tra|fra)\s+(.+)$"),
    "sleep_cancel": c(r"^(?:annulla|cancella|togli)\b.{0,15}"
                      r"(?:spegnimento|timer|sleep)"),
    "nowplaying": c(r"(cosa|che).{0,8}(suona|canzone|ascolt)"),
    # Queue management. Checked early in the router, ahead of the generic
    # play verbs, so "alla coda"/"dopo questa" never gets swallowed as part
    # of a title.
    "queue_add": c(r"\b(?:aggiungi|metti)\s+(.+?)\s+(?:alla|in)\s+coda\s*$"),
    "queue_insert": c(r"\bmetti\s+(.+?)\s+dopo\s+(?:questa|questo)"
                     r"(?:\s+canzone|\s+brano)?\s*$"),
    "queue_clear": c(r"^(?:svuota|pulisci|cancella)\s+la\s+coda\s*$"),
    "queue_list": c(r"(?:cosa|che).{0,4}(?:c['’]è|ce)\s+in\s+coda"
                    r"|coda\s+di\s+riproduzione"),
    # Favorites & radio (LMS core feature — see engine/actions.py).
    "favorites": c(r"\b(?:riproduci|metti|fai\s+partire)\s+(?:i\s+)?preferiti\b"),
    "radio": c(r"\bmetti\s+(?:la\s+)?radio\s+(.+)$"),
    "choose_number": c(r"(?:metti|scegli|voglio)?\s*(?:(?:la|il)\s+)?numero\s+([a-z0-9]+)\s*$"),
    # "la 2" and ordinals: "la seconda", "metti la seconda canzone"
    "choose_article": c(r"(?:metti|scegli|voglio)?\s*(?:la|il)\s+([a-z0-9]+)"
                        r"(?:\s+(?:canzone|brano|opzione))?\s*$"),
    "local_prefix": c(rf"{_LOCAL}\s+(?:metti\s+|riproduci\s+)?(.+)$"),
    "local_suffix": c(rf"(?:metti|riproduci|suona)\s+(.+?)\s+{_LOCAL}\s*$"),
    "service": r"(?:da {s}|su {s}|con {s})\s+(?:metti\s+|riproduci\s+)?(.+)$",
    "albums_list": c(r"(?:quali|che).{0,12}album.{0,4}di\s+(.+)$"),
    "toptracks": c(r"(?:quali.{0,10}brani|top tracks|brani.{0,15}ascoltati).*?di\s+(.+)$"),
    "name_pick": c(r"(?:(?:voglio\s+ascoltare|fai\s+partire|metti|scegli|riproduci|suona|voglio)\s+)?(.+)$"),
    "album": c(r"(?:metti|riproduci|fai partire)\s+l['’]?\s*album\s+(.+)$"),
    "playlist": c(r"(?:metti|riproduci|fai partire)\s+la\s+playlist\s+(.+)$"),
    # Plural only ("canzoni/brani"): "metti la canzone del sole" is a song
    # title (Battisti), not an artist request.
    "artist": c(r"(?:metti|riproduci|fai partire)\s+"
                r"(?:(?:la\s+)?musica\s+(?:di|dei|degli|delle|del|della|dell['’])"
                r"|l['’]?\s*artista"
                r"|(?:tutte\s+le\s+|le\s+|i\s+)?(?:canzoni|brani)\s+"
                r"(?:di|dei|degli|delle|del|della|dell['’]))\s+(.+)$"),
    "generic_play": c(r"(?:riproduci|metti|suona|fai partire|voglio ascoltare)\s+(.+)$"),
    # Kid-safe: anchored on the verb at string start, so a title containing
    # the word ("metti Block Rockin' Beats") still routes as a play.
    "block_add": c(r"^blocca\s+(.+)$"),
    "block_remove": c(r"^sblocca\s+(.+)$"),
    "block_list": c(r"^(?:(?:quali|che)\s+(?:brani|canzoni)\s+sono\s+bloccat|"
                    r"cosa\s+(?:è|e)\s+bloccat|lista\s+(?:dei\s+)?bloccat)"),
}
