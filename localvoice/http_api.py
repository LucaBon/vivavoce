"""The HTTP surface of the local web app: ``make_handler`` and its routes.

Moved verbatim from ``server.py`` (which keeps startup, discovery and the
CLI): this module owns what happens after a request arrives — routing, the
JSON contracts, and the "never a 5xx" guarantees the page relies on. Stdlib
``http.server`` only.

Two families of routes live next door rather than here, both mixed into
``Handler`` below:

* the endpoints backed by the optional audio engines (``/asr``,
  ``/transcribe``, ``/wakeword/*``), from ``audio_api.py``: they read binary
  bodies and are Pro-gated server-side, which nothing else here does;
* ``POST /api/v1/command``, from ``api_v1.py``: the one route with a
  *versioned promise* attached to it (see ``docs/api.md``). Everything else
  in this module is the web app talking to itself and may change with the
  page it serves.
"""

from __future__ import annotations

import collections
import json
import os
import threading

import httpbase
import staticfiles
import webguard
from api_v1 import api_v1_routes
from audio_api import audio_routes
from http.server import BaseHTTPRequestHandler
from router import Router

# One Router per (client id, player) — see router_for. The map is keyed on a
# client-chosen string, so it is bounded: without a cap, every page load with
# a fresh id (a private window, a cleared storage, a scanner) added an entry
# that never went away. Least-recently-used wins; an evicted client just gets
# a fresh Router, i.e. loses its open "metti la N" list.
MAX_ROUTERS = 64


def _http_fetch(url: str, timeout: float = 5.0):
    """GET ``url`` returning ``(content_type, bytes)`` — the artwork proxy's
    default transport (injectable in tests)."""
    import urllib.request
    with urllib.request.urlopen(url, timeout=timeout) as resp:
        return resp.headers.get("Content-Type") or "image/jpeg", resp.read()


