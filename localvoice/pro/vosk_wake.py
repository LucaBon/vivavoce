# Copyright (c) 2026 Luca Bonura. Proprietary — see licenses/PRO-EULA.md.
# Not covered by the repository's AGPL-3.0 license.
"""Server-side wake word for a phrase the household typed (Pro).

The engine this one replaced (openWakeWord, in a ``pro/wakeword.py`` that went
with it — the history is in CHANGELOG.md) removed the Android beep but took
the phrase away with it: it hears only the English phrases it ships a model
for, so continuous listening on the server meant "Hey Jarvis" whatever the
box was called. This module keeps the beep fixed and gives the
phrase back — free recognition with Vosk (Kaldi), matching the phrase in the
transcript.

**Why free recognition and not a grammar.** Kaldi can be restricted to a
grammar of just the phrase plus ``[unk]``, which turns an ASR into a cheap
phrase detector and is the obvious thing to do. It was measured, and it is
the wrong thing to do: on 40 minutes of a hi-fi playing in the room it fired
21 times an hour — 7 on Italian vocals, 7 on instrumental, matching flamenco
guitar and Vivaldi to «vivavoce» — while free recognition over the same audio
fired **zero** times. With only two things it may output, ambiguous audio gets
pushed toward the phrase; with a full lexicon there is always a better
explanation available. The grammar survives here only as a lexicon oracle
(:func:`phrase_out_of_vocabulary`), never as the decoder.

**The limit worth stating out loud.** This is open-vocabulary in the sense
that any phrase can be *configured*, not in the sense that any phrase can be
*heard*: Kaldi only produces words in its lexicon. Measured, «vivavoce»
detects at 83-100% and the invented «zorblax» at 0% — an 83-point swing from
changing only the word, with nothing in between to warn anybody. That is why
:func:`phrase_out_of_vocabulary` exists and why the endpoint refuses rather
than saves: a phrase that can never fire must be rejected when it is typed,
not discovered months later as "the wake word doesn't work very well".

vosk is an *optional* dependency in its own group (``uv sync --group
wakeword-vosk``), separate from ``asr`` and from ``wakeword`` for the same
reason those two are separate from each other: one optional engine failing to
install must not take a working one down with it.
"""

from __future__ import annotations

import importlib.util
import json
import os
import threading
from typing import Dict, List, Optional

from wakematch import contains_wake

# Vosk wants 16 kHz mono 16-bit PCM — the same bytes serverwake.js already
# resamples to and puts on the wire, so the transport needs no change.
SAMPLE_RATE = 16000

# A session nobody has fed for this long is gone (tab closed, phone asleep).
# Same policy and same reason as the engine before it: /wakeword/stop is the polite
# exit and usually arrives, but "usually" is not a lifecycle, and each
# abandoned session holds a Kaldi recognizer.
IDLE_SESSION_SECONDS = 120.0

# fd 2 belongs to the process, not to the caller. phrase_out_of_vocabulary()
# redirects it to read a warning only the Kaldi C++ layer can produce, and the
# HTTP server is threaded: two devices in the house saving a phrase at the
# same time would interleave as save-real → redirect-A → save-A → redirect-B →
# restore-real → restore-A, leaving the process's stderr wired to a deleted
# temp file for the rest of its life. Every traceback after that goes nowhere.
# One lock, held across the whole dup window, is the entire fix.
_fd2_lock = threading.Lock()

# The small models: ~50 MB each, enough for a wake phrase, and the ones the
# bench measured. Not the large ones — this runs continuously next to the
# music, and the whole point of choosing Vosk over Whisper was 310 MiB
# instead of 1298.
MODEL_DIRNAMES = {
    "it": "vosk-model-small-it-0.22",
    "en": "vosk-model-small-en-us-0.15",
    "fr": "vosk-model-small-fr-0.22",
    "de": "vosk-model-small-de-0.15",
    "es": "vosk-model-small-es-0.42",
}


def available() -> bool:
    """Whether the optional ``vosk`` package is importable — a pure probe,
    safe to call on every request (no load, no model file access)."""
    return importlib.util.find_spec("vosk") is not None


def models_dir(data_dir: str) -> str:
    return os.path.join(data_dir, "vosk-models")


