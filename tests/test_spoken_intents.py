"""Spoken media, the first slice (T5.4 + T5.6): a jump within the track, and a
book by name.

Two promises are held here beside the new sentences, because the new step
runs *ahead* of the transport block and could steal from it: a bare
«avanti» still skips the track, and a household with no ``--library`` gets
exactly the answers it got before — «metti l'audiolibro X» included.
"""

import contextlib

import pytest

import actions
from intents_spoken import seek_seconds
from messages import msg, set_lang
from player.composite import Composite
from player.errors import PlayerUnreachable
from player.protocols import Capabilities
from router import Router


class Player:
    """A transport that remembers what it was asked, with a track playing."""

    capabilities = Capabilities(seek=True, search=True)

    def __init__(self, elapsed=100.0, duration=600.0, mode="play"):
        self.player_id = "p1"
        self.base_url = "http://player.invalid"
        self.status = {"mode": mode, "title": "Capitolo 3",
                       "elapsed": elapsed, "duration": duration}
        self.calls = []
        # The queue position ``now_playing_info`` reports: 0 is the first
        # file a play just queued (see Composite.chapter_at).
        self.index = 0

    @contextlib.contextmanager
    def turn_deadline(self, seconds):
        yield

    def _say(self, name, *args):
        self.calls.append((name, args))
        return {}

    def status_info(self): return dict(self.status)
    def now_playing_info(self):
        return {"title": self.status["title"], "artist": "",
                "mode": self.status["mode"], "index": self.index,
                "elapsed": self.status["elapsed"], "connected": True}
    def seek(self, seconds):
        self.status["elapsed"] = float(seconds)  # a seek that lands, as most do
        return self._say("seek", seconds)
    def pause(self): return self._say("pause")
    def resume(self): return self._say("resume")
    def next_track(self): return self._say("next_track")
    def previous_track(self): return self._say("previous_track")
    def play_tracks(self, tracks): return self._say("play_tracks", [t["url"] for t in tracks])
    def search_tracks(self, query, count=20):
        self.calls.append(("search_tracks", (query,)))
        return []

    def names(self):
        return [name for name, _ in self.calls]


class Shelf:
    """A catalogue of books that answers from a table."""

    def __init__(self, books, files, progress=None):
        self.books, self.files = books, files
        self.asked = []
        # None (the default): this catalogue has no notion of progress at
        # all, as every one did before T5.6 — Composite.progress() must read
        # that as "never started" rather than raise. A dict maps an item id
        # to a position in seconds, as Audiobookshelf's own client answers.
        self._progress = progress

    def book_candidates(self, query, count=10):
        self.asked.append(query)
        return list(self.books)[:count]

    def stream_urls(self, item_id):
        return list(self.files.get(item_id, []))

    def progress(self, item_id):
        if self._progress is None:
            return None
        return self._progress.get(item_id)


HOBBIT = {"id": "b1", "title": "Lo Hobbit", "author": "J.R.R. Tolkien",
          "duration": 36000.0}


class TimedShelf(Shelf):
    """A :class:`Shelf` that also says how long each file runs — what a
    resume needs to find where it falls (``Composite.play_from``)."""

    def __init__(self, books, files, progress, duration):
        super().__init__(books, files, progress)
        self.duration = duration

    def tracks(self, item_id):
        return [{"url": url, "duration": self.duration}
                for url in self.files.get(item_id, [])]


def shelf_of(*books, files=None, progress=None, duration=None):
    """``duration``: seconds per file, making the shelf a :class:`TimedShelf`
    that can be resumed into; ``0.0`` is a length the catalogue does not
    know."""
    files = files if files is not None else {"b1": ["u1", "u2"]}
    shelf = (Shelf(books, files, progress) if duration is None
             else TimedShelf(books, files, progress, duration))
    return Composite(shelf, Capabilities(streamable=True), "Audiobookshelf")


@pytest.fixture
def player():
    return Player()


# -- the engine ---------------------------------------------------------------
def test_seek_relative_adds_to_where_the_track_is(player):
    reply = actions.seek_relative(player, 30)
    assert reply.ok
    assert player.calls == [("seek", (130.0,))]
    assert str(reply) == msg("seek_forward", span=msg("span_seconds", n=30))


def test_seek_relative_stops_at_the_start_and_short_of_the_end(player):
    actions.seek_relative(player, -600)
    actions.seek_relative(player, 3600)
    assert player.calls == [("seek", (0.0,)), ("seek", (599.0,))]


def test_seek_relative_trusts_a_track_that_has_no_duration():
    player = Player(elapsed=None, duration=None)
    actions.seek_relative(player, 90)
    assert player.calls == [("seek", (90.0,))]


