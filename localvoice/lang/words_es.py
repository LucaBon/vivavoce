"""Spanish word lists the patterns are built from — the closed sets, the two
builders composed out of them, and the two things Spanish forces on this pack
that no other language did.

Beside the patterns for ``base.py``'s reason (a pack holds the grammar, its
word lists live next door), and shared *within* the pack for ``words_de.py``'s
reason, which cost six rounds of review to learn: two patterns that must agree
about a closed set have to read the same name.

**The accent is optional and the meaning is not.** ``router.py`` hands raw
``clean_command(text)`` to the patterns and ``re.I`` folds case but not
accents, so «que suena» and «qué suena» are two different words to a regex, and
the text box writes the first one every time. :func:`acc` is that fact encoded
once — French's mechanism (``words_fr.py``) with a Spanish table, because the
mechanism is arithmetic and the table is the part that belongs to one language.
Spanish's is the smaller of the two: five vowels that take one accent each,
plus ``ñ``.

**The pronoun welds itself onto the verb, and moves the accent when it
does.** «pon» becomes «ponme», «ponlo», «pónmelo»; «sube» becomes «súbelo»;
«quita» becomes «quítala». French hyphenates («mets-moi») and German keeps its
particle at a distance; Spanish writes one word, and the stress mark appears
only once the clitic is there. :data:`_CL` is the cluster, and :func:`acc` is
what makes the accent shift free: a stem spelled as "every vowel may carry an
accent" already matches «súbe», so no verb here is written twice.

What Spanish does NOT need, and it is worth recording because French needed it
badly: no negation guard. The French imperative and its negation are the same
word, so «n'arrête pas la musique» stopped the music. Spanish negates an
imperative with the subjunctive — «no pares», «no quites», «no apagues» — which
is a different word from «para», «quita», «apaga», and ``\\b`` keeps them apart
for free. Italian escapes the same trap the same way.
"""

from __future__ import annotations

import re
import unicodedata

# base letter -> every way a recogniser or a keyboard may write it.
_FAMILIES = {
    "a": "[aá]",
    "e": "[eé]",
    "i": "[ií]",
    "o": "[oó]",
    "u": "[uúü]",
    # «ñ» and «n» are one letter to a recogniser that has dropped the tilde
    # and two to a regex. It costs nothing in the other direction: «ano» and
    # «año» are different words, but neither of them is a command.
    "n": "[nñ]",
}


def _base(ch: str) -> str:
    """``ch`` with its combining mark removed, or ``ch`` if it carries none."""
    stripped = "".join(
        c for c in unicodedata.normalize("NFKD", ch) if not unicodedata.combining(c)
    )
    return stripped or ch


def acc(word: str) -> str:
    """A Spanish word, spelled correctly, as a pattern that also matches every
    way it may arrive.

    ``acc("canción")`` -> ``c[aá][nñ]c[ií][oó][nñ]``. The argument is the real
    Spanish spelling, so a reviewer checks *the Spanish* and the accent
    handling comes for free — which is the whole point of having one of these
    rather than forty hand-written alternations that will disagree.

    It is also what makes the clitic accent free: ``acc("sube")`` matches
    «súbe», so «súbelo» is that plus :data:`_CL` and not a second entry.

    It also accepts spellings that are not Spanish («cánción»). That costs
    nothing: those strings are not titles either.
    """
    return "".join(
        _FAMILIES.get(_base(ch), re.escape(_base(ch))) for ch in word.lower()
    )


# The accented letters written out for use INSIDE a character class, where an
# alternation cannot go: the pick patterns capture a bare token, and without
# these «la décima» never reaches ``_as_number`` at all. de.py widened its own
# class to [a-z0-9äöüß] and fr.py to the vowel families for exactly this.
_ACCLASS = "áéíóúüñ"

# The clitic pronouns, welded to the imperative and stacked up to two deep:
# «ponme», «ponlo», «pónmelo», «quítamela». Written as a repeated group rather
# than as spelled-out combinations, because the combinations are a product and
# the pieces are a list. Optional throughout — a bare «pon» is the commonest
# form of all.
_CL = r"(?:me|te|nos|se|le|les|lo|la|los|las)*"

# The definite article. Read by every step that names a thing («pon el álbum
# X», «pon la lista Y») and by the device builder below.
_L = r"(?:el\s+|la\s+|los\s+|las\s+)"

