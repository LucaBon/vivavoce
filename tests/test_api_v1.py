"""The contract of ``POST /api/v1/command``.

Everything else this server answers is the web app talking to itself, and may
change with the page it serves. This one route is a promise to clients that
ship separately — a Home Assistant blueprint first (see
``docs/ha-integration-design.md``), whatever comes after it later — so the
things tested here are the things an outside caller is allowed to rely on:

* the **shape** of the reply, key for key, and the fact that it does not
  narrow when the request fails — the old ``/command`` dropped ``choices``
  from its error branch, which hid a field at the worst possible moment;
* ``needs_choice``, so "I asked instead of playing" is a flag and not an
  inference from a list's length;
* ``conversation_id`` as the session key, with ``client`` still accepted, so
  the open numbered list survives between two separate HTTP requests and two
  conversations never pick from each other's;
* ``/command``, unversioned, still answering exactly the same thing.

Driven over real HTTP through ``live_server`` — the routing, the JSON body
and the cross-site guard only exist in the handler.
"""

import json
import os

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Two library tracks that share a title: the local search finds both, cannot
# choose between them, and asks. The real "did you mean", not a list command.
TWO_LOVES = {"titles_loop": [{"id": 1, "title": "Love", "artist": "X"},
                             {"id": 2, "title": "Love", "artist": "Y"}]}

ASK_WHICH = "riproduci Love dalla mia musica"

CONTRACT_FIELDS = {"speech", "used", "ok", "terms", "choices", "needs_choice",
                   "unmatched"}


def _ambiguous(transport):
    """A library where 'Love' matches two different tracks and nothing else."""
    transport.responses["albums"] = {"count": 0}
    transport.responses["artists"] = {"count": 0}
    transport.responses["titles"] = TWO_LOVES


# -- the shape -----------------------------------------------------------------

def test_the_reply_carries_every_field_of_the_contract(live_server, transport):
    reply = live_server().json_post("/api/v1/command",
                                    {"text": "pausa",
                                     "conversation_id": "ha-1"})
    assert set(reply) == CONTRACT_FIELDS
    assert reply["ok"] is True
    assert isinstance(reply["speech"], str) and reply["speech"]
    assert reply["used"] == "pausa"
    assert reply["terms"] == [] and reply["choices"] == []
    assert reply["needs_choice"] is False and reply["unmatched"] is False
    assert ["pause", "1"] in transport.commands()


def test_the_error_branch_keeps_the_whole_shape(live_server, transport):
    # An LMSError is a normal answer ("non ci arrivo"); this is the other kind
    # — something nobody predicted escaping the router. The reply must still
    # carry every field, ``choices`` and ``needs_choice`` included: a contract
    # that loses fields on failure loses them in the caller's least-tested
    # code path.
    def explode(cmd):
        raise RuntimeError("boom")

    transport.responses["pause"] = explode
    resp = live_server().post_json("/api/v1/command",
                                   {"text": "pausa", "conversation_id": "ha-1"})
    assert resp.status == 200          # never a 5xx, like the rest of the app
    reply = resp.json()
    assert set(reply) == CONTRACT_FIELDS | {"error"}
    assert reply["ok"] is False
    assert reply["choices"] == []
    assert reply["needs_choice"] is False
    assert "boom" in reply["error"]
    assert reply["speech"]             # the caller is told something


# -- needs_choice --------------------------------------------------------------

def test_needs_choice_is_true_when_the_reply_asks_which_one(live_server,
                                                            transport):
    _ambiguous(transport)
    reply = live_server().json_post("/api/v1/command",
                                    {"text": ASK_WHICH,
                                     "conversation_id": "ha-1"})
    # A question, not a failure: ok is True and nothing played.
    assert reply["ok"] is True
    assert reply["needs_choice"] is True
    assert [c["label"] for c in reply["choices"]] == ["Love di X", "Love di Y"]
    assert not any(cmd[:1] == ["playlistcontrol"] for cmd in transport.commands())


def test_needs_choice_is_false_when_the_command_just_played(live_server,
                                                            transport):
    transport.responses["albums"] = {
        "albums_loop": [{"id": 345, "album": "90125", "artist": "Yes"}]}
    reply = live_server().json_post("/api/v1/command",
                                    {"text": "riproduci 90125",
                                     "conversation_id": "ha-1"})
    assert reply["ok"] is True
    assert reply["needs_choice"] is False
    assert reply["choices"] == []


