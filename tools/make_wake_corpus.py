#!/usr/bin/env python3
"""Synthesize a wake-word test corpus, so the bench isn't measuring one voice.

``tools/sherpa_bench.py`` needs ``--positives``: recordings that each contain
the wake phrase. Recording them by hand has a quiet failure mode — forty takes
by the same person in the same room tunes every threshold to *that* voice and
that accent, and the engine that wins is the one that overfits hardest. A
household product is used by people who don't sound like the developer.

So the positives are generated instead, with Piper (local, offline, MIT
voices), across every voice a language has, several speaking rates and a
prosody jitter. Multi-speaker models multiply that: ``en_US-l2arctic-medium``
carries 24 *non-native* English speakers, which is the closest cheap proxy for
"a guest says your wake word with an accent you didn't plan for".

    uv run python tools/make_wake_corpus.py --phrase vivavoce --out ~/audio/si

Three kinds of clip come out, and the mix is the point:

* the phrase alone — the two-step "say it, wait for the prompt" style;
* the phrase inside a command ("vivavoce metti i Pink Floyd") — the one-breath
  style, which is the harder detection and the nicer product;
* the phrase after some unrelated speech, so a detector that only ever sees
  audio *starting* with the phrase doesn't get an easy pass.

``--confusables`` writes a second set to use as **negatives**: near-misses that
must *not* fire ("vivace", "viva la vita", "provo la voce"). These are what
actually calibrate ``sherpa_bench --fuzzy``: the threshold has to sit above the
best near-miss and below the worst real pronunciation, and without them the
sweep has nothing to push against on one side.

What this does **not** replace: real recordings of the room. Synthetic speech
is too clean — no distance, no reverb, no hi-fi humming underneath. The cheap
fix is to play this corpus through the speakers and record it back; the
expensive-but-real one is a few human takes. And the *negatives* that decide
the product — the system playing music at normal volume — can only be
captured, never generated.

Output is 16 kHz mono 16-bit WAV: exactly what ``static/js/serverwake.js``
resamples to before it reaches ``/wakeword/chunk``, so the corpus is the same
shape as the audio the server actually sees.

Piper is dev-only tooling and never a runtime dependency of the app:
``uv pip install piper-tts``.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import wave
from typing import Dict, List, Optional, Sequence, Tuple

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO_ROOT, "tools"))

# The rate the server sees. sherpa_bench.read_wav would resample anyway, but
# writing it straight means the corpus and the wire carry identical audio.
SAMPLE_RATE = 16000

# Speaking rates. Piper's length_scale is duration, so >1 is *slower*. The
# spread matters more than the exact values: a wake word said briskly on the
# way past the speaker is a different signal from one said carefully.
LENGTH_SCALES = (0.85, 1.0, 1.2)

# How many speakers to take from a multi-speaker model. All 904 of libritts
# would drown the corpus in one model's idea of English; a couple of dozen is
# variety, past that it is repetition.
MAX_SPEAKERS = 12

# Carrier sentences, per language: the wake phrase does not arrive alone in
# real life. "{p}" is the phrase. The trailing forms put speech *before* it,
# which is the case a naive detector quietly fails.
CARRIERS: Dict[str, Sequence[str]] = {
    "it": ("{p}", "{p} metti i Pink Floyd", "{p} alza il volume",
           "{p}, che canzone e' questa", "aspetta un attimo, {p} metti Time",
           "allora, {p} play"),
    "en": ("{p}", "{p} play Pink Floyd", "{p} turn it up",
           "{p}, what song is this", "hang on a second, {p} play Time",
           "right then, {p} play"),
    "fr": ("{p}", "{p} mets Pink Floyd", "{p} monte le volume",
           "{p}, c'est quoi cette chanson", "attends une seconde, {p} mets Time"),
    "de": ("{p}", "{p} spiel Pink Floyd", "{p} mach lauter",
           "{p}, welches Lied ist das", "warte kurz, {p} spiel Time"),
    "es": ("{p}", "{p} pon Pink Floyd", "{p} sube el volumen",
           "{p}, que cancion es esta", "espera un momento, {p} pon Time"),
}

# Near-misses that must never fire, per language. Generated from the phrase
# where that makes sense and fixed where it doesn't; the fixed ones are chosen
# to share a stressed syllable with the Italian default.
CONFUSABLES: Dict[str, Sequence[str]] = {
    "it": ("vivace", "viva la vita", "provo la voce", "prova la voce",
           "la vita e' voce", "vieni via", "va bene la voce",
           "metti i Pink Floyd", "alza il volume", "che canzone e' questa"),
    "en": ("vivacious", "viva la vida", "leave a voice", "we've a voice",
           "play Pink Floyd", "turn it up", "what song is this"),
    "fr": ("vivace", "viva la vida", "prouve la voix", "mets Pink Floyd"),
    "de": ("vivace", "viva la vida", "wie eine Stimme", "spiel Pink Floyd"),
    "es": ("vivaz", "viva la vida", "prueba la voz", "pon Pink Floyd"),
}

LANG_PREFIX = {"it": "it_IT", "en": "en_US", "fr": "fr_FR",
               "de": "de_DE", "es": "es_ES"}

# Extra models worth pulling in beyond the target language: non-native English
# speakers, as a stand-in for the accents a real household has.
ACCENT_MODELS = ("en_US-l2arctic-medium", "en_GB-aru-medium")


def catalogue() -> Dict[str, dict]:
    """Piper's published voice list."""
    from urllib.request import urlopen

    from piper.download_voices import VOICES_JSON

    return json.loads(urlopen(VOICES_JSON).read().decode("utf-8"))


