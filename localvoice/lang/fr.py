"""French language pack — see ``base.py`` for the contract and ``words_fr.py``
for the word lists these patterns are composed from.

Three things French does that Italian, English and German do not, and each one
decided a pattern rather than being translated into it.

**The play verbs are also the words a question about the music is asked with.**
«qu'est-ce qui PASSE», «ça JOUE quoi», «j'ÉCOUTE quoi là» all carry a verb from
:data:`~lang.words_fr._PLAY`, and ``is_play`` gates the *whole* transport
block — nowplaying, pause, next, prev. Left unanchored, asking what is playing
switched off the ability to ask. So ``is_play`` here is anchored to imperative
position, and ``generic_play`` is anchored the same way: whatever one play
branch accepts as a verb the other must accept too, or the block stays open and
a title gets stolen. That is the German lesson about particles, transposed to
verbs. The anchor admits a closed list of discourse particles in front
(:data:`~lang.words_fr._LEAD`) and nothing else — not «any two words», because
the words it must never admit are «ça», «on» and «qui», which are the reason
it is anchored. It was written without that list first, and «alors, mets Time»
looked like the whole cost because it falls back harmlessly. It was not: the
transport steps are unanchored searches, so «et mets la chanson Stop» did not
fall back, it paused.

**The control word arrives last, and on either side of the object.** «monte le
son» puts it in front, «mets la musique plus fort» puts it behind a verb that
says nothing by itself — which is German's separable verb with French parts. A
``generic_play`` capturing ``(.+)$`` swallows "la musique plus fort" and
searches for it, so the device steps are built from one shared
:func:`~lang.words_fr.DEV` and they, not the play step, get the phrase first.

**Politeness lands after the object, not inside the phrase.** «mets la radio
s'il te plaît» asked LMS for a station called "s'il te plaît"; «mets la
deuxième stp» stopped being a pick; «mets Time s'il te plaît» searched for a
song by that name. Every `$`-anchored pattern and every lazy capture therefore
ends at ``_END`` rather than at ``$``. It costs the tail of a title that ends
in a filler word — «mets Encore un peu» searches for "Encore" — which is the
same trade German makes with «bitte».
"""

from __future__ import annotations

from .base import c
# Spoken tail -> mood key: a word list, not grammar, so it has a module of
# its own. Imported (not just referenced) because the pack contract in
# ``base.py`` asks the *pack* for MOOD_WORDS.
from .moods_fr import MOOD_WORDS  # noqa: F401
# Spoken numbers and durations, same reasoning — see numbers_fr.py.
from .numbers_fr import (  # noqa: F401
    DURATIONS, MINUTE_WORDS, NUM_WORDS, ORDINAL_WORDS)

CODE = "fr"
# The closed word lists these patterns are built from, and the two builders
# composed out of them.
from .words_fr import (  # noqa: F401
    AP, DEV, _A, _ACCLASS, _ADV, _C_DOWN, _C_UP, _DE, _END, _L, _LEAD, _LOCAL,
    _MOI, _NEG, _PAS, _PLAY, _POLITE, _TAIL, _V_DOWN, _V_OFF, _V_ON, _V_UP,
    acc)

# An explicit source in front of the verb («sur Tidal mets Time», «de Qobuz
# joue Time»), so the anchor above does not cost the one phrase shape that
# legitimately puts words before the imperative. Only ``is_play`` reads it:
# it is a gate and captures nothing, and the ``service`` step below does the
# actual splitting.
_SRC = r"(?:(?:sur|depuis|avec|via|de|dans)\s+\w+\s+)?"

