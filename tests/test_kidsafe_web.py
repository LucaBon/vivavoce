"""Kid-safe on the web app: JSON store, PIN + unlock window, router guard
plumbing, voice management intents, and the fail-safe policy (a revoked
license keeps ENFORCING an enabled blocklist; it only locks changes)."""

import json
import threading

import pytest

import actions
from blocklist_store import BlocklistStoreError, JsonBlocklistStore
from conftest import FakeLicense
from pro.kidsafe import KidSafe, LOCKOUT_SECONDS, MAX_ATTEMPTS, UNLOCK_SECONDS
from router import Router


@pytest.fixture
def ks(tmp_path, clock):
    return KidSafe(str(tmp_path), FakeLicense(pro=True), now=clock)


# -- JsonBlocklistStore ---------------------------------------------------------

def test_store_roundtrip_preserves_other_keys(tmp_path):
    path = str(tmp_path / "kidsafe.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump({"enabled": True, "pin": {"salt": "aa", "hash": "bb"}}, f)
    store = JsonBlocklistStore(path)
    assert store.get() == []
    store.put(["Song X", "  Some Singer "])
    assert store.get() == ["Song X", "Some Singer"]
    with open(path, encoding="utf-8") as f:
        state = json.load(f)
    assert state["enabled"] is True  # untouched
    assert state["pin"]["salt"] == "aa"


def test_store_fails_open_on_corrupt_file(tmp_path):
    path = tmp_path / "kidsafe.json"
    path.write_text("{not json", encoding="utf-8")
    assert JsonBlocklistStore(str(path)).get() == []


def test_store_fails_loud_on_unwritable_path(tmp_path):
    store = JsonBlocklistStore(str(tmp_path / "no-such-dir" / "kidsafe.json"))
    with pytest.raises(BlocklistStoreError):
        store.put(["x"])


# -- PIN / unlock window ---------------------------------------------------------

def test_enable_first_run_sets_pin_and_unlocks(ks):
    assert ks.enable("123456", "phoneA") == {"ok": True}
    assert ks.enabled()
    assert ks.has_pin()
    assert ks.is_unlocked("phoneA")
    assert not ks.is_unlocked("phoneB")


def test_enable_rejects_short_pin(ks):
    assert ks.enable("12", "c")["error"] == "pin_too_short"
    assert not ks.enabled()


def test_enable_later_requires_the_pin(ks):
    ks.enable("123456", "a")
    ks.disable("a")
    assert ks.enable("999999", "a")["error"] == "wrong_pin"
    assert ks.enable("123456", "a")["ok"]


def test_unlock_expires(ks, clock):
    ks.enable("123456", "a")
    ks.lock("a")
    assert ks.unlock("a", "123456")
    clock.t += UNLOCK_SECONDS + 1
    assert not ks.is_unlocked("a")


def test_wrong_pin_backoff(ks, clock):
    ks.enable("123456", "a")
    for _ in range(MAX_ATTEMPTS):
        assert not ks.unlock("kid", "000000")
    # Even the RIGHT pin is refused during the lockout window.
    assert not ks.unlock("kid", "123456")
    clock.t += LOCKOUT_SECONDS + 1
    assert ks.unlock("kid", "123456")


def test_lockout_is_global_not_per_client(ks, clock):
    """The client id comes from the request body, so a per-client counter is
    no counter at all: rotating the string bought 5 fresh guesses each time."""
    ks.enable("123456", "a")
    for i in range(MAX_ATTEMPTS):
        assert not ks.unlock(f"kid-{i}", "000000")
    assert not ks.unlock("a-brand-new-id", "123456")
    assert ks.locked_out_for() > 0


def test_lockout_wait_doubles_and_survives_restart(ks, clock, tmp_path):
    ks.enable("123456", "a")
    for _ in range(MAX_ATTEMPTS):
        ks.unlock("kid", "000000")
    assert ks.locked_out_for() == pytest.approx(LOCKOUT_SECONDS)
    clock.t += LOCKOUT_SECONDS + 1
    ks.unlock("kid", "000000")            # sixth miss
    assert ks.locked_out_for() == pytest.approx(2 * LOCKOUT_SECONDS)
    # A restart must not hand the guesser a clean slate.
    fresh = KidSafe(str(tmp_path), FakeLicense(pro=True), now=clock)
    assert fresh.locked_out_for() == pytest.approx(2 * LOCKOUT_SECONDS)


def test_right_pin_clears_the_lockout(ks, clock):
    ks.enable("123456", "a")
    for _ in range(MAX_ATTEMPTS - 1):
        ks.unlock("kid", "000000")
    assert ks.unlock("a", "123456")
    assert ks.locked_out_for() == 0
    for _ in range(MAX_ATTEMPTS - 1):     # the counter really restarted
        ks.unlock("kid", "000000")
    assert ks.locked_out_for() == 0


def test_enable_requires_a_six_digit_pin(ks):
    assert ks.enable("12345", "c")["error"] == "pin_too_short"
    assert ks.enable("123456", "c")["ok"]


def test_disable_requires_unlock(ks, clock):
    ks.enable("123456", "a")
    clock.t += UNLOCK_SECONDS + 1
    assert ks.disable("a")["error"] == "locked"
    ks.unlock("a", "123456")
    assert ks.disable("a")["ok"]
    assert not ks.enabled()


# -- fail-safe: revoked license --------------------------------------------------

def test_revoked_license_keeps_enforcing_but_locks_changes(tmp_path, clock):
    lic = FakeLicense(pro=True)
    ks = KidSafe(str(tmp_path), lic, now=clock)
    ks.enable("123456", "a")
    ks.edit_terms("add", "Bad Song", "a")
    lic.pro = False  # refund/revoke after setup
    # Enforcement continues for a locked client...
    guard = ks.guard_for("kid")
    assert guard is not None and guard.blocks("Bad Song")
    # ...but configuration is refused.
    ks.unlock("a", "123456")
    assert ks.edit_terms("add", "Other", "a")["error"] == "pro_required"
    assert ks.disable("a")["error"] == "pro_required"


# -- the guard checks the whole item, not just the title -------------------------

def test_a_blocked_artist_blocks_a_song_that_never_names_them():
    """The hole: only the request TEXT was checked for the artist, and every
    resolved track was then gated on its title alone. With ["Eminem"]
    blocked, a child saying «metti Lose Yourself» never says the blocked
    word — so it played, and the artist was read back aloud."""
    guard = actions.Guard(restricted=True, blocklist=["Eminem"])
    assert guard.blocks("Lose Yourself") is False        # the request text
    assert guard.blocks_item({"title": "Lose Yourself",
                              "artist": "Eminem"}) is True


def test_the_item_gate_covers_album_and_name_too():
    guard = actions.Guard(restricted=True, blocklist=["Antichrist Superstar"])
    assert guard.blocks_item({"title": "Cryptorchid",
                              "album": "Antichrist Superstar"}) is True
    guard = actions.Guard(restricted=True, blocklist=["Bad Station"])
    assert guard.blocks_item({"name": "Bad Station", "id": "fav.1"}) is True


def test_an_unrestricted_guard_stays_transparent():
    guard = actions.Guard(restricted=False, blocklist=["Eminem"])
    assert guard.blocks_item({"title": "X", "artist": "Eminem"}) is False


def test_a_blocked_artist_is_refused_through_play_song(lms, transport,
                                                       make_tidal):
    transport.responses["tidal"] = make_tidal(
        categories={"Songs": "S"},
        items={"S": [{"isaudio": 1, "url": "tidal://1.flc",
                      "name": "Lose Yourself", "artist": "Eminem"}]},
    )
    guard = actions.Guard(restricted=True, blocklist=["Eminem"])
    reply = actions.play_song(lms, "Lose Yourself", guard=guard)
    assert reply.ok is False
    assert reply == actions.BLOCKED_SPEECH
    assert not any(c[:2] == ["playlist", "play"] for c in transport.commands())


def test_a_blocked_artist_learned_late_stops_the_music(lms, transport,
                                                       make_tidal):
    """Some feeds carry no artist on the search item; the now-playing status
    does. Learning it a moment late must still not leave the song playing —
    nor read the blocked name aloud in the confirmation."""
    transport.responses["tidal"] = make_tidal(
        categories={"Songs": "S"},
        items={"S": [{"isaudio": 1, "url": "tidal://1.flc",
                      "name": "Lose Yourself"}]},
    )
    transport.responses["status"] = {
        "playlist_loop": [{"title": "Lose Yourself", "artist": "Eminem"}]}
    guard = actions.Guard(restricted=True, blocklist=["Eminem"])
    reply = actions.play_song(lms, "Lose Yourself", guard=guard)
    assert reply.ok is False
    assert "Eminem" not in reply
    assert ["playlist", "clear"] in transport.commands()


def test_a_blocked_artist_is_refused_through_a_numbered_pick(lms, transport):
    guard = actions.Guard(restricted=True, blocklist=["Eminem"])
    candidates = [{"title": "Lose Yourself", "artist": "Eminem",
                   "url": "tidal://1.flc"}]
    assert actions.choose_from(lms, candidates, 1, guard=guard) == \
        actions.BLOCKED_SPEECH
    assert actions.choose_by_name(lms, candidates, "Lose Yourself",
                                  guard=guard) == actions.BLOCKED_SPEECH
    assert not any(c[:2] == ["playlist", "play"] for c in transport.commands())


def test_a_blocked_artist_is_dropped_from_the_queue_read_out(lms, transport):
    transport.responses["status"] = {"playlist_loop": [
        {"title": "Now", "artist": "Someone"},
        {"title": "Lose Yourself", "artist": "Eminem"},
        {"title": "Clean", "artist": "Someone Else"},
    ]}
    guard = actions.Guard(restricted=True, blocklist=["Eminem"])
    reply = actions.queue_list(lms, guard=guard)
    assert "Lose Yourself" not in reply
    assert "Clean" in reply


# -- guard through the router -----------------------------------------------------

@pytest.fixture
def guarded_router(lms, tmp_path, clock):
    ks = KidSafe(str(tmp_path), FakeLicense(pro=True), now=clock)
    ks.enable("123456", "parent")
    ks.edit_terms("add", "Bad Song", "parent")
    router = Router(lms, kidsafe=ks, client_id="kid")
    return router, ks


def test_blocked_term_refused_for_locked_client_it(guarded_router, transport):
    router, _ks = guarded_router
    reply = router.handle("metti Bad Song")
    assert str(reply) == actions.msg("blocked")
    assert all(cmd[0] != "playlist" for cmd in transport.commands())


def test_blocked_term_refused_for_locked_client_en(guarded_router, transport):
    router, _ks = guarded_router
    reply = router.handle("play Bad Song", lang="en")
    assert "blocked-songs list" in str(reply)
    assert all(cmd[0] != "playlist" for cmd in transport.commands())


def test_unlocked_client_plays_blocked_term(guarded_router, transport, make_tidal):
    router, ks = guarded_router
    ks.unlock("kid", "123456")
    transport.responses["tidal"] = make_tidal(
        categories={"Songs": "S"},
        items={"S": [{"isaudio": 1, "url": "tidal://9.flc", "name": "Bad Song"}]},
    )
    router.handle("metti Bad Song", source="tidal")
    assert ["playlist", "play", "tidal://9.flc"] in transport.commands()


def test_unlock_expiry_relocks_the_router(guarded_router, transport, clock):
    router, ks = guarded_router
    ks.unlock("kid", "123456")
    clock.t += UNLOCK_SECONDS + 1
    reply = router.handle("metti Bad Song")
    assert str(reply) == actions.msg("blocked")


def test_router_without_kidsafe_unchanged(lms, transport, make_tidal):
    # The default (kidsafe=None) keeps the old behavior byte-for-byte.
    transport.responses["tidal"] = make_tidal(
        categories={"Songs": "S"},
        items={"S": [{"isaudio": 1, "url": "tidal://1.flc", "name": "Bad Song"}]},
    )
    Router(lms).handle("metti Bad Song", source="tidal")
    assert ["playlist", "play", "tidal://1.flc"] in transport.commands()


# -- voice management intents ------------------------------------------------------

def test_voice_block_requires_pro(lms, tmp_path, clock):
    ks = KidSafe(str(tmp_path), FakeLicense(pro=False), now=clock)
    router = Router(lms, kidsafe=ks, client_id="a")
    assert "Pro" in str(router.handle("blocca Bad Song"))


def test_voice_block_requires_unlock(guarded_router):
    router, _ks = guarded_router  # client "kid" is locked
    assert str(router.handle("blocca Altro")) == actions.msg("not_owner")


def test_voice_block_add_remove_list(guarded_router):
    router, ks = guarded_router
    ks.unlock("kid", "123456")
    assert "Altro" in str(router.handle("blocca Altro"))
    assert "Altro" in ks.terms()
    listing = str(router.handle("quali brani sono bloccati"))
    assert "Bad Song" in listing and "Altro" in listing
    assert "Altro" in str(router.handle("sblocca Altro"))
    assert "Altro" not in ks.terms()


def test_voice_block_en(guarded_router):
    router, ks = guarded_router
    ks.unlock("kid", "123456")
    assert "Thing" in str(router.handle("block Thing", lang="en"))
    listing = str(router.handle("what songs are blocked", lang="en"))
    assert "Thing" in listing
    assert "Thing" in str(router.handle("unblock Thing", lang="en"))


def test_block_titles_still_play(guarded_router, transport, make_tidal):
    # "metti Block Rockin' Beats" contains "block*" words but is a play.
    router, ks = guarded_router
    ks.unlock("kid", "123456")
    transport.responses["tidal"] = make_tidal(
        categories={"Songs": "S"},
        items={"S": [{"isaudio": 1, "url": "tidal://7.flc",
                      "name": "Block Rockin' Beats"}]},
    )
    router.handle("metti Block Rockin' Beats", source="tidal")
    assert ["playlist", "play", "tidal://7.flc"] in transport.commands()
    router.handle("play Block Rockin' Beats", source="tidal", lang="en")
    assert transport.commands().count(["playlist", "play", "tidal://7.flc"]) == 2


# -- HTTP endpoints -----------------------------------------------------------------

def test_kidsafe_http_flow(live_server, tmp_path, clock):
    ks = KidSafe(str(tmp_path), FakeLicense(pro=True), now=clock)
    srv = live_server(kidsafe=ks)

    def post(payload):
        return srv.json_post("/kidsafe", payload)

    state = srv.json_get("/kidsafe?client=parent")
    assert state == {"pro": True, "enabled": False, "haspin": False,
                     "locked": True}
    assert post({"client": "parent", "action": "enable",
                 "pin": "123456"})["enabled"] is True
    added = post({"client": "parent", "action": "add", "term": "Bad Song"})
    assert added["ok"] and added["terms"] == ["Bad Song"]
    # A locked client never sees the terms.
    assert "terms" not in srv.json_get("/kidsafe?client=kid")
    # Wrong pin -> still locked.
    wrong = post({"client": "kid", "action": "unlock", "pin": "000000"})
    assert wrong["ok"] is False and wrong["locked"] is True
    ok = post({"client": "kid", "action": "unlock", "pin": "123456"})
    assert ok["ok"] is True and ok["terms"] == ["Bad Song"]
    # And the genuine server-side enforcement: a hand-crafted /command with a
    # blocked term is refused for a locked client.
    reply = srv.json_post("/command", {"text": "metti Bad Song",
                                       "client": "other-kid"})
    assert reply["ok"] is False
    assert reply["speech"] == actions.msg("blocked")


# -- the wrong-PIN counter under concurrency -----------------------------------
#
# The gate was read, ~100ms of PBKDF2 ran, and only then was the counter
# re-read and incremented. Every request that arrived before the first write
# saw count 0 — so all of them passed a five-attempt gate, all of them were
# actually tested, and each wrote back "one more than the zero I read". The
# file settled on 1 or 2 instead of the real number, the backoff never
# engaged, and the next batch started from an untriggered gate again.
#
# Real time here, not the frozen `clock` fixture: the backoff is what closes
# the gate, and it closes it by comparing retry_at against now().

def _pro_kidsafe(tmp_path):
    return KidSafe(str(tmp_path), FakeLicense(pro=True))


def _hammer(ks, pin, threads):
    """Fire ``threads`` concurrent verify_pin calls, all released together."""
    start = threading.Barrier(threads)
    results = []
    guard = threading.Lock()

    def attempt():
        start.wait(timeout=10)
        got = ks.verify_pin(pin)
        with guard:
            results.append(got)

    workers = [threading.Thread(target=attempt) for _ in range(threads)]
    for w in workers:
        w.start()
    for w in workers:
        w.join(timeout=60)
    assert not any(w.is_alive() for w in workers), "verify_pin deadlocked"
    return results


def test_concurrent_wrong_pins_cannot_outrun_the_gate(tmp_path):
    ks = _pro_kidsafe(tmp_path)
    ks.enable("123456", "owner")

    results = _hammer(ks, "000000", 20)

    assert not any(results), "a wrong PIN was accepted"
    # Exactly MAX_ATTEMPTS got through and were counted; the rest met a closed
    # gate. The bug showed up here as a count of 1 or 2 — every thread writing
    # back an increment of the same stale zero.
    assert ks._lockout()["count"] == MAX_ATTEMPTS
    assert ks.locked_out_for() > 0, "the backoff never engaged"


def test_a_flood_is_not_twenty_password_hashes(tmp_path):
    # The gate exists so a hammering client costs nothing. Consulted outside
    # the critical section, it cost one PBKDF2 per waiting thread instead —
    # 200k iterations each, which is a fine way to occupy a server.
    from pro import kidsafe as kidsafe_module
    ks = _pro_kidsafe(tmp_path)
    ks.enable("123456", "owner")
    hashed = []
    real_hash = kidsafe_module._hash_pin

    def counting(pin, salt):
        hashed.append(pin)
        return real_hash(pin, salt)

    kidsafe_module._hash_pin = counting
    try:
        _hammer(ks, "000000", 20)
    finally:
        kidsafe_module._hash_pin = real_hash

    assert len(hashed) == MAX_ATTEMPTS, (
        f"{len(hashed)} PINs hashed behind a {MAX_ATTEMPTS}-attempt gate")


def test_a_correct_pin_still_clears_the_counter(tmp_path):
    ks = _pro_kidsafe(tmp_path)
    ks.enable("123456", "owner")
    assert ks.verify_pin("000000") is False
    assert ks._lockout()["count"] == 1
    assert ks.verify_pin("123456") is True
    assert ks._lockout()["count"] == 0


# -- one file, two writers -----------------------------------------------------

def test_a_pin_write_does_not_drop_a_concurrent_blocklist_edit(tmp_path,
                                                               monkeypatch):
    """kidsafe.json is read-modify-written from two places: KidSafe._save
    (PIN, enabled flag, lockout counter) and JsonBlocklistStore.put (terms).
    Atomic writes keep the file well-formed and do nothing about this: each
    reads the whole state and writes the whole state back, so whoever reads
    first writes last and silently drops the other's change. The server is
    thread-per-connection and both are reachable from the same panel.
    """
    import appdata

    ks = KidSafe(str(tmp_path), FakeLicense(pro=True))
    ks.store.put(["Old"])  # something to lose

    reading = threading.Event()
    release = threading.Event()
    real_read = appdata.read_json

    def slow_read(path, default=None):
        state = real_read(path, default)
        if not reading.is_set():
            reading.set()
            release.wait(5)  # hold the read-modify-write open
        return state

    monkeypatch.setattr(appdata, "read_json", slow_read)

    saver = threading.Thread(target=ks._save, kwargs={"enabled": True})
    saver.start()
    assert reading.wait(5), "the PIN write never reached its read"

    editor = threading.Thread(target=ks.store.put, args=(["Old", "New"],))
    editor.start()
    editor.join(1.0)
    assert editor.is_alive(), (
        "the blocklist edit sailed straight through a state file already "
        "being rewritten")

    release.set()
    saver.join(5)
    editor.join(5)

    assert ks.terms() == ["Old", "New"]
    assert ks.enabled() is True, "the blocklist edit dropped the enabled flag"


def test_a_term_that_cannot_be_saved_is_not_reported_as_saved(ks):
    """edit_terms answered ok=True over add_block/remove_block's own refusal,
    so a read-only data dir cleared the input and looked like success."""
    ks.enable("123456", "a")

    class _ReadOnlyStore:
        def get(self):
            return []

        def put(self, terms):
            raise BlocklistStoreError("read-only data dir")

    ks.store = _ReadOnlyStore()
    result = ks.edit_terms("add", "Bad Song", "a")
    assert result["ok"] is False
    assert result["error"] == "save_failed"
    assert result["speech"]  # what to tell the parent, in their language


def test_an_empty_term_is_not_reported_as_added(ks):
    ks.enable("123456", "a")
    assert ks.edit_terms("add", "   ", "a")["ok"] is False
    assert ks.terms() == []
