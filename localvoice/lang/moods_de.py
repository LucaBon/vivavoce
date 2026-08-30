"""German spoken vocabulary for vague requests — the table ``de.py`` exposes
as ``MOOD_WORDS``. See ``moods_it.py`` for why it lives beside the patterns
rather than in them.
"""

from __future__ import annotations

# Spoken tail -> mood key. Keys are written already NORMALIZED — lowercase,
# umlauts folded, ``ß`` written ``ss`` — because the lookup is a dict hit on
# the normalized tail (tests/test_moods.py enforces it). «fröhlich» is spelled
# "frohlich" here and still matches what the recogniser wrote. The match is on
# the WHOLE tail: a partial one is how a song title becomes a mood.
MOOD_WORDS = {
    # relax
    "entspannend": "relax", "entspannende": "relax", "entspannendes": "relax",
    "entspannender": "relax", "entspannten": "relax", "entspannt": "relax",
    "ruhig": "relax", "ruhige": "relax", "ruhiges": "relax", "ruhiger": "relax",
    "zum entspannen": "relax", "chillige": "relax", "chillig": "relax", "chilliges": "relax",
    "chill": "relax", "gemutlich": "relax", "gemutliche": "relax",
    "gemutliches": "relax", "sanft": "relax", "sanfte": "relax",
    "sanftes": "relax",
    # sleep
    "zum einschlafen": "sleep", "zum schlafen": "sleep",
    "fur die nacht": "sleep", "zum schlafengehen": "sleep",
    "einschlafmusik": "sleep", "schlafmusik": "sleep",
    "fur den schlaf": "sleep",
    # dinner
    "zum essen": "dinner", "zum abendessen": "dinner",
    "fur das abendessen": "dinner", "furs abendessen": "dinner",
    "fur das essen": "dinner", "furs essen": "dinner",
    "zum mittagessen": "dinner", "zum dinner": "dinner",
    # party
    "fur die party": "party", "fur eine party": "party", "party": "party",
    "zum feiern": "party", "zum tanzen": "party", "partymusik": "party",
    "tanzbare": "party", "tanzbar": "party",
    # happy
    "frohlich": "happy", "frohliche": "happy", "frohliches": "happy",
    "gute laune": "happy", "fur gute laune": "happy", "gutelaunemusik": "happy",
    "lustig": "happy", "lustige": "happy", "lustiges": "happy",
    "heiter": "happy",
    "heitere": "happy", "heiteres": "happy",
    "beschwingt": "happy", "beschwingte": "happy", "beschwingtes": "happy",
    # energetic
    "energiegeladen": "energetic", "energiegeladene": "energetic",
    "energiegeladenes": "energetic",
    "energisch": "energetic", "energische": "energetic",
    "energisches": "energetic",
    "zum sport": "energetic", "furs training": "energetic",
    "fur das training": "energetic", "zum joggen": "energetic",
    "zum laufen": "energetic", "fur das fitnessstudio": "energetic",
    "furs fitnessstudio": "energetic", "schwungvoll": "energetic",
    # focus
    "zum lernen": "focus", "zum arbeiten": "focus", "zum lesen": "focus",
    "zum konzentrieren": "focus", "fur die konzentration": "focus",
    "furs lernen": "focus", "furs arbeiten": "focus",
    # background
    "im hintergrund": "background", "als hintergrund": "background",
    "hintergrundmusik": "background", "hintergrund": "background",
    "nebenbei": "background", "leise": "background", "unaufdringlich": "background",
    "leichte": "background", "zum nebenbeihoren": "background",
    # romantic
    "romantisch": "romantic", "romantische": "romantic",
    "romantisches": "romantic", "fur ein date": "romantic",
    "fur verliebte": "romantic", "zum verlieben": "romantic",
    "sinnlich": "romantic", "sinnliche": "romantic", "sinnliches": "romantic",
    # melancholy
    "traurig": "melancholy", "traurige": "melancholy",
    "trauriges": "melancholy", "melancholisch": "melancholy",
    "melancholische": "melancholy", "melancholisches": "melancholy",
    "nachdenklich": "melancholy",
    "nachdenkliche": "melancholy", "nachdenkliches": "melancholy",
    "wehmutig": "melancholy", "wehmutige": "melancholy",
    "zum weinen": "melancholy", "bittersuss": "melancholy",
    # morning
    "fur den morgen": "morning", "zum aufwachen": "morning",
    "zum fruhstuck": "morning", "furs fruhstuck": "morning",
    "morgenmusik": "morning", "am morgen": "morning",
    "fur den start in den tag": "morning",
    # genre-shaped
    "klassik": "classical", "klassische": "classical",
    "klassisches": "classical",
    "klassische musik": "classical", "klassisch": "classical",
    "oper": "classical", "barock": "classical",
    "jazz": "jazz", "jazzige": "jazz", "jazzig": "jazz", "jazziges": "jazz",
    "rock": "rock", "rockig": "rock", "rockige": "rock", "rockiges": "rock",
    "harter rock": "rock",
    "blues": "blues", "bluesig": "blues", "bluesige": "blues",
    "bluesiges": "blues",
    # Metadata axes (T2.4-bis). Adjectives and phrases, never the bare noun:
    # «Weihnachten» and «Sommer» are both song titles a German library really
    # has, and every entry here widens the set of tails that stop being one.
    "weihnachtlich": "christmas", "weihnachtliche": "christmas",
    "weihnachtliches": "christmas", "weihnachtsmusik": "christmas",
    "zu weihnachten": "christmas",
    "fur weihnachten": "christmas",
    "instrumental": "instrumental", "instrumentale": "instrumental",
    "instrumentales": "instrumental",
    "ohne gesang": "instrumental", "ohne worte": "instrumental",
    "sommerlich": "summer", "sommerliche": "summer",
    "sommerliches": "summer", "sommermusik": "summer",
    # Decades. A bare «achtziger» needs the marker noun in front of it to get
    # here at all, which is what keeps «spiel Achtziger» a search.
    "sechziger": "sixties", "sechziger jahre": "sixties",
    "aus den sechzigern": "sixties", "aus den 60ern": "sixties",
    "60er": "sixties", "die 60er": "sixties",
    "siebziger": "seventies", "siebziger jahre": "seventies",
    "aus den siebzigern": "seventies", "aus den 70ern": "seventies",
    "70er": "seventies", "die 70er": "seventies",
    "achtziger": "eighties", "achtziger jahre": "eighties",
    "aus den achtzigern": "eighties", "aus den 80ern": "eighties",
    "80er": "eighties", "die 80er": "eighties",
    "neunziger": "nineties", "neunziger jahre": "nineties",
    "aus den neunzigern": "nineties", "aus den 90ern": "nineties",
    "90er": "nineties", "die 90er": "nineties",

    # -- die Nuancen (T2.6) ---------------------------------------------------
    # «traurig» und «frohlich» waren je ein einziger Eimer. Eine Nuance bekommt
    # nur dann einen eigenen Schlussel, wenn sie in mood_table.py woanders
    # landet; ein Synonym, das wieder auf `melancholy` fallt, bleibt oben.
    # «fur einen regentag» ist aus genau diesem Grund umgezogen.
    "aufmunternd": "uplifting", "aufmunternde": "uplifting",
    "aufmunterndes": "uplifting", "zum aufmuntern": "uplifting",
    "aufbauend": "uplifting", "aufbauende": "uplifting",
    "optimistisch": "uplifting", "optimistische": "uplifting",
    "hoffnungsvoll": "uplifting",
    "euphorisch": "euphoric", "euphorische": "euphoric",
    "euphorisches": "euphoric", "zum abgehen": "euphoric",
    "zum ausrasten": "euphoric", "mitreissend": "euphoric",
    "mitreissende": "euphoric",
    "traumerisch": "dreamy", "traumerische": "dreamy",
    "traumerisches": "dreamy", "vertraumt": "dreamy",
    "vertraumte": "dreamy", "spharisch": "dreamy",
    "schwebend": "dreamy", "schwebende": "dreamy",
    "fur ein gebrochenes herz": "heartbreak",
    "nach einer trennung": "heartbreak", "bei liebeskummer": "heartbreak",
    "fur liebeskummer": "heartbreak", "herzschmerz": "heartbreak",
    "trennungsschmerz": "heartbreak",
    "nostalgisch": "nostalgic", "nostalgische": "nostalgic",
    "nostalgisches": "nostalgic", "von fruher": "nostalgic",
    "aus alten zeiten": "nostalgic", "retro": "nostalgic",
    "vintage": "nostalgic", "die erinnerungen weckt": "nostalgic",
    "duster": "dark", "dustere": "dark", "dusteres": "dark",
    "dunkel": "dark", "dunkle": "dark", "dunkles": "dark",
    "finster": "dark", "finstere": "dark", "bedrohlich": "dark",
    "dark": "dark",

    # -- die Situationen (T2.6) -----------------------------------------------
    "fur kinder": "kids", "fur die kinder": "kids",
    "die kindern gefallt": "kids", "kindgerecht": "kids",
    "kindermusik": "kids", "fur die kleinen": "kids",
    "zum mitsingen": "singalong", "die man mitsingen kann": "singalong",
    "zum mitgrolen": "singalong", "mitsingmusik": "singalong",
    "zum zusammen singen": "singalong",
    "bekannt": "crowdpleaser", "bekannte": "crowdpleaser",
    "bekanntes": "crowdpleaser", "beruhmt": "crowdpleaser",
    "beruhmte": "crowdpleaser", "die allen gefallt": "crowdpleaser",
    "die jeder kennt": "crowdpleaser",
    "die grossten hits": "crowdpleaser", "grosste hits": "crowdpleaser",
    "zum kochen": "cooking", "beim kochen": "cooking",
    "furs kochen": "cooking", "fur die kuche": "cooking",
    "fur einen regentag": "rainy", "fur regentage": "rainy",
    "wenn es regnet": "rainy", "bei regen": "rainy",
    "regnerisch": "rainy",
    "furs autofahren": "driving", "zum autofahren": "driving",
    "fur die autofahrt": "driving", "fur die fahrt": "driving",
    "fur den roadtrip": "driving", "im auto": "driving",
    "lang": "longform", "lange": "longform", "langes": "longform",
    "die lange dauert": "longform",
    "die nicht gleich vorbei ist": "longform",
    "episch": "longform", "epische": "longform",
    "zum meditieren": "meditation", "fur die meditation": "meditation",
    "zum yoga": "meditation", "furs yoga": "meditation",
    "meditativ": "meditation", "meditative": "meditation",

    # -- die fehlenden Genres (T2.6) ------------------------------------------
    # Vier gab es, zwolf nicht — «spiel ein bisschen Reggae» ging deshalb als
    # TITELsuche los. Der Marker ist es, der das nackte Wort ungefahrlich
    # macht: das Muster ist verankert und braucht seinen Marker, «spiel Soul»
    # kommt hier also nie an, «spiel etwas Soul» schon.
    "pop": "pop",
    "soul": "soul", "soulig": "soul",
    "funk": "funk", "funkig": "funk",
    "reggae": "reggae", "ska": "reggae", "dub": "reggae",
    "metal": "metal", "heavy metal": "metal", "metallisch": "metal",
    "punk": "punk",
    "elektronisch": "electronic", "elektronische": "electronic",
    "elektro": "electronic", "techno": "electronic", "house": "electronic",
    "hip hop": "hiphop", "rap": "hiphop",
    "country": "country",
    "folk": "folk", "folkmusik": "folk",
    "latin": "latin", "latino": "latin", "salsa": "latin",
    "weltmusik": "world", "world music": "world",

    # -- die fehlenden Jahrzehnte (T2.6) --------------------------------------
    "funfziger": "fifties", "funfziger jahre": "fifties",
    "aus den funfzigern": "fifties", "aus den 50ern": "fifties",
    "50er": "fifties", "die 50er": "fifties",
    "zweitausender": "noughties", "die zweitausender": "noughties",
    "2000er": "noughties", "die 2000er": "noughties",
    "aus den 2000ern": "noughties",
    "2010er": "tens", "die 2010er": "tens", "aus den 2010ern": "tens",
}
