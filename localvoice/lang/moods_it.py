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
    "solare": "happy", "divertente": "happy", "gioiosa": "happy",
    "gioioso": "happy", "sbarazzina": "happy",
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
    "triste": "melancholy", "tristi": "melancholy",
    "struggente": "melancholy", "struggenti": "melancholy",
    "per piangere": "melancholy", "intimista": "melancholy",
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

    # -- the nuances (T2.6) ---------------------------------------------------
    # «triste» and «allegro» were one bucket each. These are the ways of being
    # sad and of being cheerful that resolve somewhere genuinely different in
    # mood_table.py; a synonym that lands back on `melancholy` or `happy`
    # belongs in the blocks above, not here.
    #
    # uplifting: not "cheerful" but "pick me up" — Gospel and Motown, where
    # `happy` is Ska and Funk.
    "che tiri su": "uplifting", "che mi tiri su": "uplifting",
    "che tiri su il morale": "uplifting",
    "che mi tiri su il morale": "uplifting",
    "che mi risollevi": "uplifting", "ottimista": "uplifting",
    "ottimistico": "uplifting", "incoraggiante": "uplifting",
    # euphoric. "a palla" is deliberately absent: it is how people ask for
    # VOLUME, and the one thing a mood must not quietly become is a
    # transport command.
    "euforico": "euphoric", "euforica": "euphoric",
    "scatenato": "euphoric", "scatenata": "euphoric",
    "che spacca": "euphoric", "adrenalinico": "euphoric",
    "adrenalinica": "euphoric", "esplosivo": "euphoric",
    "esplosiva": "euphoric",
    "sognante": "dreamy", "sognanti": "dreamy", "onirico": "dreamy",
    "onirica": "dreamy", "etereo": "dreamy", "eterea": "dreamy",
    "rarefatta": "dreamy", "rarefatto": "dreamy",
    "per un cuore infranto": "heartbreak",
    "da cuore infranto": "heartbreak",
    "per il cuore spezzato": "heartbreak",
    "per una delusione damore": "heartbreak",
    "dopo una delusione": "heartbreak",
    "per chi soffre damore": "heartbreak", "straziante": "heartbreak",
    "nostalgico": "nostalgic", "nostalgica": "nostalgic",
    "dei vecchi tempi": "nostalgic", "dei bei tempi": "nostalgic",
    "che mi faccia ricordare": "nostalgic", "di una volta": "nostalgic",
    "vintage": "nostalgic", "retro": "nostalgic", "amarcord": "nostalgic",
    "cupo": "dark", "cupa": "dark", "dark": "dark", "tenebroso": "dark",
    "tenebrosa": "dark", "oscuro": "dark", "oscura": "dark",
    "inquietante": "dark", "tetro": "dark", "tetra": "dark",

    # -- the situations (T2.6) ------------------------------------------------
    # The half of tools/mood_coverage.py's residue that was a missing mood
    # rather than a missing memory: these are phrases from the real corpus.
    #
    # Bare "bambini" stays out for the reason bare "natale" does — «metti la
    # playlist Bambini in Festa» is a name people give their own playlists.
    # Every entry here carries its preposition.
    "per i bambini": "kids", "per bambini": "kids",
    "che piaccia ai bambini": "kids",
    "che piaccia anche ai bambini": "kids",
    "per i piu piccoli": "kids", "da bambini": "kids",
    "adatta ai bambini": "kids",
    "da cantare": "singalong", "da cantare insieme": "singalong",
    "che si possa cantare": "singalong",
    "che si possa cantare insieme": "singalong",
    "da cantare tutti insieme": "singalong", "per cantare": "singalong",
    "cantabile": "singalong",
    "famoso": "crowdpleaser", "famosa": "crowdpleaser",
    "famose": "crowdpleaser", "famosi": "crowdpleaser",
    "che piaccia a tutti": "crowdpleaser",
    "che vada bene per tutti": "crowdpleaser",
    "che vada bene a tutti": "crowdpleaser",
    "i grandi successi": "crowdpleaser", "grandi successi": "crowdpleaser",
    "conosciuta": "crowdpleaser",
    "per cucinare": "cooking", "mentre cucino": "cooking",
    "per stare in cucina": "cooking", "da cucina": "cooking",
    "che mi faccia venire voglia di cucinare": "cooking",
    "per quando piove": "rainy", "per la pioggia": "rainy",
    "da pioggia": "rainy", "piovosa": "rainy",
    "da giornata di pioggia": "rainy", "per i giorni di pioggia": "rainy",
    "per il viaggio": "driving", "da viaggio": "driving",
    "per il viaggio in macchina": "driving",
    "per il viaggio in auto": "driving",
    "per viaggiare": "driving", "per la macchina": "driving",
    "da macchina": "driving", "per guidare": "driving",
    "da autostrada": "driving",
    # No leading "di" on any of these: the pattern eats it, so «qualcosa di
    # lungo» arrives here as the bare "lungo".
    "lungo": "longform", "lunghe": "longform", "lunghi": "longform",
    "che non finisca subito": "longform",
    "lungo che non finisca subito": "longform",
    "che duri un po": "longform",
    "epico": "longform", "epica": "longform", "epiche": "longform",
    "per meditare": "meditation", "per la meditazione": "meditation",
    "da meditazione": "meditation", "per lo yoga": "meditation",
    "da yoga": "meditation", "zen": "meditation",
    "per rilassare la mente": "meditation",

    # -- the genres that were missing (T2.6) ----------------------------------
    # Only classical/jazz/rock/blues were here, so «metti un po' di reggae»
    # fell through and was searched for as a TITLE. The marker is what makes
    # bare genre words safe: the pattern is anchored and needs its marker noun,
    # so «metti Soul» never reaches this table — only «metti un po' di soul»
    # does. Nothing here is a tail a title arrives on.
    "pop": "pop",
    "soul": "soul",
    "funk": "funk", "funky": "funk",
    "reggae": "reggae", "ska": "reggae",
    "metal": "metal", "heavy metal": "metal", "metallara": "metal",
    "punk": "punk",
    "elettronica": "electronic", "elettronico": "electronic",
    "techno": "electronic", "house": "electronic", "dance": "electronic",
    "hip hop": "hiphop", "hiphop": "hiphop", "rap": "hiphop",
    "country": "country",
    "folk": "folk", "popolare": "folk",
    "latina": "latin", "latino": "latin", "latinoamericana": "latin",
    "salsa": "latin",
    "etnica": "world", "world music": "world", "dal mondo": "world",
    "musica del mondo": "world",

    # -- the decades that were missing (T2.6) ---------------------------------
    "anni cinquanta": "fifties", "anni 50": "fifties",
    "degli anni cinquanta": "fifties", "dagli anni cinquanta": "fifties",
    "degli anni 50": "fifties", "dagli anni 50": "fifties",
    "anni duemila": "noughties", "anni 2000": "noughties",
    "degli anni duemila": "noughties", "dagli anni duemila": "noughties",
    "degli anni 2000": "noughties", "dagli anni 2000": "noughties",
    "anni zero": "noughties",
    "anni 2010": "tens", "degli anni 2010": "tens",
    "dagli anni 2010": "tens", "anni dieci": "tens",
    "degli anni dieci": "tens",
}
