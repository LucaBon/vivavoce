#!/usr/bin/env python3
"""Quanto della strada A copre davvero le richieste vaghe (T2.4).

L'acceptance criterion di T2.4 non chiede solo che «metti qualcosa di
rilassante» funzioni: chiede di **misurare il residuo** — quale quota di frasi
vaghe resta senza risposta — perché è quel numero, e non un'intuizione, a
decidere se T2.5 (la mappa mood→seed generata offline) vale la pena.

Questo strumento legge i corpora in ``tests/data/vague_phrases_*.txt`` — scritti
come parla una persona, non come vuole il parser — e per ogni frase chiede al
vero pattern ``mood`` della lingua e al vero ``MOOD_WORDS`` se ne esce una
chiave. Non tocca LMS: misura il vocabolario, non la libreria di qualcuno.
Con ``--residual`` stampa le frasi scoperte, che sono il materiale grezzo per
la decisione su T2.5.

    uv run python tools/mood_coverage.py
    uv run python tools/mood_coverage.py --residual

La stessa funzione ``coverage()`` è usata da ``tests/test_moods.py``, così il
numero nel piano e il numero sotto test non possono divergere.
"""

from __future__ import annotations

import argparse
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for _tree in ("engine", "localvoice"):
    _path = os.path.join(ROOT, _tree)
    if _path not in sys.path:
        sys.path.insert(0, _path)

import moods  # noqa: E402
from lang import PACKS  # noqa: E402

CORPUS_DIR = os.path.join(ROOT, "tests", "data")


def load_phrases(lang):
    """Le frasi del corpus di una lingua, senza commenti né righe vuote."""
    path = os.path.join(CORPUS_DIR, "vague_phrases_%s.txt" % lang)
    with open(path, encoding="utf-8") as fh:
        return [line.strip() for line in fh
                if line.strip() and not line.startswith("#")]


def resolve(phrase, lang):
    """La chiave mood che la frase produce davvero, o None.

    Il doppio filtro per intero, nell'ordine in cui lo esegue il router: il
    pattern della lingua deve agganciare il marcatore, e la coda che cattura
    deve essere una voce di MOOD_WORDS."""
    pack = PACKS[lang]
    match = pack.PATTERNS["mood"].search(phrase)
    if not match:
        return None
    return moods.match_mood(match.group(1).strip(), pack.MOOD_WORDS)


def coverage(lang):
    """``(coperte, scoperte)`` per una lingua."""
    covered, residual = [], []
    for phrase in load_phrases(lang):
        key = resolve(phrase, lang)
        (covered if key else residual).append((phrase, key))
    return covered, residual


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--residual", action="store_true",
                        help="stampa le frasi che restano senza risposta")
    parser.add_argument("--lang", action="append",
                        help="limita a una lingua (ripetibile)")
    args = parser.parse_args(argv)

    langs = args.lang or sorted(PACKS)
    total_covered = total_all = 0
    for lang in langs:
        covered, residual = coverage(lang)
        n = len(covered) + len(residual)
        if not n:
            continue
        total_covered += len(covered)
        total_all += n
        print("%s: %d/%d coperte (%.0f%%), %d residue"
              % (lang, len(covered), n, 100.0 * len(covered) / n, len(residual)))
        if args.residual:
            for phrase, _ in residual:
                print("    - %s" % phrase)
    if total_all:
        print("\ntotale: %d/%d (%.0f%%) — il residuo è l'input di T2.5"
              % (total_covered, total_all, 100.0 * total_covered / total_all))
    return 0


if __name__ == "__main__":
    sys.exit(main())
