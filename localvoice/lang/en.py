"""English language pack — see ``base.py`` for the contract. Patterns moved
verbatim from the pre-split router."""

from __future__ import annotations

from .base import c

CODE = "en"

NUM_WORDS = {
    "one": 1, "two": 2, "three": 3, "four": 4, "five": 5,
    "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10,
}

ORDINAL_WORDS = {
    "first": 1, "second": 2, "third": 3, "fourth": 4, "fifth": 5,
    "sixth": 6, "seventh": 7, "eighth": 8, "ninth": 9, "tenth": 10,
}

MINUTE_WORDS = dict(NUM_WORDS)
MINUTE_WORDS.update({
    "fifteen": 15, "twenty": 20, "thirty": 30, "forty": 40,
    "fifty": 50, "sixty": 60, "ninety": 90,
})

# The tail of a sleep command ("stop in <tail>"), most specific first.
DURATIONS = (
    (c(r"^half\s+an?\s+hour\b"), 30),
    (c(r"^(?:an|one|1)\W?\s*hour\b"), 60),
    (c(r"^(\d+|[a-z]+)\s*hours?\b"), "hours"),
    (c(r"^(\d+|[a-z]+)\s*(?:minut\w*|min\b)"), "minutes"),
)

_LOCAL = r"(?:from my (?:music|library)|from the library|locally)"

