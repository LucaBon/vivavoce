"""English spoken vocabulary for vague requests — the table ``en.py`` exposes
as ``MOOD_WORDS``. See ``moods_it.py`` for why it lives beside the patterns
rather than in them.
"""

from __future__ import annotations

# Spoken tail -> mood key. See it.py: keys are pre-normalized and matched
# against the WHOLE tail, never a part of it.
MOOD_WORDS = {
    # relax
    "relaxing": "relax", "relaxed": "relax", "calm": "relax",
    "calming": "relax", "chill": "relax", "chilled": "relax",
    "mellow": "relax", "quiet": "relax", "to relax": "relax",
    "laid back": "relax", "soothing": "relax",
    # sleep
    "to sleep": "sleep", "for sleeping": "sleep", "to fall asleep": "sleep",
    "for bedtime": "sleep", "for the night": "sleep", "sleepy": "sleep",
    # dinner
    "for dinner": "dinner", "for supper": "dinner", "dinner": "dinner",
    "for lunch": "dinner", "while we eat": "dinner",
    "for a dinner party": "dinner",
    # party
    "for a party": "party", "for the party": "party", "party": "party",
    "to dance": "party", "for dancing": "party", "to dance to": "party",
    # happy
    "happy": "happy", "cheerful": "happy", "upbeat": "happy",
    "feel good": "happy", "fun": "happy", "joyful": "happy",
    # energetic
    "energetic": "energetic", "for the gym": "energetic",
    "for a workout": "energetic", "for working out": "energetic",
    "for running": "energetic", "to run to": "energetic",
    "pumped up": "energetic", "high energy": "energetic",
    # focus
    "for studying": "focus", "to study": "focus", "to study to": "focus",
    "for working": "focus", "to work to": "focus", "for reading": "focus",
    "to read to": "focus", "for concentration": "focus", "to focus": "focus",
    # background
    "in the background": "background", "for the background": "background",
    "background": "background", "light": "background",
    "easy listening": "background", "unobtrusive": "background",
    # romantic
    "romantic": "romantic", "for a date": "romantic",
    "for date night": "romantic", "for lovers": "romantic",
    "sensual": "romantic",
    # melancholy
    "sad": "melancholy", "melancholy": "melancholy",
    "melancholic": "melancholy", "wistful": "melancholy",
    "downbeat": "melancholy", "bittersweet": "melancholy",
    # morning
    "for the morning": "morning", "for breakfast": "morning",
    "to wake up to": "morning", "for waking up": "morning",
    "morning": "morning",
    # genre-shaped
    "classical": "classical", "classical music": "classical",
    "opera": "classical", "baroque": "classical",
    "jazz": "jazz", "jazzy": "jazz",
    "rock": "rock", "classic rock": "rock", "hard rock": "rock",
    "blues": "blues", "bluesy": "blues",
    # Metadata axes (T2.4-bis) — see it.py for why the bare noun is the thing
    # to be careful with. Bare "christmas" is here despite naming real songs,
    # on the same terms as "fun" already in this table, and it earns it: "put
    # on some christmas music" is a phrase people say and nothing else covers
    # it. Bare "summer" was here too and is deliberately gone — measured, it
    # covered no corpus phrase that "summery" did not already cover, while it
    # did break "play some Summer", which is how a person asks for a one-word
    # title. An entry that costs a real request and buys nothing is not a
    # trade, and the fall-through is a weaker net than it looks: the phrase
    # handed back still carries its marker, so the search sees "some Summer".
    "christmas": "christmas", "for christmas": "christmas",
    "instrumental": "instrumental", "without words": "instrumental",
    "with no words": "instrumental",
    "summery": "summer",
    # Decades.
    "sixties": "sixties", "the sixties": "sixties",
    "from the sixties": "sixties", "60s": "sixties",
    "the 60s": "sixties", "from the 60s": "sixties",
    "seventies": "seventies", "the seventies": "seventies",
    "from the seventies": "seventies", "70s": "seventies",
    "the 70s": "seventies", "from the 70s": "seventies",
    "eighties": "eighties", "the eighties": "eighties",
    "from the eighties": "eighties", "80s": "eighties",
    "the 80s": "eighties", "from the 80s": "eighties",
    "nineties": "nineties", "the nineties": "nineties",
    "from the nineties": "nineties", "90s": "nineties",
    "the 90s": "nineties", "from the 90s": "nineties",

    # -- the nuances (T2.6) ---------------------------------------------------
    # "sad" and "happy" were one bucket each. Only the shades that resolve
    # somewhere different in mood_table.py get a key of their own; the rest
    # stay synonyms in the blocks above. Three entries moved out of
    # `melancholy` on that rule: "nostalgic", "moody" and "for a rainy day"
    # were never the same request as "sad", they just had nowhere else to go.
    "uplifting": "uplifting", "to cheer me up": "uplifting",
    "to pick me up": "uplifting", "that picks me up": "uplifting",
    "encouraging": "uplifting", "optimistic": "uplifting",
    "hopeful": "uplifting", "a pick me up": "uplifting",
    "euphoric": "euphoric", "banging": "euphoric", "full on": "euphoric",
    "high octane": "euphoric", "to go wild to": "euphoric",
    "dreamy": "dreamy", "ethereal": "dreamy", "hazy": "dreamy",
    "floaty": "dreamy", "shimmering": "dreamy",
    "heartbroken": "heartbreak", "for a broken heart": "heartbreak",
    "for a breakup": "heartbreak", "after a breakup": "heartbreak",
    "sad love songs": "heartbreak", "to cry to": "heartbreak",
    "nostalgic": "nostalgic", "for the old days": "nostalgic",
    "from the old days": "nostalgic", "old fashioned": "nostalgic",
    "throwback": "nostalgic", "vintage": "nostalgic", "retro": "nostalgic",
    "that takes me back": "nostalgic",
    "dark": "dark", "moody": "dark", "brooding": "dark", "gloomy": "dark",
    "sinister": "dark", "for a late night": "dark",

    # -- the situations (T2.6) ------------------------------------------------
    # Straight out of the residue tools/mood_coverage.py measures against
    # tests/data/vague_phrases_en.txt — these are the phrases people wrote,
    # not phrasings invented to be easy to match.
    "for the kids": "kids", "for kids": "kids",
    "the kids will like": "kids", "that the kids will like": "kids",
    "for children": "kids", "kid friendly": "kids",
    "we can sing along to": "singalong", "to sing along to": "singalong",
    "to sing along": "singalong", "for a singalong": "singalong",
    "everyone can sing": "singalong", "singalong": "singalong",
    "famous": "crowdpleaser", "well known": "crowdpleaser",
    "everyone will like": "crowdpleaser",
    "that everyone will like": "crowdpleaser",
    "everyone knows": "crowdpleaser", "that everyone knows": "crowdpleaser",
    "the greatest hits": "crowdpleaser", "greatest hits": "crowdpleaser",
    "crowd pleasing": "crowdpleaser",
    "for cooking": "cooking", "to cook to": "cooking",
    "while i cook": "cooking", "for the kitchen": "cooking",
    "that makes me want to cook": "cooking",
    "for a rainy day": "rainy", "for the rain": "rainy",
    "rainy": "rainy", "for a grey day": "rainy", "cosy": "rainy",
    "for a road trip": "driving", "for the drive": "driving",
    "for driving": "driving", "to drive to": "driving",
    "for the car": "driving", "road trip": "driving",
    # No leading article games here: the tail is whatever survives the marker,
    # and "something long" arrives as the bare "long".
    "long": "longform", "epic": "longform", "sprawling": "longform",
    "that wont stop soon": "longform",
    "long that wont stop soon": "longform",
    "for meditation": "meditation", "to meditate to": "meditation",
    "for meditating": "meditation", "for yoga": "meditation",
    "meditative": "meditation",

    # -- the genres that were missing (T2.6) ----------------------------------
    # Four of these existed and twelve did not, so "play some reggae" was a
    # title search for the word reggae. The marker is what makes the bare word
    # safe: the pattern is anchored and needs its marker, so "play Soul" never
    # reaches this table while "play some soul" does.
    "pop": "pop",
    "soul": "soul", "soulful": "soul",
    "funk": "funk", "funky": "funk",
    "reggae": "reggae", "ska": "reggae", "dub": "reggae",
    "metal": "metal", "heavy metal": "metal",
    "punk": "punk",
    "electronic": "electronic", "electronica": "electronic",
    "techno": "electronic", "house": "electronic", "dance": "electronic",
    "hip hop": "hiphop", "hiphop": "hiphop", "rap": "hiphop",
    "country": "country", "bluegrass": "country",
    "folk": "folk", "folky": "folk",
    "latin": "latin", "salsa": "latin",
    "world music": "world", "world": "world", "afrobeat": "world",

    # -- the decades that were missing (T2.6) ---------------------------------
    "fifties": "fifties", "the fifties": "fifties",
    "from the fifties": "fifties", "50s": "fifties",
    "the 50s": "fifties", "from the 50s": "fifties",
    "noughties": "noughties", "the noughties": "noughties",
    "2000s": "noughties", "the 2000s": "noughties",
    "from the 2000s": "noughties", "the aughts": "noughties",
    "2010s": "tens", "the 2010s": "tens", "from the 2010s": "tens",
    "twenty tens": "tens",
}
