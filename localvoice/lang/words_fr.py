"""French word lists the patterns are built from — the closed sets, the two
builders composed out of them, and the one thing French forces on this pack
that no other language did: spelling every accented word twice.

Beside the patterns for ``base.py``'s reason (a pack holds the grammar, its
word lists live next door), and shared for ``words_de.py``'s reason, which
cost six rounds of review to learn: two patterns that must agree about a
closed set have to read the same name.

French raises that stakes. German needed three umlauts; French needs six vowel
families over some forty words, and the router matches them against the RAW
text — ``router.py`` hands ``clean_command(text)`` straight to the patterns,
and ``re.I`` folds case but not accents. Every accented word is therefore two
words as far as a regex is concerned, and «arrete la musique» typed into the
box would fall past the pause step and search the library for a record called
"la musique". :func:`acc` is that fact encoded once.
"""

from __future__ import annotations

import re
import unicodedata

# Both apostrophe glyphs, in every pattern that needs one. Nothing upstream
# normalises them — ``clean_command`` strips trailing punctuation and nothing
# else — and macOS/iOS Web Speech emits U+2019 where Chrome on Linux and the
# text box emit U+0027. Elision is not an edge case in French: «j'écoute»,
# «l'album», «qu'est-ce», «s'il te plaît», «d'Édith Piaf».
AP = r"['’]"

# base letter -> every way a recogniser or a keyboard may write it.
_FAMILIES = {
    "a": "[aàâä]",
    "c": "[cç]",
    "e": "[eéèêë]",
    "i": "[iîï]",
    "o": "[oôö]",
    "u": "[uùûü]",
    "y": "[yÿ]",
    # The two ligatures NFKD leaves whole, so the loop below never reaches
    # their base letters: «cœur» and «coeur» are the same word to everyone
    # except a regex.
    "œ": "(?:œ|oe)",
    "æ": "(?:æ|ae)",
}


def _base(ch: str) -> str:
    """``ch`` with its combining mark removed, or ``ch`` if it carries none."""
    stripped = "".join(
        c for c in unicodedata.normalize("NFKD", ch) if not unicodedata.combining(c)
    )
    return stripped or ch


def acc(word: str) -> str:
    """A French word, spelled correctly, as a pattern that also matches every
    way it may arrive.

    ``acc("précédent")`` -> ``pr[eéèêë][cç][eéèêë]d[eéèêë]nt``. The argument is
    the real French spelling, so a reviewer checks *the French* and the accent
    handling comes for free — which is the whole point of having one of these
    rather than forty hand-written alternations that will disagree.

    It also accepts spellings that are not French («prêcêdênt»). That costs
    nothing: those strings are not titles either.

    Never call it on «à». It is the one word whose accent-stripped form is a
    different word that matters — the verb *avoir* — and :data:`_A` spells that
    pair out by hand instead.
    """
    return "".join(
        _FAMILIES.get(_base(ch), re.escape(_base(ch))) for ch in word.lower()
    )


# The accented letters written out for use INSIDE a character class, where an
# alternation cannot go: the pick patterns capture a bare token, and without
# these «la première» never reaches ``_as_number`` at all. de.py widened its
# own class to [a-z0-9äöüß] for exactly this. Spelled out rather than given as
# the range à-ÿ, which also contains ÷.
_ACCLASS = "àâäéèêëîï" \
           "ôöùûüÿçœæ"

# «à», by hand and not through acc(): see acc()'s docstring.
_A = "(?:à|a)"

# The definite article, elided or not. Read by every step that names a thing
# («mets l'album X», «mets la playlist Y») and by the device builder below.
_L = rf"(?:l{AP}\s*|la\s+|le\s+|les\s+)"

# "of" and the partitive, which French spends on both jobs this pack cares
# about: introducing an artist («la musique de Céline Dion», «du Pink Floyd»)
# and introducing a mood («de la musique douce»). Longest alternative first,
# or `de\s+` eats the head of «de la» and the step captures "la musique douce".
_DE = rf"(?:de\s+la\s+|de\s+l{AP}\s*|du\s+|des\s+|d{AP}\s*|de\s+)"

# Politeness. Italian carries «per favore|grazie» in one pattern and German
# «bitte» in three; French needs it in nearly all of them, because it lands
# AFTER the object rather than inside the phrase — so it hits every $-anchored
# pattern and rides along inside every greedy capture. «mets la radio s'il te
# plaît» asked LMS for a station called "s'il te plaît", which is German's
# «mach das Radio bitte aus» bug with a longer tail.
_POLITE = (rf"(?:s{AP}?\s*(?:il\s+)?(?:te|vous|t{AP}\s*)\s*{acc('plait')}"
           rf"|{acc('steuplait')}|stp|svp|{acc('merci')}"
           rf"|{acc('sil')}\s+te\s+{acc('plait')})")

# Words that may stand between a command and its end, and that a router acts
# on none of. words_de.py's ``_ADV``, transposed — and repeated (``*``) rather
# than optional (``?``) for the same reason: «coupe la musique maintenant s'il
# te plaît» is ordinary French, and one slot let the second one step around
# the guard.
_ADV = (rf"(?:un\s+peu|maintenant|tout\s+de\s+suite|vite|donc|enfin|encore"
        rf"|{_A}\s+nouveau|de\s+nouveau|allez|quand\s+{acc('meme')})")

# The real end of a command, politeness and filler aside. Read by every
# $-anchored pattern and by every lazy capture that has to stop somewhere.
_END = rf"(?:\s+(?:{_POLITE}|{_ADV}))*\s*$"