# "of", which Spanish spends on both jobs this pack cares about: introducing an
# artist («la música de Rosalía») and introducing a mood («algo de jazz»).
# Longest alternative first, or `de\s+` eats the head of «de los» and the step
# captures "los Planetas" as a title. Same lesson as connectors/it.py's
# «dell'» and words_fr.py's «de la».
_DE = r"(?:de\s+la\s+|de\s+los\s+|de\s+las\s+|del\s+|de\s+)"

# Politeness. It lands AFTER the object in Spanish, exactly as in French, so it
# hits every $-anchored pattern and rides along inside every greedy capture:
# «pon la radio por favor» asks LMS for a station called "por favor" without
# it. Italian carries «per favore|grazie» in one pattern and gets away with it
# because it is rarer there; Spanish needs it in nearly all of them.
_POLITE = r"(?:por\s+favor|porfa|porfi|gracias|si\s+eres\s+tan\s+amable)"

# Words that may stand between a command and its end, and that the router acts
# on none of. words_de.py's ``_ADV`` and words_fr.py's, transposed — and
# repeated (``*``) rather than optional (``?``) for the same reason: «quita la
# música ya por favor» is ordinary Spanish, and one slot let the second one
# step around the guard.
_ADV = (rf"(?:un\s+poco|ahora\s+mismo|ahora|ya|venga|vale|anda"
        rf"|otra\s+vez|de\s+nuevo|enter[oa]|del\s+{acc('tirón')}"
        # Nothing repeats a track, so «en bucle» is a word the router acts on
        # exactly as much as it acts on «ahora»: it belongs to the phrasing,
        # not to the title. Absorbing it here is what keeps «pon Time en
        # bucle» a request for *Time*.
        rf"|en\s+bucle|en\s+{acc('repetición')})")

# What a person may put in FRONT of an imperative without changing it. A closed
# list rather than «any two words», for the reason words_fr.py records at
# length: the words this must never admit are «qué», «quién» and «esto», which
# are the whole reason ``is_play`` is anchored in the first place.
_LEAD = (rf"(?:oye|bueno|pues|vale|venga|y|luego|{acc('después')}|ok"
         rf"|a\s+ver|mira|{_POLITE})")

# The real end of a command, politeness and filler aside. Read by every
# $-anchored pattern and by every lazy capture that has to stop somewhere.
_END = rf"(?:\s+(?:{_POLITE}|{_ADV}))*\s*$"

# The control words that trail a neutral verb — «pon la música MÁS ALTA». This
# is Spanish's version of French's separable verb: the verb says nothing, the
# object sits in the middle, and the word that decides what happens arrives
# last. The adjective agrees with the noun, so both endings are here — «más
# alto» for «el volumen», «más alta» for «la música».
_C_UP = rf"{acc('más')}\s+(?:alt[oa]|fuerte|volumen)"
_C_DOWN = (rf"(?:{acc('más')}\s+(?:baj[oa]|bajit[oa]|floj[oa]|suave)"
           rf"|menos\s+(?:alt[oa]|fuerte))")
_CTRL = rf"(?:{_C_UP}|{_C_DOWN}|en\s+pausa)"

# _END plus the control words: everything that is never part of a station or a
# title name. The ``radio`` guard reads this one and only this one — it has to
# decline «pon la radio más alta» as well as «pon la radio por favor», and
# every word it declines is caught by a step built from the same DEV(). The
# cross product in tests/test_spanish.py asserts that.
_TAIL = rf"(?:\s+(?:{_POLITE}|{_ADV}|{_CTRL}))*\s*$"

# The play verbs. ONE list, read by ten patterns, and the reason is the German
# lesson rather than tidiness: whatever any play branch accepts as a verb,
# ``is_play`` must accept too, or the transport block stays open and a title
# gets stolen. Two copies of this cannot stay equal.
#
# «pone» and «poné» are the third person and the voseo imperative — what a
# River Plate speaker says, and what a recogniser writes when it hears «pon»
# with a trailing vowel. «ponga»/«póngame» is the usted form, which is
# ``acc("ponga")`` plus a clitic and not a fourth entry. All of them are the
# same request; none of them is anything else.
#
# «toca» is here and «suena» is not, though both are what an instrument does.
# «suena» is how the now-playing question is asked — «¿qué suena?» — and as a
# play verb it would set is_play, which gates the WHOLE transport block off.
# That is words_fr.py's «passe» problem; Spanish escapes it by leaving the word
# out, because nobody asks a hi-fi to «suena algo».
_PLAY = (rf"(?:{acc('pon')}{_CL}|{acc('ponga')}{_CL}|poner|pon[eé]"
         rf"|{acc('coloca')}{_CL}|pincha{_CL}|echa{_CL}|mete{_CL}"
         rf"|reproduce{_CL}|{acc('escucha')}{_CL}|{acc('toca')}{_CL}"
         rf"|quiero\s+(?:escuchar|{acc('oír')}|poner)"
         rf"|{acc('quería')}\s+escuchar"
         rf"|me\s+apetece\s+(?:escuchar|{acc('oír')}))")