def test_seek_relative_on_a_stopped_player_says_nothing_is_playing():
    player = Player(mode="stop")
    reply = actions.seek_relative(player, 30)
    assert str(reply) == msg("nothing_playing")
    assert player.calls == []


def test_seek_relative_on_an_unreachable_player(player):
    def down():
        raise PlayerUnreachable("off")
    player.status_info = down
    assert not actions.seek_relative(player, 30).ok


def test_seek_relative_on_the_lms_is_an_absolute_time_command(lms, transport):
    transport.responses["status"] = {
        "mode": "play", "time": 42.5,
        "playlist_loop": [{"title": "Cap. 1", "duration": 300}]}
    assert actions.seek_relative(lms, -10).ok
    assert ["time", "32"] in transport.commands()


@pytest.mark.parametrize("amount, unit, seconds", [
    ("30", "secondi", 30), ("trenta", "secondi", 30), ("un", "minuto", 60),
    ("due", "minuti", 120), ("mezzo", "minuto", 30), ("half a", "minute", 30),
    ("eine halbe", "Minute", 30), ("un paio di", "minuti", 120),
    ("a couple of", "minutes", 120), ("quanti", "secondi", None),
    ("forty five", "seconds", 45), ("forty-five", "seconds", 45),
    ("quarante-cinq", "secondes", 45), ("treinta y cinco", "segundos", 35),
    ("ein paar", "Sekunden", 2), ("mezzo", "secondo", None),
    ("half a", "second", None), ("forty banana", "seconds", None),
    # From the review of the fix: a half after a number adds to it; French
    # multiplies before it adds; and the "one" of twenty-one is a number,
    # not an article.
    ("one and a half", "minutes", 90), ("two and a half", "minutes", 150),
    ("quatre-vingt-dix", "secondes", 90), ("quatre-vingt", "secondes", 80),
    ("quatre-vingt-quinze", "secondes", 95), ("vingt et une", "secondes", 21),
    ("treinta y un", "segundos", 31), ("et cinq", "secondes", None),
])
def test_seek_seconds(amount, unit, seconds):
    assert seek_seconds(amount, unit) == seconds


def test_and_a_half_is_half_of_one_more_minute():
    assert seek_seconds("un", "minuto", " e mezzo") == 90
    assert seek_seconds("30", "secondi", " e mezzo") is None


# -- the sentences, in five languages ------------------------------------------
JUMPS = [
    ("it", "vai avanti di 30 secondi", 130.0),
    ("it", "avanti di un minuto", 160.0),
    ("it", "salta 30 secondi", 130.0),
    ("it", "torna indietro di 10 secondi", 90.0),
    ("it", "indietro di mezzo minuto", 70.0),
    ("it", "riavvolgi di trenta secondi", 70.0),
    ("en", "skip ahead 30 seconds", 130.0),
    ("en", "go back a minute", 40.0),
    ("en", "rewind 30 seconds", 70.0),
    ("en", "fast forward two minutes", 220.0),
    ("de", "spul 30 Sekunden vor", 130.0),
    ("de", "eine Minute zurück", 40.0),
    ("de", "spring zurück um 10 Sekunden", 90.0),
    ("fr", "avance de 30 secondes", 130.0),
    ("fr", "recule d'une minute", 40.0),
    ("fr", "reviens 30 secondes en arrière", 70.0),
    ("es", "adelanta 30 segundos", 130.0),
    ("es", "retrocede un minuto", 40.0),
    ("es", "vuelve 10 segundos atrás", 90.0),
    # Compound amounts: before, these matched no jump and fell through to
    # «avanti»/"skip" — the next track, the very thing this step stops.
    ("en", "skip ahead forty five seconds", 145.0),
    ("en", "skip forward forty-five seconds", 145.0),
    ("it", "vai avanti di un minuto e mezzo", 190.0),
    ("fr", "avance de quarante-cinq secondes", 145.0),
    ("es", "adelanta treinta y cinco segundos", 135.0),
    ("de", "spul ein paar Sekunden vor", 102.0),
    ("en", "skip ahead one and a half minutes", 190.0),
    ("fr", "avance de quatre-vingt-dix secondes", 190.0),
    ("fr", "avance de vingt et une secondes", 121.0),
]


@pytest.mark.parametrize("lang, phrase, target", JUMPS)
def test_a_jump_is_a_seek_and_not_a_skip(player, lang, phrase, target):
    reply = Router(player, services=()).handle(phrase, lang=lang)
    assert reply.ok, f"«{phrase}»: {reply}"
    assert player.calls == [("seek", (target,))], f"«{phrase}»"


@pytest.mark.parametrize("lang, phrase, action", [
    ("it", "avanti", "next_track"),
    ("it", "vai avanti", "next_track"),
    ("it", "torna indietro", "previous_track"),
    ("en", "skip", "next_track"),
    ("en", "go back", "previous_track"),
    ("de", "zurück", "previous_track"),
])
def test_without_a_unit_of_time_the_old_meaning_stands(player, lang, phrase, action):
    Router(player, services=()).handle(phrase, lang=lang)
    assert player.names() == [action]