def resolve_model(lang: str, data_dir: str,
                  explicit: Optional[str] = None) -> Optional[str]:
    """The model directory to load, or ``None`` when there isn't one.

    Unlike the Whisper model, this is not fetched on first use: a 50 MB
    download inside the first 320 ms audio chunk would time the request out
    and look like a broken engine. It has to be on disk, and
    :func:`ServerVoskWakeSessions.available` says so honestly rather than
    announcing a working engine that fails on every chunk — the exact bug
    recorded by the engine before this one.
    """
    if explicit:
        return explicit if looks_like_model(explicit) else None
    name = MODEL_DIRNAMES.get(lang)
    if not name:
        return None
    path = os.path.join(models_dir(data_dir), name)
    return path if looks_like_model(path) else None


def looks_like_model(path: str) -> bool:
    """A Vosk model is a directory of subdirectories, not a file. Checking
    for ``conf/`` as well as the directory itself keeps a half-finished
    unzip from being loaded and raising deep inside Kaldi.

    Shared with ``vosk_model.py``, which unpacks into a scratch directory and
    asks this before publishing the result — so "is this a usable model" has
    one answer, given in one place."""
    return os.path.isdir(path) and os.path.isdir(os.path.join(path, "conf"))


def phrase_out_of_vocabulary(model, phrase: str) -> List[str]:
    """Words of ``phrase`` the model has no pronunciation for.

    Ported from ``tools/sherpa_bench.py``'s ``vosk_oov()``, where it was
    written and verified against vosk 0.3.45. Vosk exposes no API for this
    and the small models ship no ``words.txt``, so the only signal is a
    warning the C++ layer writes to **file descriptor 2** (serialized on
    :data:`_fd2_lock`, because that descriptor belongs to the process) ("Ignoring word
    missing in vocabulary: 'x'"). ``contextlib.redirect_stderr`` cannot see
    writes from C, hence the fd-level capture.

    An unknown word does not raise: the recognizer constructs happily and
    then never fires. Without this check the result is a silent 0% with no
    reason given, which is precisely what makes the limit so expensive.

    Note this builds a *grammar* — the decoding mode the bench rejected. It
    is used here only to interrogate the lexicon, never to listen. Do not
    rewire it into :meth:`ServerVoskWakeDetector.process`.
    """
    import tempfile

    import vosk

    # The temp file opens *before* the descriptor is saved: dup first and the
    # saved fd leaks if TemporaryFile then raises, with nothing left holding
    # a reference to close it.
    with _fd2_lock, tempfile.TemporaryFile() as tmp:
        saved = os.dup(2)
        try:
            os.dup2(tmp.fileno(), 2)
            vosk.SetLogLevel(0)
            vosk.KaldiRecognizer(model, SAMPLE_RATE,
                                 json.dumps([_normalized(phrase), "[unk]"]))
        finally:
            vosk.SetLogLevel(-1)
            os.dup2(saved, 2)
            os.close(saved)
        tmp.seek(0)
        noise = tmp.read().decode("utf-8", "replace")

    # An empty capture and a clean phrase both produce no matches, and the
    # difference is everything: the first means this check has stopped
    # working and every invented phrase is about to be accepted. A healthy
    # grammar build always says something on fd 2, so silence is a fault.
    if not noise.strip():
        raise RuntimeError(
            "il controllo del vocabolario non ha catturato nulla su fd 2: "
            "senza di esso una frase inventata verrebbe accettata e non "
            "innescherebbe mai")
    missing = []
    for line in noise.splitlines():
        if "missing in vocabulary" not in line:
            continue
        word = line.rsplit(":", 1)[-1].strip().strip("'\"")
        if word and word not in missing:
            missing.append(word)
    return missing


def _normalized(phrase: str) -> str:
    """The phrase as Kaldi must be given it: lowercase words, no padding."""
    from wakematch import tokens
    return " ".join(tokens(phrase))


