"""What the app remembers about services that play nothing.

The third incident of 2026-09-14, and the one that is a fact about the
HOUSEHOLD rather than about a bad afternoon: a TIDAL subscription that had
ended, and a Spotty that answers «play» and never advances. Neither can be
seen by asking — both search perfectly — and neither should have to be
rediscovered, with a real silent play, after every restart.
"""

import pytest

from lms import LMSClient
import playback
from player.silence import (PLAYBACK_MISS_TTL, PLAYBACK_PROOF_AFTER,
                            PLAYBACK_PROOF_WITHIN)
from servicestate import SilenceFile


class FakeStore:
    """``read``/``write``, and a record of every write, standing in for the
    JSON file the app hands the client."""

    def __init__(self, start=None):
        self.marks = dict(start or {})
        self.writes = 0

    def read(self):
        return dict(self.marks)

    def write(self, marks):
        self.marks = dict(marks)
        self.writes += 1


@pytest.fixture
def clock():
    class Clock:
        t = 1_000_000.0

        def __call__(self):
            return self.t

        def tick(self, seconds):
            self.t += seconds
    return Clock()


@pytest.fixture
def client(transport, clock):
    c = LMSClient(base_url="http://lms.local:9000", player_id="aa:bb",
                  transport=transport, service="tidal")
    c.now = clock
    return c


# -- what is remembered, and where -------------------------------------------
def test_a_mark_survives_the_process_that_learned_it(transport, clock):
    store = FakeStore()
    first = LMSClient(base_url="http://lms.local:9000", player_id="aa:bb",
                      transport=transport, service="tidal")
    first.now = clock
    first.remember_silence_in(store)
    first.note_playback_failure()

    # A new process, the same house: nothing is asked of the server, and the
    # answer is already known.
    second = LMSClient(base_url="http://lms.local:9000", player_id="aa:bb",
                       transport=transport, service="tidal")
    second.now = clock
    second.remember_silence_in(store)
    transport.raise_on.add("tidal")          # can_search must not be reached
    assert second.can_play() is False


def test_the_mark_lets_go_on_its_own(client, transport, clock, make_feed):
    transport.responses["tidal"] = make_feed()
    client.note_playback_failure()
    assert client.can_play() is False
    clock.tick(PLAYBACK_MISS_TTL + 1)
    # A day later the question goes back to the server, as it did the first
    # time — the mark bounds how long a service that came back on its own
    # stays out, and nothing else.
    assert client.can_play() is True
    assert "tidal" not in client._silent_until


def test_naming_the_service_clears_it_at_once(client):
    client.note_playback_failure()
    client.forget_playback_failure()
    assert "tidal" not in client._silent_until


def test_a_mark_is_about_the_service_not_the_clone(client):
    qobuz = client.for_service("qobuz")
    client.note_playback_failure()
    assert "tidal" in qobuz._silent_until      # one store, shared
    assert qobuz._service_key() == "qobuz"


# -- the third shape: says «play», never advances ----------------------------
def test_a_start_that_never_advances_is_settled_on_the_next_request(
        client, transport, clock):
    client.note_playback_started()
    transport.responses["status"] = {"mode": "play", "time": 0,
                                     "playlist_cur_index": "0",
                                     "playlist_loop": [{"title": "Time"}]}
    clock.tick(PLAYBACK_PROOF_AFTER + 1)
    client.settle_pending()
    assert "tidal" in client._silent_until


def test_nothing_is_concluded_before_the_buffer_has_had_its_chance(
        client, transport, clock):
    # Three of these five seconds are what a healthy stream spends buffering
    # with the elapsed time at zero. Concluding here is how every good stream
    # would be called dead.
    client.note_playback_started()
    transport.responses["status"] = {"mode": "play", "time": 0,
                                     "playlist_loop": [{"title": "Time"}]}
    clock.tick(PLAYBACK_PROOF_AFTER - 1)
    client.settle_pending()
    assert client._silent_until == {}
    assert client._pending, "still open: the answer comes with the next request"


