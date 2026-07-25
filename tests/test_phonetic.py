"""Tests for the catalog-aware phonetic correction (engine/phonetic.py) and its
router integration: mangled ASR transcripts ("fatta blina") get corrected
alternatives from the user's own library names, appended after the originals."""

from phonetic import SUGGEST_SCORE, EntityIndex, phonetic_key, similarity
from router import Router


# -- phonetic_key / similarity ---------------------------------------------
def test_key_collapses_sound_alikes():
    # Voiced/voiceless pairs and vowels collapse: same sound, same key.
    assert phonetic_key("Aerosmith") == phonetic_key("erosmith")
    assert phonetic_key("Paint It Black") != ""


def test_similarity_accepts_real_manglings():
    # Field-observed garblings of foreign titles by an Italian recognizer.
    assert similarity("fatta blina", "Comfortably Numb") >= SUGGEST_SCORE
    assert similarity("confortabli nam", "Comfortably Numb") >= SUGGEST_SCORE
    assert similarity("erosmith", "Aerosmith") >= SUGGEST_SCORE


def test_similarity_rejects_unrelated_pairs():
    assert similarity("love", "Hotel California") < SUGGEST_SCORE
    assert similarity("la canzone del sole", "Aerosmith") < SUGGEST_SCORE
    assert similarity("metti la quinta", "Comfortably Numb") < SUGGEST_SCORE


def test_similarity_exact_and_empty():
    assert similarity("Time", "time") == 1.0
    assert similarity("", "Time") == 0.0


# -- EntityIndex ------------------------------------------------------------
def _index(*names):
    idx = EntityIndex()
    idx.build({"titles": list(names)})
    return idx


def test_suggest_returns_best_sound_alike():
    idx = _index("Comfortably Numb", "Hotel California", "Time")
    got = idx.suggest("fatta blina")
    assert got and got[0][1] == "Comfortably Numb"


def test_suggest_skips_exact_matches_and_junk():
    idx = _index("Comfortably Numb")
    assert idx.suggest("comfortably numb") == []  # no correction needed
    assert idx.suggest("xyzzy") == []


def test_build_deduplicates_across_kinds():
    idx = EntityIndex()
    idx.build({"artists": ["Yes"], "albums": ["Yes"], "titles": ["Roundabout"]})
    assert idx.size() == 2


# -- router integration ------------------------------------------------------
def _local_library(transport, title, track_id=9):
    def titles(cmd):
        term = next((str(p).split("search:", 1)[1] for p in cmd
                     if str(p).startswith("search:")), "")
        if term and term.lower() in title.lower():
            return {"titles_loop": [{"id": track_id, "title": title}]}
        return {"count": 0}

    transport.responses["titles"] = titles
    transport.responses["albums"] = {"count": 0}
    transport.responses["artists"] = {"count": 0}


def test_mangled_title_corrected_from_library(lms, transport):
    _local_library(transport, "Comfortably Numb")
    idx = _index("Comfortably Numb")
    router = Router(lms, entity_index=idx)
    res = router.handle_many(["metti fatta blina"], source="local")
    assert res["ok"] is True
    assert res["speech"] == "Riproduco Comfortably Numb dalla tua musica."
    assert res["used"] == "metti Comfortably Numb"
    assert ["playlistcontrol", "cmd:load", "track_id:9"] in transport.commands()


def test_correct_transcript_keeps_priority_over_correction(lms, transport):
    # The original alternative hits -> corrections (appended after) never run.
    _local_library(transport, "Comfortably Numb")
    idx = _index("Comfortably Numb", "Time")
    router = Router(lms, entity_index=idx)
    res = router.handle_many(["metti Comfortably Numb"], source="local")
    assert res["used"] == "metti Comfortably Numb"


def test_no_index_no_expansion(lms, transport):
    _local_library(transport, "Comfortably Numb")
    router = Router(lms)  # no entity index configured
    res = router.handle_many(["metti fatta blina"], source="local")
    assert res["ok"] is False
