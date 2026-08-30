"""What a mood *is*, as data — the table ``moods.py`` resolves against.

Split from the resolution logic for the reason the language packs were split
from their vocabularies (``localvoice/lang/base.py``) and the catalogs from
``messages.py``: this is a **list**, not a program. It is also the half that
grows — the size guard in ``tests/test_packaging.py`` said so when the second
pass of moods took ``moods.py`` to 391 of its 400 lines — and the half
``mood_seeds.json`` is meant to replace one day without the lookup that reads
it changing at all.

It stays hand-written data on purpose, and that is a compliance property, not
a style preference: ``docs/ai-act.md`` claims this table "classifies **music**,
not the listener. Nothing infers a mood, an emotion or any other attribute of
a person." Generating it offline is fine; inferring it at runtime is not.

**The first alias is the one that plays.** ``_pick_genre`` walks the aliases in
order and takes the first tag the library actually has, so the lead alias is
the mood's real identity and every later one is a fallback. Four moods used to
lead with "Ambient" — relax, sleep, focus and background — which made them the
same command in any library carrying that tag: four questions, one answer.
That is what ``test_no_two_moods_open_on_the_same_genre`` now forbids. Sharing
a *later* alias is fine and wanted; that is what a fallback is.

Choosing the lead is therefore a judgement about what is most characteristic
of the mood rather than most common in libraries: `sleep` leads with "Sleep"
and only reaches "Ambient" fourth, so a library with both plays the tag that
was actually asked for.

The genre aliases mix English and Italian on purpose: a music library's genre
tags do not follow the UI language, so an Italian listener's "Classica" and an
English one's "Classical" are aliases of one mood. The playlist queries are
English on purpose too — TIDAL and Qobuz name their curated playlists in
English regardless of the account's country.

An entry carries ``genres`` **or** ``years``, never both and never neither:
``play_mood`` branches on which. A decade's ``years`` is the closed interval it
covers, because no LMS filter anywhere accepts a range — the load asks for a
single year picked out of that interval.

``Sequence[Any]`` and not ``Sequence[str]``: a decade's ``years`` holds two
ints, everything else holds strings.
"""

from __future__ import annotations

from typing import Any, Dict, Sequence

