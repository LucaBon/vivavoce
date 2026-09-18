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
import traceback


def _failed(exc: Exception, where: str) -> str:
    """Log ``exc`` where an administrator can read it, and answer with a word.

    ``str(exc)`` used to go back to the client. It is written for whoever is
    running the server, not for whoever is holding the phone: a
    ``faster-whisper`` failure carries the filesystem path of the model cache,
    a ``vosk`` one the directory it looked in, and an ``OSError`` on the
    phrase store the absolute path of the data directory — which on the HA
    add-on names the share, and on a systemd install the home directory of the
    account the service runs as. None of that helps the page, and the page is
    reachable by anything on the LAN (``docs/api.md``: no authentication, by
    design).

    So the detail goes to the server's log, where the person who can act on it
    already looks, and the reply carries a stable token the page can render.
    """
    traceback.print_exc()
    return where


def audio_routes(license_mgr=None, transcriber=None, wakeword_sessions=None,
                 wake_phrase_store=None):
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
            # "wakeword" — vedi pro/vosk_wake.py per il perché non è "asr").
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
                self._send(200, json.dumps(
                    {"ok": False, "error": _failed(exc, "transcribe_failed")}))
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
                self._send(200, json.dumps(
                    {"ok": False, "error": _failed(exc, "wakeword_failed")}))
                return
            self._send(200, json.dumps({"ok": True, "triggered": triggered}))

        # A phrase is a couple of words; 4 KB is a generous JSON envelope
        # around them and refuses a runaway client without buffering it.
        MAX_PHRASE_BYTES = 4 * 1024

        def _wake_phrase_get(self):
            # Not Pro-gated, and deliberately so: the phrase is household
            # configuration, and the FREE engine (Web Speech, in the browser)
            # answers to it too. The Pro gate belongs on the work that costs
            # the server's CPU — POST /wakeword/chunk — not on reading back a
            # setting the free tier also uses.
            if wake_phrase_store is None:
                self._send(200, json.dumps({"ok": False,
                                            "error": "unavailable"}))
                return
            # `stored` says whether anybody has ever chosen, which the phrase
            # alone cannot: an unconfigured house answers "vivavoce" here
            # because that is the default, and a page that reads that as a
            # choice overwrites a phrase the browser has been answering to
            # since before this endpoint existed.
            stored = getattr(wake_phrase_store, "stored", None)
            self._send(200, json.dumps(
                {"ok": True, "phrase": wake_phrase_store.get(),
                 "stored": bool(stored and stored())},
                ensure_ascii=False))

        def _wake_phrase_set(self):
            length = self.content_length()
            if wake_phrase_store is None:
                self._refuse_audio(length, "unavailable")
                return
            if length > self.MAX_PHRASE_BYTES:
                self._refuse_audio(length, "too_large")
                return
            raw = self.rfile.read(length) if length else b""
            try:
                phrase = (json.loads(raw or b"{}").get("phrase") or "").strip()
            except (ValueError, AttributeError):
                self._send(200, json.dumps({"ok": False, "error": "bad_json"}))
                return
            if not phrase:
                self._send(200, json.dumps({"ok": False, "error": "empty"}))
                return
            try:
                missing = self._phrase_out_of_vocabulary(phrase)
            except RuntimeError as exc:
                # The check reporting that IT is broken, which is not the same
                # as the phrase being fine. vosk_wake raises this when the fd-2
                # capture comes back empty, precisely because silence there
                # means every invented phrase is about to be accepted. Saving
                # anyway keeps the setting usable; saying so is what stops the
                # failure from being invisible, which was the whole point.
                wake_phrase_store.set(phrase)
                self._send(200, json.dumps(
                    {"ok": True, "phrase": phrase,
                     "unverified": _failed(exc, "vocabulary_check_failed")},
                    ensure_ascii=False))
                return
            if missing:
                # Refused, not saved. A phrase the engine has no pronunciation
                # for does not degrade — it never fires at all (measured: an
                # invented word detects at 0%, an ordinary one at 83-100%),
                # and the failure has no symptom except "the wake word doesn't
                # work very well". Saying so here is the whole point.
                self._send(200, json.dumps(
                    {"ok": False, "error": "out_of_vocabulary",
                     "words": missing}, ensure_ascii=False))
                return
            try:
                wake_phrase_store.set(phrase)
            except OSError as exc:
                self._send(200, json.dumps(
                    {"ok": False, "error": _failed(exc, "save_failed")}))
                return
            # Every open session carries the old phrase; the engine drops them
            # so the house answers to the new one without a reload per device.
            setter = getattr(wakeword_sessions, "set_phrase", None)
            if setter is not None:
                setter(phrase)
            self._send(200, json.dumps({"ok": True, "phrase": phrase},
                                       ensure_ascii=False))

        def _phrase_out_of_vocabulary(self, phrase):
            """Words the engine could never hear, or ``[]`` when there is no
            engine to ask. Advisory by construction: the browser engine has no
            lexicon limit, so with the server engine absent every phrase is
            legitimately fine and refusing one would be inventing a rule.

            Raises ``RuntimeError`` when the check cannot vouch for itself —
            see the caller. Every other failure answers ``[]``: it is a
            warning about one engine, not the authority on the phrase.
            """
            check = getattr(wakeword_sessions, "out_of_vocabulary", None)
            if check is None or not wakeword_sessions.available():
                return []
            # Asking costs a 310 MiB model load, held under the engine's lock
            # and paid inside this request. The engine it protects never runs
            # for a free-tier house — /wakeword/chunk answers pro_required
            # before loading anything — so asking there would spend the whole
            # memory budget of a 2 GB Pi to check a phrase that engine is
            # never going to listen for. This endpoint stays ungated; the
            # expensive question inside it does not.
            if license_mgr and not license_mgr.is_pro():
                return []
            try:
                return check(phrase)
            except RuntimeError:
                raise
            except Exception:
                return []

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
