"""``ok`` — the flag that says whether a reply acted on the request.

``handle_many`` reads it to decide whether to try the next speech-recognition
alternative, and ``/api/v1/command`` publishes it as part of a versioned
contract, so a caller can branch on the outcome without parsing the sentence.

It used to be inferred, for any reply that came back as a plain string, from
whether the Italian text began with "Non ". That heuristic was wrong in *both*
languages — «Per farlo in Cucina serve Pro» is a refusal that does not start
with "non", and so is "First ask me for a list" — and every one of those
replies was published as ``ok: true``.

The fix was to stop inferring: every reply now carries the flag. These tests
hold that line at all three levels — the engine functions, ``Router.handle``,
and the JSON the v1 route sends — and the cross-language cases are the point,
because the wording is exactly what must not decide this any more.
"""

import pytest

import actions
from conftest import FakeLicense
from pro.kidsafe import KidSafe
from pro.multiroom import MultiRoom
from router import Router

PLAYERS = [{"playerid": "bb:bb", "name": "Cucina"}]
ONE_CANDIDATE = [{"title": "Time", "url": "tidal://1.flc"}]


class Store:
    """The blocklist store's contract, in memory; ``boom`` fails writes."""

    def __init__(self, terms=(), boom=False):
        self.terms = list(terms)
        self.boom = boom

    def get(self):
        return list(self.terms)

    def put(self, terms):
        if self.boom:
            from blocklist_store import BlocklistStoreError
            raise BlocklistStoreError("simulated")
        self.terms = list(terms)


# -- the engine: a refusal says so ------------------------------------------

def test_choose_from_refusals_carry_ok_false(lms, transport):
    """The pick paths that answer without acting. ``no_open_list`` is the one
    that read as a success in Italian too: «Prima chiedimi un elenco»."""
    assert actions.choose_from(lms, None, 1).ok is False        # no open list
    assert actions.choose_from(lms, ONE_CANDIDATE, 9).ok is False   # out of range
    assert actions.choose_from(lms, ONE_CANDIDATE, None).ok is False
    blocked = actions.Guard(restricted=True, blocklist=["Time"])
    assert actions.choose_from(lms, ONE_CANDIDATE, 1, guard=blocked).ok is False
    transport.raise_on.add("playlist")
    assert actions.choose_from(lms, ONE_CANDIDATE, 1).ok is False


def test_choose_from_hit_still_says_ok(lms):
    assert actions.choose_from(lms, ONE_CANDIDATE, 1).ok is True


def test_choose_by_name_keeps_none_and_flags_the_rest(lms, transport):
    """``None`` still means 'not a selection, keep routing' — it is not a
    refusal and must not become one, or the router stops falling through to a
    fresh search."""
    assert actions.choose_by_name(lms, ONE_CANDIDATE, "Nothing Like It") is None
    assert actions.choose_by_name(lms, None, "Time") is None
    blocked = actions.Guard(restricted=True, blocklist=["Time"])
    assert actions.choose_by_name(lms, ONE_CANDIDATE, "Time", guard=blocked).ok is False
    transport.raise_on.add("playlist")
    assert actions.choose_by_name(lms, ONE_CANDIDATE, "Time").ok is False


def test_now_playing_unreachable_is_a_miss(lms, transport):
    transport.raise_on.add("status")
    assert actions.now_playing(lms).ok is False


# -- the engine: blocklist edits --------------------------------------------

def test_blocklist_edits_flag_refusals():
    assert actions.add_block(Store(), "X", is_owner=False).ok is False
    assert actions.add_block(Store(), "", is_owner=True).ok is False
    assert actions.add_block(Store(boom=True), "X", is_owner=True).ok is False
    assert actions.remove_block(Store(), "X", is_owner=False).ok is False
    assert actions.remove_block(Store(), "", is_owner=True).ok is False
    assert actions.list_blocks(Store(), is_owner=False).ok is False


def test_blocklist_edits_flag_the_work_they_did():
    assert actions.add_block(Store(), "X", is_owner=True).ok is True
    assert actions.remove_block(Store(["X"]), "X", is_owner=True).ok is True
    assert actions.list_blocks(Store(["X"]), is_owner=True).ok is True
    assert actions.list_blocks(Store(), is_owner=True).ok is True  # empty list


def test_a_no_op_edit_is_a_hit_not_a_miss():
    """«è già bloccato» / «non è nella lista» are ``ok=True`` deliberately.

    ``ok=False`` sends ``handle_many`` on to the next recognition alternative,
    and for an edit command the next alternative is a *different term* — so
    calling this a miss would block, or unblock, whatever the second-best
    transcription heard. The request is satisfied either way."""
    assert actions.add_block(Store(["X"]), "X", is_owner=True).ok is True
    assert actions.remove_block(Store(), "X", is_owner=True).ok is True


# -- the engine: list read-outs ---------------------------------------------