def test_a_title_after_a_play_verb_is_not_a_jump(player):
    Router(player, services=()).handle("metti avanti di 30 secondi")
    assert "seek" not in player.names()


@pytest.mark.parametrize("phrase", [
    "vai avanti di tanti secondi",
    "torna indietro di mezzo secondo",
    "vai avanti di quarantacinque secondi",
])
def test_a_jump_nobody_could_measure_is_asked_again(player, phrase):
    # Asked, and neither a guess nor a track change.
    reply = Router(player, services=()).handle(phrase)
    assert str(reply) == msg("ask_seek"), f"«{phrase}»: {reply}"
    assert player.calls == []


def test_a_system_that_cannot_seek_says_so(player):
    player.capabilities = Capabilities(search=True)
    reply = Router(player, services=()).handle("vai avanti di 30 secondi")
    assert str(reply) == msg("no_seek")
    assert player.calls == []


# -- reading speed -------------------------------------------------------------
@pytest.mark.parametrize("lang, phrase", [
    ("it", "metti a velocità 1.2"),
    ("it", "velocità 1,5"),
    ("it", "leggi più veloce"),
    ("it", "leggi più lento"),
    ("it", "più veloce"),
    ("it", "più lento"),
    ("en", "speed 1.5"),
    ("en", "play faster"),
    ("en", "play slower"),
    ("en", "read faster"),
    ("de", "Geschwindigkeit 1,5"),
    ("de", "stell die Geschwindigkeit auf 1.5"),
    ("de", "lies schneller"),
    ("de", "langsamer vorlesen"),
    ("fr", "vitesse 1.5"),
    ("fr", "mets la vitesse à 1.5"),
    ("fr", "lis plus vite"),
    ("fr", "plus lentement"),
    ("es", "velocidad 1.5"),
    ("es", "pon la velocidad a 1.5"),
    ("es", "lee más rápido"),
    ("es", "más despacio"),
])
def test_a_speed_change_answers_rather_than_erroring(player, lang, phrase):
    reply = Router(player, services=()).handle(phrase, lang=lang)
    set_lang(lang)
    assert str(reply) == msg("no_speed"), f"«{phrase}»: {reply}"
    assert not reply.ok
    assert player.calls == []  # zero transport calls


def test_a_speed_refusal_ends_the_turn_for_every_alternative(player):
    # «metti più veloce» does not match the speed pattern and carries a play
    # verb: were the refusal not a GATE, the sweep would route it next and
    # search for a song called «più veloce».
    out = Router(player, services=()).handle_many(["più veloce", "metti più veloce"])
    assert out["speech"] == msg("no_speed")
    assert player.calls == []


@pytest.mark.parametrize("lang, phrase", [
    ("it", "alza il volume"), ("it", "più forte"), ("en", "turn it up"),
])
def test_a_speed_pattern_does_not_steal_the_volume(player, lang, phrase):
    player.volume = lambda delta: player.calls.append(("volume", (delta,)))
    Router(player, services=()).handle(phrase, lang=lang)
    assert player.names() == ["volume"]


@pytest.mark.parametrize("lang, phrase", [("it", "avanti"), ("en", "next")])
def test_a_speed_pattern_does_not_steal_a_bare_skip(player, lang, phrase):
    Router(player, services=()).handle(phrase, lang=lang)
    assert player.names() == ["next_track"]


def test_a_speed_pattern_does_not_steal_a_timed_seek(player):
    reply = Router(player, services=()).handle("vai avanti di 30 secondi")
    assert reply.ok
    assert player.calls == [("seek", (130.0,))]


# -- books -------------------------------------------------------------------
def test_without_a_library_an_audiobook_is_searched_as_music(player):
    Router(player, services=()).handle("metti l'audiolibro Lo Hobbit")
    assert "play_tracks" not in player.names()
    assert player.names() == ["search_tracks"]


@pytest.mark.parametrize("lang, phrase", [
    ("it", "metti l'audiolibro Lo Hobbit"),
    ("it", "leggimi il libro Lo Hobbit"),
    ("en", "play the audiobook Lo Hobbit"),
    ("en", "read me the book Lo Hobbit"),
    ("de", "spiel das Hörbuch Lo Hobbit"),
    ("de", "lies mir das Buch Lo Hobbit vor"),
    ("fr", "mets le livre audio Lo Hobbit"),
    ("fr", "lis-moi le livre Lo Hobbit"),
    ("es", "pon el audiolibro Lo Hobbit"),
    ("es", "léeme el libro Lo Hobbit"),
])
def test_a_book_by_name_plays_its_files_in_order(player, lang, phrase):
    books = shelf_of(HOBBIT)
    reply = Router(player, services=(), books=books).handle(phrase, lang=lang)
    assert reply.ok, f"«{phrase}»: {reply}"
    assert player.calls == [("play_tracks", (["u1", "u2"],))]
    assert books.library.asked == ["Lo Hobbit"]
    set_lang(lang)
    assert str(reply) == msg("book_playing_by", title="Lo Hobbit",
                             author="J.R.R. Tolkien")


