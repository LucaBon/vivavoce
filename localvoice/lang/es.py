"""Spanish language pack — see ``base.py`` for the contract and ``words_es.py``
for the word lists these patterns are composed from.

The page has offered ``es-ES`` to the microphone since read-back shipped, and
picked a Spanish voice for it, and then answered in Italian. This is the pack
behind that choice; ``engine/catalogs/es.py`` is the other half.

Three things Spanish does that Italian, English, German and French do not, and
each one decided a pattern rather than being translated into one.

**«para» is the stop verb and it is also the commonest preposition in the
language.** «música PARA dormir», «algo PARA cenar», «Para Todos los Públicos»
— and the ``pause`` step is gated only on ¬is_play, so a bare phrase carrying
the word, typed or picked from an open list, reached an unanchored `\\bpara\\b`
and paused the hi-fi. Italian's «ferma» and German's «aus» are the same shape
one language over, and the cure is the one those two arrived at: the word lives
only inside :func:`~lang.words_es.DEV`, where an article and a device noun have
to follow it, which no preposition is ever followed by.

**The pronoun welds itself to the verb and moves the accent.** «ponme»,
«ponlo», «pónmelo», «súbelo», «quítala» are one word each, and the stress mark
appears only once the clitic is there. Every verb in this file is therefore a
stem from :func:`~lang.words_es.acc` plus :data:`~lang.words_es._CL`, and no
verb is spelled twice — see words_es.py, where both halves of that live.

**The article is what separates asking for music from pressing play.** «pon
música» is the ordinary way to ask for something to listen to; «pon la música»
is ▶. French lets «mets musique» resume and pays for it; here ``DEV()``
requires the article, and «pon música» falls to the mood step, which is where
it belongs.

Politeness lands after the object, as it does in French — «pon la radio por
favor» asks LMS for a station called "por favor" without a guard — so every
`$`-anchored pattern and every lazy capture ends at ``_END`` rather than at
``$``. And ``is_play`` is anchored to imperative position for French's reason:
the play verbs are also the words a question about the music is asked with
(«¿qué pones?»), and ``is_play`` gates the *whole* transport block.

What Spanish does not need: a negation guard. «no pares», «no quites», «no
apagues» are different words from «para», «quita», «apaga» — see words_es.py.
"""

from __future__ import annotations

from .base import c
# Spoken tail -> mood key: a word list, not grammar, so it has a module of
# its own. Imported (not just referenced) because the pack contract in
# ``base.py`` asks the *pack* for MOOD_WORDS.
from .moods_es import MOOD_WORDS  # noqa: F401
# Spoken numbers and durations, same reasoning — see numbers_es.py.
from .numbers_es import (  # noqa: F401
    DURATIONS, MINUTE_WORDS, NUM_WORDS, ORDINAL_WORDS)

CODE = "es"
# The closed word lists these patterns are built from, and the two builders
# composed out of them.
from .words_es import (  # noqa: F401
    DEV, _ACCLASS, _C_DOWN, _C_UP, _CL, _DE, _END, _L, _LEAD, _LOCAL, _PLAY,
    _TAIL, _V_DOWN, _V_OFF, _V_ON, _V_UP, acc)

# An explicit source in front of the verb («en Tidal pon Time», «desde Qobuz
# pon Time»), so the anchor on ``is_play`` does not cost the one phrase shape
# that legitimately puts words before the imperative. Only ``is_play`` reads
# it: it is a gate and captures nothing, and the ``service`` step below does
# the actual splitting.
_SRC = r"(?:(?:en|desde|con|por|de)\s+\w+\s+)?"

