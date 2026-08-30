#!/usr/bin/env python3
"""Measure sherpa-onnx as a wake-word / ASR engine, before adopting it.

The server wake word today is openWakeWord with one of five fixed English
phrases (see ``localvoice/pro/wakeword.py``). sherpa-onnx is the candidate
replacement, and the interesting question is not "does it run" but *which of
its two paths earns its place*:

**A. Keyword spotting.** Open-vocabulary — any phrase, no training — but the
only pretrained models are English, Chinese, and Chinese+English. An Italian
phrase has to be spelled with English BPE tokens ("vivavoce" ->
"▁VI VA VO CE") and fed to a model trained on English phonetics. Nobody
documents how well that works; this script measures it.

**B. VAD + offline ASR.** silero VAD gates a multilingual recognizer
(``parakeet-tdt-0.6b-v3``: it/de/en/fr/es/nl and 19 more, with automatic
language ID) and the wake phrase is matched *in the transcript*. Genuinely
open-vocabulary in every target language, and the same engine then
transcribes the command — but it burns far more CPU, and a VAD in a hi-fi
listening room fires on the music too.

**C. faster-whisper.** What ``localvoice/pro/asr.py`` already ships, as the
accuracy/speed reference the other two are judged against.

**D. Vosk.** Kaldi, streaming, one ~50 MB model per language with real
Italian — the closest fit to the transport ``/wakeword/chunk`` already has.
Two configurations, because they behave nothing alike: **D1** restricts the
recognizer to a grammar of the phrase plus ``[unk]``, which turns an
open-vocabulary ASR into a cheap phrase detector, and **D2** runs free
recognition and matches the phrase in the transcript. D1 cannot be told to
listen for a word outside the model's lexicon (see :func:`vosk_oov`); D2 can
never *output* one either, so for a coined name both lean on the fuzzy match.

    uv run python tools/sherpa_bench.py --phrase vivavoce \\
        --positives ~/audio/si --negatives ~/audio/no

``--positives`` is a directory of recordings that each contain the wake
phrase once (vary voice, distance, background). ``--negatives`` is a
directory of recordings that must *never* fire it — and at least one of them
should be the hi-fi playing music at normal listening volume, because that is
the false-trigger source this product actually has. Both take 16-bit PCM WAV
of any sample rate (convert anything else with
``ffmpeg -i in.m4a -ac 1 -ar 16000 out.wav``).

What comes out: detection rate on the positives, false triggers per hour on
the negatives, real-time factor, and peak RSS — per configuration, on *this*
machine. Run it on the box that will actually serve, a Raspberry Pi 5
included: the RTF is the number that decides whether path B is viable there.

Nothing here touches the app. Models land in ``--models-dir`` (default
``.sherpa-models/`` in the repo root, git-ignored territory), downloaded once
from the sherpa-onnx GitHub releases — 18 MB for the KWS model, 487 MB for
parakeet.

Needs ``sherpa-onnx`` installed (``uv pip install sherpa-onnx``). Config A
also needs ``sentencepiece``, and not optionally: the phrase has to be spelled
in the model's own BPE tokens, and a plausible-but-different spelling detects
nothing while erroring nowhere (measured — see :func:`bpe_tokens`). Config C
needs the existing ``asr`` group. A configuration whose engine is missing is
reported as skipped, not as a failure.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import tarfile
import time
import unicodedata
import urllib.request
import wave
from difflib import SequenceMatcher
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# The rate every model here wants. Recordings at another rate are resampled
# (linearly, like static/js/serverwake.js does in the browser) rather than
# refused: feeding a model the wrong rate produces silent garbage, never an
# error, so this conversion is not optional.
SAMPLE_RATE = 16000

RELEASES = "https://github.com/k2-fsa/sherpa-onnx/releases/download"

# name -> (url, is_tarball). Sizes are the compressed download.
MODELS = {
    # ~18 MB. English BPE keyword spotter — path A.
    "kws": (f"{RELEASES}/kws-models/"
            "sherpa-onnx-kws-zipformer-gigaspeech-3.3M-2024-01-01.tar.bz2",
            True),
    # ~640 KB. The VAD in front of path B.
    "vad": (f"{RELEASES}/asr-models/silero_vad.onnx", False),
    # ~487 MB compressed. 25 European languages, automatic language ID.
    "parakeet": (f"{RELEASES}/asr-models/"
                 "sherpa-onnx-nemo-parakeet-tdt-0.6b-v3-int8.tar.bz2", True),
}


# --------------------------------------------------------------------------
# audio


def read_wav(path: str) -> Tuple[List[float], float]:
    """One WAV file as mono float samples in [-1, 1] at :data:`SAMPLE_RATE`,
    plus its duration in seconds. 16-bit PCM only — the format every phone
    recorder and ``ffmpeg -ar 16000`` produces."""
    with wave.open(path, "rb") as wf:
        if wf.getsampwidth() != 2:
            raise ValueError(f"{path}: only 16-bit PCM WAV is supported "
                             f"(this one is {wf.getsampwidth() * 8}-bit)")
        channels = wf.getnchannels()
        rate = wf.getframerate()
        raw = wf.readframes(wf.getnframes())

    samples = _int16_to_float(raw)
    if channels > 1:  # downmix: the models are mono
        samples = [sum(samples[i:i + channels]) / channels
                   for i in range(0, len(samples) - channels + 1, channels)]
    duration = len(samples) / rate
    return resample(samples, rate, SAMPLE_RATE), duration


def _int16_to_float(raw: bytes) -> List[float]:
    try:
        import numpy as np  # optional: an hour of audio in pure Python is slow
    except ImportError:
        import array
        buf = array.array("h")
        buf.frombytes(raw)
        return [s / 32768.0 for s in buf]
    return (np.frombuffer(raw, dtype="<i2").astype("float32") / 32768.0).tolist()


def resample(samples: Sequence[float], from_rate: int,
             to_rate: int) -> List[float]:
    """Linear interpolation, the same thing ``serverwake.js`` does client-side."""
    if from_rate == to_rate:
        return list(samples)
    ratio = from_rate / to_rate
    out_len = int(len(samples) / ratio)
    out = []
    for i in range(out_len):
        pos = i * ratio
        i0 = int(pos)
        i1 = min(i0 + 1, len(samples) - 1)
        frac = pos - i0
        out.append(samples[i0] * (1 - frac) + samples[i1] * frac)
    return out


def wav_files(path: str) -> List[str]:
    if os.path.isfile(path):
        return [path]
    found = sorted(os.path.join(path, n) for n in os.listdir(path)
                   if n.lower().endswith(".wav"))
    if not found:
        raise SystemExit(f"no .wav files in {path} — convert with: "
                         f"ffmpeg -i input -ac 1 -ar 16000 output.wav")
    return found


def chunks(samples: Sequence[float], size: int) -> Iterable[Sequence[float]]:
    for i in range(0, len(samples), size):
        yield samples[i:i + size]


# --------------------------------------------------------------------------
# models


def ensure_model(name: str, models_dir: str) -> str:
    """Path to model ``name``, downloading and unpacking it on first use.

    Returns the extracted directory (tarballs) or the file itself. Downloads
    to a ``.part`` file and renames on success, so an interrupted run doesn't
    leave a truncated model that fails mysteriously later."""
    url, is_tarball = MODELS[name]
    os.makedirs(models_dir, exist_ok=True)
    basename = url.rsplit("/", 1)[-1]
    target = os.path.join(
        models_dir, basename[:-len(".tar.bz2")] if is_tarball else basename)
    if os.path.exists(target):
        return target

    archive = os.path.join(models_dir, basename)
    print(f"  scarico {basename} ...", flush=True)
    _download(url, archive + ".part")
    os.replace(archive + ".part", archive)

    if not is_tarball:
        return target
    print(f"  estraggo {basename} ...", flush=True)
    with tarfile.open(archive, "r:bz2") as tf:
        tf.extractall(models_dir)
    os.remove(archive)
    if not os.path.exists(target):
        raise SystemExit(f"{basename} did not unpack to {target}")
    return target


def _download(url: str, dest: str) -> None:
    with urllib.request.urlopen(url) as resp, open(dest, "wb") as out:
        total = int(resp.headers.get("Content-Length") or 0)
        done = 0
        while True:
            block = resp.read(1 << 20)
            if not block:
                break
            out.write(block)
            done += len(block)
            if total:
                pct = 100 * done / total
                unit, shift = ("MiB", 20) if total >> 20 else ("KiB", 10)
                print(f"\r    {done >> shift}/{total >> shift} {unit} "
                      f"({pct:.0f}%)", end="", flush=True)
        print()


def find(directory: str, *names: str) -> str:
    """First of ``names`` present in ``directory`` — model tarballs are not
    consistent about int8 suffixes across releases."""
    for name in names:
        path = os.path.join(directory, name)
        if os.path.exists(path):
            return path
    raise SystemExit(f"none of {names} found in {directory}")


# --------------------------------------------------------------------------
# phrase matching


def normalize(text: str) -> str:
    """Lowercase, unaccented, punctuation-free — so "Viva voce!" and
    "vivavoce" compare equal, in every target language."""
    text = unicodedata.normalize("NFKD", text.lower())
    text = "".join(c for c in text if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9 ]+", " ", text).strip()


def phrase_in(transcript: str, phrase: str, threshold: float) -> bool:
    """Whether ``phrase`` occurs in ``transcript``, tolerating the spelling
    the recognizer chose ("viva voce", "vivavoc"). Slides a window of the
    phrase's word count and takes the best similarity."""
    hay = normalize(transcript)
    needle = normalize(phrase)
    if not hay or not needle:
        return False
    if needle.replace(" ", "") in hay.replace(" ", ""):
        return True
    words = hay.split()
    span = max(1, len(needle.split()))
    for i in range(len(words)):
        for width in (span, span + 1):
            window = " ".join(words[i:i + width])
            if not window:
                continue
            if SequenceMatcher(None, window, needle).ratio() >= threshold:
                return True
    return False