def test_a_weak_match_is_asked_about_before_hours_of_it_start(player):
    router = Router(player, services=(), books=shelf_of(HOBBIT))
    reply = router.handle("metti l'audiolibro il signore degli anelli")
    assert str(reply) == msg("book_did_you_mean_by", title="Lo Hobbit",
                             author="J.R.R. Tolkien")
    assert player.calls == []
    assert router.handle("sì").ok
    assert player.names() == ["play_tracks"]


def test_the_words_said_outrank_the_catalogues_order(player):
    # Audiobookshelf ranked a weak match first; the exact title, second, is
    # the one that was asked for — and it plays without a question.
    other = {"id": "b2", "title": "Il Silmarillion", "author": "J.R.R. Tolkien",
             "duration": 1.0}
    books = shelf_of(other, HOBBIT, files={"b1": ["u1"], "b2": ["x"]})
    reply = Router(player, services=(), books=books).handle(
        "metti l'audiolibro Lo Hobbit")
    assert reply.ok
    assert player.calls == [("play_tracks", (["u1"],))]


def test_a_weak_match_turned_down_plays_nothing(player):
    router = Router(player, services=(), books=shelf_of(HOBBIT))
    router.handle("metti l'audiolibro il signore degli anelli")
    router.handle("no")
    assert player.calls == []


def test_no_book_found(player):
    reply = Router(player, services=(), books=shelf_of()).handle(
        "metti l'audiolibro Lo Hobbit")
    assert str(reply) == msg("no_book_found", title="Lo Hobbit")
    assert player.calls == []


def test_a_book_with_no_audio_leaves_the_queue_alone(player):
    reply = Router(player, services=(), books=shelf_of(HOBBIT, files={})).handle(
        "metti l'audiolibro Lo Hobbit")
    assert str(reply) == msg("book_no_audio", title="Lo Hobbit")
    assert player.calls == []


def test_a_song_about_a_book_is_not_looked_for_on_the_shelf(player):
    books = shelf_of(HOBBIT)
    Router(player, services=(), books=books).handle(
        "metti il libro della giungla")
    assert books.library.asked == []
    assert player.names() == ["search_tracks"]


def test_a_bookshelf_that_is_down_is_reported_as_such(player):
    books = shelf_of(HOBBIT)

    def down(query, count=10):
        raise PlayerUnreachable("off")
    books.library.book_candidates = down
    reply = Router(player, services=(), books=books).handle(
        "metti l'audiolibro Lo Hobbit")
    assert getattr(reply, "kind", None) == actions.UNREACHABLE


@pytest.mark.parametrize("lang, phrase", [
    ("it", "metti l'audiolibro Lo Hobbit"),
    ("en", "play the audiobook Lo Hobbit"),
])
def test_a_failed_book_search_names_the_catalogue(player, lang, phrase):
    # A search that fails is Audiobookshelf's own trouble, not the hi-fi's —
    # the music on the same speakers still plays — so the reply names it
    # rather than blaming "the system".
    books = shelf_of(HOBBIT)

    def down(query, count=10):
        raise PlayerUnreachable("off")
    books.library.book_candidates = down
    reply = Router(player, services=(), books=books).handle(phrase, lang=lang)
    assert getattr(reply, "kind", None) == actions.UNREACHABLE
    assert "Audiobookshelf" in str(reply), str(reply)


def test_a_failed_fetch_of_the_books_own_files_names_the_catalogue(player):
    # enqueue() makes two calls: fetching the book's files (the catalogue)
    # and sending them to the speakers (the transport). This is the first.
    books = shelf_of(HOBBIT)

    def down(item_id):
        raise PlayerUnreachable("off")
    books.library.stream_urls = down
    reply = Router(player, services=(), books=books).handle(
        "metti l'audiolibro Lo Hobbit")
    assert getattr(reply, "kind", None) == actions.UNREACHABLE
    assert "Audiobookshelf" in str(reply), str(reply)


# -- resuming (T5.6) -----------------------------------------------------------