def test_list_readout_speech_carries_the_flag(lms, transport):
    """``_remember`` hands this speech straight back to the router, so the
    dict's ``speech`` is the reply and needs the flag like any other."""
    assert actions.top_tracks_list(lms, "")["speech"].ok is False  # which artist?
    transport.raise_on.add("tidal")
    assert actions.top_tracks_list(lms, "Pink Floyd")["speech"].ok is False
    assert actions.local_albums_list(lms, "")["speech"].ok is False
    transport.raise_on.add("artists")
    assert actions.local_albums_list(lms, "Vasco")["speech"].ok is False


def test_list_readout_is_ok_but_carries_a_kind(lms, transport):
    """A read-out is an answer (``ok``), but ``Router._tag`` splices source and
    room tags only into results with no ``kind`` — a list is not a play to tag,
    and ``kind='list'`` is what keeps that untouched."""
    transport.responses["artists"] = {
        "artists_loop": [{"id": "7", "artist": "Vasco Rossi"}]}
    transport.responses["albums"] = {
        "albums_loop": [{"id": "1", "album": "Bollicine"}]}
    out = actions.local_albums_list(lms, "Vasco")
    assert out["candidates"], "fixture should produce a list to read out"
    assert out["speech"].ok is True
    assert out["speech"].kind == "list"


# -- the router: every reply carries the flag -------------------------------

@pytest.mark.parametrize("lang, text", [
    ("it", ""), ("en", ""),                    # heard_nothing
    ("it", "numero 9"), ("en", "number 9"),    # no open list
    ("it", "zzz qqq wubble"), ("en", "zzz qqq wubble"),   # router_fallback
])
def test_handle_reports_refusals_as_misses(lms, lang, text):
    assert Router(lms).handle(text, "tidal", lang).ok is False


@pytest.mark.parametrize("lang, text", [
    ("it", "metti bollicine in cucina"),
    ("en", "play bollicine in the kitchen"),
])
def test_room_needs_pro_is_a_miss_in_both_languages(lms, lang, text):
    """The headline case. «Per farlo in Cucina serve Pro» is a refusal, and it
    does not begin with "non" — under the old heuristic it was published as
    ``ok: true`` in Italian as well as English."""
    mr = MultiRoom(FakeLicense(pro=False), lambda: PLAYERS)
    reply = Router(lms, multiroom=mr).handle(text, "tidal", lang)
    assert reply.ok is False


@pytest.mark.parametrize("lang, text", [("it", "blocca X"), ("en", "block X")])
def test_pro_required_is_a_miss(lms, tmp_path, lang, text):
    ks = KidSafe(str(tmp_path), FakeLicense(pro=False))
    assert Router(lms, kidsafe=ks).handle(text, "tidal", lang).ok is False


@pytest.mark.parametrize("lang", ["it", "en"])
def test_no_reply_is_ever_a_bare_string(lms, transport, lang):
    """The invariant the bug broke: ``Router.handle`` returns an ActionResult,
    never a plain ``str``. Inferring the outcome from the wording is what this
    makes unnecessary — and, for the next reply added, impossible to fall back
    into without failing here."""
    transport.raise_on.add("status")
    phrases = ["", "zzz qqq wubble", "numero 9", "number 9", "pausa", "pause",
               "cosa sta suonando", "what is playing", "blocca X", "block X",
               "metti Time", "play Time", "svuota la coda", "clear the queue"]
    for phrase in phrases:
        reply = Router(lms).handle(phrase, "tidal", lang)
        assert hasattr(reply, "ok"), f"{lang} {phrase!r} came back a bare string"
        assert isinstance(reply.ok, bool)


# -- the contract: what /api/v1/command publishes ---------------------------

@pytest.mark.parametrize("lang, text", [
    ("it", "numero 9"), ("en", "number 9"),
    ("it", "zzz qqq wubble"), ("en", "zzz qqq wubble"),
])
def test_v1_command_publishes_the_refusal(live_server, lang, text):
    body = live_server().json_post(
        "/api/v1/command", {"text": text, "lang": lang})
    assert body["ok"] is False


def test_v1_command_still_publishes_a_hit(live_server, transport):
    transport.responses["status"] = {
        "mode": "play",
        "playlist_loop": [{"title": "Time", "artist": "Pink Floyd"}]}
    body = live_server().json_post(
        "/api/v1/command", {"text": "cosa sta suonando", "lang": "it"})
    assert body["ok"] is True


def test_unmatched_still_means_a_parser_gap(lms):
    """``ok=False`` and ``unmatched`` are different questions, and the fix must
    not have merged them: a refusal we understood is not a phrase we failed to
    parse, and only the latter offers the 'report this phrase' button."""
    r = Router(lms)
    assert r.handle_many(["numero 9"], "tidal", "it")["unmatched"] is False
    assert r.handle_many(["zzz qqq wubble"], "tidal", "it")["unmatched"] is True


