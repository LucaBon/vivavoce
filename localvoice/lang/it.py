"""Italian language pack — the reference implementation of the contract in
``base.py``. Patterns moved verbatim from the pre-split router."""

from __future__ import annotations

from .base import c
# Spoken tail -> mood key: a word list, not grammar, so it has a module of
# its own. Imported (not just referenced) because the pack contract in
# ``base.py`` asks the *pack* for MOOD_WORDS.
from .moods_it import MOOD_WORDS  # noqa: F401
# Spoken numbers and durations, same reasoning — see numbers_it.py.
from .numbers_it import (  # noqa: F401
    DURATIONS, MINUTE_WORDS, NUM_WORDS, ORDINAL_WORDS)

CODE = "it"
# The closed word lists these patterns are built from.
from .words_it import _LOCAL  # noqa: F401

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
    # Vague requests (see engine/moods.py). Three things have to hold at once,
    # and the third was learned the hard way — a marker noun plus a mood word
    # is NOT a request to play anything:
    #   1. the phrase is ANCHORED at the start. Without ^, «ferma la musica
    #      classica» carried a marker ("la musica") and a mood word
    #      ("classica"), so a phrase asking to STOP the music started it — and
    #      the step sits above the transport block, so it won a pause that used
    #      to work. Same for «togli / spegni / basta con / non voglio …», and
    #      for «blocca musica triste», which on a build without kid-safe played
    #      exactly what a parent was trying to forbid;
    #   2. the marker noun follows immediately, which is what keeps an
    #      identified request identified: «metti l'album Musica Leggera» and
    #      «riproduci la playlist Musica Rilassante» name what they want, and
    #      "l'album"/"la playlist" is not a marker, so they never get here;
    #   3. the tail has to BE a whole MOOD_WORDS entry. «metti la musica di
    #      Vasco Rossi» clears 1 and 2 and fails here, which is the point.
    "mood": c(r"^(?:(?:metti|mettimi|rimetti|riproduci|suona|fai\s+partire"
              r"|voglio\s+ascoltare|vorrei\s+ascoltare)\s+(?:su\s+)?)?"
              r"(?:qualcosa|della\s+musica|delle\s+canzoni|la\s+musica"
              r"|musica|canzoni|un\s+po['’]?|del|dello|dell['’]|dei)"
              # Only "di" is eaten, never "da": half the vocabulary is a "da"
              # phrase that means something as a unit («musica da cena», «da
              # ballare»), and swallowing the preposition left the table
              # looking for "cena" — a word nobody says on its own.
              r"(?:\s+di)?\s+(.+)$"),
    # "un'altra" only means anything while a mood is open (the router gates
    # it), so it can't shadow a pick or a transport command the rest of the
    # time. It has to be the WHOLE phrase (politeness aside): left as a prefix
    # it caught «cambia canzone» and «un'altra canzone», which mean
    # skip-this-track — the very thing the comment claimed to be excluding by
    # leaving «la prossima» out.
    "mood_another": c(r"^(?:no[,\s]+)?(?:"
                      r"un['\u2019]?\s*altra|un['\u2019]?\s*altro"
                      r"|qualcos['\u2019]?\s*altro"
                      r"|cambia(?:la|\s+musica|\s+genere)?"
                      r"|prova\s+un['\u2019]?\s*altra"
                      r")(?:\s+(?:per\s+favore|grazie|dai))?\s*$"),
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