def test_one_second_of_audio_is_proof_of_life(client, transport, clock):
    # A mark earned during a network hiccup must not outlive the evidence.
    client.note_playback_failure()
    client.note_playback_started()
    transport.responses["status"] = {"mode": "play", "time": 4.2,
                                     "playlist_loop": [{"title": "Time"}]}
    clock.tick(PLAYBACK_PROOF_AFTER + 1)
    client.settle_pending()
    assert "tidal" not in client._silent_until


def test_a_player_that_cannot_be_reached_settles_nothing(client, transport, clock):
    client.note_playback_started()
    transport.raise_on.add("status")
    clock.tick(PLAYBACK_PROOF_AFTER + 1)
    client.settle_pending()
    assert client._silent_until == {}


def test_settling_twice_costs_one_look(client, transport, clock):
    client.note_playback_started()
    transport.responses["status"] = {"mode": "play", "time": 4.2,
                                     "playlist_loop": [{"title": "Time"}]}
    clock.tick(PLAYBACK_PROOF_AFTER + 1)
    client.settle_pending()
    before = len(transport.commands())
    client.settle_pending()
    assert len(transport.commands()) == before


# -- the file itself ---------------------------------------------------------
def test_the_file_round_trips(tmp_path):
    store = SilenceFile(str(tmp_path))
    store.write({"tidal": 1789404000.0})
    assert SilenceFile(str(tmp_path)).read() == {"tidal": 1789404000.0}


def test_a_corrupt_file_reads_as_nothing_known(tmp_path):
    # Fail open, like every other piece of state: the app relearns at the cost
    # of one silent play, rather than refusing to start.
    path = tmp_path / "services.json"
    path.write_text("{ not json", encoding="utf-8")
    assert SilenceFile(str(tmp_path)).read() == {}


def test_junk_values_are_dropped_rather_than_believed(tmp_path):
    path = tmp_path / "services.json"
    path.write_text('{"tidal": "domani", "qobuz": 12.0}', encoding="utf-8")
    assert SilenceFile(str(tmp_path)).read() == {"qobuz": 12.0}


# -- what a player at rest is NOT evidence of --------------------------------
# Found in review, and it was the worst way this could have been wrong: normal,
# successful use poisoning the store. A track that plays to the end leaves the
# player exactly as a track that never started does — stopped, at index 0,
# elapsed zero — and the first version read that as "this service played
# nothing" and put a day-long mark on it.

def test_a_track_that_played_to_the_end_is_not_a_failure(client, transport, clock):
    client.note_playback_started()
    clock.tick(300)                                   # five minutes: it finished
    transport.responses["status"] = {"mode": "stop", "time": 0,
                                     "playlist_cur_index": "0",
                                     "playlist_loop": [{"title": "Time"}]}
    client.settle_pending()
    assert client.silent_services() == {}


def test_a_player_somebody_stopped_is_not_a_failure(client, transport, clock):
    # «ferma la musica» and then another request: same reading, same answer.
    client.note_playback_started()
    clock.tick(PLAYBACK_PROOF_AFTER + 1)
    transport.responses["status"] = {"mode": "stop", "time": 0,
                                     "playlist_loop": [{"title": "Time"}]}
    client.settle_pending()
    assert client.silent_services() == {}


def test_a_queue_still_walking_five_seconds_later_is_a_failure(
        client, transport, clock):
    # The slow version of the walk: too slow for playback.after_play to catch
    # at 0.6s, and still going nowhere now. Index moved, nothing ever played.
    client.note_playback_started()
    transport.responses["status"] = {"mode": "play", "time": 0,
                                     "playlist_cur_index": "7",
                                     "playlist_loop": [{"title": "Time"}]}
    clock.tick(PLAYBACK_PROOF_AFTER + 1)
    client.settle_pending()
    assert "tidal" in client.silent_services()


def test_a_walking_queue_never_counts_as_proof_of_life(client, transport, clock):
    # The inverse of the same mistake: a moving index is how a dead queue
    # looks, so it must never be read as the service being alive.
    client.note_playback_failure()
    client.note_playback_started()
    transport.responses["status"] = {"mode": "play", "time": 0,
                                     "playlist_cur_index": "7",
                                     "playlist_loop": [{"title": "Time"}]}
    clock.tick(PLAYBACK_PROOF_AFTER + 1)
    client.settle_pending()
    assert "tidal" in client.silent_services()