@pytest.mark.parametrize("lang, phrase", [
    ("it", "riprendi il libro Lo Hobbit"),
    ("it", "riprendi l'audiolibro Lo Hobbit"),
    ("it", "continua il libro Lo Hobbit"),
    ("en", "resume the book Lo Hobbit"),
    ("en", "continue the audiobook Lo Hobbit"),
    ("de", "weiter mit dem Hörbuch Lo Hobbit"),
    ("de", "setz das Hörbuch Lo Hobbit fort"),
])
def test_resume_book_routes_like_audiobook(player, lang, phrase):
    books = shelf_of(HOBBIT)
    reply = Router(player, services=(), books=books).handle(phrase, lang=lang)
    assert reply.ok, f"«{phrase}»: {reply}"
    assert player.calls == [("play_tracks", (["u1", "u2"],))]
    assert books.library.asked == ["Lo Hobbit"]


def test_a_title_ending_in_fort_keeps_its_last_word(player):
    books = shelf_of(HOBBIT)
    Router(player, services=(), books=books).handle(
        "weiter mit dem Hörbuch Sie sind fort", lang="de")
    assert books.library.asked == ["Sie sind fort"]


@pytest.mark.parametrize("lang, phrase", [
    ("it", "riprendi"), ("it", "continua"), ("en", "resume"), ("en", "continue"),
])
def test_a_bare_resume_still_means_play_unpause(player, lang, phrase):
    # The noun ("il libro"/"the book") is what turns this into a book
    # request; without it, this stays the transport's own play/unpause, with
    # a library attached and everything.
    books = shelf_of(HOBBIT)
    Router(player, services=(), books=books).handle(phrase, lang=lang)
    assert player.names() == ["resume"]
    assert books.library.asked == []


@pytest.mark.parametrize("lang, phrase", [
    ("it", "metti l'audiolibro Lo Hobbit"),
    ("en", "play the audiobook Lo Hobbit"),
])
def test_a_book_already_started_resumes_where_it_was_left(player, lang, phrase):
    books = shelf_of(HOBBIT, progress={"b1": 600.0}, duration=3600.0)
    reply = Router(player, services=(), books=books).handle(phrase, lang=lang)
    assert reply.ok, f"«{phrase}»: {reply}"
    assert player.calls == [("play_tracks", (["u1", "u2"],)), ("seek", (600,))]
    set_lang(lang)
    assert str(reply) == msg("book_resumed", title="Lo Hobbit",
                             position=msg("resume_minutes", n=10))


@pytest.mark.parametrize("seconds, said", [
    (5400.0, "un'ora e 30 minuti"), (3600.0, "un'ora"), (7260.0, "2 ore e un minuto"),
    (60.0, "un minuto"), (1500.0, "25 minuti"),
])
def test_a_resume_is_said_in_hours_and_minutes(player, seconds, said):
    books = shelf_of(HOBBIT, progress={"b1": seconds}, duration=36000.0)
    reply = Router(player, services=(), books=books).handle(
        "riprendi il libro Lo Hobbit")
    assert str(reply) == msg("book_resumed", title="Lo Hobbit", position=said)


@pytest.mark.parametrize("shelf", [
    # No ``tracks``: nothing can say where 600 s falls.
    dict(progress={"b1": 600.0}),
    # Lengths the catalogue does not know: the same.
    dict(progress={"b1": 600.0}, duration=0.0),
])
def test_a_resume_that_could_not_happen_says_so(player, shelf):
    # Not announced as a resume — it is not one — and not hidden behind a
    # plain «Metto l'audiolibro» either: the listener had a place, and the
    # book starts from the beginning. Same words as a seek that did not land.
    reply = Router(player, services=(), books=shelf_of(HOBBIT, **shelf)).handle(
        "metti l'audiolibro Lo Hobbit")
    assert str(reply) == msg("book_from_start", title="Lo Hobbit",
                             position=msg("resume_minutes", n=10))


def test_under_a_minute_in_is_not_worth_a_word(player):
    books = shelf_of(HOBBIT, progress={"b1": 40.0}, duration=3600.0)
    reply = Router(player, services=(), books=books).handle(
        "metti l'audiolibro Lo Hobbit")
    assert str(reply) == msg("book_playing_by", title="Lo Hobbit",
                             author="J.R.R. Tolkien")


def test_a_player_that_cannot_seek_announces_where_the_file_begins(player):
    # 50 minutes in is 20 minutes into the second 30-minute file: with no
    # seek, the listener hears that file from its start — 30 minutes, which
    # is what gets said, not the 50 they had reached.
    player.capabilities = Capabilities(search=True)
    books = shelf_of(HOBBIT, progress={"b1": 3000.0}, duration=1800.0)
    reply = Router(player, services=(), books=books).handle(
        "riprendi il libro Lo Hobbit")
    assert player.calls == [("play_tracks", (["u2"],))]
    assert str(reply) == msg("book_resumed", title="Lo Hobbit",
                             position="30 minuti")