PATTERNS = {
    # Anchored — see the module docstring. This is the French decision of the
    # file, and the one to re-read before widening anything below.
    "is_play": c(rf"^(?:{_LEAD}[,\s]+)*{_SRC}(?:{_LOCAL}\s+)?(?:{_PLAY})\b"),

    # -- transport -----------------------------------------------------------
    # «mets la musique en pause» carries a play verb, so the `pause` step —
    # gated on ¬is_play — would never see it. Same seam as it.py's «in pausa».
    "pause_explicit": c(rf"\ben\s+pause\b|{DEV(_V_OFF)}"),
    # The negation guard is not decoration: the French imperative and its
    # negation are the same word, so «n'arrête pas la musique» matched the
    # stop verb and stopped. Italian escapes this by accident («ferma» does
    # not match "fermare"), French does not.
    "pause": c(rf"\b(?:pause|stop|{_NEG}{acc('stoppe')}|{_NEG}{acc('arrête')}s?"
               rf"|{_NEG}{acc('éteins')}|{_NEG}coupe)\b{_PAS}"),
    # Bare ▶, and the device form: «mets la musique» / «allume la radio» name
    # nothing to play — they are the French for pressing play, and read as a
    # request they searched the library for the word «musique». It costs the
    # one-word titles *La Musique* and *La Radio*, with the same escape hatch
    # German has: «mets l'album Radio» reaches the album step.
    #
    # `end=_END` and not the default `_TAIL`, which is the subtlest line in
    # this file: this step is checked before vol_up, so a resume that also
    # swallowed a trailing control word would answer «mets la musique PLUS
    # FORT» with ▶ instead of turning it up.
    "resume_explicit": c(rf"^(?:play|reprends|relance|continue)\s*$"
                         rf"|{DEV(_V_ON, end=_END)}"),
    "resume": c(rf"\b(?:reprends|reprendre|repars|continue|play"
                rf"|{acc('redémarre')})\b"),
    # Prefix matching, like it.py. «retour» is deliberately absent: *Le Retour
    # de l'Enfant Prodigue* is a record, and this step is only gated on
    # ¬is_play, which does not protect a bare title picked from an open list.
    # «passe cette chanson» and «passe celle-là» are skips, and words_fr's
    # _PASSE declines them as play verbs so they can get here — which only
    # helps if this step actually accepts them. Guard and catcher again.
    "next": c(rf"\b(?:suivant|prochain|saute|zappe|avance|skip"
              rf"|{acc('morceau')}\s+d{AP}?\s*{acc('après')}"
              rf"|(?:passe|saute)\s+(?:cette|celui|celle))"),
    "prev": c(rf"\b(?:{acc('précédent')}|d{AP}\s*avant|en\s+{acc('arrière')}"
              rf"|reviens|retourne)"),

    # -- volume --------------------------------------------------------------
    # Both halves name the direction, so the noun alone can never reach the
    # wrong branch. «son» only ever behind an article — bare it is the
    # possessive, and «mets son dernier album» is a request to play. The
    # DEV() forms carry the article requirement; the verbs here are
    # volume-only, so a loose article costs nothing.
    # The loose form is ANCHORED, unlike it.py's «alza … volume». It is the
    # only branch here that is not gated on ¬is_play, and unanchored it read
    # a title as a command: «mets le titre Monte le son» turned the volume up
    # and played nothing. DEV() carries its own ^ for the same reason.
    "vol_up": c(rf"^(?:{_LEAD}[,\s]+)*(?:{_V_UP})\b.{{0,12}}"
                rf"\b(?:{_L}|du\s+)?(?:son|volume)\b"
                rf"|{DEV(_V_UP)}|{DEV(_V_ON, _C_UP)}"),
    "vol_down": c(rf"^(?:{_LEAD}[,\s]+)*(?:{_V_DOWN})\b.{{0,12}}"
                  rf"\b(?:{_L}|du\s+)?(?:son|volume)\b"
                  rf"|{DEV(_V_DOWN)}|{DEV(_V_ON, _C_DOWN)}"),
    # Loose forms that name no control — gated on is_play in the router, so
    # «mets Plus Fort» (Nolwenn Leroy) still plays it. Same trade as it.py's
    # «più forte» and de.py's «lauter», and «plus» earns it: it is "more" in
    # half the French catalogue.
    "vol_up_loose": c(rf"{_C_UP}"),
    "vol_down_loose": c(rf"{_C_DOWN}"),

    # -- sleep ---------------------------------------------------------------
    # The captured tail must parse as a duration (see DURATIONS), which is
    # what keeps a title carrying «dans» from becoming a timer. «pause»
    # belongs here for it.py's reason: it carries the word the pause step
    # wants, and that step would fire at once.
    "sleep": c(rf"(?:{acc('arrête')}s?|{acc('arrêter')}|{acc('éteins')}|coupe"
               rf"|{acc('stoppe')}|stop|pause|dodo)\b.{{0,25}}?"
               rf"\bdans\s+(.+)$"),
    "sleep_cancel": c(rf"^(?:annule|{acc('enlève')}|supprime|retire"
                      rf"|{acc('désactive')})\b.{{0,20}}"
                      rf"(?:minuterie|minuteur|timer|sleep|{acc('arrêt')})"),

    # -- info ----------------------------------------------------------------
    # Gated on ¬is_play, so «mets C'est Quoi Ce Bordel» stays a play. The
    # apostrophe classes are load-bearing rather than tidy: «qu'est-ce» and
    # «c'est» are how the question is asked, and both glyphs occur.
    "nowplaying": c(rf"\bqu{AP}?\s*est[\s-]?ce\s+(?:qui|qu{AP}?\s*on|que)\b"
                    rf".{{0,20}}\b(?:passe|joue|{acc('écoute')})\b"
                    rf"|\bc{AP}?\s*est\s+quoi\b.{{0,20}}"
                    rf"\b(?:{acc('chanson')}|{acc('morceau')}|titre|{_A})\b"
                    rf"|\bqui\s+(?:chante|c{AP}?\s*est)\b"
                    # «ça joue quoi», «on écoute quoi», «j'écoute quoi» —
                    # the shape the module docstring cites as the reason
                    # is_play is anchored, which the anchor alone only made
                    # harmless rather than answerable.
                    rf"|\b(?:{acc('ça')}\s+|on\s+|j{AP}\s*|tu\s+)"
                    rf"(?:joue|passe|{acc('écoute')})s?\s+quoi\b"
                    rf"|\bc{AP}?\s*est\s+quel\s+"
                    rf"(?:{acc('morceau')}|titre|{acc('chanson')})\b"
                    rf"|\bquel\s+est\s+ce\s+(?:{acc('morceau')}|titre)\b"
                    rf"|\ben\s+train\s+de\s+jouer\b"),

    # -- queue ---------------------------------------------------------------
    # Checked ahead of the generic play verbs, so «à la file d'attente» and
    # «après celle-là» never get swallowed as part of a title.
    "queue_add": c(rf"\b(?:ajoute|m(?:ets|et)|rajoute)\s+(.+?)\s+"
                   rf"(?:{_A}\s+la\s+|dans\s+la\s+|en\s+)"
                   rf"(?:file\s+d{AP}?\s*attente|liste\s+d{AP}?\s*attente"
                   rf"|file|queue|suite){_END}"),
    "queue_insert": c(rf"\b(?:m(?:ets|et)|joue|passe)\s+(.+?)\s+"
                      rf"(?:juste\s+)?{acc('après')}\s+"
                      rf"(?:{acc('celle')}|celui|{acc('ça')})"
                      rf"(?:[\s-]?(?:ci|l{_A}))?"
                      rf"(?:\s+(?:{acc('chanson')}|{acc('morceau')}))?{_END}"),
    "queue_clear": c(rf"^(?:vide|efface|nettoie|supprime)\s+(?:la\s+)?"
                     rf"(?:file\s+d{AP}?\s*attente|liste\s+d{AP}?\s*attente"
                     rf"|file|queue){_END}"),
    "queue_list": c(rf"\b(?:qu{AP}?\s*est[\s-]?ce\s+qu{AP}?\s*il\s+y\s+a"
                    rf"|c{AP}?\s*est\s+quoi)\b.{{0,20}}"
                    rf"\b(?:file|queue|suite|attente)\b"
                    # A listing marker is required, and every sibling pack
                    # says so — «coda di riproduzione», «warteschlange
                    # anzeigen», "queue list". Written as the bare noun it
                    # matched inside every add request and, running two steps
                    # earlier, answered «ajoute Time à la file d'attente» by
                    # reading the queue out.
                    rf"|\b(?:montre|affiche|liste|lis)[\s-]?(?:moi\s+)?"
                    rf"(?:la\s+)?(?:file|liste)\s+d{AP}?\s*attente\b"
                    rf"|\bqu{AP}?\s*est[\s-]?ce\s+qui\s+(?:vient|suit)\b"),

    # -- vague requests ------------------------------------------------------
    # The three conditions are it.py's, transposed. (1) ANCHORED: «arrête la
    # musique triste» carries a marker noun and a mood word and asks to STOP.
    # (2) the marker follows immediately, which keeps «mets l'album Musique
    # Douce» an identified request. (3) the tail has to BE a whole MOOD_WORDS
    # entry — «mets la musique de Céline Dion» clears 1 and 2 and fails here.
    #
    # Only «de» is eaten, never «pour»: half the vocabulary is a «pour»
    # phrase that means something as a unit («pour dîner», «pour dormir»),
    # and eating it would leave the table looking up "diner", which nobody
    # says alone. it.py's «di»/«da» note, one preposition over — and note
    # what it costs, which is that «de la musique de Noël» arrives here as
    # the bare "noel". See moods_fr.py.
    "mood": c(rf"^(?:(?:{_PLAY})\s*{_MOI}\s+)?"
              rf"(?:quelque\s+chose|quelques\s+{acc('chansons')}|un\s+truc"
              rf"|de\s+la\s+musique|des\s+{acc('chansons')}|la\s+musique"
              rf"|musique|{acc('chansons')}|un\s+peu|du|de\s+la|des)"
              # «de» elides before a vowel and the elision is obligatory, so
              # the connector arrives welded to the mood: «quelque chose
              # d'instrumental», «d'estival», «d'apaisant». Written as one
              # more alternative rather than as fifteen more table entries —
              # it is grammar, and the table is vocabulary.
              rf"(?:\s+de\b\s+|\s+d{AP}\s*|\s+)(.+?)"
              # A trailing marker noun is part of the phrasing and not of the
              # mood: «de la musique douce» asks for `douce`. Lazy plus an
              # optional tail noun, so a multi-word mood («pour dîner») still
              # backtracks its way to the whole thing.
              rf"(?:\s+(?:musique|{acc('chansons')}|sons))?{_END}"),
    # The WHOLE phrase, politeness aside — see it.py. «chanson suivante» and
    # «une autre chanson» mean skip-this-track and are deliberately absent.
    "mood_another": c(rf"^(?:non[,\s]+)?(?:une\s+autre|un\s+autre|autre\s+chose"
                      rf"|change(?:\s+(?:de\s+musique|de\s+genre|{acc('ça')}))?"
                      rf"|pas\s+(?:{acc('celle')}|celui)[\s-]?l{_A}"
                      rf"|j{AP}?\s*aime\s+pas){_END}"),

    # -- favorites & radio ---------------------------------------------------
    "favorites": c(rf"\b(?:{_PLAY})\s*{_MOI}\s+(?:mes\s+|les\s+)?"
                   rf"(?:favoris|{acc('préférés')}|{acc('préférées')}"
                   rf"|coups\s+de\s+{acc('cœur')})\b"),
    # The lookahead is «mets la radio»: with nothing after «radio» but
    # politeness, filler or a control word, this is a device command and not
    # a station name — otherwise the step asks LMS for a station called
    # "s'il te plaît" and answers that it found none, because it runs ahead
    # of the transport block that should have had the phrase. Exactly de.py's
    # «mach das Radio bitte aus».
    #
    # It reads _TAIL and not _END because it must decline the control words
    # too, and every word it declines is caught by a step built from the same
    # DEV() — asserted by the cross product in tests/test_french.py. And the
    # guard sits BEFORE the whitespace it guards, or a typed double space
    # steps around it (de.py records that one).
    "radio": c(rf"\b(?:{_PLAY})\s*{_MOI}\s+(?:la\s+|une\s+)?"
               # The capture ends at _TAIL, not _END: the guard above
               # declines a bare control word, and once a station IS named the
               # same words must not be welded into its name — «mets la radio
               # Nostalgie plus fort» asked for a station called "Nostalgie
               # plus fort". The volume request is still dropped, because this
               # step runs ahead of vol_up; that is the step order's limit,
               # and it is a smaller one than a station nobody has.
               rf"radio(?!{_TAIL})\s+(.+?){_TAIL}"),

    # -- picks ---------------------------------------------------------------
    # The character classes carry the accents, or «la première» never reaches
    # _as_number at all — de.py widened its own to [a-z0-9äöüß] for this.
    "choose_number": c(rf"(?:m(?:ets|et)|joue|choisis|prends|je\s+veux)?\s*"
                       rf"(?:(?:la|le)\s+)?{acc('numéro')}\s+"
                       rf"([a-z0-9{_ACCLASS}]+){_END}"),
    # «la 2» and ordinals: «la deuxième», «mets la deuxième chanson».
    "choose_article": c(rf"(?:m(?:ets|et)|joue|choisis|prends|je\s+veux)?\s*"
                        rf"(?:la|le|les)\s+([a-z0-9{_ACCLASS}]+)"
                        rf"(?:\s+(?:{acc('chanson')}|{acc('morceau')}|titre"
                        rf"|option))?{_END}"),
    # The answer to a yes/no offer (see ConversationState._offer). Both are
    # read ONLY while an offer is open, and both are anchored to the whole
    # sentence: «no» is a word people say to a hi-fi for other reasons, and a
    # one-word title would otherwise stop being searched for.
    "yes": c(r"^(?:oui|ouais|d['\u2019]accord|bien\s+s\u00fbr|ok(?:ay)?"
             r"|vas[-\s]y|oui\s+merci)\s*$"),
    "no": c(r"^(?:non|non\s+merci|laisse\s+tomber|tant\s+pis)\s*$"),

    # -- explicit sources ----------------------------------------------------
    # The play verb stays inside the capture — see it.py for why.
    "local_prefix": c(rf"{_LOCAL}\s+(.+?){_END}"),
    "local_suffix": c(rf"((?:{_PLAY})\s*{_MOI}\s+.+?)\s+{_LOCAL}{_END}"),
    "service": (r"(?:sur {s}|depuis {s}|avec {s}|via {s}|de {s})\s+"
                r"(.+)$"),
    # «mets X sur Qobuz» — see it.py for why the suffix form exists at all.
    # ``de`` is left out of this half, for the reason connectors/fr.py gives
    # at length: «de» is how French names an artist, so a trailing «de …» is
    # a singer far more often than a service. The four that mean nothing else
    # stay. Written with a plain `$` rather than ``_END``: this template is
    # expanded with ``.format`` and every brace in it would have to survive
    # that, which is also why ``service`` above is not built from the helpers.
    "service_suffix": (r"((?:mets|met|joue|passe|lance|remets)\s+.+?)\s+"
                       r"(?:sur|depuis|avec|via) {s}\s*$"),

    # -- lists ---------------------------------------------------------------
    "albums_list": c(rf"(?:quels|quelles|combien\s+d).{{0,20}}albums?"
                     rf".{{0,16}}{_DE}(.+?){_END}"),
    "toptracks": c(rf"(?:top\s*tracks|meilleur(?:e?s)?\s+"
                   rf"(?:{acc('chansons')}|{acc('morceaux')}|titres)"
                   rf"|plus\s+{acc('écoutés')}"
                   rf"|quel(?:s|les)?\s+(?:{acc('chansons')}|{acc('morceaux')}))"
                   rf".*?{_DE}(.+?){_END}"),
    "name_pick": c(rf"(?:(?:{_PLAY})\s*{_MOI}\s+)?(.+?){_END}"),

    # -- the named-thing steps -----------------------------------------------
    "album": c(rf"(?:{_PLAY})\s*{_MOI}\s+(?:{_L})?(?:album|disque)\s+(.+?){_END}"),
    "playlist": c(rf"(?:{_PLAY})\s*{_MOI}\s+(?:{_L})?"
                  rf"(?:playlist|liste\s+de\s+lecture)\s+(.+?){_END}"),
    # A word that says a person is coming has to introduce the artist — never
    # a bare «de», which half the French titles in a library contain («Le
    # Temps des Cerises», «La Vie en Rose»). Plural nouns only, for it.py's
    # reason: «mets la chanson de Prévert» is a Gainsbourg title, not an
    # artist request.
    # The quantifier is open — see it.py for what one missing partitive costs,
    # and French is where it cost it: «mets DES chansons de X» is the ordinary
    # way to say this, and «les chansons de X» the marked one. The partitive
    # also introduces the noun itself — «mets de la musique de X» — which _L,
    # being the definite article alone, could not read.
    "artist": c(rf"(?:{_PLAY})\s*{_MOI}\s+"
                rf"(?:(?:de\s+la\s+|{_L})?musique\s+{_DE}"
                rf"|(?:quelque\s+chose|tout|un\s+peu)\s+{_DE}"
                rf"|(?:tous?\s+les\s+|toutes\s+les\s+|les\s+|des\s+"
                rf"|quelques\s+)?"
                rf"(?:{acc('chansons')}|{acc('morceaux')}|titres)\s+{_DE}"
                rf"|(?:{_L})?artiste\s+|(?:{_L})?groupe\s+)(.+?){_END}"),
    # Anchored like is_play, and for the same reason — see the docstring.
    "generic_play": c(rf"^(?:{_LEAD}[,\s]+)*(?:{_PLAY})\s*{_MOI}\s+"
                      rf"(.+?){_END}"),
    # No ``generic_play_suffix``. English has one because "put Dark Side on"
    # is a shape its generic_play cannot read; French has no such shape, and
    # the one written here — «mets Time en boucle» — was dead code, because
    # generic_play matches it first and always will. What it was reaching for
    # is handled where it belongs: _ADV absorbs «en boucle», so the title
    # captured is «Time».

    # -- kid-safe ------------------------------------------------------------
    # Anchored on the verb at string start, so a title containing the word
    # («mets Bloque-moi») still routes as a play.
    "block_add": c(rf"^(?:bloque|interdis|bannis)\s+(.+?){_END}"),
    "block_remove": c(rf"^(?:{acc('débloque')}|autorise|{acc('réautorise')})"
                      rf"\s+(.+?){_END}"),
    "block_list": c(rf"^(?:(?:quel(?:s|les)?|combien\s+de)\s+"
                    rf"(?:{acc('chansons')}|{acc('morceaux')}|titres)\s+"
                    rf"(?:sont|est)\s+bloqu"
                    rf"|(?:c{AP}?\s*est\s+quoi|qu{AP}?\s*est[\s-]?ce\s+qui\s+est)"
                    rf"\s+.{{0,12}}bloqu"
                    rf"|liste\s+(?:des\s+)?bloqu)"),
}
