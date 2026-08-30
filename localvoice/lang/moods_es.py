"""Spanish mood vocabulary — the spoken tail of a vague request, mapped onto
the keys in ``engine/moods.py``. See ``moods_it.py`` for the shape and the
rules.

Written already normalized (lowercase, no accents — and ``ñ`` folds to ``n``,
so it is "anos ochenta" and "navidena" here), because the lookup is a dict hit
on ``_normalize``d text: an entry spelled «relajánte» or «años 80» would simply
never match, silently. ``tests/test_moods.py`` asserts it rather than trusting
this comment.

Spanish agreement is what makes this table longer than the English one and
shorter than the French: an adjective agrees in gender and number, so
«tranquilo» is also «tranquila», «tranquilos» and «tranquilas» — but half the
useful words end in -e or -ante and agree in number only, which French's
«relaxant/relaxante/relaxants/relaxantes» does not get to do.
"""

from __future__ import annotations

MOOD_WORDS = {
    # -- relax
    "relajante": "relax", "relajantes": "relax", "relajada": "relax",
    "relajado": "relax", "tranquilo": "relax", "tranquila": "relax",
    "tranquilita": "relax", "calmada": "relax", "calmado": "relax",
    "suave": "relax", "chill": "relax", "para relajarme": "relax",
    "para relajarse": "relax", "para descansar": "relax",
    "para desconectar": "relax", "sosegada": "relax",
    # -- sleep
    "para dormir": "sleep", "para dormirme": "sleep",
    "para conciliar el sueno": "sleep", "para la noche": "sleep",
    "de noche": "sleep", "para acostarse": "sleep",
    "para que duerman los ninos": "sleep", "nocturna": "sleep",
    # -- dinner
    "para cenar": "dinner", "para la cena": "dinner", "de cena": "dinner",
    "para comer": "dinner", "para la comida": "dinner",
    "para el almuerzo": "dinner", "para la mesa": "dinner",
    "de sobremesa": "dinner",
    # -- party
    "para la fiesta": "party", "para una fiesta": "party",
    "de fiesta": "party", "fiesta": "party", "para bailar": "party",
    "marchosa": "party", "bailable": "party", "para el bote": "party",
    # -- happy
    "alegre": "happy", "alegres": "happy", "animada": "happy",
    "animado": "happy", "de buen humor": "happy", "divertida": "happy",
    "positiva": "happy", "marchosa alegre": "happy",
    # -- energetic
    "energica": "energetic", "energico": "energetic",
    "marchosa para entrenar": "energetic", "para entrenar": "energetic",
    "para correr": "energetic", "para el gimnasio": "energetic",
    "para hacer deporte": "energetic", "movida": "energetic",
    "potente": "energetic", "con marcha": "energetic",
    "para darlo todo": "energetic",
    # -- focus
    "para estudiar": "focus", "para trabajar": "focus",
    "para concentrarme": "focus", "para leer": "focus",
    "de estudio": "focus", "para la concentracion": "focus",
    # -- background
    "de fondo": "background", "para poner de fondo": "background",
    "como fondo": "background", "ambiental": "background",
    "de ambiente": "background", "ambiente": "background",
    "ligera": "background", "ligero": "background",
    "para acompanar": "background", "discreta": "background",
    # -- romantic
    "romantica": "romantic", "romantico": "romantic", "de amor": "romantic",
    "para una cena romantica": "romantic", "para enamorados": "romantic",
    "sensual": "romantic",
    # -- melancholy
    "melancolica": "melancholy", "melancolico": "melancholy",
    "triste": "melancholy", "tristes": "melancholy",
    "desgarradora": "melancholy", "agridulce": "melancholy",
    "para llorar": "melancholy", "para penas": "melancholy",
    # -- morning
    "para desayunar": "morning", "para despertarme": "morning",
    "de manana": "morning", "matutina": "morning",
    "para la manana": "morning", "para empezar el dia": "morning",
    # -- genre-shaped
    "clasica": "classical", "clasico": "classical",
    "musica clasica": "classical", "opera": "classical",
    "operistica": "classical",
    "jazz": "jazz", "jazzistica": "jazz",
    "rock": "rock", "rock duro": "rock", "hard rock": "rock",
    "blues": "blues",
    # Metadata axes. Adjectives and phrases only, never the bare noun:
    # «navidad» on its own is «Blanca Navidad» and «verano» is half the
    # catalogue, and every entry here widens the set of tails that stop being
    # a title. "de navidad" is deliberately absent and would be dead anyway —
    # the pattern eats the "de", so «pon música de navidad» arrives here as
    # the bare "navidad", which is exactly the entry we refuse to have.
    # «para navidad» is the form that works. moods_it.py and moods_fr.py
    # record the same shape for «di natale» and «de Noël».
    "navidena": "christmas", "navidenas": "christmas",
    "navideno": "christmas", "para navidad": "christmas",
    "instrumental": "instrumental", "instrumentales": "instrumental",
    "sin letra": "instrumental", "sin voces": "instrumental",
    "veraniega": "summer", "veraniego": "summer", "de playa": "summer",
    # Decades. A bare "anos ochenta" needs the marker noun in front of it to
    # get here at all, which is what keeps «pon Años 60» a search.
    #
    # The article is HERE and the preposition is not, and that is not a style
    # choice: the mood pattern eats «de» and nothing else, so «pon música de
    # los años 80» arrives as "los anos 80" and «pon música años 80» as "anos
    # 80". An entry written "de los anos 80" would be dead the day it was
    # typed — silently, which is the worst way for a vocabulary entry to be
    # wrong. Four spellings per decade for that reason: with the article and
    # without, spelled and in digits.
    "anos sesenta": "sixties", "anos 60": "sixties",
    "los anos sesenta": "sixties", "los anos 60": "sixties",
    "los sesenta": "sixties", "los 60": "sixties",
    "anos setenta": "seventies", "anos 70": "seventies",
    "los anos setenta": "seventies", "los anos 70": "seventies",
    "los setenta": "seventies", "los 70": "seventies",
    "anos ochenta": "eighties", "anos 80": "eighties",
    "los anos ochenta": "eighties", "los anos 80": "eighties",
    "los ochenta": "eighties", "los 80": "eighties",
    "anos noventa": "nineties", "anos 90": "nineties",
    "los anos noventa": "nineties", "los anos 90": "nineties",
    "los noventa": "nineties", "los 90": "nineties",

    # -- los matices (T2.6) ---------------------------------------------------
    # «triste» y «alegre» eran una sola casilla cada uno. Un matiz solo merece
    # clave propia si acaba en otro sitio de mood_table.py; un sinonimo que
    # vuelve a caer en `melancholy` se queda en el bloque de arriba. Por esa
    # regla se han mudado «nostalgica» y las tres formas de «animar»: pedir
    # que te levanten el animo nunca fue lo mismo que pedir algo alegre.
    "que anime": "uplifting", "que me anime": "uplifting",
    "para animarme": "uplifting",
    "optimista": "uplifting", "que levante el animo": "uplifting",
    "para levantar el animo": "uplifting", "esperanzadora": "uplifting",
    "alentadora": "uplifting",
    "euforica": "euphoric", "euforico": "euphoric",
    "desatada": "euphoric", "desatado": "euphoric",
    "explosiva": "euphoric", "explosivo": "euphoric",
    "que reviente": "euphoric",
    "sonadora": "dreamy", "sonador": "dreamy", "onirica": "dreamy",
    "onirico": "dreamy", "eterea": "dreamy", "etereo": "dreamy",
    "flotante": "dreamy",
    "para un corazon roto": "heartbreak", "de desamor": "heartbreak",
    "para el desamor": "heartbreak",
    "despues de una ruptura": "heartbreak",
    "para una ruptura": "heartbreak", "de despecho": "heartbreak",
    "nostalgica": "nostalgic", "nostalgico": "nostalgic",
    "de los viejos tiempos": "nostalgic", "de antes": "nostalgic",
    "que me recuerde": "nostalgic", "vintage": "nostalgic",
    "retro": "nostalgic",
    "oscura": "dark", "oscuro": "dark", "sombria": "dark",
    "sombrio": "dark", "tenebrosa": "dark", "tenebroso": "dark",
    "inquietante": "dark", "dark": "dark",

    # -- las situaciones (T2.6) -----------------------------------------------
    "para los ninos": "kids", "para ninos": "kids",
    "que guste a los ninos": "kids", "para los pequenos": "kids",
    "infantil": "kids", "para la familia": "kids",
    "para cantar": "singalong", "que se pueda cantar": "singalong",
    "para cantar juntos": "singalong",
    "que podamos cantar": "singalong", "para cantar todos": "singalong",
    "famosa": "crowdpleaser", "famoso": "crowdpleaser",
    "famosas": "crowdpleaser", "conocida": "crowdpleaser",
    "conocido": "crowdpleaser", "popular": "crowdpleaser",
    "que guste a todos": "crowdpleaser",
    "que le guste a todos": "crowdpleaser",
    "los grandes exitos": "crowdpleaser", "grandes exitos": "crowdpleaser",
    "para cocinar": "cooking", "mientras cocino": "cooking",
    "para la cocina": "cooking",
    "para un dia de lluvia": "rainy", "para los dias de lluvia": "rainy",
    "cuando llueve": "rainy", "para la lluvia": "rainy",
    "lluviosa": "rainy",
    "para el viaje": "driving", "para conducir": "driving",
    "para el coche": "driving", "en el coche": "driving",
    "para la carretera": "driving", "para viajar": "driving",
    "larga": "longform", "largo": "longform", "largas": "longform",
    "que dure": "longform", "que no se acabe enseguida": "longform",
    "epica": "longform", "epico": "longform",
    "para meditar": "meditation", "para la meditacion": "meditation",
    "de meditacion": "meditation", "para el yoga": "meditation",
    "meditativa": "meditation",

    # -- los generos que faltaban (T2.6) --------------------------------------
    # Habia cuatro y faltaban doce, asi que «pon un poco de reggae» salia como
    # busqueda de TITULO. El marcador es lo que hace inofensiva la palabra
    # desnuda: el patron esta anclado y exige su marcador, de modo que «pon
    # Soul» no llega nunca aqui y «pon un poco de soul» si.
    "pop": "pop",
    "soul": "soul",
    "funk": "funk", "funky": "funk",
    "reggae": "reggae", "ska": "reggae", "dub": "reggae",
    "metal": "metal", "heavy metal": "metal",
    "punk": "punk",
    "electronica": "electronic", "electronico": "electronic",
    "tecno": "electronic", "techno": "electronic", "house": "electronic",
    "hip hop": "hiphop", "rap": "hiphop",
    "country": "country",
    "folk": "folk",
    "latina": "latin", "latino": "latin", "salsa": "latin",
    "musica del mundo": "world", "world music": "world",

    # -- las decadas que faltaban (T2.6) --------------------------------------
    # Cuatro grafias por decada, por lo que explica el bloque de arriba: con
    # articulo y sin el, escrita y en digitos.
    "anos cincuenta": "fifties", "anos 50": "fifties",
    "los anos cincuenta": "fifties", "los anos 50": "fifties",
    "los cincuenta": "fifties", "los 50": "fifties",
    "anos dos mil": "noughties", "anos 2000": "noughties",
    "los anos dos mil": "noughties", "los anos 2000": "noughties",
    "los dos mil": "noughties", "los 2000": "noughties",
    "anos 2010": "tens", "los anos 2010": "tens", "los 2010": "tens",
}
