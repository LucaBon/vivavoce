"""Tests for edition/version awareness (P4): "X" vs "X (Live)" are editions of
ONE song — honor a requested edition, prefer the plain one otherwise, and
never waste a 'did you mean' on them. Genuinely different songs still ask."""

import actions


def _feed(make_tidal, names):
    return make_tidal(
        categories={"Songs": "S"},
        items={"S": [{"isaudio": 1, "url": f"tidal://{i}.flc", "name": n}
                     for i, n in enumerate(names, start=1)]},
    )


def test_requested_live_edition_wins(lms, transport, make_tidal):
    transport.responses["tidal"] = _feed(
        make_tidal, ["Comfortably Numb", "Comfortably Numb (Live)"])
    msg = actions.play_song(lms, "comfortably numb live")
    assert msg.ok is True and msg.kind != "disambiguate"
    assert ["playlist", "play", "tidal://2.flc"] in transport.commands()


def test_unrequested_edition_trusts_service_order(lms, transport, make_tidal):
    # Only editions of one song and no qualifier requested: play the service's
    # top edition instead of asking a useless "1: X (Live), 2: X (Remastered)".
    transport.responses["tidal"] = _feed(
        make_tidal, ["Time (Live)", "Time (Remastered)"])
    msg = actions.play_song(lms, "time")
    assert msg.ok is True and msg.kind != "disambiguate"
    assert ["playlist", "play", "tidal://1.flc"] in transport.commands()


def test_edition_variants_do_not_ask(lms, transport, make_tidal):
    # Before P4 these two distinct-title strings triggered a useless
    # "1: X, 2: X (Live)" ask; now they collapse to one song.
    transport.responses["tidal"] = _feed(
        make_tidal, ["Wish You Were Here (Live)", "Wish You Were Here (Demo)"])
    msg = actions.play_song(lms, "wish you were here live")
    assert msg.kind != "disambiguate"
    assert ["playlist", "play", "tidal://1.flc"] in transport.commands()


def test_genuinely_distinct_songs_still_ask(lms, transport, make_tidal):
    transport.responses["tidal"] = _feed(
        make_tidal, ["Another Brick in the Wall, Pt. 1",
                     "Another Brick in the Wall, Pt. 2"])
    msg = actions.play_song(lms, "brick")
    assert msg.kind == "disambiguate"


def test_version_helpers():
    assert actions._version_base("Comfortably Numb (Live) - Remastered") == (
        "comfortably numb"
    )
    assert actions._version_terms("metti time live") == frozenset({"live"})
    assert actions._version_terms("metti time") == frozenset()