def bpe_tokens(phrase: str, bpe_model: str) -> str:
    """The phrase as a KWS token string ("▁VI V A VO CE").

    This has to be the model's *own* BPE segmentation, not a plausible one.
    Measured here on the model's bundled sample: "LIGHT UP" tokenized as
    "▁LI G H T ▁UP" (a greedy longest-match over ``tokens.txt``) detects
    nothing at all, while the sentencepiece answer "▁ L IGHT ▁UP" — what the
    model ships in its own ``keywords.txt`` — detects it every time. Wrong
    tokens don't error, they just never fire, so there is no approximation
    worth offering: without sentencepiece this refuses and says so."""
    text = normalize(phrase).upper()
    if not text:
        raise SystemExit(f"empty phrase after normalization: {phrase!r}")
    try:
        import sentencepiece as spm
    except ImportError:
        raise SystemExit(
            "config A needs sentencepiece to spell the phrase in the model's "
            "own BPE tokens: uv pip install sentencepiece\n"
            "(or pass the tokens yourself with --keyword-tokens, e.g. "
            "--keyword-tokens '▁VI V A VO CE')")
    sp = spm.SentencePieceProcessor()
    sp.load(bpe_model)
    return " ".join(sp.encode_as_pieces(text))


# --------------------------------------------------------------------------
# configurations


