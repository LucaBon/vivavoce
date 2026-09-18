"""A catalogue's files on somebody else's queue, in the order they are heard.

The transport here keeps a real queue rather than a list of calls: the thing
that matters about ``insert`` is where chapter 2 *ends up*, and a call log
would only restate the implementation.
"""

import pytest

from player.composite import Composite
from player.protocols import Capabilities

STREAMABLE = Capabilities(streamable=True)


class Shelf:
    def __init__(self, files):
        self.files = files
        self.asked = []

    def stream_urls(self, item_id):
        self.asked.append(item_id)
        return list(self.files.get(item_id, []))

    def book_candidates(self, query, count=10):
        return [{"id": "b1", "title": query, "author": "", "duration": 0.0}][:count]


class Queue:
    """A transport that remembers what it holds and what is playing."""

    def __init__(self, tracks=(), current=0):
        self.tracks = list(tracks)
        self.current = current
        self.calls = []

    def play_tracks(self, tracks):
        self.calls.append("play_tracks")
        self.tracks, self.current = [t["url"] for t in tracks], 0

    def add_url(self, url):
        self.calls.append("add_url")
        self.tracks.append(url)

    def insert_url(self, url):
        self.calls.append("insert_url")
        self.tracks.insert(self.current + 1, url)


BOOK = ["ch1", "ch2", "ch3"]


@pytest.fixture
def composite():
    return Composite(Shelf({"book": BOOK, "ebook": []}), STREAMABLE,
                     "Audiobookshelf")


def test_play_replaces_the_queue_and_keeps_the_chapter_order(composite):
    queue = Queue(["song-a", "song-b"], current=1)
    assert composite.enqueue(queue, "book", "play") == 3
    assert queue.tracks == BOOK
    assert queue.current == 0
    # One call for the whole book: on Music Assistant, starting the first
    # file and then appending the rest one by one races the start.
    assert queue.calls == ["play_tracks"]


def test_add_goes_after_everything_already_queued(composite):
    queue = Queue(["song-a", "song-b"])
    composite.enqueue(queue, "book", "add")
    assert queue.tracks == ["song-a", "song-b"] + BOOK


def test_insert_puts_the_whole_book_next_in_order(composite):
    # The trap: each insert lands right after the current track, so chapters
    # inserted first-to-last come out last-to-first.
    queue = Queue(["song-a", "song-b", "song-c"], current=1)
    composite.enqueue(queue, "book", "insert")
    assert queue.tracks == ["song-a", "song-b"] + BOOK + ["song-c"]


@pytest.mark.parametrize("mode", ["play", "add", "insert"])
def test_nothing_to_listen_to_sends_nothing(composite, mode):
    # An e-book must not cost the listener the queue they had.
    queue = Queue(["song-a"])
    assert composite.enqueue(queue, "ebook", mode) == 0
    assert queue.calls == []
    assert queue.tracks == ["song-a"]


def test_the_transport_is_whichever_one_is_handed_over(composite):
    # No transport is held: a room turn passes the kitchen's client, and the
    # book plays in the kitchen with no code of its own.
    lounge, kitchen = Queue(), Queue()
    composite.enqueue(kitchen, "book")
    assert kitchen.tracks == BOOK and lounge.calls == []


def test_an_unknown_mode_is_refused_before_asking_the_catalogue(composite):
    with pytest.raises(ValueError):
        composite.enqueue(Queue(), "book", "shuffle")
    assert composite.library.asked == []


def test_a_catalogue_that_cannot_stream_is_refused_at_construction():
    # Refused at startup, not at the first sentence: the flag is what the
    # engine would offer the feature on.
    with pytest.raises(ValueError, match="not streamable"):
        Composite(Shelf({}), Capabilities(), "Scaffale")


def test_book_search_is_the_catalogues(composite):
    assert composite.book_candidates("Pinocchio", 1)[0]["title"] == "Pinocchio"


# -- against the real clients --------------------------------------------------
#
# The Queue above proves the order; these prove the two music systems really
# receive it the way the order assumes.

def test_music_assistant_gets_the_whole_book_in_one_play_media(composite, ma,
                                                               ma_transport):
    ma_transport.responses["player_queues/get_active_queue"] = {
        "queue_id": "q1"}
    composite.enqueue(ma, "book", "play")
    plays = [args for command, args in ma_transport.calls
             if command == "player_queues/play_media"]
    assert plays == [{"queue_id": "q1", "media": BOOK, "option": "replace"}]


def test_lms_starts_the_first_chapter_and_appends_the_rest(composite, lms,
                                                           transport):
    composite.enqueue(lms, "book", "play")
    playlist = [cmd for _, cmd in transport.calls if cmd[0] == "playlist"]
    assert [cmd[:3] for cmd in playlist] == [
        ["playlist", "play", "ch1"], ["playlist", "add", "ch2"],
        ["playlist", "add", "ch3"]]