def test_needs_choice_is_false_on_the_answer_to_the_question(live_server,
                                                             transport):
    # The pick closes the question. A client that kept answering "the 2"
    # because the flag was still true would loop.
    _ambiguous(transport)
    srv = live_server()
    srv.json_post("/api/v1/command", {"text": ASK_WHICH,
                                      "conversation_id": "ha-1"})
    pick = srv.json_post("/api/v1/command", {"text": "metti la 2",
                                             "conversation_id": "ha-1"})
    assert pick["ok"] is True
    assert pick["needs_choice"] is False
    assert pick["choices"] == []


# -- conversation_id -----------------------------------------------------------

def test_conversation_id_holds_the_open_list_between_requests(live_server,
                                                              transport):
    # The whole reason the field is in the contract: "the 2" is only
    # answerable if the second request lands on the router that asked.
    _ambiguous(transport)
    srv = live_server()
    srv.json_post("/api/v1/command", {"text": ASK_WHICH,
                                      "conversation_id": "ha-1"})
    pick = srv.json_post("/api/v1/command", {"text": "metti la 2",
                                             "conversation_id": "ha-1"})
    assert pick["ok"] is True
    # The second track of the list, not a fresh search: the session held.
    assert ["playlistcontrol", "cmd:load", "track_id:2"] in transport.commands()


def test_client_is_still_accepted_as_an_alias(live_server, transport):
    # The page has always sent ``client``; v1 renames the field without
    # breaking anything that already speaks the old name. Asking under one
    # spelling and answering under the other is what proves they are the same
    # session key and not two that happen to both work.
    _ambiguous(transport)
    srv = live_server()
    srv.json_post("/api/v1/command", {"text": ASK_WHICH, "client": "phone"})
    pick = srv.json_post("/api/v1/command", {"text": "metti la 2",
                                             "conversation_id": "phone"})
    assert pick["ok"] is True
    assert ["playlistcontrol", "cmd:load", "track_id:2"] in transport.commands()


def test_conversation_id_wins_over_client_when_both_are_sent(live_server,
                                                             transport):
    # Which one is the session key has to be decided, not left to chance:
    # ``conversation_id`` is the contract, ``client`` the compatibility
    # spelling. The list opened under one id is not reachable through the
    # other.
    _ambiguous(transport)
    srv = live_server()
    srv.json_post("/api/v1/command", {"text": ASK_WHICH,
                                      "conversation_id": "ha-1",
                                      "client": "phone"})
    pick = srv.json_post("/api/v1/command", {"text": "metti la 2",
                                             "client": "ha-1"})
    assert pick["ok"] is True
    assert ["playlistcontrol", "cmd:load", "track_id:2"] in transport.commands()


def test_two_conversations_do_not_see_each_others_list(live_server, transport):
    # Two rooms, two HA conversations, two phones: the same failure either
    # way if the session key is ignored.
    _ambiguous(transport)
    srv = live_server()
    srv.json_post("/api/v1/command", {"text": ASK_WHICH,
                                      "conversation_id": "kitchen"})
    other = srv.json_post("/api/v1/command", {"text": "metti la 2",
                                              "conversation_id": "study"})
    assert other["needs_choice"] is False
    assert ["playlistcontrol", "cmd:load", "track_id:2"] not in transport.commands()
    # ...and the conversation that asked can still answer.
    mine = srv.json_post("/api/v1/command", {"text": "metti la 2",
                                             "conversation_id": "kitchen"})
    assert mine["ok"] is True
    assert ["playlistcontrol", "cmd:load", "track_id:2"] in transport.commands()


# -- the unversioned alias -----------------------------------------------------

def test_command_answers_exactly_what_v1_answers(live_server, transport):
    # /command stays, forever as far as anything already calling it is
    # concerned. One implementation serves both paths, and this is what says
    # so: byte for byte the same body.
    _ambiguous(transport)
    srv = live_server()
    old = srv.json_post("/command", {"text": ASK_WHICH, "client": "a"})
    new = srv.json_post("/api/v1/command", {"text": ASK_WHICH,
                                            "conversation_id": "b"})
    assert old == new
    assert old["needs_choice"] is True


def test_an_unknown_post_path_is_still_a_404(live_server):
    # With Material Skin embedded the catch-all forwards to the LMS instead
    # (test_lmsproxy.py); /api/v2 is about the versioned contract, so it is
    # asked of the server without that panel — the shape every install has
    # when Material lives somewhere else.
    from conftest import ELSEWHERE_MATERIAL_URL
    srv = live_server(material_url=ELSEWHERE_MATERIAL_URL)
    resp = srv.try_post_json("/api/v2/command", {"text": "pausa"})
    assert resp.status == 404


# -- the cross-site guard covers the new path ----------------------------------

