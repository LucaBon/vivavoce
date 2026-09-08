"""``GET``/``POST /wakeword/phrase``: the household's wake phrase.

The phrase used to live in each browser's localStorage, which was enough
while only the browser engine could hear it. The server engine listens on
behalf of every device in the house, so there has to be one answer — and,
because a Kaldi lexicon can only produce words it knows, there has to be a
refusal for phrases that would never fire at all. Measured on the bench:
"vivavoce" detects at 83-100%, the invented "zorblax" at 0%, with nothing in
between to warn anybody.

Same approach as test_wakeword_web.py: the real HTTP stack, fake engines.
"""

import json

from conftest import FakeLicense


class FakeStore:
    """Stands in for ``appdata.WakePhraseStore``."""

    def __init__(self, phrase="vivavoce", error=None):
        self.phrase = phrase
        self.error = error
        self.writes = []

    def get(self):
        return self.phrase

    def set(self, phrase):
        if self.error:
            raise self.error
        self.writes.append(phrase)
        self.phrase = phrase


class FakeVoskSessions:
    """A server engine that CAN answer the lexicon question."""

    model = "vosk-it"

    def __init__(self, missing=(), available=True, error=None):
        self.missing = list(missing)
        self._available = available
        self.error = error
        self.phrases = []

    def available(self):
        return self._available

    def out_of_vocabulary(self, phrase):
        if self.error:
            raise self.error
        return [w for w in phrase.split() if w in self.missing]

    def set_phrase(self, phrase):
        self.phrases.append(phrase)


class FakeFixedSessions:
    """A server engine that cannot: openWakeWord has no lexicon to ask."""

    model = "hey_jarvis"

    def available(self):
        return True


# -- GET ---------------------------------------------------------------------

def test_get_returns_the_stored_phrase(live_server):
    srv = live_server(wake_phrase_store=FakeStore("ciao impianto"))
    assert srv.json_get("/wakeword/phrase") == {"ok": True,
                                                "phrase": "ciao impianto"}


def test_get_without_a_store_is_unavailable_not_an_error(live_server):
    srv = live_server(wake_phrase_store=None)
    assert srv.json_get("/wakeword/phrase") == {"ok": False,
                                                "error": "unavailable"}


def test_get_phrase_is_not_shadowed_by_the_status_route(live_server):
    # Both start with "/wakeword", and the status route matched first, so
    # this endpoint answered {"available": ...} instead of the phrase.
    srv = live_server(wake_phrase_store=FakeStore(),
                      wakeword_sessions=FakeFixedSessions())
    assert "phrase" in srv.json_get("/wakeword/phrase")
    assert "available" in srv.json_get("/wakeword")


def test_get_is_not_pro_gated(live_server):
    # The free browser engine answers to this phrase too; gating the setting
    # behind Pro would lock the free tier out of its own wake word.
    srv = live_server(wake_phrase_store=FakeStore("vivavoce"),
                      license_mgr=FakeLicense(pro=False))
    assert srv.json_get("/wakeword/phrase")["ok"] is True


# -- POST: the happy path ----------------------------------------------------

def test_post_stores_the_phrase(live_server):
    store = FakeStore()
    srv = live_server(wake_phrase_store=store)
    assert srv.json_post("/wakeword/phrase", {"phrase": "ciao impianto"}) == \
        {"ok": True, "phrase": "ciao impianto"}
    assert store.writes == ["ciao impianto"]


def test_post_trims_whitespace(live_server):
    store = FakeStore()
    srv = live_server(wake_phrase_store=store)
    srv.json_post("/wakeword/phrase", {"phrase": "  vivavoce  "})
    assert store.writes == ["vivavoce"]


def test_post_tells_the_running_engine_about_the_change(live_server):
    # Every open session carries the old phrase. Without this the house keeps
    # answering to the previous one until each device reloads.
    sessions = FakeVoskSessions()
    store = FakeStore()
    srv = live_server(wake_phrase_store=store, wakeword_sessions=sessions)
    srv.json_post("/wakeword/phrase", {"phrase": "ciao impianto"})
    assert sessions.phrases == ["ciao impianto"]


def test_post_survives_an_engine_that_cannot_be_told(live_server):
    # openWakeWord has no set_phrase; that must not break saving.
    store = FakeStore()
    srv = live_server(wake_phrase_store=store,
                      wakeword_sessions=FakeFixedSessions())
    assert srv.json_post("/wakeword/phrase", {"phrase": "vivavoce"})["ok"]
    assert store.writes == ["vivavoce"]


# -- POST: the refusals ------------------------------------------------------