# -- a gate ends the turn ----------------------------------------------------
# Both cases below are regressions the ``ok`` fix itself introduced, and they
# share a cause: flipping a reply from a plain string to ``ok=False`` moved it
# out of one code path (``_tag`` ignores anything without ``.ok``) and into
# another (``handle_many`` retries anything that is not a hit). ``kind`` tells
# the two apart now — see ``matching.GATE`` and ``matching.BLOCKLIST``.

SALOTTO = [{"playerid": "aa", "name": "Salotto"}]


def a_track_for(*terms):
    """A local-library ``titles`` response that answers only ``terms``.

    Enough that a second ASR alternative genuinely *would* start music if the
    gate let it through — without that, these tests would pass on a codebase
    that still has the bug."""
    def handler(cmd):
        search = next((c[len("search:"):] for c in cmd
                       if str(c).startswith("search:")), "")
        if any(t.lower() in search.lower() for t in terms):
            return {"titles_loop": [{"id": "9", "title": search, "artist": "X"}]}
        return {}
    return handler


def played(transport):
    return [c for c in transport.commands() if c[:2] == ["playlistcontrol"]
            or c[:2] == ["playlist", "play"]]


class Blocking:
    """A kid-safe stand-in: Pro, and blocking one name."""

    def __init__(self, term="Beatles", owner=False):
        self.store = Store()
        self.term = term
        self.owner = owner

    def pro_ok(self):
        return True

    def is_unlocked(self, client_id):
        return self.owner

    def guard_for(self, client_id):
        return actions.Guard(restricted=True, blocklist=[self.term])


def test_pro_wall_is_not_retried_into_playing_somewhere_else(lms, transport):
    """The free tier's room refusal must survive the next ASR alternative.

    «metti Beatles in salotto» is refused with the room named and the way out.
    Its second-best transcription is «metti Beatles» — no room, so it sails
    past the gate and starts the music in whatever room the selector points
    at. The listener never hears the refusal, and the music is in the wrong
    place, which is the one outcome the room work exists to prevent."""
    transport.responses["titles"] = a_track_for("Beatles")
    mr = MultiRoom(FakeLicense(pro=False), lambda: SALOTTO)
    reply = Router(lms, multiroom=mr).handle_many(
        ["metti Beatles in salotto", "metti Beatles"], "local", "it")
    assert reply["ok"] is False
    assert reply["used"] == "metti Beatles in salotto"
    assert "Salotto" in reply["speech"]
    assert played(transport) == []


def test_a_blocked_song_is_not_retried_until_a_spelling_slips_past(lms, transport):
    """Kid-safe, same shape: a child re-rolling the recogniser's dice."""
    transport.responses["titles"] = a_track_for("Beatles", "Beetles")
    reply = Router(lms, kidsafe=Blocking()).handle_many(
        ["metti Beatles", "metti Beetles"], "local", "it")
    assert reply["ok"] is False
    assert reply["used"] == "metti Beatles"
    assert played(transport) == []


def test_owner_gate_is_not_retried_into_a_different_intent(lms, transport):
    """«blocca Eminem» from a child must not become «metti Eminem»."""
    transport.responses["titles"] = a_track_for("Eminem")
    reply = Router(lms, kidsafe=Blocking(term="zzz")).handle_many(
        ["blocca Eminem", "metti Eminem"], "local", "it")
    assert reply["ok"] is False
    assert reply["used"] == "blocca Eminem"
    assert played(transport) == []


def test_a_search_miss_is_still_retried(lms, transport):
    """The gate rule must not cost ``handle_many`` its purpose: a miss about
    the *words* still hands on to the next transcription. This is the case
    Web Speech exists to rescue — it hears «sfigati» for 'Audioslave'."""
    transport.responses["titles"] = a_track_for("Audioslave")
    reply = Router(lms).handle_many(["metti sfigati", "metti Audioslave"],
                                    "local", "it")
    assert reply["ok"] is True
    assert reply["used"] == "metti Audioslave"


def test_blocklist_replies_never_take_a_room(lms):
    """The store is global, so «in Salotto» must not be spliced onto a
    blocklist reply: «Ok, ho bloccato Eminem in Salotto» describes a per-room
    blocklist that does not exist, and the read-out was worse — «Brani
    bloccati: Eminem in Salotto» reads as a blocked term."""
    mr = MultiRoom(FakeLicense(pro=True), lambda: SALOTTO)
    r = Router(lms, multiroom=mr, kidsafe=Blocking(term="zzz", owner=True))
    added = r.handle("blocca Eminem in salotto", "auto", "it")
    listed = r.handle("quali brani sono bloccati in salotto", "auto", "it")
    assert "Salotto" not in added
    assert "Salotto" not in listed
    assert added.ok is True and listed.ok is True   # still hits, still not tagged