def test_a_book_never_started_gets_the_ordinary_reply(player):
    books = shelf_of(HOBBIT, progress={})
    reply = Router(player, services=(), books=books).handle(
        "metti l'audiolibro Lo Hobbit")
    assert str(reply) == msg("book_playing_by", title="Lo Hobbit",
                             author="J.R.R. Tolkien")


def test_a_failed_progress_lookup_does_not_block_playback(player):
    # Audiobookshelf owns progress and nothing else does (T5.5): not knowing
    # it is a reason to start from zero, never a reason not to play at all.
    books = shelf_of(HOBBIT)

    def down(item_id):
        raise PlayerUnreachable("off")
    books.library.progress = down
    reply = Router(player, services=(), books=books).handle(
        "metti l'audiolibro Lo Hobbit")
    assert reply.ok
    assert player.calls == [("play_tracks", (["u1", "u2"],))]


def test_a_failed_transport_while_starting_a_book_keeps_the_generic_reply(player):
    # The speakers, not the catalogue: this is the same "system" failure
    # every other action reports, so no service is named.
    books = shelf_of(HOBBIT)

    def down(tracks):
        raise PlayerUnreachable("off")
    player.play_tracks = down
    reply = Router(player, services=(), books=books).handle(
        "metti l'audiolibro Lo Hobbit")
    assert getattr(reply, "kind", None) == actions.UNREACHABLE
    assert str(reply) == msg("err_unreachable")
    assert "Audiobookshelf" not in str(reply)


# -- chapters (T5.6, third slice) ---------------------------------------------
class ChapterShelf(TimedShelf):
    """A :class:`TimedShelf` whose books also have the server's chapters."""

    def __init__(self, books, files, duration, chapters):
        super().__init__(books, files, None, duration)
        self._chapters = chapters

    def chapters(self, item_id):
        return [dict(ch) for ch in self._chapters]


THREE_FILES = {"b1": ["u1", "u2", "u3"]}


def book_playing(player, *, files=THREE_FILES, chapters=None, lang="it"):
    """A router whose player is playing Lo Hobbit, started by voice: three
    files of 600 s (the Player's own track length), and the server's
    ``chapters`` when given — otherwise each file is one."""
    shelf = (TimedShelf([HOBBIT], files, None, 600.0) if chapters is None
             else ChapterShelf([HOBBIT], files, 600.0, chapters))
    router = Router(player, services=(),
                    books=Composite(shelf, Capabilities(streamable=True),
                                    "Audiobookshelf"))
    assert router.handle("metti l'audiolibro Lo Hobbit").ok
    player.calls.clear()
    set_lang(lang)
    return router


@pytest.mark.parametrize("lang, phrase", [
    ("it", "a che capitolo sono"), ("it", "che capitolo è"),
    ("it", "di che capitolo sono?"), ("it", "in quale capitolo siamo"),
    ("en", "what chapter am I on"), ("en", "which chapter is this?"),
    ("de", "welches Kapitel ist das"), ("de", "in welchem Kapitel bin ich"),
    ("fr", "à quel chapitre je suis"), ("fr", "c'est quel chapitre"),
    ("es", "en qué capítulo estoy"), ("es", "qué capítulo es"),
    # From the review: the ways people actually ask, not only the tidy one.
    ("it", "a che capitolo siamo arrivati"), ("it", "che capitolo è questo"),
    ("it", "qual è il capitolo"), ("fr", "on est à quel chapitre"),
])
def test_which_chapter_is_said_in_five_languages(player, lang, phrase):
    router = book_playing(player)
    player.index = 1
    reply = router.handle(phrase, lang=lang)
    assert str(reply) == msg("chapter_now", n=2, total=3), f"«{phrase}»"
    assert player.calls == []


@pytest.mark.parametrize("lang, phrase", [
    ("it", "capitolo successivo"), ("it", "vai al prossimo capitolo"),
    ("it", "salta il capitolo"),
    ("en", "next chapter"), ("en", "skip to the next chapter"),
    ("de", "nächstes Kapitel"), ("de", "spring zum nächsten Kapitel"),
    ("fr", "chapitre suivant"), ("fr", "passe au chapitre suivant"),
    ("es", "siguiente capítulo"), ("es", "pasa al capítulo siguiente"),
    # A near miss here is not "not understood": it falls through to «next
    # track», which on a one-file .m4b skips the whole book. Whisper puts the
    # comma before "please"; people put the article in front.
    ("en", "Next chapter, please"), ("en", "the next chapter"),
    ("it", "il capitolo successivo"), ("it", "capitolo successivo per favore"),
    ("it", "metti il capitolo successivo"),
    ("de", "Nächstes Kapitel, bitte"), ("de", "zum nächsten Kapitel"),
    ("fr", "le chapitre suivant"), ("fr", "chapitre suivant s'il te plaît"),
    ("es", "el siguiente capítulo"), ("es", "siguiente capítulo, por favor"),
    ("es", "pon el siguiente capítulo"),
])
def test_next_chapter_plays_the_book_from_there(player, lang, phrase):
    router = book_playing(player)
    reply = router.handle(phrase, lang=lang)
    assert reply.ok, f"«{phrase}»: {reply}"
    assert player.calls == [("play_tracks", (["u2", "u3"],))]
    assert str(reply) == msg("chapter_playing", n=2, total=3)