def make_handler(lms, material_url: str, services, default_service: str,
                 ca_path=None, artwork_fetch=_http_fetch, license_mgr=None,
                 kidsafe=None, transcriber=None, multiroom=None,
                 app_version: str = "", wakeword_sessions=None,
                 allowed_hosts=None):
    # One Router (and thus its "metti la N" list state) per browser/client id
    # AND per selected player, so two phones — or one phone switched between
    # rooms — don't clobber each other's numbered list. Clients send a stable
    # id; without one they share a single default router.
    routers = collections.OrderedDict()
    lock = threading.Lock()
    services = list(services)

    def multiroom_ok() -> bool:
        """Multi-room (player selector + «in cucina» targeting) is Pro; the
        feature object lives in pro/multiroom.py, like kid-safe."""
        return multiroom is not None and multiroom.pro_ok()

    def client_for(player_id: str):
        """The LMS client for an optional per-request player override (the
        UI player selector, Pro); the startup default player otherwise."""
        return lms.for_player(player_id) if player_id and multiroom_ok() else lms

    def router_for(client_id: str, player_id: str = "") -> Router:
        key = (client_id, player_id if (player_id and multiroom_ok()) else "")
        with lock:
            r = routers.get(key)
            if r is None:
                r = Router(client_for(key[1]), default_service=default_service,
                           services=tuple(services),
                           kidsafe=kidsafe, client_id=client_id,
                           multiroom=multiroom)
                routers[key] = r
                while len(routers) > MAX_ROUTERS:
                    routers.popitem(last=False)  # drop the least recently used
            else:
                routers.move_to_end(key)
            return r

    # The audio-engine endpoints (/asr, /transcribe, /wakeword/*) and the
    # versioned command route (/api/v1/command) live in audio_api.py and
    # api_v1.py; here is the only place the halves meet, and they call back
    # into _send/_query_params/_read_json_object below.
    class Handler(api_v1_routes(router_for),
                  audio_routes(license_mgr, transcriber, wakeword_sessions),
                  httpbase.RequestBase, BaseHTTPRequestHandler):
        host_policy = webguard.HostPolicy(allowed_hosts)

        def do_GET(self):
            # Reads are guarded too: /license, /players, /kidsafe and
            # /nowplaying all describe this household, and the Host allow-list
            # is the only check that sees a rebound name for what it is (see
            # _reject_bad_host). A Host that cannot POST could never have used
            # the app anyway — do_POST has always required the same list.
            if self._reject_bad_host():
                return
            if self.path in ("/", "/index.html"):
                page = staticfiles.index_html().replace("__MATERIAL_URL__",
                                                        material_url)
                page = page.replace("__SERVICES__", json.dumps(services))
                # json.dumps: the version lands in the inline config script
                # as a quoted JS string.
                page = page.replace("__VERSION__", json.dumps(app_version))
                self._send(200, page, "text/html")
            elif self.path in staticfiles.STATIC:
                data, ctype = staticfiles.STATIC[self.path]
                self._send(200, data, ctype)
            elif self.path.startswith("/static/"):
                found = staticfiles.static_file(self.path.split("?", 1)[0])
                if found:
                    self._send(200, found[0], found[1])
                else:
                    self._send(404, "not found", "text/plain")
            elif self.path == "/ca.pem" and ca_path and os.path.exists(ca_path):
                # La CA locale da installare (una volta) sul telefono/PC: dopo,
                # lucchetto verde e PWA installabile senza avvisi.
                with open(ca_path, "rb") as f:
                    self._send(200, f.read(), "application/x-pem-file")
            elif self.path.startswith("/nowplaying"):
                self._send_nowplaying()
            elif self.path.startswith("/artwork"):
                self._send_artwork()
            elif self.path.startswith("/players"):
                self._send_players()
            elif self.path == "/tls":
                # Whether there is a local CA to install at all. The page can
                # see its own protocol, but not this: a household using its
                # own certificate (or none) must not be walked through
                # installing a ca.pem that does not exist.
                self._send(200, json.dumps(
                    {"ca": bool(ca_path and os.path.exists(ca_path))}))
            elif self.path == "/license":
                status = license_mgr.status() if license_mgr else {"pro": False}
                self._send(200, json.dumps(status))
            elif self.path.startswith("/asr"):
                self._asr_status()
            elif self.path.startswith("/kidsafe"):
                self._kidsafe_status()
            elif self.path.startswith("/wakeword"):
                self._wakeword_status()
            else:
                self._send(404, "not found", "text/plain")

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

        def _query_player(self) -> str:
            """The optional ``player`` query param (the UI player selector)."""
            return (self._query_params().get("player") or [""])[0]

        def _send_players(self):
            # La lista player per il selettore stanza della UI. Mai un 5xx:
            # con l'LMS giù (o senza il modulo multiroom) risponde ok:false e
            # il selettore resta com'è.
            if multiroom is None:
                self._send(200, json.dumps({"ok": False, "players": []}))
                return
            try:
                players = multiroom.players()
            except Exception:
                self._send(200, json.dumps({"ok": False, "players": []}))
                return
            out = [{"id": p["playerid"], "name": p.get("name") or p["playerid"]}
                   for p in players if p.get("playerid")]
            self._send(200, json.dumps(
                {"ok": True, "pro": multiroom.pro_ok(), "current": lms.player_id,
                 "players": out},
                ensure_ascii=False))

        def _nowplaying_payload(self, client=None):
            # Mai un 5xx: il pannello si nasconde su mode "unknown", niente
            # spam di errori in console quando l'LMS è giù.
            client = client or lms
            try:
                info = client.status_info()
            except Exception:
                return {"mode": "unknown"}
            if info.get("artwork"):
                # Cache-buster: cambia col brano, così il browser non mostra
                # la copertina precedente. L'URL vero lo risolve /artwork.
                from urllib.parse import quote
                token = abs(hash((info["artwork"], info.get("title")))) % 10**8
                player_q = ("" if client.player_id == lms.player_id
                            else "&player=" + quote(client.player_id))
                info["artwork"] = f"/artwork?v={token}{player_q}"
            return info

        def _send_nowplaying(self):
            payload = self._nowplaying_payload(client_for(self._query_player()))
            self._send(200, json.dumps(payload, ensure_ascii=False))

        def _player_action(self):
            # Trasporto dal mini-player (pausa/riprendi/salta/seek): neutro
            # rispetto ai contenuti, quindi niente gate kid-safe. Risponde
            # sempre 200 con lo stato aggiornato, così la UI si allinea
            # subito senza aspettare il prossimo poll.
            payload = self._read_json_object()
            action = payload.get("action") or ""
            client = client_for(payload.get("player") or "")
            actions = {
                "pause": client.pause,
                "resume": client.resume,
                "next": client.next_track,
                "prev": client.previous_track,
            }
            try:
                if action == "seek":
                    client.seek(float(payload.get("seconds") or 0))
                elif action == "volume":
                    client.volume_set(int(float(payload.get("value") or 0)))
                elif action in actions:
                    actions[action]()
                else:
                    self._send(200, json.dumps(
                        {"ok": False, "error": "unknown_action"}))
                    return
            except Exception:
                self._send(200, json.dumps({"ok": False, "mode": "unknown"}))
                return
            info = self._nowplaying_payload(client)
            info["ok"] = True
            self._send(200, json.dumps(info, ensure_ascii=False))

        def _send_artwork(self):
            # Proxy lato server della copertina: la pagina è HTTPS e l'LMS è
            # HTTP — un <img> diretto sarebbe mixed content (bloccato). Nessun
            # parametro dal client: l'URL viene sempre ricavato qui dallo
            # status del player, quindi niente open relay.
            try:
                art = client_for(self._query_player()).status_info().get("artwork")
                if not art:
                    self._send(404, "no artwork", "text/plain")
                    return
                if not art.startswith(("http://", "https://")):
                    art = lms.base_url + art
                ctype, data = artwork_fetch(art)
            except Exception:
                self._send(404, "artwork unavailable", "text/plain")
                return
            # Only ever an image: the proxy forwarded whatever Content-Type
            # the upstream announced, so anything the LMS (or something
            # answering in its place) served came back under this origin with
            # its own type. nosniff stops the browser guessing past it.
            if not (ctype or "").lower().startswith("image/"):
                self._send(404, "artwork unavailable", "text/plain")
                return
            self.send_response(200)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.end_headers()
            self.wfile.write(data)

        def do_POST(self):
            if self._reject_cross_site():
                return
            if self.path == "/license":
                self._activate_license()
                return
            if self.path == "/kidsafe":
                self._kidsafe_action()
                return
            if self.path == "/player":
                self._player_action()
                return
            if self.path.startswith("/transcribe"):
                self._transcribe()
                return
            if self.path.startswith("/wakeword/chunk"):
                self._wakeword_chunk()
                return
            if self.path.startswith("/wakeword/stop"):
                self._wakeword_stop()
                return
            # Both spellings of the same route: /api/v1/command is the
            # contract external clients get to rely on, /command the original
            # unversioned path the page and anything already integrated still
            # use. One implementation, in api_v1.py, so they cannot drift.
            #
            # Match on the path without its query string, the way webguard
            # does (httpbase strips it before the JSON_ROUTES lookup) and the
            # way /transcribe and /wakeword/* already do with startswith. An
            # exact match on self.path let a cache-buster or a stray trailing
            # "?" pass the cross-site guard and then 404 — harmless, because
            # it failed closed, but an unexplained 404 on the one route that
            # now promises stability is exactly what a client author trips on.
            if self.path.split("?", 1)[0] in ("/api/v1/command", "/command"):
                self._command()
                return
            self._send(404, '{"speech":"non trovato"}')

        def log_message(self, *args):  # keep the console quiet
            pass

    return Handler