class ServerVoskWakeDetector:
    """One continuous-listening session: a Kaldi recognizer and the phrase.

    Construction is cheap; the recognizer is built lazily on the first
    :meth:`process` under a lock. The Vosk ``Model`` itself is shared across
    sessions (it is read-only and ~50 MB — one per client would be the whole
    memory budget), while each session gets its own ``KaldiRecognizer``,
    which is the stateful part.
    """

    def __init__(self, model, phrase: str) -> None:
        self.phrase = phrase
        self._model = model
        self._rec = None
        # The last transcript already judged. Vosk grows a partial word by
        # word and re-reports it on every chunk, so without this the same
        # text is matched several times over — and the bench's scan(), whose
        # numbers this path has to reproduce, skips a repeat.
        self._seen = ""
        # Reentrant for the same reason the engine before it was: process() and
        # reset() hold it for their whole call, and a client whose inference
        # is slower than its 320 ms chunk cadence can have two chunks in
        # flight on two request threads at once.
        self._lock = threading.RLock()

    def _recognizer(self):
        import vosk
        if self._rec is None:
            self._rec = vosk.KaldiRecognizer(self._model, SAMPLE_RATE)
        return self._rec

    def process(self, pcm16_bytes: bytes) -> bool:
        """Feed one chunk of 16 kHz mono 16-bit PCM; ``True`` when the phrase
        is present in what has been heard so far.

        Matched against the rolling *partial*, not only the final transcript:
        a wake word has to fire when it is heard, not when the speaker stops
        talking, and that difference is the latency the product actually
        feels.
        """
        if not pcm16_bytes:
            return False
        with self._lock:
            rec = self._recognizer()
            if rec.AcceptWaveform(pcm16_bytes):
                text = json.loads(rec.Result()).get("text", "")
            else:
                text = json.loads(rec.PartialResult()).get("partial", "")
            if not text or text == self._seen:
                return False
            if contains_wake(text, self.phrase):
                return True          # the caller resets us; see audio_api.py
            self._seen = text
            return False

    def reset(self) -> None:
        """Start listening afresh: a new recognizer and no memory of what was
        just heard, so the same phrase said again a moment later fires again
        instead of being swallowed as a repeat."""
        with self._lock:
            self._rec = None
            self._seen = ""


class ServerVoskWakeSessions:
    """Per-client detector registry, mirroring ``ServerWakeWordSessions``.

    Holds the one shared ``Model`` and the household's phrase, and hands each
    client its own recognizer. The model loads on first use, not at startup:
    a box where nobody has ever switched continuous listening on should not
    be paying 310 MiB for it.
    """

    def __init__(self, lang: str = "it", data_dir: str = "",
                 phrase: str = "vivavoce", explicit_model: Optional[str] = None,
                 now=None) -> None:
        import time
        self.lang = lang
        self.data_dir = data_dir
        self.phrase = (phrase or "").strip()
        self.model_dir = resolve_model(lang, data_dir, explicit_model)
        self.now = now or time.monotonic
        self._model = None
        self._sessions: Dict[str, ServerVoskWakeDetector] = {}
        self._seen: Dict[str, float] = {}
        self._lock = threading.RLock()

    # The page shows the engine's own name; "vosk-model-small-it-0.22" is
    # not something to put in front of a household, so the language is.
    @property
    def model(self) -> str:
        return f"vosk-{self.lang}"

    def available(self) -> bool:
        """Package importable, a model actually on disk, and a phrase to
        listen for. All three, because any one of them missing means every
        chunk fails — reporting "available" then is the bug this repo has
        already paid for once."""
        return bool(available() and self.model_dir and self.phrase)

    def _load_model(self):
        with self._lock:
            if self._model is None:
                import vosk
                vosk.SetLogLevel(-1)      # the C++ layer is chatty on stderr
                self._model = vosk.Model(self.model_dir)
            return self._model

    def out_of_vocabulary(self, phrase: str) -> List[str]:
        """Which words of ``phrase`` this model could never hear."""
        return phrase_out_of_vocabulary(self._load_model(), phrase)

    def set_phrase(self, phrase: str) -> None:
        """Change what the house is listening for, immediately.

        Every open session is dropped: a detector carries its phrase, and a
        household that has just renamed its wake word should not have to
        reload the page on each device before the old one stops answering.
        """
        with self._lock:
            self.phrase = (phrase or "").strip()
            self._sessions.clear()
            self._seen.clear()

    def _sweep(self) -> None:
        cutoff = self.now() - IDLE_SESSION_SECONDS
        for client in [c for c, seen in self._seen.items() if seen < cutoff]:
            self._sessions.pop(client, None)
            self._seen.pop(client, None)

    def get_or_create(self, client_id: str) -> ServerVoskWakeDetector:
        with self._lock:
            self._sweep()
            det = self._sessions.get(client_id)
            if det is None:
                det = ServerVoskWakeDetector(self._load_model(), self.phrase)
                self._sessions[client_id] = det
            self._seen[client_id] = self.now()
            return det

    def stop(self, client_id: str) -> None:
        with self._lock:
            self._sessions.pop(client_id, None)
            self._seen.pop(client_id, None)
