"""The "report a misunderstood phrase" loop (privacy-first, T1.5).

The deterministic matcher improves only through user reports; the hook for
that is the ``unmatched`` flag on /command replies — true exactly when the
router fell through every pattern. An understood command that *failed*
(no search results, LMS down) is not a parser gap and must not be flagged,
or the reports would be noise. The version that lands in the pre-filled
issue comes from ``appdata.app_version()``.
"""

import appdata
from router import Router
from test_packaging import _pyproject_version


# -- the router flag -----------------------------------------------------------

def test_gibberish_is_flagged_unmatched(lms):
    reply = Router(lms).handle_many(["xyzzy frobnicate"])
    assert reply["ok"] is False
    assert reply["unmatched"] is True


def test_understood_but_failed_is_not_flagged(lms, transport):
    # "riproduci X" with zero results everywhere: a miss, but the parser DID
    # understand it — reporting it would not help the matcher.
    for name in ("albums", "artists", "titles"):
        transport.responses[name] = {"count": 0}
    reply = Router(lms).handle_many(["riproduci brano inesistente"],
                                    source="local")
    assert reply["ok"] is False
    assert reply["unmatched"] is False


def test_hit_is_not_flagged(lms, transport):
    reply = Router(lms).handle_many(["pausa"])
    assert reply["ok"] is True
    assert reply["unmatched"] is False


def test_empty_input_is_not_flagged(lms):
    # Nothing was heard: there is no phrase to report.
    reply = Router(lms).handle_many([])
    assert reply["unmatched"] is False


def test_alternatives_flag_follows_the_kept_one(lms, transport):
    # The reply the user sees is the primary alternative; the flag must
    # describe that one, not the last tried.
    reply = Router(lms).handle_many(["xyzzy frobnicate", "gibberish too"])
    assert reply["unmatched"] is True
    hit = Router(lms).handle_many(["xyzzy frobnicate", "pausa"])
    assert hit["ok"] is True
    assert hit["unmatched"] is False


# -- over HTTP -----------------------------------------------------------------

def test_command_reply_carries_the_flag(live_server):
    reply = live_server().json_post("/command", {"text": "xyzzy frobnicate",
                                                 "client": "phone"})
    assert reply["unmatched"] is True


def test_version_reaches_the_page_config(live_server):
    page = live_server(app_version="9.9.9-test").get("/").text
    assert 'version: "9.9.9-test"' in page


# -- the version helper --------------------------------------------------------

def test_app_version_reads_pyproject():
    assert appdata.app_version(environ={}) == _pyproject_version()


def test_app_version_env_override_wins():
    assert appdata.app_version(
        environ={"VIVAVOCE_VERSION": "7.7.7"}) == "7.7.7"