class Result:
    def __init__(self, name: str) -> None:
        self.name = name
        self.skipped: Optional[str] = None
        self.hits = 0
        self.positives = 0
        self.false_triggers = 0
        self.negative_seconds = 0.0
        self.audio_seconds = 0.0
        self.compute_seconds = 0.0
        self.transcripts: List[Tuple[str, str]] = []
        # (kind, filename, transcript, seconds) for every clip a
        # transcript-matching config decoded. Decoding is the expensive part
        # and the threshold is applied to the *text* afterwards, so keeping
        # these lets --fuzzy-sweep re-score every threshold for free instead
        # of re-running the model once per point on the curve.
        self.samples: List[Tuple[str, str, str, float]] = []

    @property
    def rtf(self) -> float:
        return self.compute_seconds / self.audio_seconds if self.audio_seconds else 0.0

    def as_dict(self) -> Dict[str, object]:
        return {
            "config": self.name,
            "skipped": self.skipped,
            "detection_rate": (self.hits / self.positives) if self.positives else None,
            "hits": self.hits,
            "positives": self.positives,
            "false_triggers": self.false_triggers,
            "false_triggers_per_hour": (
                self.false_triggers / (self.negative_seconds / 3600.0)
                if self.negative_seconds else None),
            "rtf": round(self.rtf, 4),
            "audio_seconds": round(self.audio_seconds, 1),
        }


def run_kws(args, models_dir: str, positives: List[str],
            negatives: List[str]) -> Result:
    """Path A: sherpa-onnx keyword spotting, English model, any phrase.

    Measured 2026-08-30, and both numbers matter when reading a result here:

    * **It needs speech around the keyword.** English "light up" (the model's
      own documented example, spelled with its own tokens) detects at **76%**
      inside a carrier sentence and **2%** spoken alone. A corpus of bare
      phrases will therefore score this path near zero for a reason that has
      nothing to do with the phrase — and the app supports the bare style, so
      that is a product limitation, not only a benchmarking one.
    * **An Italian phrase in English BPE does not work at all.** «vivavoce» ->
      "▁VI V A VO CE" fired on 0 of 72 clips, flat across 12 threshold/boost
      combinations. Verified against the model's shipped ground truth
      (``test_wavs/0.wav`` + ``test_keywords.txt``) that the harness itself
      detects correctly, so this is the engine, not the wiring.
    """
    result = Result("A: KWS zipformer (en) su frase libera")
    try:
        import sherpa_onnx
    except ImportError:
        result.skipped = "sherpa-onnx non installato (uv pip install sherpa-onnx)"
        return result

    model_dir = ensure_model("kws", models_dir)
    tokens = os.path.join(model_dir, "tokens.txt")
    keyword = args.keyword_tokens or bpe_tokens(
        args.phrase, os.path.join(model_dir, "bpe.model"))
    print(f"  frase «{args.phrase}» -> token: {keyword}")

    # KeywordSpotter demands a keywords *file* at construction even though
    # create_stream() also takes the phrase inline (checked against the real
    # 1.13.6 API, not assumed). The file carries the same phrase with its
    # boost (":") and per-keyword threshold ("#"), the two knobs this bench
    # exists to sweep.
    keywords_file = os.path.join(models_dir, "bench-keywords.txt")
    with open(keywords_file, "w", encoding="utf-8") as fh:
        fh.write(f"{keyword} :{args.boost} #{args.threshold}\n")

    spotter = sherpa_onnx.KeywordSpotter(
        tokens=tokens,
        keywords_file=keywords_file,
        encoder=find(model_dir, "encoder-epoch-12-avg-2-chunk-16-left-64.onnx",
                     "encoder-epoch-12-avg-2-chunk-16-left-64.int8.onnx"),
        decoder=find(model_dir, "decoder-epoch-12-avg-2-chunk-16-left-64.onnx"),
        joiner=find(model_dir, "joiner-epoch-12-avg-2-chunk-16-left-64.onnx",
                    "joiner-epoch-12-avg-2-chunk-16-left-64.int8.onnx"),
        num_threads=args.threads,
        keywords_score=args.boost,
        keywords_threshold=args.threshold,
        provider="cpu",
    )

    def count_triggers(path: str) -> Tuple[int, float, float]:
        samples, duration = read_wav(path)
        stream = spotter.create_stream(keyword)
        fired = 0
        started = time.perf_counter()
        # 300 ms chunks: what serverwake.js sends today.
        for chunk in chunks(samples, int(SAMPLE_RATE * 0.3)):
            stream.accept_waveform(SAMPLE_RATE, list(chunk))
            while spotter.is_ready(stream):
                spotter.decode_stream(stream)
                if spotter.get_result(stream):
                    fired += 1
                    spotter.reset_stream(stream)
        return fired, time.perf_counter() - started, duration

    for path in positives:
        fired, spent, duration = count_triggers(path)
        result.positives += 1
        result.hits += 1 if fired else 0
        result.compute_seconds += spent
        result.audio_seconds += duration
        if not fired and args.verbose:
            print(f"    miss: {os.path.basename(path)}")
    for path in negatives:
        fired, spent, duration = count_triggers(path)
        result.false_triggers += fired
        result.negative_seconds += duration
        result.compute_seconds += spent
        result.audio_seconds += duration
        if fired and args.verbose:
            print(f"    {fired} falsi trigger in {os.path.basename(path)}")
    return result


