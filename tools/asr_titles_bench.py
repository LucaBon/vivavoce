#!/usr/bin/env python3
"""Quanto un modello Whisper recupera i titoli stranieri detti in italiano.

Il problema, già misurato una volta in questo repo: `pro/asr.py:27-34` racconta
che con `tiny` e `base` i comandi in puro italiano vengono bene e i titoli
inglesi si storpiano («Comfortably Numb» → «fatta blina»), e per questo il
default è salito a `small`. Questo banco misura i gradini successivi, e serve a
decidere due cose diverse:

* **quale modello**, con il costo accanto — la qualità da sola non decide
  niente se la decodifica non sta dentro un comando vocale;
* **quanto residuo resta al matching**, che è ciò che dimensiona uno strato
  fonetico in `engine/matching.py`.

Due sorgenti di audio, e la differenza fra loro è metà del risultato.

``--synth``  genera il corpus con Piper, come ``tools/make_wake_corpus.py``, e
             con lo stesso caveat scritto lì: *non sostituisce le registrazioni
             della stanza*. La cornice la dice una voce italiana, titolo e
             artista una voce inglese — è code-switching simulato, non una
             persona. Serve ad avere un metro ripetibile, non un numero da
             citare.
``--clips``  legge una cartella di registrazioni vere più un manifest. È
             l'unica misura che vale per il README: distanza, riverbero e
             l'impianto acceso sotto non si generano.

La metrica non è «la trascrizione è giusta» ma **«il prodotto troverebbe il
brano»**, e si misura con le funzioni vere:

* la frase viene instradata con le regex di ``localvoice/lang/it.py`` — le
  stesse del router — così «la cornice ha retto?» è la domanda che si pone il
  prodotto. Una cornice rotta («METTIF wonder wall») non è un titolo sbagliato:
  è un turno che non arriva nemmeno alla ricerca, e nessuno strato di matching
  lo salva. Contarli insieme gonfia il lavoro che il matching potrebbe fare;
* quel che resta si confronta con ``matching._score``, la funzione che decide
  davvero, e si classifica nelle bande che il codice già usa
  (``NEAR_ARTIST_SCORE`` 0.5, ``CONFIDENT_SCORE`` 0.72).

Piper e faster-whisper sono strumenti di sviluppo, mai dipendenze runtime.

    # genera le clip sintetiche e misura tre modelli
    python tools/asr_titles_bench.py --synth /tmp/corpus \\
        --models small,medium,large-v3-turbo

    # misura registrazioni vere (serve <cartella>/manifest.json)
    python tools/asr_titles_bench.py --clips ~/registrazioni \\
        --models small,large-v3-turbo
"""

from __future__ import annotations

import argparse
import json
import os
import re
import statistics
import sys
import time
import wave
from typing import Dict, List, Optional

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for _sub in ("engine", "localvoice", "tools"):
    sys.path.insert(0, os.path.join(REPO_ROOT, _sub))

import matching  # noqa: E402
from lang import PACKS  # noqa: E402
from parsing import clean_command  # noqa: E402

SAMPLE_RATE = 16000
VOICES_DIR = os.path.join(REPO_ROOT, ".piper-voices")

# Voci italiane per la cornice, inglesi per i nomi propri. Più di una per
# parte: un banco su una voce sola misura quella voce, che è la ragione per cui
# make_wake_corpus.py genera invece di far leggere una persona.
IT_VOICES = ["it_IT-paola-medium", "it_IT-serena-medium",
             "it_IT-riccardo-x_low", "it_IT-serena-high"]
EN_VOICES = ["en_US-amy-medium", "en_US-ryan-medium",
             "en_US-kristin-medium", "en_US-joe-medium"]

