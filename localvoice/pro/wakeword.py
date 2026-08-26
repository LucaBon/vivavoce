# Copyright (c) 2026 Luca Bonura. Proprietary — see licenses/PRO-EULA.md.
# Not covered by the repository's AGPL-3.0 license.
"""Server-side wake-word detection (Pro): the fix for the Android beep.

Continuous listening today runs entirely in the browser (Web Speech), which
on Android plays an audible tone every few seconds when the recognizer
restarts — the single most-cited complaint in the launch feedback, and a
browser limitation Web Speech itself can't route around. When this feature
is active, the browser streams raw PCM audio to the server, which runs
openWakeWord (CPU, tiny ONNX model, no GPU) over it continuously and reports
back whether the wake word fired — no restart cycle, no beep.

openwakeword is an *optional* dependency, but in its own group
(``uv sync --group wakeword``, NOT the ``asr`` group faster-whisper uses) —
the core stays stdlib-only either way. Without it,
:func:`available` answers ``False`` and the feature degrades to the existing
Web Speech wake word; nothing else changes.

**Pinned to openwakeword==0.4.0, verified deliberately.** Every release from
0.5.0 on declares a hard (non-optional) dependency on ``tflite-runtime`` on
Linux, which has no published wheel past Python 3.11 — bundling that into
this project (which supports and tests 3.9-3.14) would break
``uv sync --group wakeword`` outright on any current install, and worse,
would have broken the *already-shipped* faster-whisper feature too had it
shared the ``asr`` group. 0.4.0 is the last release before that dependency
was added: it has no tflite-runtime requirement, ships its pretrained models
inside the wheel (no download step, no network at runtime), and its actual
installed API was inspected and exercised end-to-end (real ``Model()``,
real ``predict()`` on a silence frame, real ``reset()``) against Python 3.12
before writing this module — not assumed from the project's current
README, which describes a newer, incompatible API
(``wakeword_models=``/``inference_framework=``/``download_models()``, none
of which exist in 0.4.0). Do not casually bump this pin.

**Fixed-phrase trade-off.** openWakeWord's bundled models cover a handful of
English phrases ("hey jarvis", "alexa", "hey mycroft", "timer", "weather");
it has no built-in support for an arbitrary user-typed phrase like the
free-text Web Speech wake word, and training a custom model (e.g. an
Italian "vivavoce") needs a separate offline pipeline (synthetic-speech
generation and training, no GPU here) this module doesn't attempt. So this
path is offered as an *additional* choice next to the free-text Web Speech
wake word, not a replacement for it — "hey jarvis" today, until a custom
model is trained and shipped.

Session lifecycle: unlike a :class:`router.Router` (cheap, kept forever per
client), an openWakeWord ``Model`` holds a loaded ONNX runtime session —
non-trivial memory. Callers (``http_api.py``) create one per client when
wake-listening starts and must release it with
:meth:`ServerWakeWordSessions.stop` when it ends, or the session dict grows
unbounded.
"""

from __future__ import annotations

import importlib.util
import threading
import time
from typing import Dict, Optional

# A session whose client has not sent a chunk for this long is gone: the tab
# was closed, the phone slept, the browser was killed. POST /wakeword/stop is
# the polite exit and it usually arrives — but "usually" is not a lifecycle,
# and each abandoned session holds an ONNX runtime in memory forever.
IDLE_SESSION_SECONDS = 120.0

# openWakeWord's own guidance: feed it 16 kHz, 16-bit mono PCM, in frames
# that are multiples of 80 ms (1280 samples) for the best latency/efficiency
# balance. The browser resamples to this rate before sending (see
# static/js/serverwake.js) — feeding it anything else silently produces
# garbage features, never an error, so getting this right client-side matters
# more than usual.
SAMPLE_RATE = 16000

# The only models openWakeWord ships pretrained (see the fixed-phrase
# trade-off above). "hey_jarvis" reads naturally and isn't a real brand-name
# collision in a hi-fi context. Matched by substring against the bundled
# file's stem (e.g. "hey_jarvis_v0.1.onnx"), so a future model version bump
# upstream doesn't require a code change here.
DEFAULT_MODEL = "hey_jarvis"

# Empirically documented upstream: a low threshold fires on background
# noise, a very high one misses real speech. Not user-tunable today — a
# single reasonable default, like CONFIDENT_SCORE in actions.py.
DETECT_THRESHOLD = 0.5


