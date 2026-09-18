"""Word-level parsing the router does before it dispatches anything.

Spoken numbers and durations, and the names of the music sources. Split out of
``router.py`` because none of it is dispatch: it holds no state, it is the
vocabulary the dispatch is written in, and it is the part of that module the
language packs talk to rather than a listener.
"""

from __future__ import annotations

import re

from lang import PACKS
import wakematch


# The word tables are merged across every registered language on purpose:
# the recogniser's language and the phrasing don't always agree ("metti la
# three"), and a merged lookup answers both for free.
_NUM_WORDS = {}
_ORDINAL_WORDS = {}
_MINUTE_WORDS = {}
_TAIL_ALTS = []
for _pack in PACKS.values():
    _NUM_WORDS.update(_pack.NUM_WORDS)
    _ORDINAL_WORDS.update(_pack.ORDINAL_WORDS)
    _MINUTE_WORDS.update(_pack.MINUTE_WORDS)
    _TAIL_ALTS.extend(_pack.DURATION_TAIL)

# What may sit after a duration and leave it a duration: a separable German
# particle the sleep pattern hands through («30 Minuten aus», «30 Minuten auf
# zu spielen» — see numbers_de.py), politeness, and the words a speaker rounds
# with. Merged across the packs for the reason the word tables are: the
# recogniser's language and the phrasing do not always agree.
_DURATION_TAIL = re.compile(
    r"^(?:\s*(?:" + "|".join(_TAIL_ALTS) + r")\b)*\s*$", re.IGNORECASE)


# The longest spoken command the router will look at: a generous multiple of
# the longest real request (well under 200 characters), and a hard bound on
# backtracking. Every pack has phrases shaped ``verb\s+(.+?)\s+<literal>\s*$``
# — queue insert, local suffix, the German separable forms — and a lazy capture
# between two unbounded boundaries goes quadratic when the literal never
# arrives. ``httpbase.MAX_JSON_BYTES`` lets an unauthenticated POST carry
# 64 KB, which cost ~10 s of CPU per request on a server with no accounts
# running 128 at once. The cap is the structural cure: the shape is in every
# pack, and in every pattern of that kind nobody has written yet.
MAX_COMMAND_CHARS = 1000

# Dictation often appends final punctuation ("Metti la 2."): it would break the
# $-anchored patterns (picks, suffix forms) and leak into the search terms.
_TRAILING_PUNCT = re.compile(r"[.!?…]+$")

# Spanish opens a question with «¿» and an exclamation with «¡», and the
# recognisers that write the closing mark write the opening one too. The
# trailing strip above takes the «?» and leaves the «¿» welded to the first
# word, where it breaks every ^-anchored pattern at once — the picks, the
# yes/no answers, the mood steps, the kid-safe verbs. Stripped here rather
# than absorbed into eleven patterns, because eleven copies of the same
# character class are what words_de.py records six rounds of review about.
# Leading only: a mark inside a title is part of the title.
_LEADING_PUNCT = re.compile(r"^[¿¡]+")


def clean_command(text):
    """What was said, ready to route — or ``None`` when there is nothing to
    route and ``""`` when it is too long to be a sentence anyone spoke.

    Three outcomes rather than two because the router owes the two silences
    different answers: nothing heard, and a body that is not a command.
    """
    t = _TRAILING_PUNCT.sub("", (text or "").strip()).strip()
    t = _LEADING_PUNCT.sub("", t).strip()
    if not t:
        return None
    return "" if len(t) > MAX_COMMAND_CHARS else t


def _reportable(alt):
    """An alternative, bounded, for the ``used`` field of a reply.

    :func:`clean_command` strips before it measures, so a string far over the
    cap can still be executed — 60 KB of spaces and the word «stopp» is a
    valid pause — and every reply path echoed the whole of it back.
    """
    return alt[:MAX_COMMAND_CHARS] if alt else alt


def _as_number(token, ordinals=False):
    """A spoken position -> int, or None if the token isn't a number."""
    token = (token or "").strip().lower()
    if token.isdigit():
        return int(token)
    number = _NUM_WORDS.get(token)
    if number is None and ordinals:
        number = _ORDINAL_WORDS.get(token)
    return number


def _minutes_of(token):
    """A spoken or written number -> int, or None when it is neither."""
    token = (token or "").strip()
    return int(token) if token.isdigit() else _MINUTE_WORDS.get(token)


def _starts_like_duration(tail):
    """Whether ``tail`` BEGINS with something the duration patterns recognise,
    whatever follows it.

    The narrow question ``_parse_minutes`` cannot answer, because it folds
    "this is not a duration" and "this is a duration with something stuck to
    the end" into the same ``None``. The router needs them apart. Every sleep
    phrase carries a stop verb and a preposition — and in four of the five
    languages that preposition is the bare one that also introduces a ROOM:
    «pause in the kitchen», «stopp in der Küche», «arrête dans la cuisine».
    Refusing to pause on any unreadable tail therefore left the most ordinary
    command in the app doing nothing at all, which is a worse failure than the
    one it was written to prevent.

    So only a tail that *started* as a duration suppresses the pause. «in the
    kitchen» matches no pattern here and pauses as it always did; «tra due ore
    e un quarto» matches the hours form, fails the whole-tail check in
    ``_parse_minutes``, and is refused rather than answered with silence at
    the wrong moment.
    """
    t = (tail or "").strip().lower()
    return any(pattern.match(t)
               for pack in PACKS.values() for pattern, _spec in pack.DURATIONS)


