"""German word lists the patterns are built from — the closed sets, and the
one phrase shape composed out of them.

Beside the patterns for the reason ``moods_de.py`` and ``numbers_de.py`` are:
``base.py`` says a pack module holds the grammar and its word lists live next
to it, and ``_ADV``/``_VERB_DEV``/``_DEVICE`` are word lists — enumerations of
what a person may say, not statements about how the language is shaped.

They are here rather than inline for a second reason that cost six rounds of
review to learn: every one of these was spelled out separately in two or three
patterns, and every round found the next place the copies disagreed. Two
patterns that must agree about a closed set have to read the same name.
"""

from __future__ import annotations

_LOCAL = (r"(?:aus\s+meiner\s+(?:musik|bibliothek|sammlung)"
          r"|von\s+(?:der\s+)?(?:festplatte|platte)|lokal)")

# Words that may stand between a verb and its separable particle («hör BITTE
# auf») or between a noun and the control word after it («mach das Radio
# WIEDER an»). German drops them everywhere; a router acts on none of them.
#
# ONE list, read by the three patterns that step over them, and that is the
# point rather than tidiness. Spelled out three times with three different
# sets of words, it produced the same defect every round: one pattern's guard
# was widened, the pattern catching what it declines was not, and the phrase
# fell through to something that acts — «mach das Radio wieder an» reached the
# play step and started a stream. A closed list can only do that when there is
# more than one copy of it.
#
# Repeated (``*``), not optional (``?``): «mach das Radio jetzt bitte aus» is
# ordinary German, and one slot let the second adverb step around the guard.
_ADV = (r"(?:bitte|jetzt|endlich|sofort|mal|doch|auch|damit|schon|ganz"
        r"|wieder|nochmal|du|ihr|sie)")

# «<verb> <article> <thing> <adverbs…>» — everything a command aimed at the
# music itself carries before the word that says what to do with it.
#
# The same lesson as _ADV, one seam over. Sharing the adverbs was necessary
# and not sufficient: the ``radio`` guard declined four verbs and eight
# control words while the steps after it accepted three verbs and two words,
# so «starte das Radio wieder an» fell past every catcher to the play step
# and started a stream. Three lists that must agree are three lists that will
# not. The two cross-product tests in tests/test_german.py assert both
# directions, so the next gap is a failing test rather than a seventh review.
_VERB_DEV = r"(?:spiel(?:e|en)?|mach(?:e)?|leg(?:e)?|starte?|schalt(?:e)?)"
_DEVICE = r"(?:musik|radio(?:sender)?|anlage|mucke)"
# The ``^`` is in the constant, not in its call sites: three of the four
# spliced it in unanchored and one anchored it, and since these patterns are
# ``.search``ed, a match could start anywhere and need only END at «$» — so
# «spiel den Song Mach die Musik aus», a title that ends in a device command,
# paused. «der» is the wrong gender and stays anyway: anchored, it can only
# match a device command at position 0, and German ASR gets genders wrong.
_DEV = rf"^{_VERB_DEV}\s+(?:d(?:ie|as|en|er)\s+)?{_DEVICE}\s+(?:{_ADV}\s+)*"
