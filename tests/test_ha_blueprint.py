"""The Home Assistant blueprint's sentences, against the grammar they feed.

``blueprints/vivavoce_assist.yaml`` lists the sentences Home Assistant hands to
Vivavoce instead of answering itself. Sentence triggers are matched *before*
Home Assistant's own intents, so every sentence in that file is taken away from
something — which makes a sentence the blueprint claims but the router cannot
parse worse than one it never claimed: the phrase is intercepted, dies as
«non ho capito», and whoever could have answered it never sees it.

Nothing else in the suite can see that. The blueprint is not imported, not
served, and not copied into the image; ``tests/test_packaging.py`` checks its
shape and its agreement with DEPLOY.md, but not whether the words in it mean
anything to ``localvoice/lang/``. This file expands every trigger sentence into
the concrete phrases it can produce and puts each one through the real handler.

Six phrasings were dropped from the blueprint because of what this found, every
one of them a sentence somebody would plainly say: «che brano è questo», «quali
album hai di X», «che canzoni di X», «vorrei ascoltare X», «cosa suona», and
"what songs by X". They are recorded below rather than quietly deleted, so that
the day the grammar grows to cover one, a test says so.

**What this checks and what it cannot.** It detects a claimed sentence the
router does not understand — `unmatched`. It does not detect a claimed sentence
the router understands as *something else*, which needs an intent to compare
against and has no general form. That failure is real: "what songs by X" is
eaten by the English now-playing pattern and answered «nothing is playing», and
it took reading an answer to see it. :func:`test_what_songs_by_x_is_heard_as_a
_question_about_now_playing` pins that one case; the rest is a reading job.
"""

import itertools
import json
import re

import pytest

import lms

from conftest import FakeLicense
from pro.kidsafe import KidSafe

yaml = pytest.importorskip("yaml")

BLUEPRINT = "blueprints/vivavoce_assist.yaml"

# What each wildcard stands for. ``{when}`` has to be a real duration or the
# sleep patterns reject the tail by design (a title must never become a timer),
# so it is the one placeholder that cannot be a nonsense marker.
FILLERS = {"query": "Zzq Marker", "artist": "Zzq Marker",
           "when": {"it": "30 minuti", "en": "30 minutes"}}

# Natural phrasings the blueprint deliberately does NOT claim, because the
# router answers «non ho capito» to them. Kept here so that the day the grammar
# grows, this list fails and says so — the same ratchet as OVERSIZED_TODAY in
# test_packaging.py, and the same reason: an exemption nobody re-checks outlives
# the problem it was written for.
STILL_UNPARSED = {
    "it": ["che brano è questo", "quali album hai di Zzq Marker",
           "quali album ci sono di Zzq Marker", "che canzoni di Zzq Marker",
           "vorrei ascoltare Zzq Marker", "cosa suona"],
    "en": ["which tracks by Zzq Marker"],
}


class _Loader(yaml.SafeLoader):
    """``!input`` is Home Assistant's tag; SafeLoader alone cannot read it."""


_Loader.add_constructor("!input", lambda loader, node: str(node.value))


def _triggers():
    with open(BLUEPRINT, encoding="utf-8") as f:
        return yaml.load(f, Loader=_Loader)["triggers"]


def _expand(sentence, lang):
    """Every concrete phrase a Home Assistant sentence template can produce.

    The subset of hassil syntax the blueprint uses: ``(a|b)`` alternatives,
    ``[c]`` and ``[a|b]`` optionals, ``{name}`` wildcards.
    """
    slots = []
    for token in re.split(r"(\([^()]*\)|\[[^\[\]]*\]|\{[^{}]*\})", sentence):
        if not token:
            continue
        if token.startswith("("):
            slots.append(token[1:-1].split("|"))
        elif token.startswith("["):
            slots.append(token[1:-1].split("|") + [""])
        elif token.startswith("{"):
            fill = FILLERS[token[1:-1]]
            slots.append([fill[lang] if isinstance(fill, dict) else fill])
        else:
            slots.append([token])
    return [re.sub(r"\s+", " ", "".join(combo)).strip()
            for combo in itertools.product(*slots)]


def _every_phrase():
    """(language, sentence, phrase) for the whole blueprint."""
    for trigger in _triggers():
        lang = trigger["id"]
        for sentence in trigger["command"]:
            for phrase in _expand(sentence, lang):
                if phrase:
                    yield lang, sentence, phrase


# -- the fixture ---------------------------------------------------------------

# A library with one artist, five of their albums (so a list of five opens —
# that is LIST_LIMIT, and it is why the blueprint offers picks up to five) and
# one findable track.
LIBRARY = {
    "artists": {"count": 1, "artists_loop": [{"id": 7, "artist": "Zzq Marker"}]},
    "albums": {"count": 5, "albums_loop": [{"id": 100 + n, "album": f"Album {n}"}
                                           for n in range(1, 6)]},
    "titles": {"titles_loop": [{"id": 1, "title": "Zzq Marker",
                                "artist": "Zzq Marker"}]},
    # A genre one of the moods in engine/moods.py resolves against, so a vague
    # request really opens a mood — without it «un'altra» has nothing to
    # re-roll and would look like a sentence the router cannot read.
    "genres": {"genres_loop": [{"id": 3, "genre": "Ambient"}]},
    "years": {"years_loop": [{"year": 1975}]},
}