def test_v1_refuses_a_non_json_content_type(live_server):
    # /api/v1/command changes something and takes a JSON body, so it belongs
    # in webguard.JSON_ROUTES like /command: without the Content-Type check a
    # cross-origin page can POST it as a "simple request", with no preflight
    # to refuse.
    resp = live_server().try_post("/api/v1/command",
                                  data=json.dumps({"text": "pausa"}).encode(),
                                  content_type="text/plain")
    assert resp.status == 403
    assert resp.json()["error"] == "content_type"


# -- dogfooding ----------------------------------------------------------------

def test_the_web_app_itself_goes_through_v1():
    """The page has to be a client of the contract, not a privileged insider.

    An API only its author has ever called is an API nobody has tested, and
    the alias makes the regression invisible: point the page back at
    ``/command`` and every browser test still passes. So the call site is
    checked directly — the browser suite proves it *works*, this proves it is
    the versioned path it works through."""
    with open(os.path.join(ROOT, "localvoice", "static", "js", "chat.js"),
              encoding="utf-8") as f:
        source = f.read()
    assert 'fetch("/api/v1/command"' in source
    assert 'fetch("/command"' not in source


# -- input a real client will actually send ------------------------------------
#
# The first caller of this contract is a Home Assistant blueprint, and HA
# templates render loosely: a number stays a number, a scalar is not a list.
# These three were all reachable from a plausible YAML mistake, and the third
# was the dangerous kind — not an error, a wrong answer.

@pytest.mark.parametrize("bad", [123, ["a", "b"], {"k": 1}, True])
def test_a_wrongly_typed_text_is_answered_not_blamed(live_server, bad):
    """A bad request should get an answer about the request.

    It used to reach ``.strip()`` and come back as «Errore interno: 'int'
    object has no attribute 'strip'» — an internal-error message, with the
    caller's malformed value echoed into ``used``, which the contract declares
    to be a string. Now it is simply nothing said."""
    body = live_server().json_post("/api/v1/command", {"text": bad})
    assert isinstance(body["used"], str)
    assert "error" not in body
    assert body["ok"] is False


def test_alternatives_given_as_a_string_are_not_read_letter_by_letter(
        live_server, transport):
    """The one that was a silent wrong answer, not a visible error.

    A bare string is truthy AND iterable, so ``alternatives: "pausa"`` reached
    handle_many as five single characters. Every one missed, ``text`` was
    never tried, and the reply was "non ho capito" with ``unmatched: true`` —
    which also files a perfectly good phrase as a grammar gap. No error, no
    clue, and a pause that never happened."""
    body = live_server().json_post("/api/v1/command",
                                   {"text": "pausa",
                                    "alternatives": "pausa"})
    assert body["used"] == "pausa"
    assert body["unmatched"] is False


def test_alternatives_that_survive_nothing_fall_back_to_the_text(live_server):
    """Alternatives refine ``text``; they do not replace it with nothing.

    A list of numbers used to reach the exception branch. Answering "non ho
    sentito niente" to a caller who plainly said something would be the same
    mistake more politely, so the text is what gets tried."""
    body = live_server().json_post("/api/v1/command",
                                   {"text": "pausa",
                                    "alternatives": [1, 2]})
    assert body["used"] == "pausa"
    assert "error" not in body


@pytest.mark.parametrize("alts", [[""], ["   "], ["", "  "], []])
def test_blank_alternatives_fall_back_to_the_text_too(alts, live_server):
    """A blank string is a str, which is how it defeated the fallback.

    ``alternatives: [""]`` passed the isinstance filter, made a non-empty
    list, and so was used instead of ``text``; handle_many then dropped the
    blank and answered "non ho sentito niente" while the command sat unread in
    ``text``. A Home Assistant blueprint rendering an empty template variable
    sends exactly this body, and the pause it asked for never happened."""
    client = live_server()
    body = client.json_post("/api/v1/command",
                            {"text": "pausa", "alternatives": alts})
    assert body["used"] == "pausa"
    assert body["ok"] is True
    assert "error" not in body


def test_a_blank_alternative_does_not_hide_a_real_one(live_server):
    # Filtering the blanks must not throw away the alternatives beside them.
    body = live_server().json_post("/api/v1/command",
                                   {"text": "qualcosa che non esiste",
                                    "alternatives": ["", "pausa", "  "]})
    assert body["used"] == "pausa"
    assert body["ok"] is True


def test_the_route_tolerates_a_query_string(live_server):
    """A cache-buster is not a different route.

    The dispatcher matched ``self.path`` exactly while webguard matches the
    path with its query stripped, so ``?x=1`` passed the cross-site guard and
    then 404'd. It failed closed, which is why this is tolerance and not a
    hole — but an unexplained 404 on the one route that promises stability is
    what a client author trips over once and remembers."""
    body = live_server().json_post("/api/v1/command?ts=1",
                                   {"text": "pausa"})
    assert body["ok"] is True
