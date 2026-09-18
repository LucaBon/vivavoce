"""What the app answers on a music system that cannot do what was asked.

``Capabilities`` was declared by every backend and read by nobody (ARC-4), so
a system with speakers and no catalogue answered «metti Time» with an
``AttributeError`` three frames down — which reaches the listener as «non
riesco a contattare l'impianto», a lie about a hi-fi that is answering
perfectly.

The client here is the case the table was written for and that no backend is
yet: a pair of powered speakers. It has the transport controls and **nothing
else**, on purpose — so a branch that forgot to ask fails this file with
AttributeError rather than passing it with a plausible sentence.
"""

import contextlib

import pytest

from messages import msg
from player.protocols import Capabilities
from router import Router

#: Only the controls; no search, no library, no favorites, no genres or years,
#: no services, no sleep timer, no second player.
SPEAKERS_ONLY = Capabilities(seek=True, artwork=True)


class Speakers:
    """A transport and nothing more (see the module docstring)."""

    capabilities = SPEAKERS_ONLY

    def __init__(self):
        self.player_id = "spk"
        self.base_url = "http://speakers.invalid"
        self.calls = []

    @contextlib.contextmanager
    def turn_deadline(self, seconds):
        yield

    def _say(self, name, *args):
        self.calls.append((name, args))
        return {}

    # the transport controls, which every music system owes
    def pause(self): return self._say("pause")
    def resume(self): return self._say("resume")
    def next_track(self): return self._say("next_track")
    def previous_track(self): return self._say("previous_track")
    def volume(self, delta): return self._say("volume", delta)
    def volume_set(self, value): return self._say("volume_set", value)
    def seek(self, seconds): return self._say("seek", seconds)
    def clear_queue(self): return self._say("clear_queue")
    def queue_upcoming(self, limit=5): return []
    def now_playing_info(self): return {"title": "Qualcosa", "artist": "X",
                                        "mode": "play", "index": 0,
                                        "elapsed": 12.0, "connected": True}
    def status_info(self): return {"mode": "play", "title": "Qualcosa"}
    def play_url(self, url): return self._say("play_url", url)
    def add_url(self, url): return self._say("add_url", url)
    def insert_url(self, url): return self._say("insert_url", url)
    def play_tracks(self, tracks): return self._say("play_tracks", len(tracks))


@pytest.fixture
def speakers():
    return Speakers()


@pytest.fixture
def router(speakers):
    return Router(speakers, services=())


def test_the_speakers_have_every_control_a_music_system_owes(speakers):
    # Otherwise this file would be testing a fake nobody could build. NOT
    # `isinstance(speakers, PlayerTransport)`: that protocol also declares the
    # methods Capabilities gates — `sleep` is `sleep_timer` — so a legitimately
    # partial system is not an instance of it. Held to the mandatory set
    # instead, which is the list tests/test_player_protocol.py maintains.
    from test_player_protocol import TRANSPORT_ALWAYS

    missing = [m for m in TRANSPORT_ALWAYS if not callable(getattr(speakers, m, None))]
    assert missing == []


def test_the_controls_still_work(router, speakers):
    assert router.handle("pausa").ok
    assert router.handle("alza il volume").ok
    assert [name for name, _ in speakers.calls] == ["pause", "volume"]


@pytest.mark.parametrize("phrase, said", [
    ("metti Time", "no_search"),
    ("metti la canzone Time dei Pink Floyd", "no_search"),
    ("dalla mia musica metti Time", "no_local_library"),
    ("metti i preferiti", "no_favorites"),
    ("metti qualcosa per cena", "no_moods"),
    ("spegni tra 30 minuti", "no_sleep_timer"),
])
def test_what_it_cannot_do_it_says(router, phrase, said):
    reply = router.handle(phrase)
    assert not reply.ok, f"«{phrase}» ha finto di funzionare"
    assert str(reply) == msg(said), f"«{phrase}» ha risposto: {reply}"


def test_a_catalogue_with_no_services_is_asked_directly(speakers):
    """The other shape of partial: it can search, so the request HAS an
    answer, and refusing would be wrong. What it has not got is several
    services behind one system — no ``for_service``, no ``can_play``, no
    ``settle_pending`` — so the engine talks to it instead of to a clone of
    it aimed at one of them.
    """
    class Catalogue(Speakers):
        capabilities = Capabilities(search=True, seek=True, artwork=True)

        def search_tracks(self, query, count=20):
            self.calls.append(("search_tracks", (query,)))
            return [{"url": "x://1", "title": "Time"}]

    catalogue = Catalogue()
    reply = Router(catalogue, services=()).handle("metti Time")
    assert ("search_tracks", ("Time",)) in catalogue.calls
    assert reply.ok, str(reply)


def test_the_refusal_ends_the_turn(router):
    # kind=GATE, like kid-safe: handle_many must stop trying recognition
    # alternatives, because a better transcription will not make a speaker
    # grow a catalogue.
    import actions

    assert router.handle("metti Time").kind == actions.GATE


def test_a_sweep_of_alternatives_stops_at_the_refusal(router):
    out = router.handle_many(["metti Time", "metti Thyme", "metti Times"])
    assert out["ok"] is False
    assert out["speech"] == msg("no_search")