#: Le dodici frasi, scelte per coprire i modi di rompersi che il primo giro ha
#: fatto emergere — non per essere rappresentative di quanto si dice in casa.
#: ``kind`` sceglie la regex del router con cui va instradata; ``foreign`` dice
#: se i nomi propri vanno letti da una voce inglese (per la sintesi) ed è falso
#: per i due controlli italiani, che sono il modo di distinguere «l'inglese è
#: difficile» da «il microfono è messo male».
SENTENCES = [
    ("01", "metti Comfortably Numb dei Pink Floyd",
     "Comfortably Numb", "Pink Floyd", "song", True,
     "il caso canonico, già citato in pro/asr.py"),
    ("02", "metti Creep dei Radiohead",
     "Creep", "Radiohead", "song", True,
     "titolo corto: il peggiore del giro sintetico su tutti i modelli"),
    ("03", "metti Wish You Were Here dei Pink Floyd",
     "Wish You Were Here", "Pink Floyd", "song", True,
     "titolo che l'italiano sente come frase italiana («siamo qui»)"),
    ("04", "metti Wonderwall degli Oasis",
     "Wonderwall", "Oasis", "song", True,
     "parola composta: esce spezzata in «wonder wall»"),
    ("05", "metti Shine On You Crazy Diamond dei Pink Floyd",
     "Shine On You Crazy Diamond", "Pink Floyd", "song", True,
     "titolo lungo: più superficie per sbagliare"),
    ("06", "metti Bohemian Rhapsody",
     "Bohemian Rhapsody", "", "song", True,
     "senza artista: isola il titolo dalla coda"),
    ("07", "metti i Red Hot Chili Peppers",
     "Red Hot Chili Peppers", "", "song", True,
     "solo artista, nella forma in cui la gente lo chiede"),
    ("08", "metti l'album The Dark Side of the Moon",
     "The Dark Side of the Moon", "", "album", True,
     "cornice «album» + titolo lungo"),
    ("09", "riproduci Hotel California degli Eagles",
     "Hotel California", "Eagles", "song", True,
     "verbo diverso da «metti»: la cornice non regge solo su quello"),
    ("10", "metti Bollicine di Vasco Rossi",
     "Bollicine", "Vasco Rossi", "song", False,
     "CONTROLLO italiano: se sbaglia questa, il problema non è l'inglese"),
    ("11", "metti La Cura di Franco Battiato",
     "La Cura", "Franco Battiato", "song", False,
     "secondo controllo italiano, titolo fatto di parole comuni"),
    ("12", "metti Björk",
     "Björk", "", "song", True,
     "diacritico non italiano: matching.py lo piega già a 1.00"),
]


# -- instradamento: le regex vere, non le mie ---------------------------------

_IT = PACKS["it"].PATTERNS
# La coda dell'artista. Approssimata di proposito: l'artista arriva storpiato
# quanto il titolo, quindi non lo si può agganciare per nome. Vale lo stesso
# taglio per tutti i modelli, ed è questo a rendere il confronto onesto anche
# se il singolo valore assoluto non lo è.
_ARTIST_TAIL = re.compile(
    r"\s+(?:dei|degli|delle|della|del|dell|di|d|the|le|lei|la)\b.*$", re.I)
_LEAD_ARTICLE = re.compile(r"^(?:i|gli|le|la|il|lo|l['’])\s+", re.I)


def route(transcript: str, kind: str):
    """``(frame_ok, query)`` — quel che il router estrarrebbe da questa frase.

    ``frame_ok`` falso significa che nessuna regex di play ha agganciato: il
    turno morirebbe come «non ho capito», e non c'è titolo da recuperare. È la
    distinzione che il punteggio da solo non fa, e senza la quale si attribuisce
    al matching un lavoro che non gli arriva mai.
    """
    text = clean_command(transcript or "")
    pattern = _IT["album"] if kind == "album" else _IT["generic_play"]
    m = pattern.search(text)
    if not m:
        return False, ""
    query = (m.group(1) or "").strip()
    if kind != "album":
        query = _ARTIST_TAIL.sub("", query).strip()
    return True, _LEAD_ARTICLE.sub("", query).strip()


def band(score: float) -> str:
    if score >= 0.999:
        return "perfetto"
    if score >= matching.CONFIDENT_SCORE:
        return "confident"
    if score >= matching.NEAR_ARTIST_SCORE:
        return "dubbio"
    return "perso"


# -- sintesi ------------------------------------------------------------------

def _load_voice(name: str):
    from piper import PiperVoice
    path = os.path.join(VOICES_DIR, name + ".onnx")
    if not os.path.exists(path):
        from pathlib import Path

        from piper.download_voices import download_voice
        os.makedirs(VOICES_DIR, exist_ok=True)
        download_voice(name, Path(VOICES_DIR))
    return PiperVoice.load(path)


def _synth(voice, text: str):
    import numpy as np
    from piper import SynthesisConfig
    cfg = SynthesisConfig(length_scale=1.0, speaker_id=None,
                          noise_scale=0.667, noise_w_scale=0.8)
    pieces, rate = [], SAMPLE_RATE
    for chunk in voice.synthesize(text, syn_config=cfg):
        rate = chunk.sample_rate
        pieces.append(np.frombuffer(chunk.audio_int16_bytes, dtype="<i2"))
    if not pieces:
        return [], rate
    return (np.concatenate(pieces).astype("float32") / 32768.0).tolist(), rate


