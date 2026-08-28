"""French mood vocabulary — the spoken tail of a vague request, mapped onto the
keys in ``engine/moods.py``. See ``moods_it.py`` for the shape and the rules.

Written already normalized (lowercase, no accents, apostrophes DELETED rather
than spaced), because the lookup is a dict hit on ``_normalize``d text: an
entry spelled «détendu» or «d'ambiance» would simply never match, silently.
``tests/test_moods.py`` asserts it rather than trusting the comment.

French is the longest of these tables and the grammar is why: an adjective
agrees, so «relaxant» is also «relaxante», «relaxants» and «relaxantes», and
all four are what somebody says.
"""

from __future__ import annotations

MOOD_WORDS = {
    # -- relax
    "relaxant": "relax", "relaxante": "relax", "relaxants": "relax",
    "relaxantes": "relax", "calme": "relax", "tranquille": "relax",
    "douce": "relax", "doux": "relax", "zen": "relax", "chill": "relax",
    "cool": "relax", "pour se detendre": "relax",
    "pour me detendre": "relax", "apaisante": "relax", "apaisant": "relax",
    "decontractee": "relax", "decontracte": "relax", "posee": "relax",
    "reposante": "relax",
    # -- sleep
    "pour dormir": "sleep", "pour sendormir": "sleep",
    "pour mendormir": "sleep", "pour aller dormir": "sleep",
    "pour la nuit": "sleep", "du soir": "sleep", "pour la sieste": "sleep",
    "pour faire dormir les enfants": "sleep",
    # -- dinner
    "pour diner": "dinner", "pour le diner": "dinner", "au diner": "dinner",
    "pour un diner": "dinner", "pour manger": "dinner",
    "pour le repas": "dinner", "pour dejeuner": "dinner",
    "pour le dejeuner": "dinner", "de table": "dinner",
    # -- party
    "pour la fete": "party", "pour une fete": "party", "de fete": "party",
    "fete": "party", "pour danser": "party", "pour faire la fete": "party",
    "festive": "party", "festif": "party", "dansante": "party",
    "pour la soiree": "party", "pour lapero": "party",
    # -- happy
    "joyeuse": "happy", "joyeux": "happy", "gaie": "happy", "gai": "happy",
    "de bonne humeur": "happy", "qui met de bonne humeur": "happy",
    "enjouee": "happy", "petillante": "happy", "positive": "happy",
    "souriante": "happy",
    # -- energetic
    "energique": "energetic", "energiques": "energetic",
    "pour le sport": "energetic", "pour faire du sport": "energetic",
    "pour courir": "energetic", "pour la salle": "energetic",
    "pour mentrainer": "energetic", "pour lentrainement": "energetic",
    "punchy": "energetic", "entrainante": "energetic",
    "dynamique": "energetic", "qui bouge": "energetic",
    # -- focus
    "pour travailler": "focus", "pour bosser": "focus",
    "pour etudier": "focus", "pour reviser": "focus", "pour lire": "focus",
    "pour me concentrer": "focus", "pour la concentration": "focus",
    "de concentration": "focus",
    # -- background
    "de fond": "background", "en fond": "background",
    "en fond sonore": "background", "fond sonore": "background",
    "dambiance": "background", "ambiance": "background",
    "discrete": "background", "legere": "background", "leger": "background",
    "en arriere plan": "background",
    # -- romantic
    "romantique": "romantic", "romantiques": "romantic",
    "damour": "romantic", "pour une soiree romantique": "romantic",
    "pour les amoureux": "romantic", "sensuelle": "romantic",
    "sensuel": "romantic", "pour un diner aux chandelles": "romantic",
    # -- melancholy
    "triste": "melancholy", "tristes": "melancholy",
    "melancolique": "melancholy", "melancoliques": "melancholy",
    "nostalgique": "melancholy", "nostalgiques": "melancholy",
    "pour pleurer": "melancholy", "pour un jour de pluie": "melancholy",
    "dechirante": "melancholy",
    # -- morning
    "pour le matin": "morning", "du matin": "morning", "matinale": "morning",
    "pour le petit dejeuner": "morning", "pour me reveiller": "morning",
    "pour bien commencer la journee": "morning",
    # -- genres, which are moods here because that is how they are asked for
    "classique": "classical", "classiques": "classical",
    "musique classique": "classical", "de lopera": "classical",
    "opera": "classical", "baroque": "classical", "lyrique": "classical",
    "jazz": "jazz", "du jazz": "jazz", "jazzy": "jazz",
    "rock": "rock", "rock dur": "rock", "hard rock": "rock",
    "blues": "blues", "bluesy": "blues",
    # -- the metadata axes. Adjectives and «pour …» phrases, never the bare
    # noun: «Noël» is *Petit Papa Noël* and «Été» is a title too, and every
    # entry here widens the set of tails that stop being one.
    #
    # There is no "noel" for the same reason moods_it.py has no "natale" —
    # and note that "de noel" below can never be reached either, because the
    # mood pattern eats the «de»: «mets de la musique de Noël» arrives here
    # as the bare "noel". It is kept as the label of what the phrase means,
    # and «pour Noël» is the form that works.
    "de noel": "christmas", "pour noel": "christmas",
    "pour les fetes": "christmas", "de fin dannee": "christmas",
    "instrumentale": "instrumental", "instrumental": "instrumental",
    "instrumentales": "instrumental", "sans paroles": "instrumental",
    "sans chant": "instrumental",
    "estivale": "summer", "estival": "summer", "de lete": "summer",
    "pour la plage": "summer", "ensoleillee": "summer",
    # Decades. Spaced and never hyphenated: _normalize turns every hyphen
    # into a space, so a hyphenated key could not be hit. A bare «années 80»
    # still needs the marker noun in front of it to get here at all, which is
    # what keeps «mets Années 80» a search.
    "annees soixante": "sixties", "des annees soixante": "sixties",
    "annees 60": "sixties", "des annees 60": "sixties",
    "annees soixante dix": "seventies", "des annees soixante dix": "seventies",
    "annees 70": "seventies", "des annees 70": "seventies",
    "annees quatre vingt": "eighties", "des annees quatre vingt": "eighties",
    "annees 80": "eighties", "des annees 80": "eighties",
    "annees quatre vingt dix": "nineties",
    "des annees quatre vingt dix": "nineties",
    "annees 90": "nineties", "des annees 90": "nineties",
}