_LOCAL = (rf"(?:de\s+mi\s+(?:{acc('música')}|biblioteca|{acc('colección')})"
          rf"|en\s+mi\s+(?:{acc('música')}|biblioteca)"
          rf"|del\s+disco(?:\s+duro)?|en\s+local)")

# The playback itself. Both nouns take an article here, even the two that could
# stand without one: «pon música» is not «pon la música». The first names no
# record and is the ordinary way to ask for something to listen to — the mood
# step reads it — and the second is the Spanish for pressing ▶. Requiring the
# article is what keeps them apart, and it is the one place this pack is
# stricter than fr.py, which lets «mets musique» resume.
_DEV_FREE = rf"(?:{acc('música')}|radio|{acc('reproducción')})"
_DEV_HELD = r"(?:volumen|sonido)"
_ART = rf"(?:{_L}|del\s+|de\s+la\s+)"

# The device verbs, split by what they do to the device.
#
# _V_ON is _PLAY plus «enciende» and «arranca», and that is the point rather
# than a shorthand. The ``radio`` guard declines a phrase using _PLAY, and
# every step that must catch what it declines is built from this list. Written
# as a second, shorter list — which is how French started — the verbs in _PLAY
# and not in it fall past every catcher to the play step and start a stream.
# A catcher may be WIDER than the guard, never narrower.
_V_ON = rf"(?:{_PLAY}|enciende{_CL}|arranca{_CL})"

# «para» is here and nowhere else, and that is the Spanish decision of this
# file. Bare, it is the commonest preposition in the language: «música PARA
# dormir», «algo PARA cenar», «Para Todos los Públicos». The ``pause`` step is
# only gated on ¬is_play, so a bare title carrying it — picked from an open
# list, or typed — reaches an unanchored `\bpara\b` and pauses the hi-fi.
# Inside DEV() it has to be followed by an article and a device noun, which no
# preposition ever is.
_V_OFF = (rf"(?:{acc('para')}{_CL}|{acc('quita')}{_CL}|{acc('apaga')}{_CL}"
          rf"|corta{_CL}|{acc('detén')}{_CL}|silencia{_CL}|pausa{_CL}|stop)")
_V_UP = rf"(?:{acc('sube')}{_CL}|aumenta{_CL}|incrementa{_CL})"
_V_DOWN = rf"(?:{acc('baja')}{_CL}|reduce{_CL}|disminuye{_CL})"


def DEV(verbs: str, ctrl: str = None, end: str = None) -> str:
    """«<verb> <article> <device> [<control>]» — a command aimed at the
    playback itself rather than at anything to play.

    The ``^`` lives in here and not at the call sites, for words_de.py's
    recorded reason: these patterns are ``.search``ed, so unanchored one could
    match anywhere and need only END at «$» — and «pon la canción Quita el
    Volumen», a title that ends in a device command, would pause.

    ``end`` is the one argument that is not cosmetic. :data:`_TAIL` (the
    default) lets a step swallow a trailing control word, which is right for
    the stop and volume steps: «quita la música más alta» is a stop. But
    ``resume_explicit`` must pass :data:`_END` instead, because it is checked
    before ``vol_up`` — a resume that accepted «pon la música MÁS ALTA» would
    answer a volume command with ▶.
    """
    end = _TAIL if end is None else end
    tail = rf"\s+(?:{_ADV}\s+)*(?:{ctrl})" if ctrl else ""
    return (rf"^(?:{_LEAD}[,\s]+)*(?:{verbs})\s+{_ART}"
            rf"(?:{_DEV_FREE}|{_DEV_HELD}){tail}{end}")