def available() -> bool:
    """Whether the optional ``openwakeword`` package is importable — a pure
    probe, safe to call on every request (no load, no model file access)."""
    return importlib.util.find_spec("openwakeword") is not None


def _model_path(name: str) -> Optional[str]:
    """The bundled ``.onnx`` path for a model name ("hey_jarvis" ->
    ".../hey_jarvis_v0.1.onnx"), or ``None`` if openwakeword ships nothing
    matching — models are bundled in the wheel itself (0.4.0), no download."""
    import openwakeword
    for path in openwakeword.get_pretrained_model_paths():
        stem = path.rsplit("/", 1)[-1].rsplit("\\", 1)[-1]
        if stem.startswith(name):
            return path
    return None


class ServerWakeWordDetector:
    """One continuous-listening session's worth of wake-word state.

    Construction is cheap; the model loads lazily on the first
    :meth:`process`, guarded by a lock — the HTTP server is threaded, and
    ``openwakeword.Model`` is not documented as thread-safe, so this
    instance must only ever be driven by one client's sequential chunk
    stream (enforced by :class:`ServerWakeWordSessions`, one detector per
    client id).
    """

    model_name = DEFAULT_MODEL

    def __init__(self, model: str = DEFAULT_MODEL) -> None:
        self.model_name = model
        self._model = None
        # Reentrant: process()/reset() hold this for their whole call (not
        # just around _load()) to serialize every touch of the underlying
        # Model — openwakeword.Model isn't documented as thread-safe, and
        # without this a client whose inference is slower than its chunk
        # cadence (see serverwake.js) could have two chunks for the same
        # session in flight on two request threads at once. RLock so _load()
        # calling back in from inside an already-held lock doesn't deadlock.
        self._lock = threading.RLock()

    def available(self) -> bool:
        return available() and _model_path(self.model_name) is not None

    def _load(self):
        with self._lock:
            if self._model is None:
                from openwakeword.model import Model
                path = _model_path(self.model_name)
                if path is None:
                    raise RuntimeError(
                        f"no bundled openwakeword model matches {self.model_name!r}")
                self._model = Model(wakeword_model_paths=[path])
            return self._model

    def process(self, pcm16_bytes: bytes) -> bool:
        """Feed one chunk of 16 kHz mono 16-bit PCM audio; ``True`` if the
        wake word's score crossed :data:`DETECT_THRESHOLD` in this chunk.

        Frames should keep arriving in order for the same session — the
        model's internal buffer spans calls (see the class docstring)."""
        import numpy as np

        with self._lock:
            model = self._load()
            frame = np.frombuffer(pcm16_bytes, dtype=np.int16)
            if frame.size == 0:
                return False
            scores = model.predict(frame)
            return any(score >= DETECT_THRESHOLD for score in scores.values())

    def reset(self) -> None:
        """Clear the model's rolling buffers (e.g. after a detection fires,
        so the same phrase said again a moment later can re-trigger)."""
        with self._lock:
            if self._model is not None:
                self._model.reset()


class ServerWakeWordSessions:
    """Per-client detector registry, mirroring the ``routers`` dict in
    ``http_api.py``: one client id -> one persistent detector, created on
    first use and released when wake-listening stops (or memory would grow
    with every device that has ever used the feature)."""

    def __init__(self, model: str = DEFAULT_MODEL,
                 now=time.monotonic) -> None:
        self.model = model
        self.now = now
        self._sessions: Dict[str, ServerWakeWordDetector] = {}
        self._seen: Dict[str, float] = {}
        self._lock = threading.Lock()

    def available(self) -> bool:
        return available()

    def _sweep(self) -> None:
        """Drop sessions nobody has fed for a while. Called under the lock
        from get_or_create — a client that stopped streaming has, by
        definition, stopped calling in, so there is no other moment to notice
        it; the next client's chunk is a fine one."""
        cutoff = self.now() - IDLE_SESSION_SECONDS
        for client in [c for c, seen in self._seen.items() if seen < cutoff]:
            self._sessions.pop(client, None)
            self._seen.pop(client, None)

    def get_or_create(self, client_id: str) -> ServerWakeWordDetector:
        with self._lock:
            self._sweep()
            det = self._sessions.get(client_id)
            if det is None:
                det = ServerWakeWordDetector(self.model)
                self._sessions[client_id] = det
            self._seen[client_id] = self.now()
            return det

    def stop(self, client_id: str) -> None:
        with self._lock:
            self._sessions.pop(client_id, None)
            self._seen.pop(client_id, None)