def _parse_minutes(tail):
    """A spoken duration ('30 minuti', "mezz'ora", 'an hour') -> minutes, or
    None when the tail isn't a duration (then the phrase wasn't a sleep
    command and routing falls through). Tries every language's DURATIONS in
    pack order. Those patterns are *mostly* language-disjoint; the generic
    minute form is not — German's ``30 minuten`` and Italian's ``30 minuti``
    are the same regex once ``minut`` plus a wildcard has done its work, so
    whichever pack
    comes first answers. It reads the token through the merged MINUTE_WORDS
    table either way, so the two paths cannot disagree.

    **The whole tail has to be a duration.** The patterns are anchored only at
    the start, and for a long time that was all that was asked of them: «tra
    un'ora e mezza» matched on «un'ora» and set a timer thirty minutes short,
    silently. What is left over is checked against :data:`_DURATION_TAIL`,
    which holds the words that legitimately trail one — German writes the
    second half of its verb there and every language puts its "please" there —
    and nothing else. A tail that is *nearly* a duration is now not one, which
    is what sends «metti in pausa tra un'ora e mezza» to the half-hour forms
    added beside the plain ones rather than to a wrong number.
    """
    t = (tail or "").strip().lower()
    for pack in PACKS.values():
        for pattern, spec in pack.DURATIONS:
            m = pattern.match(t)
            if not m or not _DURATION_TAIL.match(t[m.end():]):
                continue
            if spec == "hours":
                hours = _minutes_of(m.group(1))
                return hours * 60 if hours else None
            if spec == "minutes":
                return _minutes_of(m.group(1))
            if spec == "hours_half":
                hours = _minutes_of(m.group(1))
                return hours * 60 + 30 if hours else None
            if spec == "hours_minutes":
                hours, minutes = _minutes_of(m.group(1)), _minutes_of(m.group(2))
                if hours and minutes is not None:
                    return hours * 60 + minutes
                return None
            return spec
    return None


# Web Speech rarely transcribes the service names right — they aren't real
# words, so each recognizer writes what it hears in its own language:
#   qobuz -> it «kobuz»/«cobus», en "kaboots"/"cabooze", es «cobús»/«cobos»/
#            «que bus», de «Kobutz»/«Kobuts»/«Kobus», fr «cobusse»/«kobuze»
#   tidal -> it «taidal»/«tidol», en "title", es «Vidal»/«tídal»,
#            de «Titel»/«Taidel»/«Tiedal», fr «tidale»/«tidalle»
# The explicit-source phrase must match what was *heard*, so each service name
# expands to a sound-alike pattern instead of the literal spelling.
_SERVICE_SOUNDS = {
    "tidal": r"(?:t(?:ai|ay|ei|ie|i|í|y)[\s\-]?d[aeoà]?l{1,2}e?|tider|tida)",
    "qobuz": r"(?:[qkc](?:u?[oóa]|ue)[\s\-]?b(?:oo|[uoaúù])[\s\-]?"
             r"(?:ts|tz|zz|ss|z|s)e?)",
    # Spotify needs far less of this than the other two: it is a household
    # name, so recognizers have it in their vocabulary and mostly write it
    # correctly. The variants are the tail — the final syllable is the only
    # part that drifts, and the plugin's own name leaks through now and then.
    "spotify": r"(?:spo[\s\-]?ti[\s\-]?f(?:y|ai|ay|i|ie)|spotty)",
}

# The sound-alikes that are ORDINARY WORDS, and so are only read as a service
# name where the sentence ends on them.
#
# «Titel» is German for "track", "titles" is an English plural, and «Vidal» is
# a surname. In the SUFFIX form — «metti X da Titel» — the word is the last
# thing said and there is nothing else it could be. In the prefix form the
# service name is followed by the request, so the same word is far more often
# the first word of a title than a source: «play from titles of the unknown»
# went looking for "of the unknown" on TIDAL, and the request the user made
# was never searched for at all.
#
# The price is declared: «spiel auf Titel Dark Side» no longer names TIDAL and
# is answered by the default service instead. That is a source silently
# swapped — which the reply still says out loud (``_source_suffix``) — against
# a title silently truncated, which nothing says at all.
_SERVICE_SOUNDS_FINAL = {
    "tidal": r"(?:titles?|titel|vidal)",
}