def _to_16k(samples, rate):
    import sherpa_bench
    return (sherpa_bench.resample(samples, rate, SAMPLE_RATE)
            if rate != SAMPLE_RATE else samples)


def _write_wav(path: str, samples, rate: int) -> None:
    import sherpa_bench
    samples = _to_16k(samples, rate)
    part = path + ".part"
    with wave.open(part, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(SAMPLE_RATE)
        wf.writeframes(sherpa_bench.float_to_int16_bytes(samples))
    os.replace(part, path)


def synthesize(out_dir: str, takes: int) -> List[Dict]:
    """Le dodici frasi, ``takes`` volte ciascuna con voci diverse, più il
    manifest che le registrazioni vere useranno identico."""
    os.makedirs(out_dir, exist_ok=True)
    it_cache: Dict[str, object] = {}
    en_cache: Dict[str, object] = {}
    entries = []
    for t in range(takes):
        itname = IT_VOICES[t % len(IT_VOICES)]
        enname = EN_VOICES[t % len(EN_VOICES)]
        for num, text, expect, artist, kind, foreign, _why in SENTENCES:
            name = f"{num}-{t + 1}.wav"
            path = os.path.join(out_dir, name)
            if not os.path.exists(path):
                it_voice = it_cache.setdefault(itname, None) or _load_voice(itname)
                it_cache[itname] = it_voice
                if foreign:
                    en_voice = en_cache.setdefault(enname, None) or _load_voice(enname)
                    en_cache[enname] = en_voice
                    # Cornice italiana, nomi propri inglesi, concatenati con
                    # una pausa breve. Non è una persona che fa code-switching,
                    # è la sua imitazione più economica.
                    gap = [0.0] * int(0.06 * SAMPLE_RATE)
                    head, tail = text.split(expect, 1) if expect in text else (text, "")
                    parts = []
                    for voice, chunk in ((it_voice, head.strip()),
                                         (en_voice, expect),
                                         (it_voice, tail.strip().split(" ")[0]
                                          if tail.strip() else ""),
                                         (en_voice, artist)):
                        if not chunk:
                            continue
                        sm, rt = _synth(voice, chunk)
                        if sm:
                            parts.append(_to_16k(sm, rt))
                    samples = []
                    for k, part in enumerate(parts):
                        if k:
                            samples += gap
                        samples += list(part)
                    rate = SAMPLE_RATE
                else:
                    samples, rate = _synth(it_voice, text)
                if not samples:
                    continue
                _write_wav(path, samples, rate)
            entries.append({"file": name, "text": text, "expect": expect,
                            "kind": kind, "n": num})
    manifest = os.path.join(out_dir, "manifest.json")
    with open(manifest, "w", encoding="utf-8") as f:
        json.dump(entries, f, ensure_ascii=False, indent=2)
    return entries


# -- lettura di una cartella di registrazioni ---------------------------------

def load_clips(clips_dir: str, manifest_path: Optional[str]) -> List[Dict]:
    """Il manifest, più il controllo che ogni file esista davvero.

    Un manifest che nomina clip mancanti è il modo silenzioso in cui un banco
    misura metà corpus e riporta una percentuale sull'altra metà, quindi qui
    è un errore e non un avviso.
    """
    manifest_path = manifest_path or os.path.join(clips_dir, "manifest.json")
    if not os.path.exists(manifest_path):
        raise SystemExit(
            f"manca {manifest_path}. Genera le clip sintetiche una volta con "
            f"--synth per avere il manifest, poi sostituisci i .wav con le "
            f"registrazioni vere tenendo gli stessi nomi.")
    with open(manifest_path, encoding="utf-8") as f:
        entries = json.load(f)
    missing = [e["file"] for e in entries
               if not os.path.exists(os.path.join(clips_dir, e["file"]))]
    if missing:
        raise SystemExit(f"il manifest nomina clip che non ci sono: {missing}")
    return entries


# -- misura -------------------------------------------------------------------

def measure(clips_dir: str, entries: List[Dict], model_name: str,
            cache_dir: str) -> Dict:
    from faster_whisper import WhisperModel
    t0 = time.time()
    model = WhisperModel(model_name, device="cpu", compute_type="int8",
                         download_root=cache_dir)
    load_s = time.time() - t0
    rows, decode_s = [], 0.0
    for e in entries:
        t1 = time.time()
        segments, _info = model.transcribe(
            os.path.join(clips_dir, e["file"]), language="it", beam_size=5,
            vad_filter=True)
        heard_raw = " ".join(s.text.strip() for s in segments).strip()
        decode_s += time.time() - t1
        frame_ok, query = route(heard_raw, e.get("kind", "song"))
        score = matching._score(query, e["expect"], subset_floor=False)
        rows.append({"n": e.get("n", e["file"]), "file": e["file"],
                     "expect": e["expect"], "heard_raw": heard_raw,
                     "query": query, "frame_ok": frame_ok, "score": score,
                     "band": band(score)})
    return {"model": model_name, "rows": rows, "load_s": load_s,
            "decode_s": decode_s}


def report(res: Dict) -> None:
    rows = res["rows"]
    n = len(rows)
    scores = [r["score"] for r in rows]
    broken = [r for r in rows if not r["frame_ok"]]
    bands: Dict[str, int] = {}
    for r in rows:
        bands[r["band"]] = bands.get(r["band"], 0) + 1
    print(f"\n=== {res['model']} — {n} clip ===")
    print(f"caricamento {res['load_s']:5.1f}s · decodifica {res['decode_s']:6.1f}s"
          f" · {res['decode_s']/max(1, n):5.2f}s per clip")
    print(f"punteggio medio {statistics.mean(scores):.3f} · "
          f"mediano {statistics.median(scores):.3f}")
    for b in ("perfetto", "confident", "dubbio", "perso"):
        k = bands.get(b, 0)
        print(f"  {b:10s} {k:3d}  {100*k/n:5.1f}%")
    print(f"  cornice rotta {len(broken):3d}  {100*len(broken)/n:5.1f}%"
          f"   (il router non instrada: nessun matching può salvarli)")
    recoverable = [r for r in rows
                   if r["frame_ok"] and r["band"] in ("dubbio", "perso")]
    print(f"  recuperabili  {len(recoverable):3d}  {100*len(recoverable)/n:5.1f}%"
          f"   (cornice ok, titolo sotto soglia: è qui che agirebbe la fonetica)")
    print("  peggiori:")
    for r in sorted(rows, key=lambda r: r["score"])[:8]:
        flag = "" if r["frame_ok"] else "  [cornice rotta]"
        print(f"    {r['score']:.3f}  {r['expect']!r} ← {r['query']!r}{flag}")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--clips", help="cartella di registrazioni + manifest.json")
    ap.add_argument("--manifest", help="manifest alternativo")
    ap.add_argument("--synth", metavar="DIR",
                    help="genera il corpus sintetico in DIR e misura quello")
    ap.add_argument("--takes", type=int, default=4,
                    help="quante voci diverse per frase con --synth (default 4)")
    ap.add_argument("--models", default="small")
    ap.add_argument("--cache", default=os.path.join(REPO_ROOT, ".sherpa-models",
                                                    "whisper"))
    ap.add_argument("--json", help="scrive tutte le righe in questo file")
    args = ap.parse_args()

    if not args.clips and not args.synth:
        ap.error("serve --clips <cartella> oppure --synth <cartella>")

    if args.synth:
        print(f"genero {len(SENTENCES)} frasi × {args.takes} voci in {args.synth}…",
              flush=True)
        entries = synthesize(args.synth, args.takes)
        clips_dir = args.synth
        print(f"{len(entries)} clip (SINTETICHE: un metro ripetibile, non un "
              f"numero da citare)")
    else:
        clips_dir = args.clips
        entries = load_clips(clips_dir, args.manifest)
        print(f"{len(entries)} registrazioni da {clips_dir}")

    results = []
    for name in [m.strip() for m in args.models.split(",") if m.strip()]:
        print(f"\ntrascrivo con {name}…", flush=True)
        res = measure(clips_dir, entries, name, args.cache)
        report(res)
        results.append(res)

    if len(results) > 1:
        base = results[0]
        bm = statistics.mean(r["score"] for r in base["rows"])
        print("\n=== confronto ===")
        for res in results[1:]:
            m = statistics.mean(r["score"] for r in res["rows"])
            print(f"{base['model']} → {res['model']}: {bm:.3f} → {m:.3f} "
                  f"({m - bm:+.3f}), decodifica "
                  f"×{res['decode_s']/max(0.01, base['decode_s']):.1f}")

    if args.json:
        with open(args.json, "w", encoding="utf-8") as f:
            json.dump(results, f, ensure_ascii=False, indent=2)
        print(f"\nrighe complete in {args.json}")


if __name__ == "__main__":
    main()
