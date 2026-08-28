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
match first and hand the particle on.

A title that really ends in a particle («Wach auf») survives in
``generic_play`` and nowhere else — that is why the plain verbs stand alone
there. The named-thing steps (``album``, ``playlist``, ``artist``) must list
the separable verbs, «leg das Album Nevermind auf» being ordinary German, so
they strip the particle whatever the verb was and «spiel das Album Steh auf»
loses its "auf". A real cost, written here because nobody looks for it in a
step comment.

**«mach» is not a play verb on its own.** It heads «mach lauter» (volume),
«mach aus» (stop) and «mach die Musik an» (play) alike, so ``is_play`` asks
for the particle too and the volume and stop forms stay reachable. The words
that may stand between a verb and its particle, and the verbs and nouns a
command aimed at the playback itself is built from, are the shared ``_ADV`` /
``_VERB_DEV`` / ``_DEVICE`` below: six review rounds found the same defect
whenever two patterns spelled one of those lists out separately.

**The adjective moves.** German puts the mood on either side of the marker
noun — «etwas Entspannendes», «etwas entspannende Musik» — so ``mood`` allows
a trailing «Musik»/«Lieder» after the captured tail, the trick ``en.py`` uses
for "some upbeat music". It does not drop the marker: «spiel entspannende
Musik» stays a title search, exactly as "play relaxing music" does in English,
because the marker noun is one of the three conditions that keep an identified
request identified.