def _vad_segments(vad, samples: Sequence[float]) -> Iterable[Sequence[float]]:
    for chunk in chunks(samples, 512):
        vad.accept_waveform(list(chunk))
        while not vad.empty():
            yield vad.front.samples
            vad.pop()
    vad.flush()
    while not vad.empty():
        yield vad.front.samples
        vad.pop()


def run_vad_asr(args, models_dir: str, positives: List[str],
                negatives: List[str]) -> Result:
    """Path B: silero VAD + multilingual ASR, phrase matched in the transcript."""
    result = Result("B: silero VAD + parakeet-tdt-0.6b-v3 (25 lingue)")
    try:
        import sherpa_onnx
    except ImportError:
        result.skipped = "sherpa-onnx non installato (uv pip install sherpa-onnx)"
        return result

    vad_model = ensure_model("vad", models_dir)
    asr_dir = ensure_model("parakeet", models_dir)

    vad_config = sherpa_onnx.VadModelConfig()
    vad_config.silero_vad.model = vad_model
    vad_config.silero_vad.threshold = args.vad_threshold
    vad_config.silero_vad.min_silence_duration = 0.4
    vad_config.sample_rate = SAMPLE_RATE
    recognizer = sherpa_onnx.OfflineRecognizer.from_transducer(
        encoder=find(asr_dir, "encoder.int8.onnx", "encoder.onnx"),
        decoder=find(asr_dir, "decoder.int8.onnx", "decoder.onnx"),
        joiner=find(asr_dir, "joiner.int8.onnx", "joiner.onnx"),
        tokens=os.path.join(asr_dir, "tokens.txt"),
        num_threads=args.threads,
        model_type="nemo_transducer",
        provider="cpu",
    )

    def transcribe_segments(path: str) -> Tuple[List[str], float, float]:
        samples, duration = read_wav(path)
        vad = sherpa_onnx.VoiceActivityDetector(vad_config,
                                                buffer_size_in_seconds=60)
        texts = []
        started = time.perf_counter()
        for segment in _vad_segments(vad, samples):
            stream = recognizer.create_stream()
            stream.accept_waveform(SAMPLE_RATE, segment)
            recognizer.decode_stream(stream)
            texts.append(stream.result.text)
        return texts, time.perf_counter() - started, duration

    for path in positives:
        texts, spent, duration = transcribe_segments(path)
        hit = any(phrase_in(t, args.phrase, args.fuzzy) for t in texts)
        result.positives += 1
        result.hits += 1 if hit else 0
        result.compute_seconds += spent
        result.audio_seconds += duration
        result.transcripts.append((os.path.basename(path), " | ".join(texts)))
        result.samples.append(("pos", os.path.basename(path),
                               " | ".join(texts), duration))
        if args.verbose:
            print(f"    {'ok ' if hit else 'MISS'} {os.path.basename(path)}: "
                  f"{' | '.join(texts)}")
    for path in negatives:
        texts, spent, duration = transcribe_segments(path)
        fired = sum(1 for t in texts if phrase_in(t, args.phrase, args.fuzzy))
        result.samples.append(("neg", os.path.basename(path),
                               " | ".join(texts), duration))
        result.false_triggers += fired
        result.negative_seconds += duration
        result.compute_seconds += spent
        result.audio_seconds += duration
        if args.verbose:
            print(f"    {os.path.basename(path)}: {len(texts)} segmenti VAD, "
                  f"{fired} falsi trigger")
    return result


