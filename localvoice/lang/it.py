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

# Spoken tail -> mood key (the table in engine/moods.py). Keys are written
# already normalized — lowercase, no accents, no apostrophes ("damore", not
# "d'amore") — because the lookup is a dict hit on the normalized tail, and
# tests/test_moods.py enforces it. The match is on the WHOLE tail: a partial
# one is exactly how a song title would become a mood.
MOOD_WORDS = {
    # relax
    "rilassante": "relax", "rilassanti": "relax", "rilassata": "relax",
    "rilassato": "relax", "tranquillo": "relax", "tranquilla": "relax",
    "calmo": "relax", "calma": "relax", "chill": "relax", "relax": "relax",
    "per rilassarmi": "relax", "per rilassarsi": "relax",
    "distensiva": "relax", "soft": "relax",
    # sleep
    "per dormire": "sleep", "per addormentarmi": "sleep",
    "per prendere sonno": "sleep", "per la notte": "sleep",
    "della buonanotte": "sleep", "per far dormire i bambini": "sleep",
    # dinner
    "per cena": "dinner", "per la cena": "dinner", "a cena": "dinner",
    "da cena": "dinner", "per mangiare": "dinner", "per pranzo": "dinner",
    "per il pranzo": "dinner", "per la tavola": "dinner",
    # party
    "per la festa": "party", "per una festa": "party", "da festa": "party",
    "festa": "party", "per ballare": "party", "per fare festa": "party",
    "da ballare": "party",
    # happy
    "allegro": "happy", "allegra": "happy", "allegre": "happy",
    "di buonumore": "happy", "buonumore": "happy", "spensierata": "happy", "spensierato": "happy",
    "solare": "happy", "che tiri su": "happy", "divertente": "happy",
    # energetic
    "energico": "energetic", "energica": "energetic", "carico": "energetic",
    "carica": "energetic", "per allenarmi": "energetic",
    "per correre": "energetic", "per la palestra": "energetic",
    "per fare sport": "energetic", "grintoso": "energetic",
    "grintosa": "energetic", "movimentata": "energetic",
    # focus
    "per studiare": "focus", "per lavorare": "focus",
    "per concentrarmi": "focus", "per leggere": "focus",
    "da studio": "focus", "per la concentrazione": "focus",
    # background
    "di sottofondo": "background", "in sottofondo": "background",
    "come sottofondo": "background", "sottofondo": "background",
    "leggera": "background", "leggero": "background",
    "di accompagnamento": "background", "accompagnamento": "background",
    "di atmosfera": "background", "atmosfera": "background",
    # romantic
    "romantico": "romantic", "romantica": "romantic", "damore": "romantic",
    "per una serata romantica": "romantic", "per innamorati": "romantic",
    "sensuale": "romantic",
    # melancholy
    "malinconico": "melancholy", "malinconica": "melancholy",
    "triste": "melancholy", "nostalgico": "melancholy",
    "nostalgica": "melancholy", "struggente": "melancholy",
    "per piangere": "melancholy",
    # morning
    "per la colazione": "morning", "per svegliarmi": "morning",
    "del mattino": "morning", "mattutina": "morning",
    "per la mattina": "morning", "per iniziare la giornata": "morning",
    # genre-shaped
    "classica": "classical", "classico": "classical",
    "musica classica": "classical", "lirica": "classical",
    "operistica": "classical",
    "jazz": "jazz", "jazzistica": "jazz",
    "rock": "rock", "rock duro": "rock", "hard rock": "rock",
    "blues": "blues",
    # Metadata axes (T2.4-bis). Adjectives and phrases only, never the bare
    # noun: «natale» on its own is «Bianco Natale» and «estate» is Vivaldi and
    # De André at once, and every entry here widens the set of tails that stop
    # being a title. "di natale" is deliberately absent and would be dead
    # anyway — the pattern eats the "di", so «metti musica di natale» arrives
    # here as the bare "natale", which is exactly the entry we refuse to have.
    "natalizia": "christmas", "natalizie": "christmas",
    "natalizio": "christmas", "per natale": "christmas",
    "strumentale": "instrumental", "strumentali": "instrumental",
    "senza parole": "instrumental",
    "estivo": "summer", "estiva": "summer", "da spiaggia": "summer",
    # Decades. A bare "anni ottanta" needs the marker noun in front of it to
    # get here at all, which is what keeps «metti Anni 60» a search.
    "anni sessanta": "sixties", "anni 60": "sixties",
    "degli anni sessanta": "sixties", "dagli anni sessanta": "sixties",
    "degli anni 60": "sixties", "dagli anni 60": "sixties",
    "anni settanta": "seventies", "anni 70": "seventies",
    "degli anni settanta": "seventies", "dagli anni settanta": "seventies",
    "degli anni 70": "seventies", "dagli anni 70": "seventies",
    "anni ottanta": "eighties", "anni 80": "eighties",
    "degli anni ottanta": "eighties", "dagli anni ottanta": "eighties",
    "degli anni 80": "eighties", "dagli anni 80": "eighties",
    "anni novanta": "nineties", "anni 90": "nineties",
    "degli anni novanta": "nineties", "dagli anni novanta": "nineties",
    "degli anni 90": "nineties", "dagli anni 90": "nineties",
}