Umlauts are written as alternations (``h(?:ö|oe)r``) throughout: browser ASR
and typed input disagree about them constantly, and one spelling is a silent
miss. ``MOOD_WORDS`` keys are folded instead (``frohlich``, ``fur die party``),
because that table is looked up on the *normalized* tail — see ``it.py``.
"""

from __future__ import annotations

from .base import c
# Spoken tail -> mood key: a word list, not grammar, so it has a module of
# its own. Imported (not just referenced) because the pack contract in
# ``base.py`` asks the *pack* for MOOD_WORDS.
from .moods_de import MOOD_WORDS  # noqa: F401
# Spoken numbers and durations, same reasoning — see numbers_de.py.
from .numbers_de import (  # noqa: F401
    DURATIONS, MINUTE_WORDS, NUM_WORDS, ORDINAL_WORDS)

CODE = "de"
# The closed word lists these patterns are built from.
from .words_de import _ADV, _DEV, _DEVICE, _LOCAL, _VERB_DEV  # noqa: F401

# One entry per routing step; the handle() flow is identical across languages.
# ``service`` is a template expanded per streaming service name.
PATTERNS = {
    # «mach» only counts with its particle — see the module docstring.
    # ``spielt``/``spielst`` are deliberately NOT here: they are how the
    # question is asked («was spielt gerade»), not how the command is given,
    # and is_play is what switches the whole transport block off.
    "is_play": c(r"\b(?:spiel(?:e|en)?|abspielen|leg(?:e)?|starte?"
                 r"|h(?:ö|oe)r(?:e|en)?|auflegen)\b"
                 # Anchored at the end, not measured in characters: a
                 # separable particle goes LAST, and a window («mach» within
                 # 30 characters of «an») is a length limit on titles wearing
                 # a grammar rule's clothes. «mach die Playlist Zurück in die
                 # Zukunft an» is 32, so is_play went False, the transport
                 # block opened, and «zurück» skipped to the previous track.
                 #
                 # The particles ``generic_play_suffix`` accepts, not just
                 # «an»: «mach Zurück auf» left is_play False and «prev»
                 # skipped a track instead of playing the record. «aus» is
                 # pointedly absent — that one is the stop command — and so
                 # is «hören», which the first alternative above already
                 # matches («hören» is «hör» plus an ending).
                 #
                 # It costs the awkward «mach das nächste Lied auf», which
                 # now searches instead of skipping. The phrasing people
                 # actually use, «… an», was already a search before this,
                 # so nothing anyone says out loud changed hands.
                 r"|\bmach(?:e)?\b.*\b(?:an|auf|ab)\s*$"
                 r"|\bich\s+(?:will|m(?:ö|oe)chte|mag)\b"),
    # «hör auf» belongs here rather than in ``pause``, and for the reason
    # «metti in pausa» does in Italian: it carries a play verb, so the
    # is_play gate would never let ``pause`` see it, and the phrase went
    # looking for a song called "auf".
    #
    # Two things this must NOT do, and the first draft did both. The verb's
    # ending is spelled out rather than left as ``\w*``: German builds nouns
    # on the same stem, so «leg das Hörbuch auf» — a staple of an LMS library
    # — paused the player instead of playing the audiobook. And what may
    # stand between the verb and the particle is a CLOSED LIST of adverbs,
    # not a character window: a window is a length limit on titles wearing a
    # grammar rule's clothes, which is the exact flaw ``is_play`` below had.
    # With the list, «hör Wach Auf» is not stolen either — "Wach" is not an
    # adverb — so the pattern now costs nothing at all.
    #
    # «hör auf zu spielen» is the same alternative with a tail, NOT one of
    # its own. Given its own — a bare «auf zu spielen» matched anywhere — it
    # inverted the sentence («hör NICHT auf zu spielen» paused: nothing bound
    # the phrase to a verb the negation could precede) and swallowed «hör in
    # einer Stunde auf zu spielen», which is a timer.
    #
    # What it costs, said accurately: a title made of «hör» plus one of the
    # _ADV words plus «auf» — «spiel Hör mal auf» and «spiel Hör Du Auf»
    # pause. Not nothing, but the list is closed, so the cost is enumerable
    # instead of being whatever fits in fifteen characters.
    "pause_explicit": c(r"\bauf\s+pause\b"
                        r"|\bh(?:ö|oe)r(?:e|en|st|t)?\b"
                        rf"(?:\s+{_ADV})*"
                        r"\s+auf(?:\s+zu\s+(?:spielen|h(?:ö|oe)ren))?\s*$"
                        # «mach das Radio aus» and every verb it comes with.
                        # Here rather than in ``pause`` because that step is
                        # gated on ``not is_play`` and every one of these
                        # verbs sets it.
                        #
                        # No «ab»: ``abspielen`` is the German for "to play
                        # back" and the particle is a PLAY one in four other
                        # patterns here, so it sits with «an» in
                        # ``resume_explicit``.
                        rf"|{_DEV}(?:aus|stopp?)\s*$"),
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
                         r"|(?:spiel(?:e)?|mach(?:e)?)\s+weiter"
                         # «mach die Musik an» names no title: it is the
                         # German for pressing ▶, and reading it as a request
                         # for a record called "die Musik" searched the
                         # library for the word. «weiter» is the same
                         # sentence after a pause.
                         #
                         # What it costs is four one-word titles: a record
                         # called exactly *Musik*, *Radio* (Rammstein, 2019),
                         # *Anlage* or *Mucke* cannot be asked for this way.
                         # The escape hatch is to name what it is — «mach das
                         # Album Radio an» reaches the album step untouched —
                         # and the trade is worth it because the four words
                         # are how everyone in the house says ▶.
                         r"|(?:mach(?:e)?|schalt(?:e)?|spiel(?:e)?)\s+"
                         r"(?:d(?:ie|as|en)\s+)?"
                         rf"{_DEVICE}"
                         rf"\s+(?:{_ADV}\s+)*(?:an|weiter))\s*$"
                         # The same sentence with the other verbs, and with
                         # «auf» («mach das Radio auf» is how it is said in
                         # the south) and «ab» («spiel die Musik ab» is
                         # ``abspielen``, split — it starts music, it does
                         # not stop it).
                         rf"|{_DEV}(?:an|auf|ab|weiter)\s*$"),
    "resume": c(r"\b(weiter|weiterspielen|weitermachen|fortsetzen"
                r"|fortfahren|play)\b"),
    # Prefix matching, like the Italian pack: German inflects the ending.
    "next": c(r"\b(n(?:ä|ae)chst|(?:ü|ue)berspring|skip|vorw(?:ä|ae)rts)"),
    "prev": c(r"\b(vorherig|vorig|zur(?:ü|ue)ck|r(?:ü|ue)ckw(?:ä|ae)rts)"),
    # Both halves name the direction, so «mach die Lautstärke leiser» can
    # never reach the "up" branch on the strength of the noun alone.
    "vol_up": c(r"lautst(?:ä|ae)rke\b.{0,20}\b(?:h(?:ö|oe)her|hoch|rauf"
                r"|lauter|erh(?:ö|oe)hen?)"
                r"|\b(?:erh(?:ö|oe)he|steigere)\b.{0,20}\blautst(?:ä|ae)rke"
                rf"|{_DEV}lauter\s*$"),
    "vol_down": c(r"lautst(?:ä|ae)rke\b.{0,20}\b(?:niedriger|runter|leiser"
                  r"|verringern?|reduzieren?|senken?)"
                  r"|\b(?:verringere|reduziere|senke)\b.{0,20}"
                  r"\blautst(?:ä|ae)rke"
                  rf"|{_DEV}leiser\s*$"),
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
               r"|aufh(?:ö|oe)ren|schlaftimer|schluss)\b"
               # The split form of the same verb: «hör in 30 Minuten auf»
               # (and «… auf zu spielen») keeps its particle at the very end,
               # where the one-word alternatives above cannot see it. Without
               # this the phrase fell past the timer and reached
               # ``pause_explicit``, which paused at once.
               #
               # The verb half is a nested lookahead, not a second ``.*``:
               # two unbounded stars in sequence backtrack against each other,
               # and on a 64 KB body — which is exactly what
               # ``httpbase.MAX_JSON_BYTES`` allows an unauthenticated POST to
               # /api/v1/command — this pattern took 3.3 seconds instead of
               # four milliseconds. Zero-width, it is scanned once.
               #
               # Unlike ``pause_explicit`` above, this asks only whether a
               # stop verb is present ANYWHERE, with no closed list between
               # the halves — which is how every other alternative here has
               # always worked, and it is safe for a reason that pattern has
               # no equivalent of: the captured tail must still parse through
               # DURATIONS, so a phrase that is not a duration falls through.
               r"|(?=.*\bh(?:ö|oe)r(?:e|en|st|t)?\b)"
               r".*\bauf(?:\s+zu\s+(?:spielen|h(?:ö|oe)ren))?\s*$)"
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
    # The lookahead is «mach das Radio an»: with the separable verbs listed
    # here, a bare control word is all that follows «Radio», and the step
    # answered «Ich habe keinen Radiosender namens an gefunden» — after
    # asking LMS, because this step runs at 0b, before the transport block
    # that should have had the phrase.
    #
    # It has to cover every such word, not only the separable particles.
    # «mach das Radio aus» is the stop command and was the same bug one
    # particle over; «leiser»/«lauter»/«weiter» are the volume and resume
    # forms. And the guard sits BEFORE the whitespace it guards: after a
    # greedy ``\s+`` the regex can hand a space back and slip past it, so a
    # typed double space («mach das radio  an») asked for a station named
    # " an". Nothing upstream collapses inner whitespace.
    "radio": c(r"\b(?:spiel(?:e|en)?|mach(?:e)?|leg(?:e)?|starte?)\s+"
               r"(?:d(?:as|en|ie)\s+)?radio(?:sender)?\b"
               # _ADV because an exact-final guard is defeated by one word
               # («mach das Radio bitte aus» asked for a station called
               # "bitte aus"). Every word declined here is caught by a step
               # below, built from the same _DEV and asserted by the
               # cross-product test: five reviews running found the same
               # thing — a guard widened, its catcher not widened with it.
               rf"(?!\s*(?:{_ADV}\s+)*"
               r"(?:an|auf|ab|aus|lauter|leiser|weiter|stopp?)\s*$)"
               r"\s+(.+?)(?:\s+(?:an|auf|ab))?\s*$"),
    "choose_number": c(r"(?:spiel(?:e)?|nimm|w(?:ä|ae)hl(?:e)?)?\s*"
                       r"(?:die\s+)?nummer\s+([a-z0-9äöüß]+)\s*$"),
    # «die 2» and ordinals: «die zweite», «spiel das zweite Lied»
    "choose_article": c(r"(?:spiel(?:e)?|nimm|w(?:ä|ae)hl(?:e)?)?\s*"
                        r"d(?:ie|as|er|en)\s+([a-z0-9äöüß]+)"
                        r"(?:\s+(?:lied|song|st(?:ü|ue)ck|titel|option))?\s*$"),
    "local_prefix": c(rf"{_LOCAL}\s+(?:spiel(?:e)?\s+|leg(?:e)?\s+)?(.+)$"),
    "local_suffix": c(rf"\b(?:spiel(?:e|en)?|leg(?:e)?|starte?)\s+(.+?)\s+"
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
    # The three named-thing steps all list the separable verbs, so all three
    # need the particle taken back off: «leg das Album Nevermind auf» named
    # an album called "Nevermind auf", and nothing downstream strips it — it
    # went into the LMS search and dragged every score down. The trailing
    # group is optional and lazy-bounded, so the plain forms are untouched.
    # It costs an album or artist whose name really ends in «an»/«auf»/«ab»,
    # which is the same trade ``generic_play_suffix`` already makes and the
    # opposite of the one ``generic_play`` makes — there, the plain verbs are
    # alone, so nothing has to be given up at all.
    "album": c(r"\b(?:spiel(?:e|en)?|leg(?:e)?|starte?|mach(?:e)?)\s+"
               r"(?:d(?:as|ie|en)\s+)?album\s+"
               r"(.+?)(?:\s+(?:an|auf|ab))?\s*$"),
    "playlist": c(r"\b(?:spiel(?:e|en)?|leg(?:e)?|starte?|mach(?:e)?)\s+"
                  r"(?:d(?:ie|as)\s+)?playlist\s+"
                  r"(.+?)(?:\s+(?:an|auf|ab))?\s*$"),
    # Only «von» introduces the artist, and only behind a word that says a
    # person is coming: «spiel Musik von X», never a bare «von» — half the
    # German song titles in a library contain one.
    "artist": c(r"\b(?:spiel(?:e|en)?|leg(?:e)?|starte?|mach(?:e)?)\s+"
                r"(?:(?:etwas|was|alles|nur)\s+von"
                r"|(?:d(?:ie|as)\s+)?(?:musik|lieder|songs|titel|st(?:ü|ue)cke)"
                r"\s+von"
                r"|d(?:en|ie)\s+k(?:ü|ue)nstler(?:in)?)\s+"
                r"(.+?)(?:\s+(?:an|auf|ab))?\s*$"),
    # No «leg»/«mach» here: those are separable and land in the suffix form
    # below, which is the only one that strips the particle. See the module
    # docstring — this is what lets «spiel Wach Auf» keep its "auf".
    # The \b is load-bearing in German in a way it is not in the other two
    # packs: the verbs compound. Without it «hör» matched inside «gehöre» and
    # «start» inside «Neustart», so a bare title reaching this step — which
    # is how a pick from an open list arrives — searched for its own tail:
    # «Ich gehöre nur mir» looked for "nur mir".
    "generic_play": c(r"\b(?:spiel(?:e|en)?|abspielen|starte?"
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