@pytest.mark.parametrize("lang, phrase", [
    ("it", "capitolo precedente"), ("it", "torna al capitolo precedente"),
    ("en", "previous chapter"), ("en", "go back a chapter"),
    ("de", "vorheriges Kapitel"), ("de", "ein Kapitel zurück"),
    ("fr", "chapitre précédent"), ("fr", "reviens au chapitre précédent"),
    ("es", "capítulo anterior"), ("es", "vuelve al capítulo anterior"),
    ("en", "chapter back"), ("en", "Previous chapter, please"),
    ("it", "il capitolo precedente"), ("de", "zum vorherigen Kapitel"),
    ("fr", "le chapitre précédent"), ("es", "el capítulo anterior"),
])
def test_previous_chapter_plays_the_book_from_there(player, lang, phrase):
    router = book_playing(player)
    player.index = 2
    reply = router.handle(phrase, lang=lang)
    assert reply.ok, f"«{phrase}»: {reply}"
    assert player.calls == [("play_tracks", (["u2", "u3"],))]
    assert str(reply) == msg("chapter_playing", n=2, total=3)


def test_there_is_no_chapter_before_the_first(player):
    router = book_playing(player)
    reply = router.handle("capitolo precedente")
    assert str(reply) == msg("chapter_first")
    assert player.calls == []


def test_there_is_no_chapter_after_the_last(player):
    router = book_playing(player)
    player.index = 2
    reply = router.handle("capitolo successivo")
    assert str(reply) == msg("chapter_last")
    assert player.calls == []


SERVER_CHAPTERS = [
    {"start": 0.0, "end": 900.0, "title": "Una festa a lungo attesa"},
    {"start": 900.0, "end": 1800.0, "title": "Capitolo 2"},
]


def test_a_chapter_with_a_name_is_said_by_name(player):
    router = book_playing(player, files={"b1": ["u1", "u2", "u3"]},
                          chapters=SERVER_CHAPTERS)
    reply = router.handle("a che capitolo sono")
    assert str(reply) == msg("chapter_now_titled", n=1, total=2,
                             title="Una festa a lungo attesa")


def test_a_numbered_title_that_is_not_the_position_is_said(player):
    # «Prologo» is chapter 1, so the book's own «Capitolo 1» is second: its
    # title is information, not a repeat of the number.
    chapters = [dict(SERVER_CHAPTERS[0], title="Prologo"),
                dict(SERVER_CHAPTERS[1], title="Capitolo 1")]
    router = book_playing(player, chapters=chapters)
    player.status["elapsed"] = 1000.0
    reply = router.handle("a che capitolo sono")
    assert str(reply) == msg("chapter_now_titled", n=2, total=2,
                             title="Capitolo 1")


@pytest.mark.parametrize("title, said", [
    ("02 - Gli Dei", "Gli Dei"),          # LibriVox's .m4b, as Audiobookshelf reads it
    ("2. Gli Dei", "Gli Dei"),
    ("Capitolo 2: Gli Dei", "Gli Dei"),
    ("07 - Gli Dei", "07 - Gli Dei"),     # not its position: kept whole
])
def test_a_title_numbered_as_its_position_is_said_once(player, title, said):
    chapters = [dict(SERVER_CHAPTERS[0]), dict(SERVER_CHAPTERS[1], title=title)]
    router = book_playing(player, chapters=chapters)
    player.status["elapsed"] = 1000.0
    reply = router.handle("a che capitolo sono")
    assert str(reply) == msg("chapter_now_titled", n=2, total=2, title=said)


@pytest.mark.parametrize("title", ["Capitolo 2", "Chapter 2", "02", "Track 2", ""])
def test_a_chapter_named_after_its_number_is_said_by_number(player, title):
    chapters = [dict(SERVER_CHAPTERS[0]), dict(SERVER_CHAPTERS[1], title=title)]
    router = book_playing(player, chapters=chapters)
    player.status["elapsed"] = 1000.0
    reply = router.handle("a che capitolo sono")
    assert str(reply) == msg("chapter_now", n=2, total=2)


