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
from typing import Any, Callable, Dict

from .errors import PlayerError

#: The port MusicAssistant serves its API and web interface on.
DEFAULT_PORT = 8095

#: A transport takes ``{"command": str, "args": dict}`` and returns the parsed
#: result. The shape is the wire body minus the message id, which is bookkeeping
#: this synchronous client does not need: one POST, one reply, no matching up.
Transport = Callable[[Dict[str, Any]], Any]


class MusicAssistantError(PlayerError):
    """Raised when MusicAssistant cannot be reached or refuses a command."""


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
        raise MusicAssistantError(
            f"{hint} ({exc.code}) for {request['command']}") from exc
    except (urllib.error.URLError, OSError, http.client.HTTPException) as exc:
        raise MusicAssistantError(
            f"MusicAssistant at {base_url} is not answering: {exc}") from exc
    if not payload:
        # A command that returns nothing (every players/cmd/*) answers with an
        # empty body rather than a JSON null. Not an error, and not a result.
        return None
    try:
        return json.loads(payload)
    except ValueError as exc:
        raise MusicAssistantError(
            f"MusicAssistant sent something that is not JSON: {exc}") from exc
