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

``/command`` is routed here too, unversioned and unchanged in behaviour, so
nothing that already calls it has to move. Stdlib only, like the rest.
"""

from __future__ import annotations

import json

from messages import msg


def api_v1_routes(router_for):
    """The versioned command route, bound to the handler's router registry.

    A mixin class rather than a module of functions, like ``audio_routes``:
    ``BaseHTTPRequestHandler`` instantiates the handler per request, so
    ``router_for`` has to be captured. Supplied by ``http_api``, which also
    provides ``_send`` and ``_read_json_object``.
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
            # Note there is no ``room`` in v1 — see docs/api.md for why.
            player_id = payload.get("player") or ""
            # Auto source (default): the router tries the local library first,
            # then TIDAL. Explicit phrases ("dalla mia musica", "da tidal") and
            # an explicit source still override.
            source = payload.get("source") or "auto"
            # The language the user is speaking (the page's mic-language
            # selector): commands are parsed and answered in that language.
            lang = payload.get("lang") or "it"
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
            alternatives = ([a for a in alts if isinstance(a, str)]
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
