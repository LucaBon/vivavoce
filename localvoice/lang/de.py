"""German language pack — see ``base.py`` for the contract.

Written against ``it.py`` and ``en.py``, not translated from them: German
puts the load-bearing word in a place neither of the other two does, and
three of those places decide whether a phrase routes at all.

**Separable verbs.** «mach die Musik an», «leg Time auf», «ich möchte Time
hören» all carry their verb in two pieces, with the title wedged between
them. A pattern that captures «(.+)$» after the verb swallows the particle
and searches for a song called "die musik an". So the separable forms live in
``generic_play_suffix`` — the same key English uses for "put Dark Side on" —
and ``generic_play`` deliberately does NOT list ``leg``/``mach``, or it would
match first and hand the particle on. The one that costs something: a title
that really ends in a particle («Wach auf») still loses it after those verbs.
It keeps it after ``spiel``/``starte``/``hör``, which is where it is actually
said.

**«mach» is not a play verb on its own.** It heads «mach lauter» (volume),
«mach aus» (stop) and «mach die Musik an» (play) alike, so ``is_play`` asks
for the particle too — ``mach … an`` — and the volume and stop forms stay
reachable.

**The adjective moves.** Italian and English put the mood after the marker
noun («qualcosa di rilassante», "something relaxing"); German says either
«etwas Entspannendes» or «entspannende Musik», the marker on the far side.
The ``mood`` pattern therefore allows a trailing «Musik»/«Lieder» after the
captured tail — the same trick ``en.py`` uses for "some upbeat music" — and,
like both other packs, refuses everything that does not open with a marker.

Umlauts are written as alternations (``h(?:ö|oe)r``) throughout: browser ASR
and typed input disagree about them constantly, and one spelling is a silent
miss. ``MOOD_WORDS`` keys are folded instead (``frohlich``, ``fur die party``),
because that table is looked up on the *normalized* tail — see ``it.py``.
"""

from __future__ import annotations

from .base import c

CODE = "de"

# Web Speech transcribes a spoken position as a word ("drei"), not "3". The
# umlaut spellings are listed twice on purpose: ``_as_number`` lowercases its
# token but does not fold it, so "fünf" and "funf" are two different keys.
NUM_WORDS = {
    "eins": 1, "ein": 1, "eine": 1, "einer": 1, "zwei": 2, "drei": 3,
    "vier": 4, "fünf": 5, "funf": 5, "sechs": 6, "sieben": 7, "acht": 8,
    "neun": 9, "zehn": 10,
}

# People answer a read-out list with «die zweite» at least as often as with
# the bare number, and German inflects the ordinal for gender and case: the
# recogniser writes whichever the speaker used.
ORDINAL_WORDS = {
    "erste": 1, "erster": 1, "erstes": 1, "ersten": 1,
    "zweite": 2, "zweiter": 2, "zweites": 2, "zweiten": 2,
    "dritte": 3, "dritter": 3, "drittes": 3, "dritten": 3,
    "vierte": 4, "vierter": 4, "viertes": 4, "vierten": 4,
    "fünfte": 5, "funfte": 5, "fünfter": 5, "funfter": 5,
    "fünftes": 5, "funftes": 5, "fünften": 5, "funften": 5,
    "sechste": 6, "sechster": 6, "sechstes": 6, "sechsten": 6,
    "siebte": 7, "siebter": 7, "siebtes": 7, "siebten": 7,
    "siebente": 7, "achte": 8, "achter": 8, "achtes": 8, "achten": 8,
    "neunte": 9, "neunter": 9, "neuntes": 9, "neunten": 9,
    "zehnte": 10, "zehnter": 10, "zehntes": 10, "zehnten": 10,
}

# Durations go beyond list positions: the sleep timer needs the spoken tens
# too («schalt in dreißig Minuten aus»).
MINUTE_WORDS = dict(NUM_WORDS)
MINUTE_WORDS.update({
    "fünfzehn": 15, "funfzehn": 15, "zwanzig": 20,
    "dreißig": 30, "dreissig": 30, "vierzig": 40,
    "fünfzig": 50, "funfzig": 50, "sechzig": 60, "neunzig": 90,
})

# The tail of a sleep command («… in <tail>»), most specific first. The tail
# keeps whatever the separable verb left behind it («30 Minuten aus»); every
# pattern here is anchored at the start and simply ignores it.
DURATIONS = (
    (c(r"^(?:einer\s+)?halben?\s+stunde\b"), 30),
    (c(r"^(?:einer|eine|einem|ein|1)\W?\s*stunde\b"), 60),
    (c(r"^(\d+|[a-zäöüß]+)\s*stunden\b"), "hours"),
    (c(r"^(\d+|[a-zäöüß]+)\s*(?:minut\w*|min\b)"), "minutes"),
)

