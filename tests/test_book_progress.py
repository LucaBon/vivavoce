"""The progress sampler: every half minute, where each book of ours is, saved
to Audiobookshelf (T5.6). No clock and no sleep here — the loop's wait is
injected, and the book side is a stand-in for ``Composite``."""

import book_progress
from player.errors import PlayerUnreachable


class Books:
    """What the sampler needs of a Composite: the players, and a save."""

    def __init__(self, players, failing=()):
        self._players = list(players)
        self.failing = set(failing)
        self.saved = []

    def players(self):
        return list(self._players)

    def save_progress(self, transport):
        if transport in self.failing:
            raise PlayerUnreachable(f"{transport} is off")
        if transport == "broken":
            raise KeyError("a bug, not a network")
        self.saved.append(transport)
        return 1.0


class Rounds:
    """A stop event whose ``wait`` lets ``n`` rounds through, then stops —
    and remembers how long each wait was asked to be."""

    def __init__(self, n):
        self.n = n
        self.waits = []

    def wait(self, seconds):
        self.waits.append(seconds)
        self.n -= 1
        return self.n < 0


def test_every_player_with_a_book_is_saved():
    books = Books(["lounge", "kitchen"])
    book_progress.save_all(books)
    assert books.saved == ["lounge", "kitchen"]


def test_one_player_failing_does_not_cost_the_others(capsys):
    # Audiobookshelf down, or a player unplugged: logged, and the next
    # player — and the next round — still happen.
    books = Books(["lounge", "kitchen", "broken", "study"], failing={"kitchen"})
    book_progress.save_all(books)
    assert books.saved == ["lounge", "study"]
    log = capsys.readouterr().out
    assert "kitchen is off" in log and "a bug" in log


def test_an_outage_is_logged_once_not_every_half_minute(capsys):
    # The hi-fi switched off for the night is one line in the log, not one
    # every thirty seconds until morning; and its return is a line too.
    books = Books(["lounge"], failing={"lounge"})
    failures = {}
    for _ in range(5):
        book_progress.save_all(books, failures)
    assert capsys.readouterr().out.count("lounge is off") == 1
    books.failing.clear()
    book_progress.save_all(books, failures)
    assert "di nuovo" in capsys.readouterr().out
    assert failures == {}


def test_a_round_that_cannot_even_list_its_players_is_survived(capsys):
    class Broken(Books):
        def players(self):
            raise RuntimeError("bug in players()")
    book_progress.save_all(Broken([]))
    assert "bug in players()" in capsys.readouterr().out


def test_the_loop_saves_once_per_round_until_stopped():
    books = Books(["lounge"])
    rounds = Rounds(3)
    book_progress.start(books, every=30.0, stop=rounds).join(timeout=5)
    assert books.saved == ["lounge"] * 3
    assert rounds.waits == [30.0] * 4


def test_the_loop_waits_before_the_first_save():
    # A server just started has no books of ours; and a save in the same
    # instant as the play that made the record would only repeat it.
    books = Books(["lounge"])
    book_progress.start(books, stop=Rounds(0)).join(timeout=5)
    assert books.saved == []


def test_the_thread_does_not_keep_the_server_alive():
    thread = book_progress.start(Books([]), stop=Rounds(0))
    thread.join(timeout=5)
    assert thread.daemon
