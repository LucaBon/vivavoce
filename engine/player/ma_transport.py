"""The wire to a MusicAssistant server: one HTTP POST, and what can go wrong.

MusicAssistant is usually described as a websocket API, and it has one. It
also serves the same commands over a plain ``POST /api``, which is what this
uses: the request body is ``{"message_id", "command", "args"}``, the reply is
the command's result as JSON, and the whole exchange fits in ``urllib``. That
matters more than it sounds — a websocket client would have been the first
third-party dependency in ``engine/``, and the reason this project installs
anywhere is that there are none.

Verified against ``music-assistant/server`` on 2026-09-11:
``controllers/webserver/controller.py`` registers ``("POST", "/api",
self._handle_jsonrpc_api_command)`` alongside ``("GET", "/ws", ...)``.

Structurally this is the twin of ``LMSClient._http_transport``: a function
that takes a request and hands back the parsed result, injectable so that no
test in this repo has to touch the network.
"""

from __future__ import annotations

import http.client
import json
import urllib.error
import urllib.request
from typing import Any, Callable, Dict, List

from .errors import (PlayerError, PlayerRefused, PlayerUnreachable,
                     never_delivered)

#: The port MusicAssistant serves its API and web interface on.
DEFAULT_PORT = 8095

#: A transport takes ``{"command": str, "args": dict}`` and returns the parsed
#: result. The shape is the wire body minus the message id, which is bookkeeping
#: this synchronous client does not need: one POST, one reply, no matching up.
Transport = Callable[[Dict[str, Any]], Any]


class MusicAssistantError(PlayerError):
    """Raised when MusicAssistant cannot be reached or refuses a command."""


class MusicAssistantUnreachable(MusicAssistantError, PlayerUnreachable):
    """MusicAssistant gave no answer (see ``player/errors.py``)."""


class MusicAssistantRefused(MusicAssistantError, PlayerRefused):
    """MusicAssistant answered, and it was an error or not what was asked."""


#: Statuses that come from something standing in front of MusicAssistant
#: rather than from it: a reverse proxy that could not reach it. That is
#: silence wearing a status code, and it counts as silence.
_GATEWAY_STATUSES = (502, 504)


#: What the server's own error statuses mean, in words worth putting in a log.
#: From ``_handle_jsonrpc_api_command``: 400 for an unknown command or bad
#: arguments, 403 for a token without the scope, 503 before anyone has
#: finished the first-run setup.
_STATUS_HINTS = {
    400: "MusicAssistant rejected the command",
    401: "MusicAssistant refused the access token",
    403: "the access token lacks the permission for this command",
    503: "MusicAssistant has not been set up yet",
}


def post(base_url: str, token: str, request: Dict[str, Any],
         timeout: float) -> Any:
    """Send one command and return its result.

    Every failure becomes a :class:`MusicAssistantError`, including the ones
    the server states politely in a 4xx: from here up, "the music server did
    not do it" is one outcome with one reply, and the detail is for the log.
    """
    body = json.dumps({
        # The server echoes this back and we never read it: the id exists so a
        # websocket client can pair a reply with its request, and over POST the
        # reply is simply the response to this call. Sent anyway because the
        # field is part of the message and omitting it relies on the server's
        # forgiveness rather than on the contract.
        "message_id": "vivavoce",
        "command": request["command"],
        "args": request.get("args") or {},
    }).encode("utf-8")
    http_request = urllib.request.Request(
        base_url.rstrip("/") + "/api", data=body,
        headers={"Content-Type": "application/json",
                 "Authorization": f"Bearer {token}"})
    try:
        with urllib.request.urlopen(http_request, timeout=timeout) as response:
            payload = response.read()
    except urllib.error.HTTPError as exc:
        hint = _STATUS_HINTS.get(exc.code, "MusicAssistant returned an error")
        kind = (MusicAssistantUnreachable if exc.code in _GATEWAY_STATUSES
                else MusicAssistantRefused)
        raise kind(f"{hint} ({exc.code}) for {request['command']}") from exc
    except (urllib.error.URLError, OSError, http.client.HTTPException) as exc:
        raise MusicAssistantUnreachable(
            f"MusicAssistant at {base_url} is not answering: {exc}",
            delivered=not never_delivered(exc)) from exc
    if not payload:
        # A command that returns nothing (every players/cmd/*) answers with an
        # empty body rather than a JSON null. Not an error, and not a result.
        return None
    try:
        return json.loads(payload)
    except ValueError as exc:
        raise MusicAssistantRefused(
            f"MusicAssistant sent something that is not JSON: {exc}") from exc


class MusicAssistantCalls:
    """How the client puts one command on the wire, and reads what comes back.

    A mixin, next to the wire it speaks: ``_call`` goes through the client's
    ``_guarded`` (breaker, budget, retry), and the rest are what that retry
    and the callers need to know about MusicAssistant's commands — which ones
    are safe to send twice, and what shape an answer has to have.
    """

    #: Commands that move from where the player is, or add to the queue: sent
    #: twice after a lost reply, they skip two tracks or queue an album twice.
    _NOT_REPEATABLE = frozenset({
        "players/cmd/next", "players/cmd/previous",
        "players/cmd/volume_up", "players/cmd/volume_down",
    })

    def _repeat_safe(self, request: Dict[str, Any]) -> bool:
        command = request.get("command")
        if command in self._NOT_REPEATABLE:
            return False
        if command == "player_queues/play_media":
            # "replace" puts the same thing on the queue however often it is
            # sent; "add" and "next" put it there again.
            return (request.get("args") or {}).get("option") == "replace"
        return True

    def _dict(self, command: str, **args: Any) -> Dict[str, Any]:
        """A command whose answer is an object: ``{}`` for nothing, and a
        refusal for anything else. A JSON list where an object was expected
        used to become «Errore interno: 'list' object has no attribute
        'get'» three frames up, past every ``except PlayerError``."""
        result = self._call(command, **args)
        if result is None:
            return {}
        if not isinstance(result, dict):
            raise MusicAssistantRefused(
                f"{command} answered {type(result).__name__}, not an object")
        return result

    def _list(self, command: str, **args: Any) -> List[Dict[str, Any]]:
        """A command whose answer is a list of objects: ``[]`` for nothing,
        a refusal for a non-list, and any row that is not an object dropped —
        one odd row is not a reason to lose the other nineteen."""
        result = self._call(command, **args)
        if result is None:
            return []
        if not isinstance(result, list):
            raise MusicAssistantRefused(
                f"{command} answered {type(result).__name__}, not a list")
        return [row for row in result if isinstance(row, dict)]

    def _call(self, command: str, **args: Any) -> Any:
        """One command, behind the breaker and the turn budget.

        Arguments that are ``None`` are dropped rather than sent: every
        optional argument on the server has a default worth having, and
        spelling it ``null`` overrides it with nothing.
        """
        return self._guarded({
            "command": command,
            "args": {k: v for k, v in args.items() if v is not None},
        })