_LOCAL = (r"(?:aus\s+meiner\s+(?:musik|bibliothek|sammlung)"
          r"|von\s+(?:der\s+)?(?:festplatte|platte)|lokal)")

# One entry per routing step; the handle() flow is identical across languages.
# ``service`` is a template expanded per streaming service name.
PATTERNS = {
    # «mach» only counts with its particle — see the module docstring.
    # ``spielt``/``spielst`` are deliberately NOT here: they are how the
    # question is asked («was spielt gerade»), not how the command is given,
    # and is_play is what switches the whole transport block off.
    "is_play": c(r"\b(?:spiel(?:e|en)?|abspielen|leg(?:e)?|starte?"
                 r"|h(?:ö|oe)r(?:e|en)?|auflegen)\b"
                 r"|\bmach(?:e)?\b.{0,30}\ban\b"
                 r"|\bich\s+(?:will|m(?:ö|oe)chte|mag)\b"),
    "pause_explicit": c(r"\bauf\s+pause\b"),
    # «aus» is far too common a German word to stand alone («aus Liebe», «aus
    # meiner Musik»): it only counts as the tail of «mach … aus», which is how
    # the command is said and where the word cannot be anything else. Bare
    # «halt» is anchored for the same reason — mid-sentence it is a filler
    # particle, not an order.
    "pause": c(r"\b(?:pause|pausiere|stopp|stop|stoppe|stoppen|anhalten"
               r"|ausmachen|ausschalten)\b"
               r"|^halt\b"
               r"|\bmach\w*\b.{0,25}\baus\s*$"),
    # Bare "play"/«weiter» resumes (like a remote's ▶). «spiel weiter» has to
    # be here rather than in ``resume``: it carries a play verb, so the
    # is_play gate below would never let the loose pattern see it. What that
    # costs, said out loud: a record called *Weiter* cannot be asked for by
    # name. «weiter» after a play verb is what a person says to un-pause, many
    # times a day, and the title is one record — the same trade ``it.py``
    # makes with a bare «play».
    "resume_explicit": c(r"^(?:play|weiter|weiterspielen"
                         r"|(?:spiel(?:e)?|mach(?:e)?)\s+weiter)\s*$"),
    "resume": c(r"\b(weiter|weiterspielen|weitermachen|fortsetzen"
                r"|fortfahren|play)\b"),
    # Prefix matching, like the Italian pack: German inflects the ending.
    "next": c(r"\b(n(?:ä|ae)chst|(?:ü|ue)berspring|skip|vorw(?:ä|ae)rts)"),
    "prev": c(r"\b(vorherig|vorig|zur(?:ü|ue)ck|r(?:ü|ue)ckw(?:ä|ae)rts)"),
    # Both halves name the direction, so «mach die Lautstärke leiser» can
    # never reach the "up" branch on the strength of the noun alone.
    "vol_up": c(r"lautst(?:ä|ae)rke\b.{0,20}\b(?:h(?:ö|oe)her|hoch|rauf"
                r"|lauter|erh(?:ö|oe)hen?)"
                r"|\b(?:erh(?:ö|oe)he|steigere)\b.{0,20}\blautst(?:ä|ae)rke"),
    "vol_down": c(r"lautst(?:ä|ae)rke\b.{0,20}\b(?:niedriger|runter|leiser"
                  r"|verringern?|reduzieren?|senken?)"
                  r"|\b(?:verringere|reduziere|senke)\b.{0,20}"
                  r"\blautst(?:ä|ae)rke"),
    # Loose forms that name no control: gated on is_play in the router, so a
    # title containing them still plays (see the Italian pack).
    "vol_up_loose": c(r"\blauter\b"),
    "vol_down_loose": c(r"\bleiser\b"),
    # Sleep timer. German writes the verb on either side of the duration
    # («schalt in 30 Minuten aus», «in 30 Minuten ausschalten»), so the verb
    # is required by a lookahead over the whole phrase and the capture starts
    # at the first «in». The tail must still parse as a duration (see
    # DURATIONS), or the phrase falls through to pause/play — which is what
    # keeps a title carrying «in» from becoming a timer.
    "sleep": c(r"^(?=.*\b(?:(?:aus)?schalt\w*|stopp?\w*|pausier\w*"
               r"|aufh(?:ö|oe)ren|schlaftimer|schluss)\b)"
               r".*?\bin\s+(.+)$"),
    "sleep_cancel": c(r"^(?:l(?:ö|oe)sch\w*|entferne?|brich|beende"
                      r"|deaktiviere|storniere)\b.{0,20}"
                      r"(?:schlaftimer|timer|sleep)"
                      r"|^(?:schlaftimer|timer)\s+(?:aus|abbrechen"
                      r"|l(?:ö|oe)schen|beenden|stopp)"),
    # Loose on purpose (mirrors the other packs) and gated by is_play in
    # handle(), so «spiel Was Ist Das» stays a play command.
    # Tighter than the other two packs, and it has to be: «welche Lieder von
    # Pink Floyd» is a request for a LIST, and a pattern that accepted
    # «welch…» plus «Lieder» claimed it four steps before the list step ever
    # ran. The question word must reach an actual verb of playing.
    "nowplaying": c(r"\b(?:was|welch\w*)\b.{0,25}\b(?:l(?:ä|ae)uft|spielt)\b"
                    r"|\bwer\s+(?:singt|ist\s+das)\b"
                    r"|\bl(?:ä|ae)uft\s+gerade\b"
                    r"|\bwas\s+ist\s+das\s+f(?:ü|ue)r\s+ein\b"),
    # Queue management. Checked early in the router, ahead of the generic
    # play verbs, so «zur Warteschlange»/«als nächstes» never gets swallowed
    # as part of a title.
    "queue_add": c(r"\b(?:f(?:ü|ue)ge?|pack|setze?|h(?:ä|ae)ng(?:e)?)\s+(.+?)"
                   r"\s+(?:zur|in\s+die|an\s+die|auf\s+die)\s+"
                   r"(?:warteschlange|warteliste|queue)(?:\s+hinzu|\s+an)?\s*$"),
    "queue_insert": c(r"\bspiel(?:e|en)?\s+(.+?)\s+"
                      r"(?:als\s+n(?:ä|ae)chstes|danach|gleich\s+danach)\s*$"),
    "queue_clear": c(r"^(?:leere?|l(?:ö|oe)sche?|r(?:ä|ae)ume?)\s+(?:die\s+)?"
                     r"(?:warteschlange|warteliste|queue)"
                     r"(?:\s+(?:auf|leer))?\s*$"),
    "queue_list": c(r"\bwas\b.{0,20}\b(?:warteschlange|warteliste|queue)\b"
                    r"|\b(?:warteschlange|warteliste)\s+(?:anzeigen|zeigen)"
                    r"|was\s+kommt\s+(?:als\s+)?n(?:ä|ae)chstes"),
    # Vague requests — the three conditions are the Italian ones (see it.py),
    # transposed. The anchor is what keeps «mach die Musik aus» from starting
    # music: it opens with a play verb, but «die» is not a marker noun, so the
    # step declines and the transport block below gets the phrase.
    #
    # The trailing «Musik»/«Lieder» after the capture is the German half of
    # the problem: the mood may sit on either side of the marker («etwas
    # Entspannendes», «etwas entspannende Musik»), and without it the second
    # form would look up "entspannende musik" and miss.
    #
    # The trailing «an»/«hören» is the separable verb catching up with its
    # own particle («mach Musik für die Party an»).
    "mood": c(r"^(?:(?:spiel(?:e|en)?|leg(?:e)?|mach(?:e)?|starte?"
              r"|h(?:ö|oe)r(?:e)?|ich\s+(?:will|m(?:ö|oe)chte|mag))"
              r"\s+(?:mir\s+)?)?"
              r"(?:irgendwas|irgendwelche|etwas|was|ein\s+bisschen"
              r"|ein\s+wenig|musik|lieder|songs|st(?:ü|ue)cke)"
              r"\s+(.+?)"
              r"(?:\s+(?:musik|lieder|songs|st(?:ü|ue)cke))?"
              r"(?:\s+(?:an|h(?:ö|oe)ren))?\s*$"),
    # The whole phrase, politeness aside — see it.py. «nächstes Lied» is
    # skip-this-track and is deliberately absent for exactly that reason.
    "mood_another": c(r"^(?:nein[,\s]+)?(?:"
                      r"(?:et)?was\s+anderes|ein\s+ander(?:es|er|s)"
                      r"|anderes|(?:ä|ae)nder(?:e|n|s)?"
                      r"|nicht\s+d(?:as|ie|en)|gef(?:ä|ae)llt\s+mir\s+nicht"
                      r")(?:\s+(?:bitte|danke))?\s*$"),
    # Favorites & radio (LMS core feature — see engine/actions.py).
    "favorites": c(r"\b(?:spiel(?:e|en)?|leg(?:e)?|mach(?:e)?|starte?)\s+"
                   r"(?:meine\s+)?favoriten\b"),
    "radio": c(r"\b(?:spiel(?:e|en)?|mach(?:e)?|leg(?:e)?|starte?)\s+"
               r"(?:d(?:as|en|ie)\s+)?radio(?:sender)?\s+(.+)$"),
    "choose_number": c(r"(?:spiel(?:e)?|nimm|w(?:ä|ae)hl(?:e)?)?\s*"
                       r"(?:die\s+)?nummer\s+([a-z0-9äöüß]+)\s*$"),
    # «die 2» and ordinals: «die zweite», «spiel das zweite Lied»
    "choose_article": c(r"(?:spiel(?:e)?|nimm|w(?:ä|ae)hl(?:e)?)?\s*"
                        r"d(?:ie|as|er|en)\s+([a-z0-9äöüß]+)"
                        r"(?:\s+(?:lied|song|st(?:ü|ue)ck|titel|option))?\s*$"),
    "local_prefix": c(rf"{_LOCAL}\s+(?:spiel(?:e)?\s+|leg(?:e)?\s+)?(.+)$"),
    "local_suffix": c(rf"(?:spiel(?:e|en)?|leg(?:e)?|starte?)\s+(.+?)\s+"
                      rf"{_LOCAL}\s*$"),
    "service": r"(?:von {s}|auf {s}|mit {s}|(?:ü|ue)ber {s})\s+(?:spiel(?:e)?\s+|leg(?:e)?\s+)?(.+)$",
    "albums_list": c(r"welch\w*\s.{0,20}alben.{0,20}?\bvon\s+(.+)$"),
    "toptracks": c(r"(?:beste[nrs]?\s+(?:lieder|songs|titel|st(?:ü|ue)cke)"
                   r"|top\s*tracks|meistgespielte\w*|meist\s*geh(?:ö|oe)rte\w*"
                   r"|welche\s+(?:lieder|songs|titel))"
                   r".*?\bvon\s+(.+)$"),
    "name_pick": c(r"(?:(?:ich\s+(?:will|m(?:ö|oe)chte)|spiel(?:e|en)?|nimm"
                   r"|w(?:ä|ae)hl(?:e)?|leg(?:e)?|starte?|mach(?:e)?)\s+)?"
                   r"(.+)$"),
    "album": c(r"(?:spiel(?:e|en)?|leg(?:e)?|starte?|mach(?:e)?)\s+"
               r"(?:d(?:as|ie|en)\s+)?album\s+(.+)$"),
    "playlist": c(r"(?:spiel(?:e|en)?|leg(?:e)?|starte?|mach(?:e)?)\s+"
                  r"(?:d(?:ie|as)\s+)?playlist\s+(.+)$"),
    # Only «von» introduces the artist, and only behind a word that says a
    # person is coming: «spiel Musik von X», never a bare «von» — half the
    # German song titles in a library contain one.
    "artist": c(r"(?:spiel(?:e|en)?|leg(?:e)?|starte?|mach(?:e)?)\s+"
                r"(?:(?:etwas|was|alles|nur)\s+von"
                r"|(?:d(?:ie|as)\s+)?(?:musik|lieder|songs|titel|st(?:ü|ue)cke)"
                r"\s+von"
                r"|d(?:en|ie)\s+k(?:ü|ue)nstler(?:in)?)\s+(.+)$"),
    # No «leg»/«mach» here: those are separable and land in the suffix form
    # below, which is the only one that strips the particle. See the module
    # docstring — this is what lets «spiel Wach Auf» keep its "auf".
    "generic_play": c(r"(?:spiel(?:e|en)?|abspielen|starte?"
                      r"|h(?:ö|oe)r(?:e)?)\s+(.+)$"),
    # Separable/split forms: «leg Time auf», «mach die Musik an», «ich möchte
    # Time hören».
    "generic_play_suffix": c(r"^(?:leg(?:e)?|mach(?:e)?"
                             r"|ich\s+(?:will|m(?:ö|oe)chte|mag))\s+(.+?)\s+"
                             r"(?:an|auf|ab|h(?:ö|oe)ren)\s*$"),
    # Kid-safe: anchored on the verb at string start, so a title containing
    # the word still routes as a play.
    "block_add": c(r"^(?:blockiere?|sperre?)\s+(.+)$"),
    "block_remove": c(r"^(?:entblockiere?|entsperre?|erlaube?"
                      r"|gib\s+frei)\s+(.+)$"),
    "block_list": c(r"^(?:welche\s+(?:lieder|songs|titel)\s+sind\s+"
                    r"(?:gesperrt|blockiert)"
                    r"|was\s+ist\s+(?:gesperrt|blockiert)"
                    r"|(?:zeige?|liste)\w*\s+(?:die\s+)?"
                    r"(?:gesperrten|blockierten))"),
}

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
    "zum weinen": "melancholy", "fur einen regentag": "melancholy",
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
}
