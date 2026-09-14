"""``POST /api/v1/command`` — the versioned contract for external clients.

Everything else this server answers is the web app talking to itself: the
page and the handler ship together, so their shape can change in the same
commit. This one route cannot. The Home Assistant spike
(``docs/ha-integration-design.md``) established that a blueprint would call
the command endpoint directly, which turns it into a contract whether or not
anyone declares it — so it is declared here, versioned, and written down in
``docs/api.md``.

Split out of ``http_api.py`` for the same two reasons ``audio_api.py`` was:
that module is at its 400-line ceiling (``tests/test_packaging.py``), and
there is a real seam here — this is the only route with a *promise* attached
to it. What v1 adds over the older ``/command``:

* **``needs_choice``**, explicit. The router already answers "I read you a
  numbered list, pick one" by returning ``choices``; a client that has to
  infer that from a list's length is a client that breaks the day the list is
  used for something else. The flag comes from ``Router._needs_choice``.
* **``conversation_id``**, named. The router has always kept the open list per
  client with an expiry (``Router.candidates`` / ``cand_until``); that *is* a
  conversation session, and an external agent maps its own conversation id
  onto it. ``client`` stays accepted as an alias — the page still sends it,
  and so does anything already calling ``/command``.
* **a response shape that does not change under failure.** The old error
  branch dropped ``choices`` from the body: a field that disappears exactly
  when things go wrong is the worst possible time for it to disappear. Every
  key below is present in both branches.
* **``room``**, added after the fact — v1 shipped without it deliberately, and
  ``docs/api.md`` carries both the original reasoning and what changed. The
  short version: the objection was that a name→player resolver would have to
  be invented against no real client. The resolver exists
  (``pro/multiroom.py``) and Home Assistant is now a real client, so the field
  is an addition, which this contract allows.

``/command`` is routed here too, unversioned and unchanged in behaviour, so
nothing that already calls it has to move. Stdlib only, like the rest.
"""

from __future__ import annotations

import json

from messages import msg, set_lang


def _room_player(multiroom, room: str):
    """The player a ``room`` field names — three answers, not one nullable.

    * ``""`` — pay it no mind. Multi-room is absent or unlicensed, so a room
      is not something this install acts on and the default player is right.
      Nothing is refused: the caller never asked for Pro, it just said where
      it was standing, and a free install has one player anyway.
    * a player id — that room, that player.
    * ``None`` — a room was named and cannot be honoured. The turn is refused;
      see ``_command`` for why that is not pedantry.

    ``multiroom`` is the injected Pro object (``pro/multiroom.py``), reached
    through the same narrow contract ``Router`` uses. The resolution itself
    lives there, next to the one the spoken path uses, so there is one
    threshold and one rule about disconnected players rather than two.
    """
    if multiroom is None or not multiroom.pro_ok():
        return ""
    player = multiroom.player_for_room(room)
    return player["playerid"] if player else None


