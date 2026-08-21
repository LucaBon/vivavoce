"""The HTTP surface of the local web app: ``make_handler`` and its routes.

Moved verbatim from ``server.py`` (which keeps startup, discovery and the
CLI): this module owns everything that happens after a request arrives —
routing, the JSON contracts, and the "never a 5xx" guarantees the page
relies on. Stdlib ``http.server`` only.
"""

from __future__ import annotations

import json
import os
import threading

import staticfiles
from http.server import BaseHTTPRequestHandler
from messages import msg
from router import Router


def _http_fetch(url: str, timeout: float = 5.0):
    """GET ``url`` returning ``(content_type, bytes)`` — the artwork proxy's
    default transport (injectable in tests)."""
    import urllib.request
    with urllib.request.urlopen(url, timeout=timeout) as resp:
        return resp.headers.get("Content-Type") or "image/jpeg", resp.read()


def make_handler(lms, material_url: str, services, default_service: str,
                 ca_path=None, artwork_fetch=_http_fetch, license_mgr=None,
                 kidsafe=None, transcriber=None, multiroom=None):
    # One Router (and thus its "metti la N" list state) per browser/client id
    # AND per selected player, so two phones — or one phone switched between
    # rooms — don't clobber each other's numbered list. Clients send a stable
    # id; without one they share a single default router.
    routers = {}
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
            return r

    class Handler(BaseHTTPRequestHandler):
        def _send(self, code, body, ctype="application/json"):
            data = body.encode("utf-8") if isinstance(body, str) else body
            self.send_response(code)
            self.send_header("Content-Type", f"{ctype}; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def do_GET(self):
            if self.path in ("/", "/index.html"):
                page = staticfiles.index_html().replace("__MATERIAL_URL__",
                                                        material_url)
                page = page.replace("__SERVICES__", json.dumps(services))
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
            elif self.path == "/license":
                status = license_mgr.status() if license_mgr else {"pro": False}
                self._send(200, json.dumps(status))
            elif self.path.startswith("/asr"):
                self._asr_status()
            elif self.path.startswith("/kidsafe"):
                self._kidsafe_status()
            else:
                self._send(404, "not found", "text/plain")

        def _asr_status(self):
            # La pagina mostra l'interruttore «riconoscimento locale» solo se
            # il motore c'è davvero (gruppo opzionale "asr" installato).
            ok = transcriber is not None and transcriber.available()
            payload = {"available": ok}
            if ok:
                payload["model"] = getattr(transcriber, "model_name", None)
            self._send(200, json.dumps(payload))

        # Un comando parlato dura pochi secondi: 15 MB coprono con margine
        # anche un wav non compresso, e tolgono senso a un upload-bomba.
        MAX_AUDIO_BYTES = 15 * 1024 * 1024

        def _transcribe(self):
            # Il corpo è il blob audio di MediaRecorder (webm/opus o wav),
            # la lingua viaggia nella query string. Come gli altri endpoint:
            # mai un 5xx — i casi degradati rispondono 200 con ok:false.
            length = int(self.headers.get("Content-Length", 0) or 0)

            def refuse(error):
                if length:  # drena il corpo: keep-alive pulito anche su rifiuto
                    self.rfile.read(length)
                self._send(200, json.dumps({"ok": False, "error": error}))

            if transcriber is None or not transcriber.available():
                refuse("unavailable")
                return
            # Funzione Pro, applicata lato server come il kid-safe: il toggle
            # nascosto nella UI non basta a proteggere la CPU del server.
            if license_mgr and not license_mgr.is_pro():
                refuse("pro_required")
                return
            if not length:
                refuse("empty")
                return
            if length > self.MAX_AUDIO_BYTES:
                refuse("too_large")
                return
            audio = self.rfile.read(length)
            from urllib.parse import parse_qs, urlparse
            query = parse_qs(urlparse(self.path).query)
            lang = (query.get("lang") or ["it"])[0]
            try:
                result = transcriber.transcribe(audio, lang)
            except Exception as exc:
                self._send(200, json.dumps({"ok": False, "error": str(exc)}))
                return
            text = (result.get("text") or "").strip()
            alternatives = [a for a in (result.get("alternatives") or [])
                            if a and a.strip()]
            if not alternatives and text:
                alternatives = [text]
            self._send(200, json.dumps(
                {"ok": True, "text": text, "alternatives": alternatives},
                ensure_ascii=False))

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
            from urllib.parse import parse_qs, urlparse
            query = parse_qs(urlparse(self.path).query)
            client_id = (query.get("client") or ["default"])[0]
            self._send(200, json.dumps(self._kidsafe_state(client_id)))

        def _kidsafe_action(self):
            if not kidsafe:
                self._send(200, json.dumps(
                    {"ok": False, "error": "unavailable"}))
                return
            length = int(self.headers.get("Content-Length", 0))
            raw = self.rfile.read(length) if length else b"{}"
            try:
                payload = json.loads(raw.decode("utf-8"))
            except (ValueError, UnicodeDecodeError):
                payload = {}
            client_id = payload.get("client") or "default"
            action = payload.get("action") or ""
            pin = payload.get("pin") or ""
            term = payload.get("term") or ""
            if action == "unlock":
                result = ({"ok": True} if kidsafe.unlock(client_id, pin)
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
            length = int(self.headers.get("Content-Length", 0))
            raw = self.rfile.read(length) if length else b"{}"
            try:
                key = json.loads(raw.decode("utf-8")).get("key", "")
            except (ValueError, UnicodeDecodeError):
                key = ""
            result = license_mgr.activate(key)
            if result.get("ok"):
                result.update(license_mgr.status())
            self._send(200, json.dumps(result))

        def _query_player(self) -> str:
            """The optional ``player`` query param (the UI player selector)."""
            from urllib.parse import parse_qs, urlparse
            query = parse_qs(urlparse(self.path).query)
            return (query.get("player") or [""])[0]

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
            length = int(self.headers.get("Content-Length", 0))
            raw = self.rfile.read(length) if length else b"{}"
            try:
                payload = json.loads(raw.decode("utf-8"))
            except (ValueError, UnicodeDecodeError):
                payload = {}
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
            self.send_response(200)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(data)

        def do_POST(self):
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
            if self.path != "/command":
                self._send(404, '{"speech":"non trovato"}')
                return
            length = int(self.headers.get("Content-Length", 0))
            raw = self.rfile.read(length) if length else b"{}"
            client_id, text, player_id = "default", "", ""
            try:
                payload = json.loads(raw.decode("utf-8"))
                text = payload.get("text", "")
                client_id = payload.get("client") or "default"
                # The UI player selector: commands go to that player's router.
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
                alternatives = payload.get("alternatives") or ([text] if text else [])
            except (ValueError, UnicodeDecodeError):
                source, alternatives, lang = "auto", [], "it"
            try:
                result = router_for(client_id, player_id).handle_many(
                    alternatives, source, lang)
            except Exception as exc:  # never 500 the client
                result = {"speech": msg("internal_error", error=exc), "used": text,
                          "ok": False, "error": str(exc), "terms": []}
            self._send(200, json.dumps(result, ensure_ascii=False))

        def log_message(self, *args):  # keep the console quiet
            pass

    return Handler
