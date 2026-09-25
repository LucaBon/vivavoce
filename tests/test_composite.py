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


# -- chapters (T5.6) -----------------------------------------------------------

class Playing(SeekingQueue):
    """A :class:`SeekingQueue` that also says what it is playing, as
    ``now_playing_info`` and ``status_info`` do: the queue position, the
    seconds played of it, and — when the player knows it — its length."""

    def __init__(self, *args, player_id="lounge", mode="play", elapsed=0.0,
                 duration=0.0, **kwargs):
        super().__init__(*args, **kwargs)
        self.player_id = player_id
        self.mode, self.elapsed, self.duration = mode, elapsed, duration

    def now_playing_info(self):
        return {"title": "", "artist": "", "mode": self.mode,
                "index": self.current, "elapsed": self.elapsed,
                "connected": True}

    def status_info(self):
        return {"mode": self.mode, "elapsed": self.elapsed,
                "duration": self.duration}


class ShelfWithChapters(ShelfWithTracks):
    def __init__(self, tracks, chapters):
        super().__init__(tracks)
        self._chapters = chapters
        self.chapters_asked = []

    def chapters(self, item_id):
        self.chapters_asked.append(item_id)
        return [dict(ch) for ch in self._chapters.get(item_id, [])]


#: One file, three chapters inside it: the ``.m4b`` shape.
ONE_FILE = {"book": [{"url": "all", "duration": 3000.0}]}
THREE_INSIDE = {"book": [{"start": 0.0, "end": 1000.0, "title": "Uno"},
                         {"start": 1000.0, "end": 2000.0, "title": "Due"},
                         {"start": 2000.0, "end": 3000.0, "title": "Tre"}]}


def test_no_book_played_on_this_player_is_no_chapter():
    composite = Composite(ShelfWithTracks(RESUMABLE), STREAMABLE, "Audiobookshelf")
    assert composite.chapter_at(Playing()) is None


def test_with_no_chapters_on_the_server_each_file_is_one():
    # 350s in: the queue starts at file 2 of 3, so its head is the book's
    # second file, and 20s into it is 320s into the book.
    composite = Composite(ShelfWithTracks(RESUMABLE), STREAMABLE, "Audiobookshelf")
    queue = Playing()
    composite.play_from(queue, "book", 350.0)
    queue.elapsed = 20.0
    where = composite.chapter_at(queue)
    assert where["item_id"] == "book"
    assert where["position"] == 320.0
    assert where["index"] == 1
    assert [ch["start"] for ch in where["chapters"]] == [0.0, 300.0, 600.0]


def test_the_servers_chapters_are_found_inside_one_file():
    shelf = ShelfWithChapters(ONE_FILE, THREE_INSIDE)
    composite = Composite(shelf, STREAMABLE, "Audiobookshelf")
    queue = Playing()
    composite.enqueue(queue, "book", "play")
    queue.elapsed = 1500.0
    where = composite.chapter_at(queue)
    assert where["index"] == 1
    assert where["chapters"][1]["title"] == "Due"


def test_the_queue_moving_on_moves_the_chapter():
    composite = Composite(ShelfWithTracks(RESUMABLE), STREAMABLE, "Audiobookshelf")
    queue = Playing()
    composite.enqueue(queue, "book", "play")
    queue.current, queue.elapsed = 2, 10.0
    assert composite.chapter_at(queue)["index"] == 2


def test_another_player_has_not_got_the_book():
    # The record is per player: «capitolo successivo» in the kitchen must not
    # move the book playing in the lounge — nor start it in the kitchen.
    composite = Composite(ShelfWithTracks(RESUMABLE), STREAMABLE, "Audiobookshelf")
    composite.enqueue(Playing(player_id="lounge"), "book", "play")
    assert composite.chapter_at(Playing(player_id="kitchen")) is None


def test_a_stopped_player_is_not_playing_the_book():
    composite = Composite(ShelfWithTracks(RESUMABLE), STREAMABLE, "Audiobookshelf")
    queue = Playing()
    composite.enqueue(queue, "book", "play")
    queue.mode = "stop"
    assert composite.chapter_at(queue) is None


def test_a_queue_past_the_book_is_not_the_book():
    composite = Composite(ShelfWithTracks(RESUMABLE), STREAMABLE, "Audiobookshelf")
    queue = Playing()
    composite.enqueue(queue, "book", "play")
    queue.current = 3  # three files queued: index 3 is something else
    assert composite.chapter_at(queue) is None