def test_a_chapter_inside_a_file_is_reached_with_a_seek(player):
    router = book_playing(player, chapters=SERVER_CHAPTERS)
    reply = router.handle("capitolo successivo")
    assert reply.ok
    # 900 s in: 600 s of file 1 gone, 300 s into file 2.
    assert player.calls == [("play_tracks", (["u2", "u3"],)), ("seek", (300,))]


def test_a_player_that_cannot_seek_is_not_sent_the_wrong_chapter(player):
    router = book_playing(player, chapters=SERVER_CHAPTERS)
    player.capabilities = Capabilities(search=True)
    reply = router.handle("capitolo successivo")
    assert str(reply) == msg("no_seek_chapter")
    assert player.calls == []


def test_no_book_playing_is_said_and_nothing_moves(player):
    router = book_playing(player)
    player.status["mode"] = "stop"
    reply = router.handle("capitolo successivo")
    assert str(reply) == msg("no_book_playing")
    assert player.calls == []


def test_music_put_on_since_is_not_the_book(player):
    router = book_playing(player)
    player.status["duration"] = 241.0  # a song, from Material Skin
    reply = router.handle("capitolo successivo")
    assert str(reply) == msg("no_book_playing")
    assert player.calls == []


def test_a_bookshelf_down_mid_chapter_is_named(player):
    router = book_playing(player)

    def down(item_id):
        raise PlayerUnreachable("off")
    router.books.library.tracks = down
    reply = router.handle("capitolo successivo")
    assert getattr(reply, "kind", None) == actions.UNREACHABLE
    assert str(reply) == msg("err_unreachable_service", service="Audiobookshelf")


@pytest.mark.parametrize("lang, phrase, call", [
    ("it", "avanti", "next_track"), ("it", "indietro", "previous_track"),
    ("en", "next", "next_track"), ("en", "previous", "previous_track"),
    ("it", "prossimo", "next_track"), ("en", "next track", "next_track"),
])
def test_a_bare_skip_still_skips_the_file_with_a_book_playing(player, lang,
                                                              phrase, call):
    router = book_playing(player)
    router.handle(phrase, lang=lang)
    assert player.names() == [call]


def test_without_a_library_a_chapter_is_not_this_steps(player):
    # No --library: the step does not look at the sentence, and no reply
    # about audiobooks reaches a household that has none.
    reply = Router(player, services=()).handle("capitolo successivo")
    assert str(reply) not in (msg("no_book_playing"), msg("chapter_last"))


def test_a_seek_that_fails_does_not_name_the_chapter(player):
    # The file started, the seek into it did not: what plays is the file
    # from its start, and naming chapter 2 there would be a lie.
    router = book_playing(player, chapters=SERVER_CHAPTERS)

    def still_loading(seconds):
        raise PlayerUnreachable("loading")
    player.seek = still_loading
    reply = router.handle("capitolo successivo")
    assert str(reply) == msg("chapter_file_start", n=2)
    assert player.names() == ["play_tracks"]


def test_a_chapter_that_cannot_be_placed_is_not_blamed_on_the_player(player):
    # The player can seek; it is the book whose lengths do not reach the
    # chapter (the server's chapter list longer than its files).
    chapters = SERVER_CHAPTERS + [{"start": 5000.0, "end": 6000.0, "title": ""}]
    router = book_playing(player, chapters=chapters)
    player.status["elapsed"] = 1000.0
    player.index = 1
    reply = router.handle("capitolo successivo")
    assert str(reply) == msg("chapter_unplaceable")
    assert player.calls == []


def test_file_chapters_count_every_file_even_past_an_unknown_length(player):
    # Files of unknown length: each is still one chapter, so the total is
    # the number of files, not the number of lengths known.
    router = book_playing(player)
    router.books.library.duration = 0.0
    player.status["duration"] = 0.0
    player.index = 1
    reply = router.handle("a che capitolo sono")
    assert str(reply) == msg("chapter_now", n=2, total=3)
    reply = router.handle("capitolo successivo")
    assert str(reply) == msg("chapter_unplaceable")
    assert player.calls == []


def test_a_resume_the_player_did_not_reach_is_said(player):
    # The hi-fi, 2026-09-25: LMS accepted the seek into an .m4b and played it
    # from 0 s. «Metto l'audiolibro» there would hide that the listener's
    # place was not found.
    books = shelf_of(HOBBIT, files={"b1": ["u1"]}, progress={"b1": 7200.0},
                     duration=36000.0)
    books._sleep = lambda seconds: None
    ticks = iter(range(100))
    books._now = lambda: float(next(ticks))
    player.seek = lambda seconds: player._say("seek", seconds)  # never lands
    player.status["elapsed"] = 0.0
    reply = Router(player, services=(), books=books).handle(
        "riprendi il libro Lo Hobbit")
    assert str(reply) == msg("book_from_start", title="Lo Hobbit",
                             position=msg("resume_hours", n=2))