MOODS: Dict[str, Dict[str, Sequence[Any]]] = {

    # -- where the music is going to be heard ---------------------------------
    #
    # The four that used to collide. Each now leads with the tag that names its
    # own situation and keeps the shared ambient/classical ones as fallbacks,
    # so a library that has only "Ambient" still answers all four — it just no
    # longer answers them identically when it has more.
    "relax": {
        "genres": ("Ambient", "Chillout", "Chill Out", "Downtempo", "New Age",
                   "Easy Listening"),
        "playlists": ("Relaxing", "Unwind", "Calm"),
    },
    "sleep": {
        "genres": ("Sleep", "Piano", "Meditation", "New Age", "Ambient"),
        "playlists": ("Sleep", "Deep Sleep", "Night"),
    },
    "focus": {
        "genres": ("Minimal", "Post-Rock", "Modern Classical",
                   "Contemporary Classical", "Ambient", "Electronic"),
        "playlists": ("Focus", "Deep Focus", "Study"),
    },
    "background": {
        "genres": ("Lounge", "Easy Listening", "Bossa Nova", "Ambient", "Jazz"),
        "playlists": ("Background", "Coffee Shop", "Easy Listening"),
    },
    "dinner": {
        "genres": ("Bossa Nova", "Cool Jazz", "Soul", "Jazz", "Lounge"),
        "playlists": ("Dinner", "Dinner Jazz", "Supper Club"),
    },
    "morning": {
        "genres": ("Acoustic", "Folk Rock", "Bossa Nova", "Jazz", "Pop"),
        "playlists": ("Morning", "Wake Up", "Breakfast"),
    },
    "party": {
        "genres": ("Disco", "Dance", "House", "Funk", "Electronic", "Pop"),
        "playlists": ("Party", "Dance Party", "Club"),
    },
    "cooking": {
        "genres": ("Salsa", "Latin", "Bossa Nova", "Funk", "Soul", "Jazz"),
        "playlists": ("Cooking", "Kitchen Groove", "Feel Good"),
    },
    "driving": {
        "genres": ("Americana", "Pop Rock", "Classic Rock", "Rock"),
        "playlists": ("Road Trip", "Driving", "Highway"),
    },
    "rainy": {
        "genres": ("Lo-Fi", "Chamber Jazz", "Slowcore", "Blues", "Folk"),
        "playlists": ("Rainy Day", "Cosy", "Grey Skies"),
    },
    # The mood most likely to be asked for in a household that has kid-safe
    # turned on. The guard filters genre NAMES only, so a blocked artist inside
    # an allowed genre still plays — the hole is `play_mood`'s, documented
    # there, and this entry does not widen it. It is named here because this is
    # the entry that makes it likely to be met.
    "kids": {
        "genres": ("Children's", "Bambini", "Enfants", "Kinder", "Infantil",
                   "Disney", "Soundtrack"),
        "playlists": ("Kids", "Children", "Family"),
    },
    "meditation": {
        "genres": ("Meditation", "Drone", "Raga", "New Age", "Ambient"),
        "playlists": ("Meditation", "Mindfulness", "Zen"),
    },
    # «qualcosa di lungo che non finisca subito» — the request is about track
    # length, which LMS has no filter for, so it is answered by the genres
    # where long tracks are the norm rather than the exception.
    "longform": {
        "genres": ("Progressive Rock", "Krautrock", "Minimalism", "Post-Rock",
                   "Rock Progressivo"),
        "playlists": ("Long Listening", "Epic", "Deep Cuts"),
    },
    "singalong": {
        "genres": ("Classic Rock", "Musica Italiana", "Canzone Italiana",
                   "Pop Rock", "Rock"),
        "playlists": ("Sing Along", "Anthems", "Karaoke"),
    },
    "crowdpleaser": {
        "genres": ("Pop Rock", "Classic Pop", "Pop", "Rock"),
        "playlists": ("Greatest Hits", "All Time Classics", "Popular"),
    },

    # -- how it is meant to feel ----------------------------------------------
    #
    # «triste» and «allegro» were one bucket each, which is the whole reason
    # this pass exists: five ways of saying sad all loaded the same genre. The
    # nuances below are only worth their key because each resolves somewhere
    # different — a synonym that lands on an existing mood belongs in a
    # language pack's MOOD_WORDS, not here.
    "happy": {
        "genres": ("Ska", "Funk", "Soul", "Reggae", "Disco", "Pop"),
        "playlists": ("Feel Good", "Happy", "Good Mood"),
    },
    "uplifting": {
        "genres": ("Gospel", "Motown", "Northern Soul", "Soul"),
        "playlists": ("Uplifting", "Mood Booster", "Good Vibes"),
    },
    "euphoric": {
        "genres": ("Trance", "Techno", "House", "Big Beat", "Dance"),
        "playlists": ("Euphoria", "Peak Time", "Bangers"),
    },
    "dreamy": {
        "genres": ("Dream Pop", "Shoegaze", "Ambient Pop", "Slowcore"),
        "playlists": ("Dreamy", "Ethereal", "Floating"),
    },
    "energetic": {
        "genres": ("Dance", "Big Beat", "Punk", "Metal", "Electronic", "Rock"),
        "playlists": ("Workout", "Energy", "Running"),
    },
    "romantic": {
        "genres": ("Quiet Storm", "Soul", "R&B", "Bossa Nova", "Jazz", "Pop"),
        "playlists": ("Romantic", "Love Songs", "Date Night"),
    },
    "melancholy": {
        "genres": ("Cantautori", "Singer-Songwriter", "Indie", "Alternative",
                   "Folk", "Blues"),
        "playlists": ("Melancholy", "Sad Songs", "Introspective"),
    },
    "heartbreak": {
        "genres": ("Torch Songs", "Ballads", "Soul", "R&B", "Cantautori"),
        "playlists": ("Heartbreak", "Sad Love Songs", "Breakup"),
    },
    "nostalgic": {
        "genres": ("Oldies", "Classic Pop", "Swing", "Musica Leggera",
                   "Schlager", "Chanson"),
        "playlists": ("Nostalgia", "Throwback", "Golden Oldies"),
    },
    "dark": {
        "genres": ("Post-Punk", "Gothic", "Goth", "Industrial", "Trip-Hop",
                   "Doom Metal"),
        "playlists": ("Dark", "Moody", "Late Night"),
    },

    # -- metadata axes LMS already carries ------------------------------------
    #
    # Christmas is a genre tag people really do have; "instrumental" and
    # "summer" are not — no library has a tag called either — so both are
    # spelled out as the genres that genuinely ARE that thing. `summer` used to
    # lead with "Reggae" and now leads with "Surf", because `reggae` is a mood
    # of its own since this pass and the two must not be the same load.
    "christmas": {
        "genres": ("Christmas", "Natale", "Holiday", "Natalizio"),
        "playlists": ("Christmas", "Christmas Classics", "Holiday"),
    },
    "instrumental": {
        "genres": ("Instrumental", "Strumentale", "Post-Rock", "Ambient",
                   "Classical"),
        "playlists": ("Instrumental", "Instrumental Focus", "No Vocals"),
    },
    "summer": {
        "genres": ("Surf", "Reggae", "Latin", "Bossa Nova", "Ska"),
        "playlists": ("Summer", "Summer Hits", "Beach"),
    },

    # -- genre-shaped vague requests ------------------------------------------
    #
    # «metti un po' di jazz» has no title, no artist and nothing for the parser
    # to find — the same gap as a mood, answered by the same lookup at no extra
    # cost. Four of these existed; the twelve that did not meant «metti un po'
    # di reggae» fell through to a title search for the word "reggae".
    #
    # Each claims its own tag as its lead, which is what pushes the mood-shaped
    # entries above onto leads of their own: `happy` cannot open on "Pop"
    # because `pop` is a request in its own right and the two are not the same
    # answer.
    "classical": {
        "genres": ("Classical", "Classica", "Baroque", "Barocco", "Opera",
                   "Lirica"),
        "playlists": ("Classical Essentials", "Classical", "Composers"),
    },
    "jazz": {
        "genres": ("Jazz", "Bebop", "Swing", "Hard Bop", "Jazz Vocal"),
        "playlists": ("Jazz Essentials", "Jazz", "Jazz Classics"),
    },
    "rock": {
        "genres": ("Rock", "Hard Rock", "Rock Progressivo", "Garage Rock"),
        "playlists": ("Rock Classics", "Rock", "Rock Essentials"),
    },
    "blues": {
        "genres": ("Blues", "Delta Blues", "Chicago Blues",
                   "Rhythm and Blues"),
        "playlists": ("Blues Essentials", "Blues", "Blues Classics"),
    },
    "pop": {
        "genres": ("Pop", "Synth Pop", "Power Pop", "Pop Italiano"),
        "playlists": ("Pop Hits", "Pop", "Pop Essentials"),
    },
    "soul": {
        "genres": ("Soul", "Neo Soul", "Motown", "Southern Soul"),
        "playlists": ("Soul Classics", "Soul", "Soul Essentials"),
    },
    "funk": {
        "genres": ("Funk", "P-Funk", "Funk Soul", "Jazz Funk"),
        "playlists": ("Funk Classics", "Funk", "Funk Essentials"),
    },
    "reggae": {
        "genres": ("Reggae", "Dub", "Roots Reggae", "Dancehall", "Rocksteady"),
        "playlists": ("Reggae Classics", "Reggae", "Reggae Essentials"),
    },
    "metal": {
        "genres": ("Metal", "Heavy Metal", "Thrash Metal", "Death Metal"),
        "playlists": ("Metal Essentials", "Metal", "Metal Classics"),
    },
    "punk": {
        "genres": ("Punk", "Punk Rock", "Hardcore", "Hardcore Punk"),
        "playlists": ("Punk Classics", "Punk", "Punk Essentials"),
    },
    "electronic": {
        "genres": ("Electronic", "Elettronica", "Electronica", "IDM",
                   "Downtempo"),
        "playlists": ("Electronic Essentials", "Electronic", "Electronica"),
    },
    "hiphop": {
        "genres": ("Hip Hop", "Hip-Hop", "Rap", "Rap Italiano"),
        "playlists": ("Hip Hop Essentials", "Hip Hop", "Rap"),
    },
    "country": {
        "genres": ("Country", "Bluegrass", "Country Rock", "Alt-Country"),
        "playlists": ("Country Classics", "Country", "Country Essentials"),
    },
    "folk": {
        "genres": ("Folk", "Folk Revival", "Acoustic", "Folk Italiano"),
        "playlists": ("Folk Essentials", "Folk", "Folk Classics"),
    },
    "latin": {
        "genres": ("Latin", "Latino", "Samba", "Tango", "Cumbia"),
        "playlists": ("Latin Hits", "Latin", "Latin Essentials"),
    },
    "world": {
        "genres": ("World", "World Music", "Afrobeat", "Musica Etnica",
                   "Musiques du Monde"),
        "playlists": ("World Music", "World", "Global"),
    },

    # -- decades: the year axis -----------------------------------------------
    #
    # See moods.py on why the value is an interval and the load is one year out
    # of it. Note this is the one axis a kid-safe household cannot restrict at
    # all — the blocklist matches names, and 1985 is not one — so each decade
    # added here extends that gap by ten years. Documented, not fixed.
    "fifties": {
        "years": (1950, 1959),
        "playlists": ("50s", "50s Hits"),
    },
    "sixties": {
        "years": (1960, 1969),
        "playlists": ("60s", "60s Hits"),
    },
    "seventies": {
        "years": (1970, 1979),
        "playlists": ("70s", "70s Hits"),
    },
    "eighties": {
        "years": (1980, 1989),
        "playlists": ("80s", "80s Hits"),
    },
    "nineties": {
        "years": (1990, 1999),
        "playlists": ("90s", "90s Hits"),
    },
    "noughties": {
        "years": (2000, 2009),
        "playlists": ("2000s", "2000s Hits"),
    },
    "tens": {
        "years": (2010, 2019),
        "playlists": ("2010s", "2010s Hits"),
    },
}