def api_v1_routes(router_for, multiroom=None):
    """The versioned command route, bound to the handler's router registry.

    A mixin class rather than a module of functions, like ``audio_routes``:
    ``BaseHTTPRequestHandler`` instantiates the handler per request, so
    ``router_for`` has to be captured. Supplied by ``http_api``, which also
    provides ``_send`` and ``_read_json_object``.

    ``multiroom`` is optional in exactly the way it is everywhere else: a
    server built without the Pro module (or a test that does not care) passes
    nothing, and the ``room`` field is inert.
    """

    class ApiV1Routes:
        def _command(self):
            """Handle ``POST /api/v1/command`` (and its ``/command`` alias)."""
            payload = self._read_json_object()
            # Coerce before use, because the first client of this contract is
            # a Home Assistant blueprint and YAML templates render loosely.
            # Without this a wrong type does not fail politely: a non-string
            # ``text`` reached ``.strip()`` and came back as
            # «Errore interno: 'int' object has no attribute 'strip'», which
            # is an internal error message for what is really just a bad
            # request. ``used`` is documented as a string, so it has to be one.
            text = payload.get("text") or ""
            if not isinstance(text, str):
                text = ""
            # The conversation session key. ``conversation_id`` is the v1
            # name (it is what a Home Assistant agent has to hand); ``client``
            # is the original one and still works. Same string either way:
            # it selects the Router that holds the open numbered list, so two
            # phones — or two HA conversations — never pick from each other's.
            conversation_id = (payload.get("conversation_id")
                               or payload.get("client") or "default")
            # The UI player selector: commands go to that player's router.
            # An id, not a name, so it needs no resolving and outranks
            # everything below.
            player_id = payload.get("player") or ""
            # Auto source (default): the router tries the local library first,
            # then TIDAL. Explicit phrases ("dalla mia musica", "da tidal") and
            # an explicit source still override.
            source = payload.get("source") or "auto"
            # The language the user is speaking (the page's mic-language
            # selector): commands are parsed and answered in that language.
            # Set it here rather than leaving it to ``handle_many``, which also
            # does: the room refusal below answers before the router is ever
            # reached, and it has to answer in the caller's language. set_lang
            # is also what makes an unsupported code fall back to Italian
            # instead of raising a KeyError out of ``msg``.
            lang = payload.get("lang") or "it"
            set_lang(lang)
            # The room the command arrived FROM — a Home Assistant satellite
            # in the kitchen — which is a different thing from the room said
            # inside the sentence, and resolved in a different place. Here,
            # before the Router is picked, which is what gives the precedence
            # its shape for free: «metti Time in cucina» is applied later by
            # ``Router._handle``, which re-aims the turn on top of whatever
            # this chose. So saying a room while standing in another one still
            # wins, and it should — that is an intention, not a mistake.
            room = payload.get("room") or ""
            if not isinstance(room, str):
                room = ""
            room = room.strip()
            if room and not player_id:
                target = _room_player(multiroom, room)
                if target is None:
                    # A room was named and cannot be honoured — no player by
                    # that name, or that player is not connected. The turn
                    # stops here rather than playing on the default player.
                    # Refusing costs a repeat; starting the music in the
                    # living room because the kitchen did not resolve is an
                    # event in somebody's house that they have to go and undo,
                    # and it is the failure this whole field exists to avoid.
                    # Same asymmetry the room-in-the-sentence path settled on
                    # (T2.7, 2026-08-26).
                    self._send(200, json.dumps(
                        {"speech": msg("room_unknown", room=room),
                         "used": text, "ok": False, "terms": [], "choices": [],
                         "needs_choice": False, "unmatched": False},
                        ensure_ascii=False))
                    return
                player_id = target
            # Prefer the ASR alternatives when present (mic hands-free mode);
            # the plain text box just sends one string.
            #
            # The isinstance check is the one that matters most here, and it
            # is not defensive coding for its own sake. A bare string is
            # truthy AND iterable, so ``alternatives: "pausa"`` used to reach
            # handle_many as ['p','a','u','s','a'] — five alternatives that
            # all miss, ``text`` never tried, and the reply is a cheerful
            # "non ho capito" with ``unmatched: true``, which also files the
            # phrase as a grammar gap it isn't. No error, no clue. Confusing a
            # YAML scalar for a one-element list is an everyday mistake, and
            # a silent wrong answer is the one failure this contract must not
            # have.
            alts = payload.get("alternatives")
            # ``a.strip()`` and not just ``isinstance``: a blank string is a
            # str, so ``alternatives: [""]`` passed the filter, survived as a
            # one-element list, and defeated the fallback below — handle_many
            # then dropped the blank and answered "non ho sentito niente" to a
            # caller who plainly said something. A Home Assistant blueprint
            # rendering an empty template variable sends exactly that.
            alternatives = ([a for a in alts if isinstance(a, str) and a.strip()]
                            if isinstance(alts, list) else [])
            # Alternatives refine ``text``; they do not replace it with
            # nothing. If none of them survived — the wrong type, or a list of
            # numbers — fall back to what was actually asked rather than
            # answering "non ho sentito niente" to a caller who said something.
            if not alternatives and text:
                alternatives = [text]
            try:
                result = router_for(conversation_id, player_id).handle_many(
                    alternatives, source, lang)
            except Exception as exc:  # never 500 the client
                # Same keys as the success branch, plus ``error``. A contract
                # whose shape narrows on failure makes the caller's failure
                # path the one it never got to test.
                result = {"speech": msg("internal_error", error=exc),
                          "used": text, "ok": False, "error": str(exc),
                          "terms": [], "choices": [], "needs_choice": False,
                          "unmatched": False}
            self._send(200, json.dumps(result, ensure_ascii=False))

    return ApiV1Routes
