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
from parsing import _service_label, _source_suffix


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

    def _never_searched(self, res) -> bool:
        """Whether ``res`` is the one outcome a service that was never asked
        has no right to report: a plain miss.

        A gate (kid-safe, Pro) carries ``kind`` and speaks for itself; a hi-fi
        that stopped answering between the probe and the request says so in
        its own words. What is left is "non ho trovato", which offline is not
        true of the music at all: nobody was asked."""
        if getattr(res, "ok", False) or getattr(res, "kind", None):
            return False
        return str(res) != msg("err_unreachable")

    def _if_searched(self, res, message):
        """``res``, unless nothing was ever searched — then ``message``."""
        if not self._never_searched(res):
            return res
        return actions.ActionResult(message, ok=False)

    def _connected_service(self, exclude=None):
        """The first configured service that can answer today, or None.

        ``_stream_name`` picks one to substitute silently; this one picks one
        to OFFER, which is the same question asked where the user named a
        source and a silent swap would be answering a different request from
        the one they made."""
        try:
            for name in self.services:
                if name != exclude and self.lms.for_service(name).can_search():
                    return name
        except LMSError:
            return None
        return None

    def _offer_other_service(self, preamble, exclude, play_at, fallback):
        """«… is not connected. Shall I play it from Qobuz?», and remember
        what a «sì» means (``ConversationState._offer``).

        ``play_at`` takes the service that gets offered and runs the original
        request against it — next turn, if the answer is yes. With no other
        service connected there is nothing to offer and ``fallback`` is the
        answer: a question whose only answer is "no" is not worth asking."""
        alt = self._connected_service(exclude)
        if alt is None:
            return fallback
        return self._offer(
            preamble + " " + msg("offer_play_from", service=_service_label(alt)),
            lambda: play_at(alt))

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

    #: Play branch (see ``Router._PLAY_BRANCHES``) -> the streaming action that
    #: serves it. A phrase that named a source explicitly is routed through
    #: this table instead of straight to ``play_song``: naming Qobuz says WHERE
    #: to look, never WHAT to look for, and until this existed it said both —
    #: «da qobuz metti canzoni dei Pink Floyd» searched for a song called
    #: "canzoni" and played whatever came back first.
    _NAMED_ACTIONS = {"album": actions.play_album,
                      "playlist": actions.play_playlist,
                      "artist": actions.play_artist}

    #: The same table for the local library. Only the artist branch differs
    #: from the generic resolver — see ``library.play_local_artist``; an album
    #: or a bare title is what ``play_local`` was written for.
    _NAMED_LOCAL = {"artist": actions.play_local_artist}

    def _service_play(self, text: str, service: str, P: dict):
        """Act on ``text`` (the request with the service phrase removed) at the
        service the user NAMED, through whichever play branch reads it."""
        branch, query = self._play_branch(text, P)
        return self._resolve_named(
            query if branch else text,
            self._NAMED_ACTIONS.get(branch, actions.play_song), service)

    def _local_play(self, text: str, P: dict):
        """:meth:`_service_play` for «dalla mia musica …» / «… from my music».

        The library can hold a record and still be unable to play it: a
        streaming plugin imports its favourites as library rows whose audio is
        still the plugin's, and with the plugin logged out they are ten tracks
        of silence (``LMSClient.blocking_service``). The rows are dropped
        before they can be chosen, so a request that named no source simply
        carries on to a service that can play them — but this one DID name a
        source, and "I couldn't find it" would be a lie about a library that
        has it. Say what is in the way, and offer the way round it."""
        branch, query = self._play_branch(text, P)
        play_fn = self._NAMED_LOCAL.get(branch, actions.play_local)
        arg = query if branch else text
        return self._local_answer(
            play_fn(self.lms, arg, guard=self._guard), arg,
            self._NAMED_ACTIONS.get(branch, actions.play_song))

    def _local_answer(self, res, arg: str, stream_fn):
        """A local result for someone who ASKED for the local library — by
        phrase or by the source selector, which are the same request said two
        ways. Everything passes through untouched except the one answer that
        needs a question after it: see :meth:`_local_play`."""
        if getattr(res, "kind", None) != actions.IMPORT_OFFLINE:
            return self._played(res, "local")
        return self._offer_other_service(
            str(res), None,
            lambda alt: self._resolve_named(arg, stream_fn, alt), res)

    def _resolve_named(self, arg: str, play_fn, service: str):
        """A service named out loud, so nothing is substituted for it: the
        answer names the service the user asked for. (The selector's silent
        fall-through to a connected service lives in ``_stream_name``, and is
        only right where the user expressed no preference — which is why this
        does not go through ``_streaming``.)

        What a logged-out service gets instead of a substitution is a question.
        Saying only "TIDAL is not connected" is true and leaves the listener to
        say the whole sentence over at a service they now have to pick
        themselves; playing it from Qobuz without asking answers a request
        nobody made. Asking is neither."""
        stream = self.lms.for_service(service)
        res = play_fn(stream, arg, guard=self._guard)
        if not stream.can_search():
            if not self._never_searched(res):
                return res
            label = _service_label(service)
            return self._offer_other_service(
                msg("service_not_connected", service=label),
                service,
                lambda alt: self._resolve_named(arg, play_fn, alt),
                actions.ActionResult(msg("service_offline", service=label),
                                     ok=False))
        return self._played(self._tag(res, _source_suffix(service)), service)

    def _resolve(self, arg: str, stream_fn, source: str, *, local_fn=None):
        """Point a request at the selected source. ``local_fn`` is the local
        library's counterpart of ``stream_fn`` and defaults to the generic
        resolver; only the artist branch overrides it, because only there does
        the local library have a narrower answer than ``play_local``'s."""
        guard = self._guard
        local_fn = local_fn or actions.play_local
        if source == "local":
            return self._local_answer(
                local_fn(self.lms, arg, guard=guard), arg, stream_fn)
        if source == "auto":
            # Auto: prefer a confident local-library hit, else fall back to the
            # default streaming service (no cascading across services).
            # local_fn only plays when it matches, so a miss has no effect.
            # Ahead of _stream_name, which now talks to the server: a local hit
            # settles the request without asking any service whether it is up.
            # A local "intendevi?" carries ok=True and so ends the turn here:
            # asking which of two artists, then overriding the question with
            # Qobuz, would be worse than either answer on its own.
            res = local_fn(self.lms, arg, guard=guard)
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
