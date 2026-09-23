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

    @contextlib.contextmanager
    def turn_deadline(self, seconds):
        yield

    def _say(self, name, *args):
        self.calls.append((name, args))
        return {}

    def status_info(self): return dict(self.status)
    def seek(self, seconds): return self._say("seek", seconds)
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

    def __init__(self, books, files):
        self.books, self.files = books, files
        self.asked = []

    def book_candidates(self, query, count=10):
        self.asked.append(query)
        return list(self.books)[:count]

    def stream_urls(self, item_id):
        return list(self.files.get(item_id, []))


HOBBIT = {"id": "b1", "title": "Lo Hobbit", "author": "J.R.R. Tolkien",
          "duration": 36000.0}


def shelf_of(*books, files=None):
    files = files if files is not None else {"b1": ["u1", "u2"]}
    return Composite(Shelf(books, files), Capabilities(streamable=True),
                     "Audiobookshelf")


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
