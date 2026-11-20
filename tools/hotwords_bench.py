#!/usr/bin/env python3
"""Do Whisper hotwords help this household's names — and do they hurt others?

Phase 3 of docs/name-recognition-design.md hands Whisper the names a
household plays (``Names.hotwords``). Whether that helps cannot be simulated:
it has to be heard. This runs every clip of ``tools/asr_titles_bench.py``'s
corpus twice — without hotwords and with them — and scores both with the
product's own routing and matching (``route``, ``matching._score``).

The second half of the report is the one to read first. The known risk of
hotwords is a recogniser that starts hearing the hinted names where they are
not: a clip whose score *drops* with them is that, and a handful of drops is a
reason to hint less, whatever the average says.

Where the names come from — pick one:

``--data-dir DIR``     the household's own: ``name_index.json`` and
                       ``corrections.json`` in Vivavoce's data directory,
                       through ``Names.hotwords`` exactly as the server builds
                       them. The realistic measure.
``--from-manifest``    every name the corpus expects. An upper bound — the
                       recogniser is told the answers — useful only to see
                       how much there is to gain at all.
``--hotwords "a, b"``  a string of your own.

Usage (needs ``uv sync --group asr``, like the bench it extends)::

    python tools/hotwords_bench.py --clips ~/registrazioni --data-dir ~/vivavoce-data
"""

from __future__ import annotations

import argparse
import os
import statistics
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import asr_titles_bench as bench  # noqa: E402  (also puts engine/, localvoice/ on the path)


def household_hotwords(data_dir: str, lang: str = "it") -> str:
    from pro.corrections import Corrections
    from pro.name_index import NameIndex
    from pro.names import Names

    class _Licensed:
        def is_pro(self):
            return True

    names = Names(NameIndex(os.path.join(data_dir, "name_index.json")),
                  _Licensed(),
                  corrections=Corrections(os.path.join(data_dir, "corrections.json")),
                  spawn=lambda fn, *a: None)
    return names.hotwords(lang) or ""


def manifest_hotwords(entries) -> str:
    seen, out = set(), []
    for e in entries:
        name = (e.get("expect") or "").strip()
        if name and name.lower() not in seen:
            seen.add(name.lower())
            out.append(name)
    return ", ".join(out)


def transcribe_all(model, clips_dir, entries, hotwords):
    rows = []
    for e in entries:
        extra = {"hotwords": hotwords} if hotwords else {}
        segments, _info = model.transcribe(
            os.path.join(clips_dir, e["file"]), language="it", beam_size=5,
            vad_filter=True, **extra)
        heard = " ".join(s.text.strip() for s in segments).strip()
        frame_ok, query = bench.route(heard, e.get("kind", "song"))
        rows.append({"file": e["file"], "expect": e["expect"], "heard": heard,
                     "frame_ok": frame_ok,
                     "score": bench.matching._score(query, e["expect"],
                                                    subset_floor=False)})
    return rows


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--clips", required=True, help="cartella + manifest.json")
    ap.add_argument("--manifest", help="manifest alternativo")
    ap.add_argument("--model", default="small")
    ap.add_argument("--cache", default=os.path.join(bench.REPO_ROOT, ".sherpa-models",
                                                    "whisper"))
    src = ap.add_mutually_exclusive_group(required=True)
    src.add_argument("--data-dir", help="la cartella dati di Vivavoce")
    src.add_argument("--from-manifest", action="store_true")
    src.add_argument("--hotwords")
    args = ap.parse_args()

    entries = bench.load_clips(args.clips, args.manifest)
    if args.data_dir:
        hotwords = household_hotwords(args.data_dir)
    elif args.from_manifest:
        hotwords = manifest_hotwords(entries)
    else:
        hotwords = args.hotwords
    if not hotwords:
        raise SystemExit("nessun nome da suggerire: storico e correzioni vuoti?")
    print(f"{len(entries)} clip · hotwords ({len(hotwords)} caratteri): "
          f"{hotwords[:120]}{'…' if len(hotwords) > 120 else ''}")

    from faster_whisper import WhisperModel
    model = WhisperModel(args.model, device="cpu", compute_type="int8",
                         download_root=args.cache)
    before = transcribe_all(model, args.clips, entries, None)
    after = transcribe_all(model, args.clips, entries, hotwords)

    mean_b = statistics.mean(r["score"] for r in before)
    mean_a = statistics.mean(r["score"] for r in after)
    print(f"\npunteggio medio {mean_b:.3f} → {mean_a:.3f} ({mean_a - mean_b:+.3f})")
    pairs = list(zip(before, after))
    worse = [(b, a) for b, a in pairs if a["score"] < b["score"] - 0.05]
    better = [(b, a) for b, a in pairs if a["score"] > b["score"] + 0.05]
    print(f"\nPEGGIORATE con gli hotwords: {len(worse)}  (leggere prima queste)")
    for b, a in sorted(worse, key=lambda p: p[1]["score"] - p[0]["score"]):
        print(f"  {b['score']:.2f} → {a['score']:.2f}  {b['expect']!r}: "
              f"{b['heard']!r} → {a['heard']!r}")
    print(f"\nmigliorate: {len(better)}")
    for b, a in sorted(better, key=lambda p: p[0]["score"] - p[1]["score"]):
        print(f"  {b['score']:.2f} → {a['score']:.2f}  {b['expect']!r}: "
              f"{b['heard']!r} → {a['heard']!r}")


if __name__ == "__main__":
    main()
