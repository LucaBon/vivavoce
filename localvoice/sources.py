"""Which source answers a request, and what the reply says about it.

The router owns the dispatch flow, ``intents.py`` the phrase-to-action table
and ``conversation.py`` the state that outlives a turn. This is the fourth
part: a request that could be served by the local library or by any of the
streaming plugins has to be pointed at ONE of them, and the answer has to say
which one it was.

Both halves of that are less obvious than they look, and both are here for the
same reason. A service the user never named can be swapped for another —
silently, but never secretly: the confirmation carries the tag ("… da Qobuz")
that says where the music came from. And a service that could not be asked at
all must not be reported as a library that did not have the song. See
``_stream_name`` for the first and ``_if_searched`` for the second.

A mixin over :class:`router.Router`, like the other two: this reads the
router's own configuration (``services``, ``default_service``) and its client.
"""

from __future__ import annotations

import actions
from lms import LMSError
from messages import msg
from parsing import _source_suffix


class SourceChoice:
    """Pointing a request at a source, and naming that source in the reply."""

    def _stream_name(self, source):
        """The streaming service a request goes to: ``source`` when it names a
        known service, else the default one — **and, when that service is not
        connected, the first configured service that is.**

        A logged-out plugin answers its whole menu with an "authenticate in
        Settings" notice and no search node, so every search against it comes
        back empty and the request died as "non ho trovato nessun brano" — a
        statement about the music library, made by a client that never got to
        ask anybody. A hi-fi with three services installed and one of them
        logged out should play from the other two, and only then have anything
        to say about what it could not find.

        The substitution is silent by design in one respect only: the reply is
        still tagged with the service that actually answered ("… da Qobuz"),
        so the user is told where the music came from rather than left to
        guess. ``None`` when nothing is connected — see ``_streaming``.

        The probe costs no round-trip on the ordinary path: ``can_search``
        asks for the search node, which the search itself asks for moments
        later and finds memoized (``LMSClient.SEARCH_NODE_TTL``).
        """
        nominal = source if source in self.services else self.default_service
        try:
            if self.lms.for_service(nominal).can_search():
                return nominal
            for name in self.services:
                if name != nominal and self.lms.for_service(name).can_search():
                    return name
        except LMSError:
            # The server did not answer at all, which is not the same fact as
            # "no service is connected" and must not be reported as it. Hand
            # the request on to the service it was going to: the action makes
            # the same call, fails the same way, and says so in the words the
            # app already has for a hi-fi that is not answering.
            return nominal
        return None

    def _streaming(self, source):
        """``(client, offline)`` for a streaming request.

        The client is never None: even with nothing connected the request is
        run against the service it was aimed at, because the action may have
        an answer that has nothing to do with the plumbing — a kid-safe
        refusal is about what was asked for, and answering a child with "no
        streaming service is connected" is answering a question nobody put.
        ``offline`` says the reply needs re-wording *if* it comes back a plain
        miss; ``_if_searched`` is where that judgement is made."""
        name = self._stream_name(source)
        if name is not None:
            return self.lms.for_service(name), name, False
        name = source if source in self.services else self.default_service
        return self.lms.for_service(name), name, True

    def _if_searched(self, res, message):
        """``res``, unless nothing was ever searched — then ``message``.

        Only a plain miss is replaced. A gate (kid-safe, Pro) carries ``kind``
        and speaks for itself; a hi-fi that stopped answering between the
        probe and the request says so in its own words. What is left is "non
        ho trovato", which offline is not true of the music at all: nobody was
        asked."""
        if getattr(res, "ok", False) or getattr(res, "kind", None):
            return res
        if str(res) == msg("err_unreachable"):
            return res
        return actions.ActionResult(message, ok=False)

    def _tag(self, res, suffix: str):
        """Splice the source tag into a play confirmation ('Riproduco Time.' ->
        'Riproduco Time da Qobuz.'). Only acted-on plays are tagged: misses,
        errors and 'did you mean' questions pass through untouched.

        It goes into the FIRST sentence, which is the same thing as the last
        one for every confirmation that has only one — all of them until the
        mood read-back, which ends by inviting «un'altra» and turned
        «… in cucina» into an instruction about where to say it."""
        if not suffix or not getattr(res, "ok", False) or getattr(res, "kind", None):
            return res
        head, sep, rest = str(res).partition(". ")
        if head.endswith("."):
            head = head[:-1]
        speech = head + suffix + "." + ((" " + rest) if sep else "")
        return actions.ActionResult(speech, ok=True, candidates=res.candidates,
                                    kind=res.kind, terms=res.terms,
                                    label=getattr(res, "label", None))

    def _resolve(self, arg: str, stream_fn, source: str):
        guard = self._guard
        if source == "local":
            return self._played(
                actions.play_local(self.lms, arg, guard=guard), "local")
        if source == "auto":
            # Auto: prefer a confident local-library hit, else fall back to the
            # default streaming service (no cascading across services).
            # play_local only plays when it matches, so a miss has no effect.
            # Ahead of _stream_name, which now talks to the server: a local hit
            # settles the request without asking any service whether it is up.
            res = actions.play_local(self.lms, arg, guard=guard)
            if getattr(res, "ok", False):
                return self._played(res, "local")
        stream, name, offline = self._streaming(source)
        res = stream_fn(stream, arg, guard=guard)
        if offline:
            return self._if_searched(res, msg("no_service_online"))
        return self._played(self._tag(res, _source_suffix(name)), name)

    def _resolve_queue(self, arg: str, mode: str, source: str):
        """Like :meth:`_resolve`, but for a song queued (mode: 'add' or
        'insert') instead of played — only play_song/play_local accept a
        queue mode. No explicit source-override phrases ("da tidal ...",
        "dalla mia musica ...") for queue commands: out of scope, the UI
        source selector still decides where a queued song comes from."""
        guard = self._guard
        if source == "local":
            return self._played(
                actions.play_local(self.lms, arg, mode=mode, guard=guard),
                "local", mode=mode)
        if source == "auto":
            res = actions.play_local(self.lms, arg, mode=mode, guard=guard)
            if getattr(res, "ok", False):
                return self._played(res, "local", mode=mode)
        stream, name, offline = self._streaming(source)
        res = actions.play_song(stream, arg, mode=mode, guard=guard)
        if offline:
            return self._if_searched(res, msg("no_service_online"))
        return self._played(self._tag(res, _source_suffix(name)), name, mode=mode)