def _service_re(name: str, *, final: bool = False) -> str:
    """Regex snippet matching a service name as ASR may transcribe it.

    ``final`` widens it with the sound-alikes that are real words, and is for
    the one pattern where the name ends the sentence — see
    :data:`_SERVICE_SOUNDS_FINAL`.

    Without a table entry the name matches itself, except that an underscore
    stands for the gap a config key writes and a person speaks: a
    MusicAssistant provider is ``apple_music`` and the household says «Apple
    Music». Matching only the written form would mean the source somebody
    named out loud is silently ignored and the default one answers instead.
    """
    sound = _SERVICE_SOUNDS.get(name)
    if not sound:
        return r"[\s_]+".join(re.escape(part) for part in name.split("_"))
    words = _SERVICE_SOUNDS_FINAL.get(name) if final else None
    return f"(?:{sound}|{words})" if words else sound


# The display name of a source, and the ' da TIDAL' tag built out of it, used
# to live here. They are in ``sources.py`` now, as methods: the spelling is
# the backend's own (``ServiceSpec.label``, ``MAService.label``) and has to be
# asked of the client, and this module holds nothing that knows a client.


# Quanto corto può essere un verbo prima che una modifica sola non voglia più
# dire niente. ``wakematch.token_matches`` mette un pavimento di 4 caratteri
# sul ramo del prefisso ma non su quello della singola modifica, e su tre
# lettere quel ramo è troppo largo per questo uso: lo spagnolo «pon» diventa
# «con», «son», «por» — tutte parole vere con cui una frase può cominciare.
# Quattro è lo stesso numero che wakematch ha già scelto, per la stessa
# ragione, e i pack tengono fuori da PLAY_VERBS le forme più corte.
#
# È un pavimento, non una garanzia, e non lo è in nessuna lingua. A quattro
# lettere restano dentro parole vere a una modifica dal verbo — misurate:
# «lay/pay/pray/clay/plan» -> play e «smart» -> start in inglese,
# «mes/met» -> mets e «jour» -> joue in francese, «letti/mette» -> metti e
# «suora» -> suona in italiano. L'ultima è la stessa cosa che il commit che ha
# introdotto la riparazione ha dichiarato e accettato: «letti sfatti» diventa
# un comando quando il router non ha nient'altro con cui leggerlo.
#
# Alzare il pavimento a cinque non è la risposta: salverebbe «play» e
# ucciderebbe «mets» e «pone», cioè i verbi più comuni di francese e spagnolo,
# che sono esattamente il motivo per cui la riparazione esiste. Restringere la
# regola (stessa lunghezza, stessa iniziale) taglia metà di quella lista e
# lascia l'altra metà. Il numero qui sopra è tarato sulle 24 registrazioni di
# tools/asr_titles_bench.py: cambiarlo senza rifare quella misura vuol dire
# scambiare un guadagno misurato con un timore ipotetico.
MIN_REPAIRABLE_VERB = 4


def repair_play_verb(text, verbs):
    """``text`` col primo verbo rimesso a posto, o ``None`` se non c'è niente
    da riparare.

    Il difetto che esiste per chiudere, misurato su 24 registrazioni vere:
    Whisper trascrive «metti» come «Matti» in circa due terzi dei comandi —
    «Matti Comfortably Numb dei Pink Floyd» — e il titolo lo prende benissimo.
    Il router non aggancia il verbo, il turno muore come «non ho capito», e un
    titolo trascritto alla perfezione non arriva mai alla ricerca. Non è un
    limite di taglia del modello: `small`, `medium` e `large-v3-turbo`
    sbagliano tutti e tre lo stesso verbo e prendono tutti e tre gli stessi
    titoli.

    La regola è quella della parola chiave e non una nuova:
    :func:`wakematch.token_matches` — uguale, prefisso quasi completo, o al
    massimo una modifica — perché è la stessa domanda (un sì/no su una parola
    corta) e perché il suo docstring spiega già perché il punteggio di
    ``matching.py`` non serve qui.

    Due limiti dichiarati. Solo il **primo** token, e solo verbi di una parola:
    «fai partire» mal sentito resta fuori. E un token già uguale a un verbo non
    viene toccato, così la riparazione non può cambiare una frase che il router
    capiva già.

    E un prezzo dichiarato, in tutte e cinque le lingue e non solo in quella
    per cui è stata misurata: una parola vera a una modifica dal verbo viene
    riparata come se fosse il verbo. «pay the bill» diventa «play the bill»
    esattamente come «letti sfatti» diventa «metti sfatti». Succede solo dove
    la riparazione vive — il fallback, cioè su una frase che ogni altra lettura
    ha già rifiutato — e il rimedio non è il numero qui sopra: vedi il commento
    a :data:`MIN_REPAIRABLE_VERB` per cosa costerebbe stringerlo, e a chi.
    """
    words = (text or "").split()
    # Una parola sola non è un comando: ripararla trasformerebbe un titolo
    # nudo — che il router legge come scelta da un elenco aperto — in un play.
    if len(words) < 2:
        return None
    first = wakematch.normalize(words[0].strip(",.!?;:«»\"'"))
    if not first:
        return None
    candidates = [v for v in verbs if len(v) >= MIN_REPAIRABLE_VERB]
    if any(first == wakematch.normalize(v) for v in candidates):
        return None      # già giusto
    for verb in candidates:
        if wakematch.token_matches(first, wakematch.normalize(verb)):
            return " ".join([verb] + words[1:])
    return None