def test_a_queue_somebody_skipped_and_then_stopped_is_not_a_failure(
        client, transport, clock):
    # Found in review: «prossima» twice, then stop from the remote. Stopped,
    # past the first entry, elapsed zero — the reading a silent queue that
    # walked to its end would leave too, so it proves neither, and it used to
    # put TIDAL out for a day.
    client.note_playback_started()
    clock.tick(PLAYBACK_PROOF_AFTER + 1)
    transport.responses["status"] = {"mode": "stop", "time": 0,
                                     "playlist_cur_index": "2",
                                     "playlist_loop": [{"title": "Money"}]}
    client.settle_pending()
    assert client.silent_services() == {}


def test_a_reading_long_after_the_start_is_not_evidence(
        client, transport, clock):
    # An hour later the player describes the evening, not our start: a track
    # changing over at that instant reads «play», elapsed zero.
    client.note_playback_started()
    clock.tick(PLAYBACK_PROOF_WITHIN + 1)
    transport.responses["status"] = {"mode": "play", "time": 0,
                                     "playlist_cur_index": "0",
                                     "playlist_loop": [{"title": "Time"}]}
    client.settle_pending()
    assert client.silent_services() == {}
    assert not client._pending, "closed: a later request must not re-read it"


def test_a_player_that_is_not_connected_blames_no_service(
        client, transport, clock):
    client.note_playback_started()
    clock.tick(PLAYBACK_PROOF_AFTER + 1)
    transport.responses["status"] = {"mode": "play", "time": 0,
                                     "player_connected": 0,
                                     "playlist_loop": [{"title": "Time"}]}
    client.settle_pending()
    assert client.silent_services() == {}


def test_a_start_on_a_disconnected_player_says_so_and_marks_nothing(
        client, transport, monkeypatch):
    # An unplugged Squeezebox takes the queue and stays at stop. That used to
    # read as «TIDAL non è collegato» — and then Qobuz, on the retry — with a
    # day-long mark on each.
    monkeypatch.setattr(playback.time, "sleep", lambda _s: None)
    transport.responses["status"] = {"mode": "stop", "time": 0,
                                     "player_connected": 0,
                                     "playlist_loop": [{"title": "Time"}]}
    client.play_url("tidal://42.flc")
    res = playback.started(client, "Riproduco Time.")
    assert res.kind == playback.PLAYER_OFFLINE and not res.ok
    assert "lettore" in str(res)
    assert client.silent_services() == {}
    assert ["playlist", "clear"] in transport.commands()


class BrokenStore(FakeStore):
    def write(self, marks):
        raise OSError(28, "No space left on device")


def test_a_store_that_cannot_write_costs_the_restart_not_the_request(
        client, transport, clock):
    # The write happens in the middle of a play. Raising there skipped the
    # undo that takes a silent track back off the queue.
    client.remember_silence_in(BrokenStore())
    client.note_playback_failure()
    assert "tidal" in client.silent_services()   # still known in memory
    assert not client.can_play()


def test_the_file_says_it_could_not_save_and_carries_on(tmp_path, capsys):
    store = SilenceFile(str(tmp_path / "gone"))   # a directory that isn't there
    store.write({"tidal": 1789404000.0})
    assert "services.json" in capsys.readouterr().out


def test_another_room_settles_nothing(client, transport, clock):
    # Multi-room: the kitchen started the track, the next command comes from
    # the living room. Its player is idle, and idle is not evidence about a
    # service nobody asked it to play.
    client.note_playback_started()
    other_room = client.for_player("bb:cc")
    transport.responses["status"] = {"mode": "stop", "time": 0,
                                     "playlist_loop": []}
    clock.tick(PLAYBACK_PROOF_AFTER + 1)
    other_room.settle_pending()
    assert client.silent_services() == {}


def test_an_expired_mark_is_not_announced(client, clock):
    # The startup banner reads this: naming a service the very next request
    # will happily use would be a lie told once a day.
    client.note_playback_failure()
    clock.tick(PLAYBACK_MISS_TTL + 1)
    assert client.silent_services() == {}
