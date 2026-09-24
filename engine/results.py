"""The reply every action hands back, and the ``kind`` values it can carry.

Split out of :mod:`matching`, which re-exports all of it: a reply is not a
match, and the two had outgrown one file together.
"""

from __future__ import annotations

from typing import Optional

from messages import msg

# ``kind`` values that mean something to the dispatch, not just to bookkeeping.
#
# GATE marks a refusal the words cannot argue with: no Pro licence, not the
# owner, blocked for this listener. It answers a question about *who is asking*
# and what they hold, never about what was heard — which is why ``handle_many``
# must stop trying speech-recognition alternatives when it sees one. Retrying
# is not merely pointless (a second transcription does not buy a licence): an
# alternative that mangles the room name, or the blocked artist, misses the
# gate entirely and routes somewhere that *acts*. A free listener asking for
# music in the front room heard it start in the kitchen instead of the pitch,
# and a child could re-roll the dice until one alternative slipped past.
#
# It is also, being a truthy ``kind``, invisible to ``Router._tag`` — which is
# right on its own terms: a refusal is not a play to hang a source or a room on.
GATE = "gate"

#: The ``kind`` of «the hi-fi is not answering». A kind rather than a sentence
#: to compare against, because a caller that needs to tell this reply from a
#: plain miss (``SourceChoice._never_searched``) was comparing the translated
#: text, and any rewording — a room suffix, a second error message — would
#: have quietly turned "nobody answered" into "nothing found".
UNREACHABLE = "unreachable"

# A blocklist reply is about the whole house — the store behind it is global —
# so ``Router._tag`` must not splice a room into it. «Ok, ho bloccato Eminem in
# Salotto» describes a per-room blocklist that does not exist, and the read-out
# was worse: «Brani bloccati: Eminem in Salotto» reads as a blocked *term*.
BLOCKLIST = "blocklist"


class ActionResult(str):
    """A speech string that also carries structured outcome data.

    Subclassing ``str`` keeps every existing caller and test working (equality,
    ``startswith``, ``.speak(...)``), while new callers can read ``.ok`` — did we
    act on the request? — and ``.candidates`` — a numbered list to disambiguate
    from. ``handle_many`` uses ``.ok`` instead of sniffing the ``"Non "`` prefix.
    """

    def __new__(cls, speech, *, ok=True, candidates=None, kind=None, terms=None,
                label=None, retag=None):
        obj = super().__new__(cls, speech)
        obj.ok = ok
        obj.candidates = list(candidates or [])
        obj.kind = kind
        # Foreign names (title/artist/album/playlist) that appear verbatim in the
        # speech, so the web client can read those parts in their own language
        # while the Italian frame is read by an Italian voice.
        obj.terms = [t for t in (terms or []) if t]
        # What this result CHOSE, for a caller that must not choose it again —
        # «un'altra» (see engine/moods.py). Defaults to the foreign name, and
        # is not always it: a year is a choice and not a name in any language,
        # and carrying "1985" in `terms` had the web client hand it to a
        # foreign voice mid-sentence.
        obj.label = label if label is not None else (
            obj.terms[0] if obj.terms else None)
        # How to say this again with a source or room tag spliced in:
        # ``(suffix) -> speech``, or None to put the tag before the final full
        # stop. Only a message with a SECOND sentence needs one; see
        # ``moods._mood_result``, which is the only thing that builds one.
        obj.retag = retag
        return obj


def unreachable(service: Optional[str] = None) -> "ActionResult":
    """The reply for a system that did not answer (:data:`UNREACHABLE`).

    ``service`` names it when the caller knows which one — a catalogue such as
    Audiobookshelf rather than the hi-fi as a whole.
    """
    key = "err_unreachable_service" if service else "err_unreachable"
    return ActionResult(msg(key, service=service), ok=False, kind=UNREACHABLE)