# Openers for the two kinds of question a follow-up can be answering. A
# sentence like «la 4» or «un'altra» is meaningless on its own — it is an
# answer — so it is asked in a conversation where the question is open.
OPENERS = {
    "it": ["", "quali album ho di Zzq Marker", "metti qualcosa di rilassante"],
    "en": ["", "which albums do i have by Zzq Marker", "play something relaxing"],
}


@pytest.fixture
def blueprint_server(live_server, transport, tmp_path, clock):
    transport.responses.update(LIBRARY)
    # Kid-safe present and licensed: «blocca X» is a real intent only when the
    # feature is wired up, and the blueprint claims it.
    # Every registered service configured, read from the registry rather than
    # listed here: «da qobuz metti X» is only a service phrase on an install
    # whose LMS has that plugin, so a service added to engine/lms.py and to the
    # blueprint but not to this line would look like a sentence the router
    # cannot read. (It did, the first time Spotify was added.)
    srv = live_server(services=tuple(lms.SERVICES),
                      kidsafe=KidSafe(str(tmp_path), FakeLicense(pro=True),
                                      now=clock),
                      license_mgr=FakeLicense(pro=True))
    return srv


def _understood(srv, phrase, lang, convo):
    reply = srv.json_post("/api/v1/command",
                          {"text": phrase, "lang": lang,
                           "conversation_id": convo})
    return not reply["unmatched"], reply


def _understood_in_any_state(srv, phrase, lang, tag):
    """Try the phrase after each opener; a follow-up needs its question open."""
    last = None
    for n, opener in enumerate(OPENERS[lang]):
        convo = f"{tag}-{n}"
        if opener:
            srv.json_post("/api/v1/command",
                          {"text": opener, "lang": lang, "conversation_id": convo})
        ok, last = _understood(srv, phrase, lang, convo)
        if ok:
            return True, last
    return False, last


# -- the check ------------------------------------------------------------------

def test_every_sentence_the_blueprint_claims_is_one_the_router_parses(
        blueprint_server):
    dead = []
    for i, (lang, sentence, phrase) in enumerate(_every_phrase()):
        ok, reply = _understood_in_any_state(blueprint_server, phrase, lang,
                                             f"bp{i}")
        if not ok:
            dead.append((sentence, phrase, reply["speech"]))
    assert dead == [], (
        "the blueprint takes these sentences away from Home Assistant and the "
        "router then answers «non ho capito»:\n"
        + "\n".join(f"  {s!r} -> {p!r}: {sp}" for s, p, sp in dead))


def test_the_expansion_covers_what_the_blueprint_actually_says(blueprint_server):
    # A check whose subject expands to nothing passes for the wrong reason, and
    # the expander is hand-written. Pin the shape of what it produced.
    phrases = list(_every_phrase())
    assert len(phrases) > 300, f"only {len(phrases)} phrases: the expander broke"
    flat = {p for _lang, _s, p in phrases}
    for expected in ("metti Zzq Marker", "da qobuz metti Zzq Marker",
                     "la 5", "la quinta", "spegni tra 30 minuti",
                     "play Zzq Marker", "the fifth", "clear the queue"):
        assert expected in flat, f"{expected!r} is not among the expansions"


@pytest.mark.parametrize("lang", ["it", "en"])
def test_the_phrasings_left_out_are_still_the_ones_the_router_cannot_read(
        blueprint_server, lang):
    # The other half of the ratchet. If the grammar grows to cover one of
    # these, this fails and the blueprint can claim it — which is the whole
    # point of writing them down rather than quietly dropping them.
    now_parsed = []
    for i, phrase in enumerate(STILL_UNPARSED[lang]):
        ok, _reply = _understood_in_any_state(blueprint_server, phrase, lang,
                                              f"gap-{lang}{i}")
        if ok:
            now_parsed.append(phrase)
    assert now_parsed == [], (
        f"{now_parsed} now parse: add them to the blueprint's triggers and "
        f"drop them from STILL_UNPARSED")


def test_what_songs_by_x_is_heard_as_a_question_about_now_playing(
        blueprint_server):
    # The reason "what songs by X" is not in the blueprint, and it is not the
    # reason the others are missing. The engine *does* parse it — as the
    # now-playing question, because en.py's `nowplaying` alternates on "song"
    # and «what songs …» clears it. Claiming it would have Home Assistant hand
    # over a request for an artist's tracks and hear "nothing is playing".
    #
    # A wrong answer given confidently is worse than no answer, so this is
    # pinned: if the grammar ever tells the two apart, this test fails and the
    # blueprint can have the sentence.
    reply = blueprint_server.json_post(
        "/api/v1/command", {"text": "what songs by Zzq Marker", "lang": "en",
                            "conversation_id": "misparse"})
    assert reply["unmatched"] is False
    assert "playing" in reply["speech"].lower(), (
        "«what songs by X» no longer answers the now-playing question — check "
        "what it does answer, and give it to the blueprint if it is right")


def test_a_sentence_the_router_cannot_read_would_be_caught(blueprint_server):
    # The check above is only worth its runtime if it can fail. Prove it does,
    # with a phrase shaped exactly like the ones that were removed.
    ok, reply = _understood_in_any_state(blueprint_server,
                                         "quali album hai di Zzq Marker", "it",
                                         "canary")
    assert not ok and reply["unmatched"] is True
    assert json.loads(json.dumps(reply))["speech"]  # a real reply, not a crash