PATTERNS = {
    # Anchored — see the module docstring. This is the Spanish decision of the
    # file after «para», and the one to re-read before widening anything below.
    "is_play": c(rf"^(?:{_LEAD}[,\s]+)*{_SRC}(?:{_LOCAL}\s+)?(?:{_PLAY})\b"),

    # -- transport -----------------------------------------------------------
    # «pon la música en pausa» carries a play verb, so the `pause` step — gated
    # on ¬is_play — would never see it. Same seam as it.py's «in pausa».
    "pause_explicit": c(rf"\ben\s+pausa\b|{DEV(_V_OFF)}"),
    # The bare stop words, which are the ones that are nothing else. «para» is
    # absent by design and reaches the router through DEV() above; a lone
    # «para» with no object is still a stop, and that is the one shape written
    # out here.
    "pause": c(rf"\b(?:pausa|stop|{acc('quita')}{_CL}|{acc('apaga')}{_CL}"
               rf"|{acc('detén')}{_CL}|silencia{_CL}|corta\s+la\s+{acc('música')})\b"
               # «para» with no object at all, and «párala» — the clitic IS
               # the object. Anchored to the whole command, which is what
               # keeps «Para Todos los Públicos» and «para siempre» out.
               rf"|^{acc('para')}{_CL}{_END}"),
    # Bare ▶, and the device form: «pon la música» / «enciende la radio» name
    # nothing to play — they are the Spanish for pressing play, and read as a
    # request they searched the library for the word «música». It costs the
    # one-word titles *La Música* and *La Radio*, with the same escape hatch
    # German and French have: «pon el álbum Radio» reaches the album step.
    #
    # `end=_END` and not the default `_TAIL` is the subtlest line in this
    # file: this step is checked before vol_up, so a resume that also
    # swallowed a trailing control word would answer «pon la música MÁS ALTA»
    # with ▶ instead of turning it up.
    "resume_explicit": c(rf"^(?:play|sigue|{acc('continúa')}|reanuda|dale)\s*$"
                         rf"|{DEV(_V_ON, end=_END)}"),
    "resume": c(rf"\b(?:reanuda|{acc('continúa')}|{acc('continúe')}|sigue"
                rf"|play|retoma|reanudar)\b"),
    # «pasa» is a skip only when it says what it is skipping to. Bare it is
    # «Lo Que Pasa, Pasa» and half the catalogue besides — and this step is
    # gated only on ¬is_play, which does not protect a title picked from an
    # open list. words_fr.py records the same reasoning for its «passe».
    "next": c(rf"\b(?:siguiente|{acc('próxima')}|{acc('próximo')}|salta"
              rf"|adelante|skip|otra\s+{acc('canción')}"
              rf"|pasa\s+(?:a\s+(?:la\s+|el\s+)?)?(?:siguiente|otra))\b"),
    # «vuelve» says what it is going back TO, for the reason «pasa» does above:
    # bare, it is a Ricky Martin record, and this step is gated only on
    # ¬is_play — which does not protect a title picked from an open list.
    "prev": c(rf"\b(?:anterior|{acc('atrás')}|retrocede|previa"
              rf"|vuelve\s+(?:{acc('atrás')}|a[la]?\s+anterior)"
              rf"|la\s+de\s+antes)\b"),

    # -- volume --------------------------------------------------------------
    # Both halves name the direction, so the noun alone can never reach the
    # wrong branch. The loose forms below are ANCHORED nowhere and gated on
    # is_play instead; these two are gated on nothing at all (see intents.py),
    # so they carry their own ^ — unanchored, «pon la canción Sube el Volumen»
    # turned the volume up and played nothing. DEV() carries its own ^ for the
    # same reason.
    "vol_up": c(rf"^(?:{_LEAD}[,\s]+)*(?:{_V_UP})\b.{{0,12}}"
                rf"\b(?:{_L}|del\s+)?(?:volumen|sonido|{acc('música')})\b"
                rf"|{DEV(_V_UP)}|{DEV(_V_ON, _C_UP)}"),
    "vol_down": c(rf"^(?:{_LEAD}[,\s]+)*(?:{_V_DOWN})\b.{{0,12}}"
                  rf"\b(?:{_L}|del\s+)?(?:volumen|sonido|{acc('música')})\b"
                  rf"|{DEV(_V_DOWN)}|{DEV(_V_ON, _C_DOWN)}"),
    # Loose forms that name no control — gated on is_play in the router, so
    # «pon Más Fuerte» still plays it. Same trade as it.py's «più forte»,
    # de.py's «lauter» and fr.py's «plus fort», and «más» earns it: it opens a
    # great many Spanish titles.
    "vol_up_loose": c(rf"{_C_UP}"),
    "vol_down_loose": c(rf"{_C_DOWN}"),

    # -- sleep ---------------------------------------------------------------
    # The captured tail must parse as a duration (see DURATIONS), which is what
    # keeps a title carrying «en» from becoming a timer. «pausa» belongs here
    # for it.py's reason: it carries the word the pause step wants, and that
    # step would fire at once. «para» belongs here too, and safely — the tail
    # is what disarms it, exactly as it disarms «en».
    "sleep": c(rf"(?:{acc('apaga')}{_CL}|{acc('para')}{_CL}|{acc('quita')}{_CL}"
               rf"|corta|{acc('detén')}|pausa|stop|duerme|apagar)"
               rf"\b.{{0,25}}?\b(?:dentro\s+de|en)\s+(.+)$"),
    "sleep_cancel": c(rf"^(?:anula|cancela|{acc('quita')}{_CL}|desactiva"
                      rf"|elimina|borra)\b.{{0,20}}"
                      rf"(?:temporizador|apagado|timer|sleep|cuenta\s+atr)"),

    # -- info ----------------------------------------------------------------
    # Gated on ¬is_play, so «pon Qué Bonito» stays a play. The inverted mark is
    # not spelled here: ``clean_command`` strips a leading «¿» before anything
    # is matched (see parsing.py), because otherwise it would have to be
    # written into eleven anchored patterns that will drift apart.
    "nowplaying": c(rf"\b(?:{acc('qué')}|{acc('cuál')})\b.{{0,20}}"
                    rf"\b(?:suena|sonando|{acc('canción')}|tema|escuchando"
                    rf"|escuchamos|poniendo|puesto|es\s+esto)\b"
                    rf"|\b{acc('quién')}\s+(?:canta|es)\b"
                    rf"|\b{acc('qué')}\s+es\s+est[oa]\b"
                    rf"|\b{acc('está')}\s+sonando\b"),

    # -- queue ---------------------------------------------------------------
    # Checked ahead of the generic play verbs, so «a la cola» and «después de
    # esta» never get swallowed as part of a title.
    "queue_add": c(rf"\b(?:{acc('añade')}{_CL}|agrega{_CL}|mete{_CL}"
                   rf"|{acc('pon')}{_CL})\s+(.+?)\s+"
                   rf"(?:a|en)\s+(?:la\s+)?(?:cola|lista\s+de\s+espera)"
                   rf"(?:\s+de\s+{acc('reproducción')})?{_END}"),
    "queue_insert": c(rf"\b(?:{acc('pon')}{_CL}|reproduce|mete{_CL})\s+(.+?)\s+"
                      rf"(?:justo\s+)?(?:{acc('después')}\s+de\s+est[aeo]"
                      rf"|a\s+{acc('continuación')})"
                      rf"(?:\s+(?:{acc('canción')}|tema))?{_END}"),
    "queue_clear": c(rf"^(?:{acc('vacía')}|limpia|borra|elimina)\s+(?:la\s+)?"
                     rf"(?:cola|lista\s+de\s+espera){_END}"),
    # A listing marker is required, and every sibling pack says so — «coda di
    # riproduzione», «warteschlange anzeigen», "queue list", «liste
    # d'attente». Written as the bare noun it matched inside every add request
    # and, running two steps earlier, answered «añade Time a la cola» by
    # reading the queue out.
    "queue_list": c(rf"\b{acc('qué')}\s+hay\s+en\s+la\s+cola\b"
                    rf"|\b{acc('qué')}\s+(?:viene|suena)\s+"
                    rf"(?:ahora\s+)?{acc('después')}\b"
                    rf"|\bcola\s+de\s+{acc('reproducción')}\b"
                    rf"|\b(?:{acc('muéstrame')}|{acc('enséñame')}|lista)\s+"
                    rf"(?:la\s+)?cola\b"),

    # -- vague requests ------------------------------------------------------
    # The three conditions are it.py's, transposed. (1) ANCHORED: «quita la
    # música triste» carries a marker noun and a mood word and asks to STOP.
    # (2) the marker follows immediately, which keeps «pon el álbum Música
    # Ligera» an identified request. (3) the tail has to BE a whole MOOD_WORDS
    # entry — «pon la música de Rosalía» clears 1 and 2 and fails here.
    #
    # Only «de» is eaten, never «para»: half the vocabulary is a «para» phrase
    # that means something as a unit («para cenar», «para dormir»), and eating
    # it would leave the table looking up "cenar", which nobody says alone.
    # it.py's «di»/«da» note, one language over — and note what it costs, which
    # is that «música de navidad» arrives here as the bare "navidad". See
    # moods_es.py.
    "mood": c(rf"^(?:(?:{_PLAY})\s+)?"
              rf"(?:alguna\s+cosa|algo|unas\s+canciones|algunas\s+canciones"
              rf"|la\s+{acc('música')}|{acc('música')}|canciones|temas"
              rf"|un\s+poco)"
              rf"(?:\s+de\b\s+|\s+)(.+?)"
              # A trailing marker noun is part of the phrasing and not of the
              # mood: «música tranquila» asks for `tranquila`. Lazy plus an
              # optional tail noun, so a multi-word mood («para cenar») still
              # backtracks its way to the whole thing.
              rf"(?:\s+(?:{acc('música')}|canciones|temas))?{_END}"),
    # The WHOLE phrase, politeness aside — see it.py. «otra canción» and «la
    # siguiente» mean skip-this-track and are deliberately absent.
    "mood_another": c(rf"^(?:no[,\s]+)?(?:otra|otro|otra\s+cosa"
                      rf"|algo\s+(?:distinto|diferente|{acc('más')})"
                      rf"|cambia(?:{_CL}|\s+de\s+{acc('música')}"
                      rf"|\s+de\s+{acc('género')})?"
                      rf"|est[ae]\s+no|no\s+me\s+gusta){_END}"),

    # -- favorites & radio ---------------------------------------------------
    "favorites": c(rf"\b(?:{_PLAY})\s+(?:mis\s+|los\s+)?"
                   rf"(?:favoritos|preferid[oa]s){_END}"),
    # The lookahead is «pon la radio»: with nothing after «radio» but
    # politeness, filler or a control word, this is a device command and not a
    # station name — otherwise the step asks LMS for a station called "por
    # favor" and answers that it found none, because it runs ahead of the
    # transport block that should have had the phrase. Exactly de.py's «mach
    # das Radio bitte aus» and fr.py's «mets la radio s'il te plaît».
    #
    # It reads _TAIL and not _END because it must decline the control words
    # too, and every word it declines is caught by a step built from the same
    # DEV() — asserted by the cross product in tests/test_spanish.py. And the
    # guard sits BEFORE the whitespace it guards, or a typed double space steps
    # around it (de.py records that one).
    "radio": c(rf"\b(?:{_PLAY})\s+(?:la\s+|una\s+)?"
               # The capture ends at _TAIL, not _END: once a station IS named
               # the control words must not be welded into its name — «pon la
               # radio Cadena SER más alta» asked for a station called "Cadena
               # SER más alta".
               rf"radio(?!{_TAIL})\s+(.+?){_TAIL}"),

    # -- picks ---------------------------------------------------------------
    # The character classes carry the accents, or «la décima» never reaches
    # _as_number at all — de.py widened its own to [a-z0-9äöüß] for this.
    "choose_number": c(rf"(?:{acc('pon')}{_CL}|elige|escoge|quiero|reproduce)?"
                       rf"\s*(?:(?:el|la)\s+)?{acc('número')}\s+"
                       rf"([a-z0-9{_ACCLASS}]+){_END}"),
    # «la 2» and ordinals: «la segunda», «pon la segunda canción».
    "choose_article": c(rf"(?:{acc('pon')}{_CL}|elige|escoge|quiero|reproduce)?"
                        rf"\s*(?:el|la|los|las)\s+([a-z0-9{_ACCLASS}]+)"
                        rf"(?:\s+(?:{acc('canción')}|tema|{acc('opción')}))?"
                        rf"{_END}"),
    # The answer to a yes/no offer (see ConversationState._offer). Both are
    # read ONLY while an offer is open, and both are anchored to the whole
    # sentence: «no» is a word people say to a hi-fi for other reasons, and a
    # one-word title would otherwise stop being searched for.
    "yes": c(rf"^(?:{acc('sí')}|claro|vale|de\s+acuerdo|ok(?:ay)?|venga"
             rf"|por\s+supuesto|{acc('sí')}\s+gracias)\s*$"),
    "no": c(rf"^(?:no|no\s+gracias|{acc('déjalo')}|nada|{acc('olvídalo')}"
            rf"|da\s+igual|no\s+importa)\s*$"),

    # -- explicit sources ----------------------------------------------------
    # The play verb stays inside the capture — see it.py for why.
    "local_prefix": c(rf"{_LOCAL}\s+(.+?){_END}"),
    "local_suffix": c(rf"((?:{_PLAY})\s+.+?)\s+{_LOCAL}{_END}"),
    "service": r"(?:en {s}|desde {s}|con {s}|por {s})\s+(.+)$",
    # «pon X en Qobuz» — see it.py for why the suffix form exists at all.
    # «de» is left out of both halves, for the reason connectors/es.py gives:
    # «de» is how Spanish names an artist, so a trailing «de …» is a singer far
    # more often than a service.
    #
    # Built from ``_PLAY`` and not from a hand-copied verb list, which is the
    # one place this pack does something fr.py does not. The reason it can is
    # arithmetic: this template is expanded with ``.format`` and every brace in
    # it has to survive that, and ``_PLAY`` contains none — no quantifier, no
    # group repeat count, nothing but alternations and the classes ``acc()``
    # writes. ``tests/test_spanish.py`` asserts that, because it is a property
    # of the helper and not of this line. A second list here is the defect
    # words_de.py records: the verbs in _PLAY and not in the copy would set
    # is_play and then lose the suffix form, so «escucha Time en Qobuz» would
    # be answered by the default service. Only ``service`` above is still
    # written out, and it has no verb in it to disagree about.
    "service_suffix": (r"((?:" + _PLAY + r")\s+.+?)\s+"
                       r"(?:en|desde|con|por) {s}\s*$"),

    # -- lists ---------------------------------------------------------------
    "albums_list": c(rf"(?:{acc('qué')}|{acc('cuáles')}|{acc('cuántos')})"
                     rf".{{0,20}}(?:{acc('álbum')}(?:es)?|discos?)"
                     rf".{{0,16}}{_DE}(.+?){_END}"),
    "toptracks": c(rf"(?:top\s*tracks|mejores\s+(?:canciones|temas)"
                   rf"|{acc('más')}\s+escuchad[oa]s"
                   rf"|{acc('qué')}\s+(?:canciones|temas))"
                   rf".*?{_DE}(.+?){_END}"),
    "name_pick": c(rf"(?:(?:{_PLAY})\s+)?(.+?){_END}"),

    # -- the named-thing steps -----------------------------------------------
    "album": c(rf"(?:{_PLAY})\s+(?:{_L})?(?:{acc('álbum')}|disco)\s+(.+?){_END}"),
    "playlist": c(rf"(?:{_PLAY})\s+(?:{_L})?"
                  rf"(?:playlist|lista(?:\s+de\s+{acc('reproducción')})?)"
                  rf"\s+(.+?){_END}"),
    # Plural nouns only, for it.py's reason: «pon la canción de Alaska» is a
    # title, not an artist request. The quantifier in front of the noun is open
    # on purpose — see it.py for what one missing partitive costs, and «unas
    # canciones de X» is the ordinary way to ask in Spanish.
    "artist": c(rf"(?:{_PLAY})\s+"
                rf"(?:(?:{_L})?{acc('música')}\s+{_DE}"
                rf"|(?:algo|todo|un\s+poco)\s+{_DE}"
                rf"|(?:todas\s+las\s+|las\s+|unas\s+|algunas\s+"
                rf"|un\s+poco\s+de\s+)?(?:canciones|temas)\s+{_DE}"
                rf"|(?:{_L})?(?:artista|grupo)\s+)(.+?){_END}"),
    # Anchored like is_play, and for the same reason — see the docstring.
    "generic_play": c(rf"^(?:{_LEAD}[,\s]+)*(?:{_PLAY})\s+(.+?){_END}"),
    # No ``generic_play_suffix``. English has one because "put Dark Side on" is
    # a shape its generic_play cannot read; Spanish has no such shape — the
    # clitic goes on the front of the object, not after it.

    # -- kid-safe ------------------------------------------------------------
    # Anchored on the verb at string start, so a title containing the word
    # («pon Bloquea Mi Corazón») still routes as a play.
    "block_add": c(rf"^(?:bloquea{_CL}|{acc('prohíbe')}{_CL}|veta{_CL})"
                   rf"\s+(.+?){_END}"),
    "block_remove": c(rf"^(?:desbloquea{_CL}|permite{_CL}|autoriza{_CL})"
                      rf"\s+(.+?){_END}"),
    "block_list": c(rf"^(?:(?:{acc('qué')}|{acc('cuántas')})\s+"
                    rf"(?:canciones|temas)\s+(?:{acc('están')}|hay)\s+bloquead"
                    rf"|{acc('qué')}\s+hay\s+bloquead"
                    rf"|lista\s+de\s+(?:los\s+|las\s+)?bloquead)"),
}