def pick_voices(lang: str, accents: bool) -> List[str]:
    """Every Piper voice for ``lang``, plus the accented English models when
    asked — sorted, so a rerun writes the same corpus."""
    voices = catalogue()
    prefix = LANG_PREFIX.get(lang, lang)
    chosen = sorted(n for n in voices if n.startswith(prefix))
    if not chosen:
        raise SystemExit(
            f"Piper has no voice for {lang!r} (looked for {prefix}*). "
            f"Languages with voices: "
            f"{', '.join(sorted(LANG_PREFIX))}")
    if accents:
        chosen += [n for n in ACCENT_MODELS if n in voices and n not in chosen]
    return chosen


def speakers_of(name: str, voices: Dict[str, dict]) -> List[Optional[int]]:
    count = int(voices.get(name, {}).get("num_speakers") or 1)
    if count <= 1:
        return [None]
    # Spread across the range rather than taking the first N: consecutive ids
    # in these datasets are often the same recording session.
    step = max(1, count // MAX_SPEAKERS)
    return list(range(0, count, step))[:MAX_SPEAKERS]


def load_voice(name: str, data_dir: str):
    """Download the voice on first use, then load it.

    ``PiperVoice.load`` takes a *path*, not a catalogue name — handed a name it
    raises FileNotFoundError for the .json rather than fetching anything, so
    the download is an explicit step."""
    from pathlib import Path

    from piper import PiperVoice
    from piper.download_voices import download_voice

    os.makedirs(data_dir, exist_ok=True)
    model = os.path.join(data_dir, name + ".onnx")
    if not os.path.exists(model):
        download_voice(name, Path(data_dir))
    return PiperVoice.load(model)


def write_wav(path: str, samples: Sequence[float], rate: int) -> None:
    """One clip as 16 kHz mono 16-bit PCM, resampled with the same linear
    interpolation the browser uses (sherpa_bench.resample mirrors
    static/js/serverwake.js), so nothing here is gentler than the wire."""
    import sherpa_bench

    if rate != SAMPLE_RATE:
        samples = sherpa_bench.resample(samples, rate, SAMPLE_RATE)
    with wave.open(path, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(SAMPLE_RATE)
        wf.writeframes(sherpa_bench.float_to_int16_bytes(samples))


def synth(voice, text: str, length_scale: float,
          speaker: Optional[int]) -> Tuple[List[float], int]:
    """One utterance as float samples plus its native rate."""
    import numpy as np
    from piper import SynthesisConfig

    cfg = SynthesisConfig(length_scale=length_scale, speaker_id=speaker,
                          # A little jitter so three rates don't produce three
                          # identical readings of the same prosody.
                          noise_scale=0.667, noise_w_scale=0.8)
    pieces = []
    rate = SAMPLE_RATE
    for chunk in voice.synthesize(text, syn_config=cfg):
        rate = chunk.sample_rate
        pieces.append(np.frombuffer(chunk.audio_int16_bytes, dtype="<i2"))
    if not pieces:
        return [], rate
    audio = np.concatenate(pieces).astype("float32") / 32768.0
    return audio.tolist(), rate


def slugify(text: str) -> str:
    keep = [c if c.isalnum() else "_" for c in text.lower()]
    return "".join(keep).strip("_")[:40] or "clip"


def generate(args) -> int:
    voices_json = catalogue()
    names = pick_voices(args.lang, args.accents)
    texts = ([c.format(p=args.phrase)
              for c in CARRIERS.get(args.lang, CARRIERS["en"])]
             if not args.confusables
             else list(CONFUSABLES.get(args.lang, CONFUSABLES["en"])))

    os.makedirs(args.out, exist_ok=True)
    print(f"{len(names)} voci, {len(texts)} frasi, "
          f"{len(LENGTH_SCALES)} velocita' -> {args.out}")
    written = 0
    for name in names:
        try:
            voice = load_voice(name, args.data_dir)
        except Exception as exc:                     # a voice failing to
            print(f"  {name}: saltata ({exc})")      # download is not fatal
            continue
        for speaker in speakers_of(name, voices_json):
            for scale in LENGTH_SCALES:
                for text in texts:
                    samples, rate = synth(voice, text, scale, speaker)
                    if not samples:
                        continue
                    stem = (f"{name}_s{speaker if speaker is not None else 0}"
                            f"_l{scale}_{slugify(text)}.wav")
                    write_wav(os.path.join(args.out, stem), samples, rate)
                    written += 1
        print(f"  {name}: {written} file finora")
    print(f"\n{written} clip in {args.out}")
    if not written:
        # Every voice failing is the same shape as one voice failing, and the
        # difference is the whole run. Do not let it look like a success.
        print("nessuna clip generata: nessuna voce si e' caricata.",
              file=sys.stderr)
        return 1
    if not args.confusables:
        print("Ricorda: questi sono troppo puliti. Riproducili sull'impianto e "
              "ri-registrali per avere la stanza, e cattura i NEGATIVI veri "
              "(musica a volume normale) — quelli non si generano.")
    return 0


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(
        description="Genera un corpus di prova per la parola di attivazione.",
        formatter_class=argparse.RawDescriptionHelpFormatter, epilog=__doc__)
    ap.add_argument("--phrase", required=True,
                    help="la frase di attivazione, es. 'vivavoce'")
    ap.add_argument("--out", required=True, help="cartella di destinazione")
    ap.add_argument("--lang", default="it",
                    choices=sorted(LANG_PREFIX),
                    help="lingua delle voci (default: it)")
    ap.add_argument("--confusables", action="store_true",
                    help="genera i quasi-uguali da usare come NEGATIVI, "
                         "invece dei positivi")
    ap.add_argument("--accents", action="store_true",
                    help="aggiungi i modelli inglesi multi-parlante non "
                         "madrelingua (l2arctic, aru): accenti che in casa ci "
                         "sono e nel corpus di solito no")
    ap.add_argument("--data-dir",
                    default=os.path.join(REPO_ROOT, ".piper-voices"),
                    help="dove scaricare le voci (default: .piper-voices/)")
    args = ap.parse_args(argv)
    return generate(args)


if __name__ == "__main__":
    raise SystemExit(main())