def run_faster_whisper(args, models_dir: str, positives: List[str],
                       negatives: List[str]) -> Result:
    """Path C: what the app already ships, as the reference point."""
    result = Result(f"C: faster-whisper {args.whisper_model} (riferimento)")
    try:
        from faster_whisper import WhisperModel
    except ImportError:
        result.skipped = "faster-whisper non installato (uv sync --group asr)"
        return result

    model = WhisperModel(args.whisper_model, device="cpu", compute_type="int8",
                         download_root=os.path.join(models_dir, "whisper"))

    def transcribe(path: str) -> Tuple[str, float, float]:
        _, duration = read_wav(path)
        started = time.perf_counter()
        segments, _info = model.transcribe(path, language=args.lang, beam_size=5)
        text = " ".join(s.text.strip() for s in segments)
        return text, time.perf_counter() - started, duration

    for path in positives:
        text, spent, duration = transcribe(path)
        hit = phrase_in(text, args.phrase, args.fuzzy)
        result.positives += 1
        result.hits += 1 if hit else 0
        result.compute_seconds += spent
        result.audio_seconds += duration
        result.transcripts.append((os.path.basename(path), text))
        result.samples.append(("pos", os.path.basename(path), text, duration))
        if args.verbose:
            print(f"    {'ok ' if hit else 'MISS'} {os.path.basename(path)}: {text}")
    for path in negatives:
        text, spent, duration = transcribe(path)
        result.samples.append(("neg", os.path.basename(path), text, duration))
        result.false_triggers += 1 if phrase_in(text, args.phrase, args.fuzzy) else 0
        result.negative_seconds += duration
        result.compute_seconds += spent
        result.audio_seconds += duration
    return result


# Vosk ships one model per language, as a zip (not the tarballs above).
# The "small" line is the one that matters here: ~50 MB, built for exactly
# this job — streaming recognition on a low-power box — where the full
# models are 1.5 GB and want a server. Names are upstream's own; a 404 here
# means the version was bumped, so check https://alphacephei.com/vosk/models.
VOSK_SMALL = "https://alphacephei.com/vosk/models"
VOSK_MODELS = {
    "it": f"{VOSK_SMALL}/vosk-model-small-it-0.22.zip",
    "en": f"{VOSK_SMALL}/vosk-model-small-en-us-0.15.zip",
    "fr": f"{VOSK_SMALL}/vosk-model-small-fr-0.22.zip",
    "de": f"{VOSK_SMALL}/vosk-model-small-de-0.15.zip",
    "es": f"{VOSK_SMALL}/vosk-model-small-es-0.42.zip",
}


def ensure_vosk_model(lang: str, models_dir: str) -> str:
    """The unpacked Vosk model directory for ``lang``, downloading once.

    Separate from :func:`ensure_model` because Vosk publishes zips on its own
    site rather than tarballs on the sherpa-onnx releases page."""
    import zipfile

    if lang not in VOSK_MODELS:
        raise SystemExit(
            f"no Vosk model configured for {lang!r} "
            f"(have: {', '.join(sorted(VOSK_MODELS))}); pass --vosk-model "
            f"with a directory you unpacked yourself")
    url = VOSK_MODELS[lang]
    os.makedirs(models_dir, exist_ok=True)
    basename = url.rsplit("/", 1)[-1]
    target = os.path.join(models_dir, basename[:-len(".zip")])
    if os.path.exists(target):
        return target

    archive = os.path.join(models_dir, basename)
    print(f"  scarico {basename} ...", flush=True)
    _download(url, archive + ".part")
    os.replace(archive + ".part", archive)
    print(f"  estraggo {basename} ...", flush=True)
    with zipfile.ZipFile(archive) as zf:
        zf.extractall(models_dir)
    os.remove(archive)
    if not os.path.exists(target):
        raise SystemExit(f"{basename} did not unpack to {target}")
    return target


def float_to_int16_bytes(samples: Sequence[float]) -> bytes:
    """Float samples to the little-endian 16-bit PCM Vosk eats — the same
    bytes ``static/js/serverwake.js`` already puts on the wire."""
    try:
        import numpy as np
    except ImportError:
        import struct
        clipped = [max(-1.0, min(1.0, s)) for s in samples]
        return struct.pack(f"<{len(clipped)}h",
                           *[int(s * 32767) for s in clipped])
    arr = np.clip(np.asarray(samples, dtype="float32"), -1.0, 1.0)
    return (arr * 32767).astype("<i2").tobytes()


