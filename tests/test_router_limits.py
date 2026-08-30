"""The length cap on a spoken command, and why it is not a nicety.

Every language pack carries phrases shaped ``verb\\s+(.+?)\\s+<literal>\\s*$``
— the queue insert, the local suffix, German's separable forms. A lazy capture
between two unbounded boundaries backtracks quadratically when the literal
never arrives, and ``httpbase.MAX_JSON_BYTES`` lets an unauthenticated POST to
``/api/v1/command`` carry 64 KB. Measured before the cap: 5.3 s in the Italian
``queue_insert`` alone, 6.8 s in ``local_suffix``, ~10 s through the router —
per request, against a server with no accounts that runs 128 at once.

The cap is the structural cure because the shape is in every pack and in every
pattern of that kind, including the ones nobody has written yet.
"""

import time

import pytest

from parsing import MAX_COMMAND_CHARS, clean_command
from router import Router


@pytest.fixture
def router(lms):
    return Router(lms)


@pytest.mark.parametrize("lang", ["it", "en", "de", "fr", "es"])
def test_an_oversized_command_is_refused_quickly(router, transport, lang):
    hostile = "spielen " * 8000
    assert len(hostile) > MAX_COMMAND_CHARS
    start = time.monotonic()
    speech = router.handle(hostile, lang=lang)
    elapsed = time.monotonic() - start
    assert elapsed < 1.0, f"{elapsed:.1f}s in {lang}"
    assert getattr(speech, "ok", None) is False
    assert transport.commands() == []


def test_a_command_at_the_limit_still_routes(router, transport):
    # The cap must not be reachable by anything a person says. A title padded
    # to just under it still plays.
    padded = "metti " + "a" * (MAX_COMMAND_CHARS - 10)
    assert len(padded) < MAX_COMMAND_CHARS
    speech = router.handle(padded)
    # It finds nothing (there is no such song), but it LOOKED — which is the
    # difference between the cap and a refusal.
    assert not str(speech).startswith("Non ho capito.")


def test_an_ordinary_command_is_nowhere_near_the_cap():
    longest = ("aggiungi Shine On You Crazy Diamond Parts One To Five "
               "di Pink Floyd alla coda")
    assert len(longest) * 4 < MAX_COMMAND_CHARS


def test_clean_command_tells_the_two_silences_apart():
    # Nothing heard and "that is not a command" are different answers, so the
    # helper returns different things: None and "".
    assert clean_command("   ") is None
    assert clean_command(None) is None
    assert clean_command("x" * (MAX_COMMAND_CHARS + 1)) == ""
    # ...and it still does what the router used to do inline.
    assert clean_command("Metti la 2.") == "Metti la 2"
