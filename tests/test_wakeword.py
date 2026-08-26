"""``pro/wakeword.py`` against the real ``openwakeword`` package.

Skips cleanly when the optional ``wakeword`` dependency group isn't
installed (``uv sync --group wakeword`` — deliberately its own group, not
``asr``; see the module docstring for why). Where it can run, this is the
one place a real API mismatch against the pinned ``openwakeword==0.4.0``
release would be caught — the HTTP-layer tests use a fake detector and
can't see that.
"""

import pytest

pytest.importorskip("openwakeword", reason="openwakeword not installed "
                    "(dev group: uv sync --group wakeword)")

import numpy as np

from pro.wakeword import (DEFAULT_MODEL, SAMPLE_RATE, ServerWakeWordDetector,
                          ServerWakeWordSessions, available)


def _silence(ms: int = 80) -> bytes:
    n = int(SAMPLE_RATE * ms / 1000)
    return np.zeros(n, dtype=np.int16).tobytes()


def test_available_is_true_when_installed():
    assert available() is True


def test_default_model_is_available():
    det = ServerWakeWordDetector(DEFAULT_MODEL)
    assert det.available() is True


def test_unknown_model_is_unavailable():
    det = ServerWakeWordDetector("not-a-real-model")
    assert det.available() is False


def test_processing_silence_never_triggers():
    det = ServerWakeWordDetector(DEFAULT_MODEL)
    assert det.process(_silence()) is False


def test_processing_several_chunks_in_sequence():
    # The model is stateful across calls (its own rolling feature buffer);
    # feeding it a short stream of silence must not raise or drift into a
    # false trigger.
    det = ServerWakeWordDetector(DEFAULT_MODEL)
    for _ in range(10):
        assert det.process(_silence()) is False


def test_empty_chunk_is_a_safe_no_op():
    det = ServerWakeWordDetector(DEFAULT_MODEL)
    assert det.process(b"") is False


def test_reset_is_callable_after_processing():
    det = ServerWakeWordDetector(DEFAULT_MODEL)
    det.process(_silence())
    det.reset()  # must not raise


def test_unknown_model_raises_on_process_not_on_construction():
    det = ServerWakeWordDetector("not-a-real-model")
    with pytest.raises(RuntimeError):
        det.process(_silence())


def test_sessions_are_independent_model_instances():
    sessions = ServerWakeWordSessions(DEFAULT_MODEL)
    a = sessions.get_or_create("phone")
    b = sessions.get_or_create("tablet")
    assert a is not b
    assert sessions.get_or_create("phone") is a  # same client -> same session
    sessions.stop("phone")
    assert sessions.get_or_create("phone") is not a  # released -> fresh one


def test_process_is_thread_safe_under_concurrent_chunks():
    # ThreadingHTTPServer runs one thread per request; if a client's chunk
    # cadence (see serverwake.js) ever outruns inference time, two chunks
    # for the SAME client_id can be in flight on two threads at once.
    # openwakeword.Model isn't documented as thread-safe, so process() must
    # serialize every touch of it — this hammers one detector from many
    # threads and only asserts nothing blows up (a race here would show up
    # as an exception or a hang, not a wrong return value).
    import threading

    det = ServerWakeWordDetector(DEFAULT_MODEL)
    errors = []

    def hammer():
        try:
            for _ in range(5):
                det.process(_silence())
        except Exception as exc:  # pragma: no cover - failure path
            errors.append(exc)

    threads = [threading.Thread(target=hammer) for _ in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=30)
    assert not any(t.is_alive() for t in threads), "a thread hung"
    assert errors == [], errors