# The control words that trail a neutral verb — «mets la musique PLUS FORT».
# This is French's separable verb: the verb says nothing, the object sits in
# the middle, and the word that decides what happens arrives last.
_C_UP = r"(?:plus\s+fort|plus\s+haut)"
_C_DOWN = r"(?:moins\s+fort|plus\s+bas|plus\s+doucement|moins\s+haut)"
_CTRL = rf"(?:{_C_UP}|{_C_DOWN}|en\s+pause)"

# _END plus the control words: everything that is never part of a station or a
# title name. The ``radio`` guard reads this one and only this one — it has to
# decline «mets la radio plus fort» as well as «mets la radio s'il te plaît»,
# and every word it declines is caught by a step below built from the same
# DEV(). The cross-product test in tests/test_french.py asserts that.
_TAIL = rf"(?:\s+(?:{_POLITE}|{_ADV}|{_CTRL}))*\s*$"

# «n'arrête pas la musique» is not a request to stop. Italian escapes this by
# accident — «ferma» does not match "fermare" — but the French imperative and
# its negation are the same word, so the guard has to be explicit. Both forms
# are fixed-width, which is what a lookbehind requires.
_NEG = rf"(?<!n{AP})(?<!ne\s)"

# «mets-moi», «passe-nous». \b already holds before the hyphen.
_MOI = r"(?:\s*-\s*(?:moi|nous))?"

# `passe` is a play verb («passe-moi du Pink Floyd») and half of two questions
# that are not — «qu'est-ce qui passe» is now-playing, «passe à la suivante»
# is a skip. Listed bare it sets is_play on both, and is_play switches off the
# WHOLE transport block: nowplaying, next, prev, pause. This is de.py's «mach»
# problem — a verb that heads three different commands — solved the same way,
# by recognising the reading only with the words that identify it.
_PASSE = rf"(?<!qui\s)(?<!que\s)passe(?!\s+(?:{_A}|au|aux)\b)"

# The play verbs. ONE list, read by ten patterns, and the reason is the German
# lesson rather than tidiness: whatever any play branch accepts as a verb,
# is_play must accept too, or the transport block stays open and a title gets
# stolen. Two copies of this cannot stay equal.
#
# «mes» and «mais» are deliberately absent though both are /mɛ/ and both are
# what a recogniser writes for «mets». «mais» is one of the twenty commonest
# French words: as a play verb it would set is_play — and so disable pause,
# next, prev and nowplaying — on any sentence that happened to contain it.
# Not understanding «mais Time» is the smaller cost by a wide margin.
_PLAY = (rf"(?:m(?:ets|et)|remets?|joue[rz]?|lance[rz]?|relance"
         rf"|{acc('demarre')}|balance|fais\s+jouer|{acc('ecoute')}[rz]?"
         rf"|je\s+(?:veux|voudrais)\s+{acc('ecouter')}"
         rf"|j{AP}\s*aimerais\s+{acc('ecouter')}"
         rf"|{_PASSE})")

_LOCAL = (rf"(?:de\s+ma\s+(?:musique|{acc('bibliotheque')}|collection)"
          rf"|dans\s+ma\s+(?:musique|{acc('bibliotheque')})"
          rf"|sur\s+(?:le\s+)?disque|en\s+local)")

# The playback itself, split by whether the noun can stand without an article.
#
# «son» cannot, and that is the French trap German has no equivalent of: it is
# also the possessive. «mets son dernier album», «joue son premier disque»,
# «mets son album préféré» are ordinary requests, and a device pattern that
# accepted a bare «son» would answer all three with a volume command.
_DEV_FREE = rf"(?:musique|radio|zique|{acc('chaine')})"
_DEV_HELD = r"(?:son|volume)"
_ART = rf"(?:{_L}|du\s+|de\s+la\s+)"

# The device verbs, split by what they do to the device.
_V_ON = rf"(?:m(?:ets|et)|remets?|allume|lance|relance|{acc('demarre')}|joue)"
_V_OFF = (rf"(?:coupe|{acc('eteins')}|{acc('arrete')}s?|{acc('arreter')}"
          rf"|stoppe|stop)")
_V_UP = rf"(?:monte|augmente|remonte)"
_V_DOWN = rf"(?:baisse|diminue|{acc('reduis')})"


def DEV(verbs: str, ctrl: str = None, end: str = None) -> str:
    """«<verb> <article> <device> [<control>]» — a command aimed at the
    playback itself rather than at anything to play.

    The ``^`` lives in here and not at the call sites, for words_de.py's
    recorded reason: these patterns are ``.search``ed, so unanchored one could
    match anywhere and need only END at «$» — and «mets la chanson Coupe le
    son», a title that ends in a device command, would pause.

    ``end`` is the one argument that is not cosmetic. :data:`_TAIL` (the
    default) lets a step swallow a trailing control word, which is right for
    the stop and volume steps: «coupe la musique plus fort» is a stop. But
    ``resume_explicit`` must pass :data:`_END` instead, because it is checked
    before ``vol_up`` — a resume that accepted «mets la musique PLUS FORT»
    would answer a volume command with ▶.
    """
    end = _TAIL if end is None else end
    tail = rf"\s+(?:{_ADV}\s+)*(?:{ctrl})" if ctrl else ""
    return rf"^(?:{verbs})\s+(?:{_ART}?{_DEV_FREE}|{_ART}{_DEV_HELD}){tail}{end}"