def vosk_oov(model, phrase: str) -> List[str]:
    """Words of ``phrase`` that the Vosk model has no pronunciation for.

    This is the catch that decides whether grammar mode (D1) can serve an
    arbitrary customer phrase at all: Kaldi can only listen for words in its
    lexicon, so a genuinely invented name is not something it can be told to
    expect. Measured against the small Italian model: "vivavoce" passes (it is
    an ordinary Italian word for speakerphone, and so are "alexa", "sonos" and
    "jarvis"), while "zorblax" and "qwertzuiop" do not. So the limit is real
    but narrower than it sounds — it bites on coined names, not on the kind of
    phrase most households would actually pick.

    Vosk gives no API for this and the small models ship no ``words.txt``, so
    the only signal is a warning the C++ layer writes to **file descriptor 2**
    while the grammar is built ("Ignoring word missing in vocabulary: 'x'") —
    which :func:`_run_vosk` otherwise suppresses with ``SetLogLevel(-1)``.
    Verified against vosk 0.3.45: an unknown word does not raise, the
    recognizer constructs happily and then never fires, so without this the
    result is a silent 0% and no reason given. Hence the fd-level capture:
    ``contextlib.redirect_stderr`` cannot see writes from C.
    """
    import tempfile

    import vosk

    # The temp file opens *before* the descriptor is saved: dup first and the
    # saved fd leaks if TemporaryFile then raises, with nothing left holding a
    # reference to close it. This way the only fd in hand is one that a
    # try/finally is already responsible for.
    with tempfile.TemporaryFile() as tmp:
        saved = os.dup(2)
        try:
            os.dup2(tmp.fileno(), 2)
            vosk.SetLogLevel(0)
            vosk.KaldiRecognizer(model, SAMPLE_RATE,
                                 json.dumps([normalize(phrase), "[unk]"]))
        finally:
            vosk.SetLogLevel(-1)
            os.dup2(saved, 2)
            os.close(saved)
        tmp.seek(0)
        noise = tmp.read().decode("utf-8", "replace")
    return re.findall(r"Ignoring word missing in vocabulary: '([^']*)'", noise)


def _run_vosk(args, models_dir: str, positives: List[str],
              negatives: List[str], grammar: bool) -> Result:
    """Paths D1/D2: Vosk (Kaldi), streaming, one ~50 MB model per language.

    D1 restricts the recognizer to a grammar of just the phrase plus
    ``[unk]``, which turns an open-vocabulary ASR into a cheap phrase
    detector; D2 runs free recognition and matches the phrase in the
    transcript. They cost and mis-fire very differently, which is the whole
    reason both are measured."""
    label = "D1: Vosk grammatica ristretta" if grammar else "D2: Vosk libero"
    result = Result(f"{label} ({args.lang})")
    try:
        import vosk
    except ImportError:
        result.skipped = "vosk non installato (uv pip install vosk)"
        return result

    vosk.SetLogLevel(-1)          # the C++ layer is chatty on stderr
    model_dir = args.vosk_model or ensure_vosk_model(args.lang, models_dir)
    model = vosk.Model(model_dir)

    grammar_json = None
    if grammar:
        missing = vosk_oov(model, args.phrase)
        if missing:
            result.skipped = (
                f"parole fuori vocabolario: {', '.join(missing)} — la "
                f"grammatica Kaldi puo' ascoltare solo parole che il modello "
                f"conosce, quindi un nome inventato qui non innesca mai. "
                f"Scrivilo con parole reali, o misura D2, che non ha questo "
                f"limite.")
            return result
        grammar_json = json.dumps([normalize(args.phrase), "[unk]"])

    def scan(path: str) -> Tuple[int, float, float, List[str]]:
        samples, duration = read_wav(path)
        rec = (vosk.KaldiRecognizer(model, SAMPLE_RATE, grammar_json)
               if grammar else vosk.KaldiRecognizer(model, SAMPLE_RATE))
        fired = 0
        seen = ""
        # Every distinct text the recognizer showed, so --fuzzy-sweep can
        # re-score the same candidates this pass actually judged. Vosk fires
        # on a rolling partial rather than one final transcript, so scoring
        # only the final would sweep over something the detector never saw.
        candidates: List[str] = []
        started = time.perf_counter()
        # 300 ms, matching run_kws and what serverwake.js sends today.
        for chunk in chunks(samples, int(SAMPLE_RATE * 0.3)):
            data = float_to_int16_bytes(chunk)
            # A wake word must fire when it is *heard*, not when the speaker
            # stops, so the partial is checked on every chunk — that is the
            # latency the product actually feels.
            if rec.AcceptWaveform(data):
                text = json.loads(rec.Result()).get("text", "")
            else:
                text = json.loads(rec.PartialResult()).get("partial", "")
            if text and text != seen:
                candidates.append(text)
                if phrase_in(text, args.phrase, args.fuzzy):
                    fired += 1
                    rec = (vosk.KaldiRecognizer(model, SAMPLE_RATE, grammar_json)
                           if grammar else vosk.KaldiRecognizer(model, SAMPLE_RATE))
                    seen = ""
                    continue
                seen = text
        final = json.loads(rec.FinalResult()).get("text", "")
        if final:
            candidates.append(final)
            if phrase_in(final, args.phrase, args.fuzzy):
                fired += 1
        spent = time.perf_counter() - started
        if args.verbose:
            result.transcripts.append((os.path.basename(path), final))
        return fired, spent, duration, candidates

    for path in positives:
        fired, spent, duration, cands = scan(path)
        result.positives += 1
        result.hits += 1 if fired else 0
        result.compute_seconds += spent
        result.audio_seconds += duration
        result.samples.append(("pos", os.path.basename(path),
                               " | ".join(cands), duration))
        if not fired and args.verbose:
            print(f"    miss: {os.path.basename(path)}")
    for path in negatives:
        fired, spent, duration, cands = scan(path)
        result.samples.append(("neg", os.path.basename(path),
                               " | ".join(cands), duration))
        result.false_triggers += fired
        result.negative_seconds += duration
        result.compute_seconds += spent
        result.audio_seconds += duration
        if fired and args.verbose:
            print(f"    {fired} falsi trigger in {os.path.basename(path)}")
    return result


