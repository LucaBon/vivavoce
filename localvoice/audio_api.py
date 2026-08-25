"""The endpoints backed by the optional audio engines: ASR and wake word.

Split out of ``http_api.py``, which had grown past the 400-line ceiling the
repo sets itself (see ``tests/test_packaging.py``). The cut follows a real
seam rather than a line count: everything here reads a *binary* body from an
optional engine that may not be installed, and shares one shape because of
it —

* the engine is optional, so "not installed" is a normal answer
  (``ok:false``), not an error;
* the work costs the server's CPU, so it is Pro-gated server-side — the
  browser mic and the language picker are trust-based by construction, these
  two are not (see ``licensing.py``);
* the body is bounded before it is read, and refused bodies are still drained
  so keep-alive survives a rejection.

The routes are a mixin over the ``http_api`` handler, which supplies
``_send`` and ``_query_params``; the two halves are only ever combined there.
Stdlib only, like the rest of the HTTP surface.
"""

from __future__ import annotations

import json


def audio_routes(license_mgr=None, transcriber=None, wakeword_sessions=None):
    """The audio-engine half of the request handler, bound to its engines.

    A class rather than a module of functions for the same reason
    ``make_handler`` is a closure: ``BaseHTTPRequestHandler`` instantiates the
    handler per request, so the engines have to be captured, not passed.
    """

    class AudioRoutes:
        # Un comando parlato dura pochi secondi: 15 MB coprono con margine
        # anche un wav non compresso, e tolgono senso a un upload-bomba.
        MAX_AUDIO_BYTES = 15 * 1024 * 1024

        # A wake-word chunk is ~300 ms of 16-bit mono PCM at 16 kHz (~10 KB);
        # 256 KB is a generous multiple of that, and refuses a runaway client
        # rather than buffering an unbounded body.
        MAX_WAKEWORD_CHUNK_BYTES = 256 * 1024

        def _refuse_audio(self, length: int, error: str):
            """Reject a binary POST without reading it as audio. Drains the
            body first: a refusal that leaves it unread desynchronises the
            connection, so the *next* request on it fails too. Drained in
            chunks — an oversized body is refused precisely because we don't
            want it in memory."""
            remaining = length
            while remaining > 0:
                chunk = self.rfile.read(min(remaining, 65536))
                if not chunk:
                    break
                remaining -= len(chunk)
            self._send(200, json.dumps({"ok": False, "error": error}))

        def _audio_body_error(self, length: int, engine, max_bytes: int):
            """The reason to refuse this body, or ``None`` to go ahead — the
            same four checks in the same order for both engines."""
            if engine is None or not engine.available():
                return "unavailable"
            # Funzione Pro, applicata lato server come il kid-safe: il toggle
            # nascosto nella UI non basta a proteggere la CPU del server.
            if license_mgr and not license_mgr.is_pro():
                return "pro_required"
            if not length:
                return "empty"
            if length > max_bytes:
                return "too_large"
            return None

        def _asr_status(self):
            # La pagina mostra l'interruttore «riconoscimento locale» solo se
            # il motore c'è davvero (gruppo opzionale "asr" installato).
            ok = transcriber is not None and transcriber.available()
            payload = {"available": ok}
            if ok:
                payload["model"] = getattr(transcriber, "model_name", None)
            self._send(200, json.dumps(payload))

        def _wakeword_status(self):
            # Come /asr: l'interruttore «parola chiave lato server» compare
            # solo se il motore c'è davvero (gruppo opzionale SEPARATO
            # "wakeword" — vedi pro/wakeword.py per il perché non è "asr").
            # Il gate Pro è sull'azione (POST /wakeword/chunk), non qui —
            # stessa scelta di /asr rispetto a /transcribe.
            ok = wakeword_sessions is not None and wakeword_sessions.available()
            payload = {"available": ok}
            if ok:
                payload["model"] = wakeword_sessions.model
            self._send(200, json.dumps(payload))

        def _transcribe(self):
            # Il corpo è il blob audio di MediaRecorder (webm/opus o wav),
            # la lingua viaggia nella query string. Come gli altri endpoint:
            # mai un 5xx — i casi degradati rispondono 200 con ok:false.
            # content_length() rather than int(header): a non-numeric value
            # used to raise here, uncaught, and drop the connection with no
            # reply at all.
            length = self.content_length()
            error = self._audio_body_error(length, transcriber,
                                           self.MAX_AUDIO_BYTES)
            if error:
                self._refuse_audio(length, error)
                return
            audio = self.rfile.read(length)
            lang = (self._query_params().get("lang") or ["it"])[0]
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

        def _wakeword_chunk(self):
            # Il corpo è un chunk PCM16 mono a 16 kHz (vedi
            # static/js/serverwake.js), il client id viaggia in query string —
            # come /transcribe, mai un 5xx: i casi degradati rispondono 200
            # con ok:false.
            length = self.content_length()
            error = self._audio_body_error(length, wakeword_sessions,
                                           self.MAX_WAKEWORD_CHUNK_BYTES)
            if error:
                self._refuse_audio(length, error)
                return
            client_id = (self._query_params().get("client") or ["default"])[0]
            audio = self.rfile.read(length)
            detector = wakeword_sessions.get_or_create(client_id)
            try:
                triggered = detector.process(audio)
                if triggered:
                    detector.reset()  # ready to fire again right away
            except Exception as exc:
                self._send(200, json.dumps({"ok": False, "error": str(exc)}))
                return
            self._send(200, json.dumps({"ok": True, "triggered": triggered}))

        def _wakeword_stop(self):
            # Rilascia il modello del client: senza, la sessione (memoria ONNX)
            # resterebbe viva per sempre a ogni dispositivo che ha mai usato
            # la funzione. Idempotente e mai un errore: fermare due volte, o
            # fermare una sessione mai aperta, non cambia nulla.
            if wakeword_sessions is not None:
                client_id = (self._query_params().get("client")
                             or ["default"])[0]
                wakeword_sessions.stop(client_id)
            self._send(200, json.dumps({"ok": True}))

    return AudioRoutes
