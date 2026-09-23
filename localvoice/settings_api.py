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
import traceback

# ``_text`` rather than a local ``or ""``: its docstring in ``api_v1`` records
# the bug this route would otherwise reintroduce — a ``lang`` that arrives as
# a list reaches ``set_lang``, where ``lang in CATALOGS`` raises
# ``TypeError: unhashable type`` from outside any handler's try, and the
# connection is dropped with no reply at all. Shared rather than copied so
# that lesson has one home.
from api_v1 import _text
from messages import msg, set_lang


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
            # Before any branch, not inside the one that speaks today: this
            # route phrases its own answers (the blocklist ones come back as
            # ``speech``), and ``httpbase`` has just reset the language to the
            # default for this request. Without this the panel answered every
            # language in Italian while the page's own comment said otherwise.
            # ``GET /kidsafe`` needs none of it — its payload carries no
            # sentence for anyone to read.
            set_lang(_text(payload.get("lang")))
            client_id = payload.get("client") or "default"
            action = payload.get("action") or ""
            pin = payload.get("pin") or ""
            term = payload.get("term") or ""
            # Everything from here writes to disk, and the whole of it is
            # inside the guard for that reason. ``add``/``remove`` already
            # answer a store that cannot be written (engine/guard.py turns
            # BlocklistStoreError into a sentence); ``enable``, ``disable``
            # and ``unlock`` — which writes the lockout counter even when the
            # PIN is wrong — go straight to appdata.atomic_write_json, and an
            # OSError from a full disk or a read-only data dir escaped all the
            # way past do_POST, dropping the connection with no reply. So does
            # the state merge below, which reads the file again.
            #
            # ``except Exception`` and not ``except OSError``: the promise on
            # this side of the app is that a route always answers (see
            # api_v1.py and audio_api.py, which do the same). That promise is
            # not kept by a narrower catch. The engine keeps the opposite
            # rule, and keeps it: nothing here is inside engine/.
            #
            # The snapshot is taken BEFORE the write, and it is not an
            # optimisation. The page assigns this whole reply over its kid-safe
            # state and re-renders from it, and one of the things it renders is
            # whether the Material Skin browser is reachable — hidden only
            # while ``enabled`` and ``locked`` are both true. An error reply
            # that carried neither read as "kid-safe is off" and put a screen
            # the child can start anything from back on their locked device.
            # A write that failed changed nothing, so the state from before it
            # is the true one, and it is what goes back.
            try:
                state = self._kidsafe_state(client_id)
            except Exception:
                traceback.print_exc()
                state = {}
            try:
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
            except Exception:
                # The reason is for the log, never for the page: it carries
                # the path of the data directory.
                traceback.print_exc()
                # Which list could not be saved matters to whoever reads it:
                # ``add``/``remove`` really are the blocklist, but ``enable``,
                # ``disable`` and ``unlock`` write the PIN and the lockout
                # counter, and telling a parent that "the list" failed points
                # them at the wrong thing.
                result = {"ok": False, "error": "save_failed",
                          "speech": msg("blocklist_save_error"
                                        if action in ("add", "remove")
                                        else "settings_save_error")}
                result.update(state)
            self._send(200, json.dumps(result, ensure_ascii=False))

        def _activate_license(self):
            # Attivazione una tantum dalla UI impostazioni. Server solo LAN:
            # nessuna auth extra, come per /command.
            if not license_mgr:
                self._send(200, json.dumps(
                    {"ok": False, "error": "unavailable"}))
                return
            key = self._read_json_object().get("key", "")
            # activate() already answers its own failures — a server that did
            # not reply, a key the server refused — but it ends by writing the
            # activation to disk, and that write has nobody above it. A full
            # disk here used to drop the connection on the one request a
            # customer makes after paying.
            try:
                result = license_mgr.activate(key)
                if result.get("ok"):
                    result.update(license_mgr.status())
            except Exception as exc:
                traceback.print_exc()
                # Its own token, not "invalid": the key may well have been
                # good, and telling somebody who just paid that their key is
                # not valid is the worst available answer.
                result = {"ok": False, "error": "save_failed",
                          "detail": type(exc).__name__}
            self._send(200, json.dumps(result))

    return SettingsRoutes