PATTERNS = {
    # ``put`` alone (not just "put on") so the suffix form "put X on" is
    # guarded from transport words too ("put Don't Stop Me Now on").
    "is_play": c(r"\b(?:play|put|start|listen\s+to|i\s+want\s+to\s+(?:hear|listen\s+to))\b"),
    "pause_explicit": c(r"\bon\s+pause\b"),
    "pause": c(r"\b(pause|stop|halt)\b"),
    # Bare "play" resumes (like a remote's ▶), even though it's a play verb.
    "resume_explicit": c(r"^(?:play|resume)\s*$"),
    "resume": c(r"\b(resume|continue|unpause|keep\s+going)\b"),
    "next": c(r"\b(next|skip|forward)\b"),
    "prev": c(r"\b(previous|go\s+back|back)\b"),
    "vol_up": c(r"(?:turn|put|pump|crank)?\s*up.{0,12}volume|volume\s+up"
                r"|(?:raise|increase)\s.{0,8}volume"),
    "vol_down": c(r"(?:turn|put)?\s*down.{0,12}volume|volume\s+down"
                  r"|(?:lower|decrease|reduce)\s.{0,8}volume"),
    # Loose forms that name no control: gated on is_play in the router, so a
    # title containing them still plays (see the Italian pack).
    "vol_up_loose": c(r"turn\s+it\s+up|louder"),
    "vol_down_loose": c(r"turn\s+it\s+down|quieter|softer"),
    # Sleep timer: the captured tail must parse as a duration (see DURATIONS),
    # otherwise the phrase falls through to pause/play.
    # "pause" belongs here too: "pause in 30 minutes" used to pause now. The
    # tail must still parse as a duration, so a title can't become a timer.
    "sleep": c(r"(?:sleep|stop|pause|turn\s+off|switch\s+off"
               r"|shut\s+(?:down|off))\b.{0,20}?\bin\s+(.+)$"),
    "sleep_cancel": c(r"^(?:cancel|clear|remove)\b.{0,15}(?:sleep|timer)"),
    # Loose on purpose (mirrors the Italian style) and gated by is_play in
    # handle(), so "play What Is This Feeling" stays a play command. Also
    # covers the apostrophe-less ASR form "whats playing".
    "nowplaying": c(r"\bwhat'?s?\b.{0,10}(?:playing|song|this\b)"
                    r"|now\s+playing|who\s+(?:is\s+this|sings)"),
    # Queue management. Checked early in the router, ahead of the generic
    # play verbs, so "to the queue"/"next" never gets swallowed as part of
    # a title.
    "queue_add": c(r"\b(?:add|queue)\s+(.+?)\s+to\s+(?:the\s+)?queue\s*$"),
    "queue_insert": c(r"\bplay\s+(.+?)\s+next\s*$"),
    "queue_clear": c(r"^(?:clear|empty)\s+the\s+queue\s*$"),
    "queue_list": c(r"what'?s\s+(?:in|on)\s+the\s+queue|queue\s+list"),
    # Vague requests — see it.py for the three conditions and why the anchor
    # is one of them ("stop playing something sad" and "I don't want something
    # sad" both used to start the music), and engine/moods.py for the lookup. "for" is deliberately never consumed: "for dinner" is the
    # whole tail MOOD_WORDS is asked about, not "dinner" with a stray word.
    "mood": c(r"^(?:(?:play|put\s+on|start"
              r"|i\s+want\s+to\s+(?:hear|listen\s+to))\s+(?:me\s+)?)?"
              r"(?:some|a\s+bit\s+of|a\s+little|something|anything"
              r"|music|songs|tunes)"
              r"(?:\s+(?:music|songs))?"
              # A trailing "music"/"songs" is part of the phrasing, not of the
              # mood: "some upbeat music" asks for `upbeat`. Lazy plus an
              # optional tail-noun, so a multi-word mood ("for studying")
              # still backtracks its way to the whole thing.
              r"\s+(.+?)(?:\s+(?:music|songs|tunes))?\s*$"),
    # The whole phrase, politeness aside — see it.py. As a prefix it caught
    # "another song", which is skip-this-track. And no "next one": same
    # reason, and it would have shadowed the transport pattern outright.
    "mood_another": c(r"^(?:no[,\s]+)?(?:another(?:\s+one)?"
                      r"|something\s+else|change\s+it|not\s+this\s+one"
                      r")(?:\s+(?:please|thanks))?\s*$"),
    # Favorites & radio (LMS core feature — see engine/actions.py).
    "favorites": c(r"\b(?:play|put\s+on|start)\s+(?:my\s+)?favou?rites\b"),
    "radio": c(r"\bplay\s+(?:the\s+)?radio\s+(.+)$"),
    "choose_number": c(r"(?:play|choose|pick|put\s+on)?\s*(?:the\s+)?number\s+([a-z0-9]+)\s*$"),
    # "the 2" and ordinals: "the second", "play the second one/song"
    "choose_article": c(r"(?:play|choose|pick|put\s+on)?\s*the\s+([a-z0-9]+)"
                        r"(?:\s+(?:one|song|track|option))?\s*$"),
    "local_prefix": c(rf"{_LOCAL}\s+(?:play\s+|put\s+on\s+)?(.+)$"),
    "local_suffix": c(rf"(?:play|put\s+on|start)\s+(.+?)\s+{_LOCAL}\s*$"),
    "service": r"(?:from {s}|on {s}|with {s})\s+(?:play\s+|put\s+on\s+)?(.+)$",
    "albums_list": c(r"(?:which|what).{0,12}albums?.{0,16}(?:by|of|from)\s+(.+)$"),
    "toptracks": c(r"(?:top\s+tracks|best\s+(?:songs|tracks)|most\s+(?:played|listened)"
                   r"|which\s+songs).*?(?:by|of|from)\s+(.+)$"),
    "name_pick": c(r"(?:(?:i\s+want\s+to\s+(?:hear|listen\s+to)|play|choose|pick|put\s+on|start)\s+)?(.+)$"),
    "album": c(r"(?:play|put\s+on|start)\s+(?:the\s+)?album\s+(.+)$"),
    "playlist": c(r"(?:play|put\s+on|start)\s+(?:the\s+)?playlist\s+(.+)$"),
    # Only "by" for songs/tracks: "songs of/from" collide with real titles
    # ("Songs from the Wood", "Songs of Innocence").
    "artist": c(r"(?:play|put\s+on|start)\s+"
                r"(?:(?:some\s+|the\s+)?music\s+(?:by|of|from)|something\s+by"
                r"|the\s+artist|(?:all\s+)?(?:the\s+)?(?:songs?|tracks?)\s+by)\s+(.+)$"),
    "generic_play": c(r"(?:play|put\s+on|start|listen\s+to"
                      r"|i\s+want\s+to\s+(?:hear|listen\s+to))\s+(.+)$"),
    # Suffix form: "put Dark Side of the Moon on"
    "generic_play_suffix": c(r"^put\s+(.+?)\s+on\s*$"),
    # Kid-safe: anchored on the verb at string start, so a title containing
    # the word ("play Block Rockin' Beats") still routes as a play.
    "block_add": c(r"^block\s+(.+)$"),
    "block_remove": c(r"^unblock\s+(.+)$"),
    "block_list": c(r"^(?:(?:what|which)\s+(?:songs?|tracks?)\s+(?:are|is)\s+blocked|"
                    r"what'?s\s+blocked|list\s+(?:the\s+)?blocked)"),
}

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
}
