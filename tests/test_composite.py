"""A catalogue's files on somebody else's queue, in the order they are heard.

The transport here keeps a real queue rather than a list of calls: the thing
that matters about ``insert`` is where chapter 2 *ends up*, and a call log
would only restate the implementation.
"""

import pytest

from player.composite import Composite
from player.errors import PlayerUnreachable
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


class ShelfWithTracks(Shelf):
    """A catalogue that also knows each file's length — Audiobookshelf's
    actual shape (T5.6), unlike the plain ``Shelf`` above."""

    def __init__(self, tracks):
        super().__init__({item_id: [t["url"] for t in files]
                          for item_id, files in tracks.items()})
        self.tracks_asked = []
        self._tracks = tracks

    def tracks(self, item_id):
        self.tracks_asked.append(item_id)
        return [dict(t) for t in self._tracks.get(item_id, [])]


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


class SeekingQueue(Queue):
    """A :class:`Queue` that also remembers a ``seek``, with the
    capabilities the engine reads before calling one."""

    def __init__(self, *args, seekable=True, **kwargs):
        super().__init__(*args, **kwargs)
        self.capabilities = Capabilities(seek=seekable)
        self.sought = []

    def seek(self, seconds):
        self.calls.append("seek")
        self.sought.append(seconds)


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


# -- resuming (T5.6) ------------------------------------------------------------

RESUMABLE = {"book": [{"url": "ch1", "duration": 300.0},
                      {"url": "ch2", "duration": 300.0},
                      {"url": "ch3", "duration": 300.0}]}


def test_a_never_started_book_plays_from_zero_with_no_seek():
    composite = Composite(ShelfWithTracks(RESUMABLE), STREAMABLE, "Audiobookshelf")
    queue = SeekingQueue()
    assert composite.enqueue(queue, "book", "play", 0.0) == 3
    assert queue.tracks == ["ch1", "ch2", "ch3"]
    assert queue.sought == []
    # start <= 0 never needs a file's length: the plain stream_urls path is
    # taken, exactly as before T5.6.
    assert composite.library.tracks_asked == []
    assert composite.library.asked == ["book"]


def test_resuming_mid_file_queues_only_what_is_left_and_seeks_into_it():
    composite = Composite(ShelfWithTracks(RESUMABLE), STREAMABLE, "Audiobookshelf")
    queue = SeekingQueue()
    # 350s in: 300s of chapter 1 gone, 50s into chapter 2 of 3.
    assert composite.enqueue(queue, "book", "play", 350.0) == 2
    assert queue.tracks == ["ch2", "ch3"]
    assert queue.sought == [50]


def test_a_transport_that_cannot_seek_still_gets_the_right_file():
    composite = Composite(ShelfWithTracks(RESUMABLE), STREAMABLE, "Audiobookshelf")
    queue = SeekingQueue(seekable=False)
    assert composite.enqueue(queue, "book", "play", 350.0) == 2
    assert queue.tracks == ["ch2", "ch3"]
    assert queue.sought == []
    assert "seek" not in queue.calls


def test_missing_durations_fall_back_to_playing_from_the_start():
    unknown = {"book": [{"url": "ch1", "duration": 0.0},
                        {"url": "ch2", "duration": 0.0}]}
    composite = Composite(ShelfWithTracks(unknown), STREAMABLE, "Audiobookshelf")
    queue = SeekingQueue()
    assert composite.enqueue(queue, "book", "play", 100.0) == 2
    assert queue.tracks == ["ch1", "ch2"]
    assert queue.sought == []


@pytest.mark.parametrize("shelf, seekable, reached", [
    (ShelfWithTracks(RESUMABLE), True, 350.0),   # seeks to the very second
    (ShelfWithTracks(RESUMABLE), False, 300.0),  # the start of chapter 2
    (ShelfWithTracks({"book": [{"url": "ch1", "duration": 0.0},
                               {"url": "ch2", "duration": 0.0}]}), True, 0.0),
    (Shelf({"book": ["ch1", "ch2"]}), True, 0.0),  # no ``tracks`` at all
    # Past the end of a book whose lengths are all known: from the start,
    # not a seek past the last file that would play nothing.
    (ShelfWithTracks({"book": [{"url": "ch1", "duration": 100.0},
                               {"url": "ch2", "duration": 100.0}]}), True, 0.0),
    # The last file's length unknown: no bound, so the seek is trusted.
    (ShelfWithTracks({"book": [{"url": "ch1", "duration": 300.0},
                               {"url": "ch2", "duration": 0.0}]}), True, 350.0),
])
def test_play_from_answers_where_playback_really_begins(shelf, seekable, reached):
    # The reply says this number, so it must be where the listener actually
    # is — not where Audiobookshelf says they stopped.
    composite = Composite(shelf, STREAMABLE, "Audiobookshelf")
    assert composite.play_from(SeekingQueue(seekable=seekable), "book",
                               350.0)[1] == reached


def test_a_seek_that_fails_leaves_the_book_playing_from_the_file_start():
    class FailingSeek(SeekingQueue):
        def seek(self, seconds):
            raise PlayerUnreachable("still loading")
    composite = Composite(ShelfWithTracks(RESUMABLE), STREAMABLE, "Audiobookshelf")
    queue = FailingSeek()
    assert composite.play_from(queue, "book", 350.0) == (2, 300.0)
    assert queue.tracks == ["ch2", "ch3"]


def test_start_is_ignored_outside_play_mode():
    composite = Composite(ShelfWithTracks(RESUMABLE), STREAMABLE, "Audiobookshelf")
    queue = SeekingQueue(["song-a"])
    composite.enqueue(queue, "book", "add", 350.0)
    assert queue.tracks == ["song-a", "ch1", "ch2", "ch3"]
    assert composite.library.tracks_asked == []


def test_a_catalogue_with_no_notion_of_progress_costs_nothing():
    # Shelf (unlike ShelfWithTracks) has no ``progress`` at all — the plain
    # shape most of this file uses, and the one every catalogue had before
    # T5.6.
    composite = Composite(Shelf({}), STREAMABLE, "Audiobookshelf")
    assert composite.progress("book") is None


def test_progress_is_read_off_the_catalogue_when_it_has_one():
    shelf = ShelfWithTracks(RESUMABLE)
    shelf.progress = lambda item_id: 42.0
    composite = Composite(shelf, STREAMABLE, "Audiobookshelf")
    assert composite.progress("book") == 42.0


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