def test_post_refuses_a_phrase_the_engine_could_never_hear(live_server):
    store = FakeStore("vivavoce")
    sessions = FakeVoskSessions(missing=["zorblax"])
    srv = live_server(wake_phrase_store=store, wakeword_sessions=sessions)
    body = srv.json_post("/wakeword/phrase", {"phrase": "zorblax"})
    assert body == {"ok": False, "error": "out_of_vocabulary",
                    "words": ["zorblax"]}
    # Refused means NOT saved: the old phrase still works.
    assert store.writes == []
    assert store.get() == "vivavoce"
    assert sessions.phrases == []


def test_post_names_only_the_words_that_are_missing(live_server):
    sessions = FakeVoskSessions(missing=["zorblax"])
    srv = live_server(wake_phrase_store=FakeStore(),
                      wakeword_sessions=sessions)
    body = srv.json_post("/wakeword/phrase", {"phrase": "ciao zorblax"})
    assert body["words"] == ["zorblax"]


def test_post_refuses_an_empty_phrase(live_server):
    store = FakeStore()
    srv = live_server(wake_phrase_store=store)
    assert srv.json_post("/wakeword/phrase", {"phrase": "   "}) == \
        {"ok": False, "error": "empty"}
    assert store.writes == []


def test_post_without_a_store_is_unavailable(live_server):
    srv = live_server(wake_phrase_store=None)
    assert srv.json_post("/wakeword/phrase", {"phrase": "vivavoce"}) == \
        {"ok": False, "error": "unavailable"}


def test_post_rejects_a_body_that_is_not_json(live_server):
    srv = live_server(wake_phrase_store=FakeStore())
    resp = srv.post("/wakeword/phrase", b"not json at all")
    assert resp.status == 200
    assert resp.json() == {"ok": False, "error": "bad_json"}


def test_post_refuses_an_oversized_body(live_server):
    store = FakeStore()
    srv = live_server(wake_phrase_store=store)
    huge = json.dumps({"phrase": "x" * 8192}).encode("utf-8")
    assert srv.post("/wakeword/phrase", huge).json() == \
        {"ok": False, "error": "too_large"}
    assert store.writes == []


def test_a_failed_write_is_reported_not_swallowed(live_server):
    # Answering "saved" over a discarded write leaves somebody saying a
    # phrase nothing is listening for.
    store = FakeStore(error=OSError("read-only file system"))
    srv = live_server(wake_phrase_store=store)
    body = srv.json_post("/wakeword/phrase", {"phrase": "vivavoce"})
    assert body["ok"] is False
    assert "read-only" in body["error"]


# -- the lexicon check is advisory, never an obstacle ------------------------

def test_no_check_when_the_engine_is_unavailable(live_server):
    # The browser engine has no lexicon limit, so with no server engine
    # running every phrase is legitimately fine.
    store = FakeStore()
    sessions = FakeVoskSessions(missing=["zorblax"], available=False)
    srv = live_server(wake_phrase_store=store, wakeword_sessions=sessions)
    assert srv.json_post("/wakeword/phrase", {"phrase": "zorblax"})["ok"]
    assert store.writes == ["zorblax"]


def test_a_broken_check_does_not_block_the_setting(live_server):
    # The check is a warning about one engine, not the authority on the
    # phrase; if it throws, the setting still gets made.
    store = FakeStore()
    sessions = FakeVoskSessions(error=RuntimeError("fd 2 capture failed"))
    srv = live_server(wake_phrase_store=store, wakeword_sessions=sessions)
    assert srv.json_post("/wakeword/phrase", {"phrase": "vivavoce"})["ok"]
    assert store.writes == ["vivavoce"]


def test_endpoints_never_5xx(live_server):
    # The promise the whole audio surface makes: degraded is 200 + ok:false.
    srv = live_server(wake_phrase_store=None, wakeword_sessions=None)
    assert srv.try_get("/wakeword/phrase").status == 200
    assert srv.try_post("/wakeword/phrase", b"{}").status == 200
    assert srv.try_post("/wakeword/phrase", b"\xff\xfe").status == 200


def test_status_advertises_a_free_phrase_engine(live_server):
    # The two engines are SPOKEN differently — one breath for a free-phrase
    # engine, two steps for a fixed one — so the page has to be told which it
    # is talking to rather than guessing from the model name.
    srv = live_server(wakeword_sessions=FakeVoskSessions())
    assert srv.json_get("/wakeword") == {"available": True,
                                         "model": "vosk-it",
                                         "free_phrase": True}


def test_status_says_nothing_extra_when_no_engine_is_available(live_server):
    srv = live_server(wakeword_sessions=FakeVoskSessions(available=False))
    assert srv.json_get("/wakeword") == {"available": False}