def test_a_track_of_another_length_is_music_played_since():
    # Somebody put a record on from Material Skin: same player, index 0,
    # playing — only its length says it is not chapter 1. And once seen,
    # the record is dropped, so the book cannot come back by coincidence.
    composite = Composite(ShelfWithTracks(RESUMABLE), STREAMABLE, "Audiobookshelf")
    queue = Playing()
    composite.enqueue(queue, "book", "play")
    queue.duration = 241.0
    assert composite.chapter_at(queue) is None
    queue.duration = 300.0
    assert composite.chapter_at(queue) is None


@pytest.mark.parametrize("duration", [0.0, 300.0, 301.5])
def test_a_length_that_is_unknown_or_close_is_the_book(duration):
    composite = Composite(ShelfWithTracks(RESUMABLE), STREAMABLE, "Audiobookshelf")
    queue = Playing(duration=duration)
    composite.enqueue(queue, "book", "play")
    assert composite.chapter_at(queue)["index"] == 0


@pytest.mark.parametrize("mode", ["add", "insert"])
def test_a_book_queued_behind_something_else_cannot_be_placed(mode):
    # Its first file is not at the head of the queue, and where it is
    # depends on what was there: forgotten rather than guessed.
    composite = Composite(ShelfWithTracks(RESUMABLE), STREAMABLE, "Audiobookshelf")
    queue = Playing()
    composite.enqueue(queue, "book", "play")
    composite.enqueue(queue, "book", mode)
    assert composite.chapter_at(queue) is None


def test_an_unknown_file_length_before_the_head_places_nothing():
    unknown = {"book": [{"url": "ch1", "duration": 0.0},
                        {"url": "ch2", "duration": 300.0}]}
    composite = Composite(ShelfWithTracks(unknown), STREAMABLE, "Audiobookshelf")
    queue = Playing()
    composite.enqueue(queue, "book", "play")
    queue.current = 1
    assert composite.chapter_at(queue) is None


def test_the_catalogue_failing_is_tagged_as_the_catalogue():
    shelf = ShelfWithTracks(RESUMABLE)
    composite = Composite(shelf, STREAMABLE, "Audiobookshelf")
    queue = Playing()
    composite.enqueue(queue, "book", "play")

    def down(item_id):
        raise PlayerUnreachable("off")
    shelf.tracks = down
    with pytest.raises(PlayerUnreachable) as caught:
        composite.chapter_at(queue)
    assert caught.value.from_library


def test_a_chapter_inside_a_file_is_a_seek():
    composite = Composite(ShelfWithChapters(ONE_FILE, THREE_INSIDE),
                          STREAMABLE, "Audiobookshelf")
    queue = Playing()
    assert composite.play_chapter(queue, "book", THREE_INSIDE["book"][2]) == 2000.0
    assert queue.tracks == ["all"]
    assert queue.sought == [2000]


def test_a_chapter_that_is_a_file_needs_no_seek():
    composite = Composite(ShelfWithTracks(RESUMABLE), STREAMABLE, "Audiobookshelf")
    queue = Playing(seekable=False)
    assert composite.play_chapter(queue, "book", {"start": 300.0}) == 300.0
    assert queue.tracks == ["ch2", "ch3"]
    # ...and the record follows it: chapter 2 is now the queue's head.
    assert composite.chapter_at(queue)["index"] == 1


def test_a_chapter_inside_a_file_on_a_player_that_cannot_seek_sends_nothing():
    # Playing the file from its start would be chapter 1 announced as
    # chapter 3: the one thing this must not do.
    composite = Composite(ShelfWithChapters(ONE_FILE, THREE_INSIDE),
                          STREAMABLE, "Audiobookshelf")
    queue = Playing(["song-a"], seekable=False)
    assert composite.play_chapter(queue, "book", THREE_INSIDE["book"][2]) is None
    assert queue.calls == []
    assert queue.tracks == ["song-a"]


def test_the_first_chapter_is_the_book_from_the_start():
    composite = Composite(ShelfWithChapters(ONE_FILE, THREE_INSIDE),
                          STREAMABLE, "Audiobookshelf")
    queue = Playing(seekable=False)
    assert composite.play_chapter(queue, "book", THREE_INSIDE["book"][0]) == 0.0
    assert queue.tracks == ["all"]


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
