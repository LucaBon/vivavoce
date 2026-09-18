"""The settings panel's routes: kid-safe and licence activation.

Next door to ``http_api`` for the same reason ``api_v1`` and ``audio_api``
are, and the docstring there says which: this is the Pro-gated surface. The
two halves of it — a blocklist a parent edits behind a PIN, and the one-off
activation of a licence key — are the only routes in the app that *write to
disk on a POST*, which is a different set of failure modes from everything
else here and is easier to keep right in one place.

A mixin class rather than a module of functions, like ``api_v1_routes``:
``BaseHTTPRequestHandler`` instantiates the handler per request, so
``kidsafe`` and ``license_mgr`` have to be captured. ``http_api`` supplies
``_send``, ``_query_params`` and ``_read_json_object``, and keeps the routing
— ``do_GET``/``do_POST`` call back into the methods below.

Both arguments are optional in exactly the way they are everywhere else: a
server built without the Pro module (or a test that does not care) passes
nothing, and the routes answer ``unavailable`` instead of failing.
"""

from __future__ import annotations

import json


def settings_routes(kidsafe=None, license_mgr=None):
    """The kid-safe and licence routes, bound to the objects that back them."""

    class SettingsRoutes:
        def _kidsafe_state(self, client_id: str) -> dict:
            state = {
                "pro": kidsafe.pro_ok(),
                "enabled": kidsafe.enabled(),
                "haspin": kidsafe.has_pin(),
                "locked": not kidsafe.is_unlocked(client_id),
            }
            if not state["locked"]:
                # I termini si vedono solo da sbloccati: un bambino non deve
                # poter leggere la lista per aggirarla.
                state["terms"] = kidsafe.terms()
            return state

        def _kidsafe_status(self):
            if not kidsafe:
                self._send(200, json.dumps({"pro": False, "enabled": False}))
                return
            client_id = (self._query_params().get("client") or ["default"])[0]
            self._send(200, json.dumps(self._kidsafe_state(client_id)))

        def _kidsafe_action(self):
            if not kidsafe:
                self._send(200, json.dumps(
                    {"ok": False, "error": "unavailable"}))
                return
            payload = self._read_json_object()
            client_id = payload.get("client") or "default"
            action = payload.get("action") or ""
            pin = payload.get("pin") or ""
            term = payload.get("term") or ""
            if action == "unlock":
                if kidsafe.unlock(client_id, pin):
                    result = {"ok": True}
                else:
                    wait = kidsafe.locked_out_for()
                    result = ({"ok": False, "error": "locked_out",
                               "retry_in": int(wait) + 1} if wait > 0
                              else {"ok": False, "error": "wrong_pin"})
            elif action == "lock":
                kidsafe.lock(client_id)
                result = {"ok": True}
            elif action == "enable":
                result = kidsafe.enable(pin, client_id)
            elif action == "disable":
                result = kidsafe.disable(client_id)
            elif action in ("add", "remove"):
                result = kidsafe.edit_terms(action, term, client_id)
            else:
                result = {"ok": False, "error": "unknown_action"}
            result.update(self._kidsafe_state(client_id))
            self._send(200, json.dumps(result, ensure_ascii=False))

        def _activate_license(self):
            # Attivazione una tantum dalla UI impostazioni. Server solo LAN:
            # nessuna auth extra, come per /command.
            if not license_mgr:
                self._send(200, json.dumps(
                    {"ok": False, "error": "unavailable"}))
                return
            key = self._read_json_object().get("key", "")
            result = license_mgr.activate(key)
            if result.get("ok"):
                result.update(license_mgr.status())
            self._send(200, json.dumps(result))

    return SettingsRoutes