def run_vosk_grammar(args, models_dir: str, positives: List[str],
                     negatives: List[str]) -> Result:
    return _run_vosk(args, models_dir, positives, negatives, grammar=True)


def run_vosk_free(args, models_dir: str, positives: List[str],
                  negatives: List[str]) -> Result:
    return _run_vosk(args, models_dir, positives, negatives, grammar=False)


# --------------------------------------------------------------------------


def peak_rss_mib() -> float:
    """Peak resident memory of this process, or 0.0 where unavailable."""
    try:
        import resource
    except ImportError:  # Windows
        return 0.0
    rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    # Linux reports KiB, macOS bytes.
    return rss / 1024.0 if sys.platform != "darwin" else rss / (1024.0 ** 2)


def report(results: List[Result]) -> None:
    print()
    print("=" * 72)
    for res in results:
        print(f"\n{res.name}")
        if res.skipped:
            print(f"  saltata: {res.skipped}")
            continue
        if res.positives:
            print(f"  rilevamenti      {res.hits}/{res.positives} "
                  f"({100 * res.hits / res.positives:.0f}%)")
        if res.negative_seconds:
            per_hour = res.false_triggers / (res.negative_seconds / 3600.0)
            print(f"  falsi trigger    {res.false_triggers} in "
                  f"{res.negative_seconds / 60:.1f} min  ->  {per_hour:.1f}/ora")
        print(f"  RTF              {res.rtf:.3f}  "
              f"({res.compute_seconds:.1f}s di calcolo su "
              f"{res.audio_seconds:.1f}s di audio)")
    print(f"\nRAM di picco del processo: {peak_rss_mib():.0f} MiB")
    print("=" * 72)


SWEEP_POINTS = (0.65, 0.70, 0.75, 0.80, 0.85, 0.90, 0.95)


def _events(joined: str, phrase: str, threshold: float) -> int:
    """How many separate times a candidate stream would have fired.

    A detection rate counts *clips*, but a false-trigger rate counts
    **events** — the summary above counts every fire, and a negative long
    enough to fire twice has annoyed the household twice. Counting matching
    candidates instead of matching files is what makes the two comparable;
    they were not, and grammar mode showed 14 in the summary against 8 here
    for the same audio.

    Every matching candidate counts, including consecutive ones: the live
    loop rebuilds the recognizer the moment it fires, so two matches in a row
    are two separate utterances rather than one seen twice. At the threshold
    the run was recorded with, this reproduces the summary's count exactly.

    Away from that threshold it is an approximation, and deliberately a
    pessimistic one. A looser setting can match several partials of one
    utterance as it grows ("vi", "viva", "vivavoce") where the live detector
    would have fired once and reset; that inflates the count. Over-reporting
    false triggers is the safe direction for the number this tool exists to
    protect — an engine is never adopted because the sweep flattered it.
    """
    return sum(1 for text in joined.split(" | ")
               if phrase_in(text, phrase, threshold))


