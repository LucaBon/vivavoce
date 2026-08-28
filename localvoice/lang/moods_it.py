"""Italian spoken vocabulary for vague requests — the table ``it.py`` exposes
as ``MOOD_WORDS``.

Split from the patterns because it is a different kind of thing: the patterns
are the grammar of a language, this is a word list, and it is the half T2.5
replaces with generated data (see ``engine/moods.py``). It is also the half
that grows — the size guard in ``tests/test_packaging.py`` is what said so
first, when the German pack went over on the strength of its vocabulary.
"""

from __future__ import annotations

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
