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
    "melancholic": "melancholy", "nostalgic": "melancholy",
    "moody": "melancholy", "for a rainy day": "melancholy",
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
}