def sweep_report(results: List[Result], phrase: str) -> List[dict]:
    """Detection rate against false triggers per hour, across --fuzzy.

    A single threshold is a single point on a curve, and the point that looks
    best on one corpus is rarely the one to ship. The decoding already
    happened, so every extra threshold here costs a string comparison: what
    the model heard is in ``Result.samples`` and only the *matching* changes.

    Configurations whose threshold lives inside the engine (KWS scoring, and
    Vosk's grammar mode, which has no fuzzy step at all) have nothing to
    sweep and are listed as such rather than silently shown flat.
    """
    rows = []
    print("\n" + "=" * 72)
    print(f"soglia --fuzzy: rilevamenti / falsi trigger, frase «{phrase}»")
    print("(un positivo conta una volta; un negativo conta ogni innesco, "
          "come il riepilogo qui sopra)")
    for res in results:
        if res.skipped or not res.samples:
            note = res.skipped or "nessuna trascrizione (soglia interna al motore)"
            print(f"\n{res.name}\n  non applicabile: {note}")
            continue
        pos = [s for s in res.samples if s[0] == "pos"]
        neg = [s for s in res.samples if s[0] == "neg"]
        neg_hours = sum(s[3] for s in neg) / 3600.0
        print(f"\n{res.name}")
        print("  soglia   rilevamenti      falsi trigger")
        for th in SWEEP_POINTS:
            hits = sum(1 for s in pos
                       if any(phrase_in(t, phrase, th) for t in s[2].split(" | ")))
            fires = sum(_events(s[2], phrase, th) for s in neg)
            rate = (100.0 * hits / len(pos)) if pos else 0.0
            per_hour = (fires / neg_hours) if neg_hours else None
            tail = f"{fires:3d}  ({per_hour:.1f}/ora)" if per_hour is not None \
                else f"{fires:3d}  (nessun negativo)"
            print(f"   {th:.2f}    {hits:3d}/{len(pos):-3d} ({rate:3.0f}%)     {tail}")
            rows.append({"config": res.name, "fuzzy": th, "hits": hits,
                         "positives": len(pos), "false_trigger_events": fires,
                         "false_triggers_per_hour": per_hour})
    print("=" * 72)
    return rows


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(
        description="Misura sherpa-onnx come motore di parola chiave / ASR.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__)
    ap.add_argument("--phrase", required=True,
                    help="la frase di attivazione da misurare, es. 'vivavoce'")
    ap.add_argument("--positives", required=True,
                    help="cartella (o file) WAV che contengono la frase")
    ap.add_argument("--negatives",
                    help="cartella (o file) WAV che NON devono mai innescarla — "
                         "includi almeno un brano dell'impianto a volume normale")
    ap.add_argument("--config", default="all",
                    choices=["all", "A", "B", "C", "D", "D1", "D2"],
                    help="quale configurazione misurare (default: tutte). "
                         "D = D1 + D2")
    ap.add_argument("--models-dir",
                    default=os.path.join(REPO_ROOT, ".sherpa-models"),
                    help="dove scaricare i modelli (default: .sherpa-models/)")
    ap.add_argument("--threads", type=int, default=4,
                    help="thread di inferenza (default: 4, come un Pi 5)")
    ap.add_argument("--threshold", type=float, default=0.25,
                    help="soglia di attivazione del KWS (default: 0.25)")
    ap.add_argument("--boost", type=float, default=1.5,
                    help="boost score del KWS: alza i rilevamenti e i falsi "
                         "positivi insieme (default: 1.5)")
    ap.add_argument("--keyword-tokens",
                    help="token del KWS scritti a mano (es. '▁VI VA VO CE'), "
                         "invece di derivarli dalla frase")
    ap.add_argument("--vad-threshold", type=float, default=0.5,
                    help="soglia del silero VAD (default: 0.5)")
    ap.add_argument("--fuzzy", type=float, default=0.8,
                    help="somiglianza minima frase/trascrizione (default: 0.8)")
    ap.add_argument("--lang", default="it",
                    help="lingua per faster-whisper e Vosk (C/D, default: it)")
    ap.add_argument("--vosk-model",
                    help="cartella di un modello Vosk gia' scompattato, "
                         "invece di scaricare quello piccolo per --lang")
    ap.add_argument("--whisper-model", default="small",
                    help="modello faster-whisper per il confronto (default: small)")
    ap.add_argument("--fuzzy-sweep", action="store_true",
                    help="stampa la curva rilevamenti/falsi trigger al variare "
                         "di --fuzzy, invece del singolo punto (gratis: usa "
                         "le trascrizioni gia' fatte)")
    ap.add_argument("--json", help="scrive i risultati anche in questo file")
    ap.add_argument("-v", "--verbose", action="store_true",
                    help="stampa ogni file, con la trascrizione")
    args = ap.parse_args(argv)

    positives = wav_files(args.positives)
    negatives = wav_files(args.negatives) if args.negatives else []
    print(f"{len(positives)} registrazioni positive, "
          f"{len(negatives)} negative, frase «{args.phrase}»")
    if not negatives:
        print("ATTENZIONE: senza --negatives non si misurano i falsi trigger, "
              "che sono il rischio principale di un microfono acceso vicino a "
              "un impianto hi-fi.")

    runners = {"A": run_kws, "B": run_vad_asr, "C": run_faster_whisper,
               "D1": run_vosk_grammar, "D2": run_vosk_free}
    if args.config == "all":
        chosen = list(runners)
    elif args.config == "D":
        chosen = ["D1", "D2"]
    else:
        chosen = [args.config]
    results = []
    for key in chosen:
        print(f"\n--- configurazione {key} ---")
        results.append(runners[key](args, args.models_dir, positives, negatives))

    report(results)
    sweep = sweep_report(results, args.phrase) if args.fuzzy_sweep else None
    if args.json:
        payload: Dict[str, object] = {
            "phrase": args.phrase,
            "configs": [r.as_dict() for r in results],
        }
        if sweep is not None:
            payload["fuzzy_sweep"] = sweep
        with open(args.json, "w", encoding="utf-8") as fh:
            json.dump(payload, fh, indent=2, ensure_ascii=False)
        print(f"risultati in {args.json}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
