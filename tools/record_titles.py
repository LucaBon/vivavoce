#!/usr/bin/env python3
"""Registra le frasi di prova per ``tools/asr_titles_bench.py``.

Perché esiste: il corpus sintetico del banco ha un tetto di realismo, e lo si
tocca prima di quanto sembri. Sintetizzare la cornice («metti») separata dal
titolo per simulare il code-switching produce un «metti» isolato di tre decimi
di secondo che Whisper trascrive «Matti» — e il banco finisce per misurare la
concatenazione invece del modello. Sintetizzare tutta la frase con una voce
italiana evita l'artefatto ma legge l'inglese a pronuncia ortografica, che è
l'estremo opposto. In mezzo c'è una persona, e va registrata.

Quel che il sintetico non può dare, e che questo raccoglie: la distanza dal
microfono, il riverbero della stanza, e l'impianto acceso sotto. È lo stesso
limite che ``tools/make_wake_corpus.py`` dichiara per la parola chiave — «the
negatives that decide the product can only be captured, never generated» — e
vale identico qui.

    python tools/record_titles.py --out ~/vivavoce-clip

Poi:

    python tools/asr_titles_bench.py --clips ~/vivavoce-clip \\
        --models small,medium,large-v3-turbo

Le frasi, il manifest e i nomi dei file sono gli stessi che il banco genera con
``--synth``, così le due misure si confrontano riga per riga.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
import wave

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO_ROOT, "tools"))

from asr_titles_bench import SENTENCES  # noqa: E402

SAMPLE_RATE = 16000

# Sotto questo RMS nessuno ha parlato: microfono spento, muto, o su un altro
# ingresso. Un banco che scorre queste come «il modello non ha capito» dà la
# colpa al modello per un cavo.
#
# 1000 e non un valore prudente tipo 120: misurato: due secondi di sola stanza
# su questo portatile danno RMS 717 e picco 3494, quindi una soglia bassa
# promuove il silenzio a clip valida — che è il difetto esatto che questa
# costante dovrebbe impedire. Il parlato a distanza di conversazione sta molto
# sopra. Se il tuo microfono ha un guadagno diverso, il verdetto stampa RMS e
# picco a ogni clip: alza o abbassa di conseguenza.
MIN_RMS = 1000
# Quanta parte della clip può stare a fondo scala prima che sia un problema.
#
# NON un picco: il picco è il controllo ovvio ed è sbagliato, perché un solo
# campione a -32768 condanna sei secondi di parlato perfetto. Misurato su
# dodici registrazioni vere: picco 32768 su tutte, fattore di cresta 3,4-5,5
# (il valore normale del parlato, non quello di un segnale schiacciato), fra
# lo 0,5% e il 2,2% di campioni al limite — e `small` le ha trascritte quasi
# tutte alla perfezione. Il primo controllo le bocciò tutte e dodici, e la
# risposta giusta a quel verdetto era ignorarlo.
#
# 3% è largo di proposito: questo guardiano esiste per intercettare un
# microfono col guadagno sbagliato, non per fare da fonometro. Quando scatta
# lo dice con la percentuale accanto, così chi legge può non credergli.
MAX_CLIPPED_FRACTION = 0.03
#: |campione| oltre il quale lo contiamo come "al limite".
CLIP_LEVEL = 32000


def level(path: str):
    """``(secondi, rms, picco, frazione_al_limite)`` di un WAV registrato."""
    import array
    import audioop
    with wave.open(path) as w:
        frames = w.readframes(w.getnframes())
        secs = w.getnframes() / float(w.getframerate() or 1)
    if not frames:
        return secs, 0, 0, 0.0
    samples = array.array("h")
    samples.frombytes(frames)
    clipped = sum(1 for v in samples if v >= CLIP_LEVEL or v <= -CLIP_LEVEL)
    return (secs, audioop.rms(frames, 2), audioop.max(frames, 2),
            clipped / float(len(samples) or 1))


def verdict(secs: float, rms: int, peak: int, clipped: float) -> str:
    if rms < MIN_RMS:
        return "MUTA — controlla il microfono, questa non vale"
    if clipped > MAX_CLIPPED_FRACTION:
        return (f"SATURA — {100*clipped:.1f}% dei campioni al limite, "
                f"abbassa il guadagno")
    if secs < 0.8:
        return "troppo corta"
    return "ok"


def record(path: str, seconds: int, device: str = "") -> bool:
    cmd = ["arecord", "-f", "S16_LE", "-r", str(SAMPLE_RATE), "-c", "1",
           "-d", str(seconds), "-q"]
    if device:
        cmd += ["-D", device]
    cmd.append(path)
    try:
        subprocess.run(cmd, check=True)
        return True
    except FileNotFoundError:
        print("arecord non c'è: installa alsa-utils.")
        return False
    except subprocess.CalledProcessError as exc:
        print(f"registrazione fallita ({exc.returncode}).")
        return False


def _tone(path: str, freq: float, ms: int, vol: float = 0.35) -> str:
    """Un bip, scritto una volta e riusato."""
    import math
    if os.path.exists(path):
        return path
    n = int(SAMPLE_RATE * ms / 1000)
    # Rampa di 5 ms in entrata e in uscita: un seno tagliato di netto fa un
    # click che il microfono raccoglie e che finisce nella clip successiva.
    ramp = int(SAMPLE_RATE * 0.005)
    frames = bytearray()
    for i in range(n):
        env = min(1.0, i / ramp, (n - i) / ramp)
        v = int(32767 * vol * env * math.sin(2 * math.pi * freq * i / SAMPLE_RATE))
        frames += int(v).to_bytes(2, "little", signed=True)
    with wave.open(path, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SAMPLE_RATE)
        w.writeframes(bytes(frames))
    return path


# I bip vanno dove suona il resto del computer, e sotto PipeWire non è dove
# finisce ``aplay``. ALSA grezzo apre la scheda 0, che su questo portatile è
# l'uscita HDMI del monitor: i bip esistono e non li sente nessuno, e chi sta
# registrando resta fermo ad aspettare un segnale che è già passato. ``paplay``
# e ``pw-play`` usano il sink predefinito — qui gli altoparlanti — che è la cosa
# che l'utente ha già scelto e che nessuno strumento dovrebbe scavalcare.
# ``aplay`` resta ultimo, per una macchina senza server audio.
_PLAYERS = (["paplay"], ["pw-play"], ["aplay", "-q"])


def _play(path: str) -> None:
    for player in _PLAYERS:
        try:
            r = subprocess.run(player + [path], check=False,
                               stdout=subprocess.DEVNULL,
                               stderr=subprocess.DEVNULL)
        except FileNotFoundError:
            continue
        if r.returncode == 0:
            return


def _say(text: str, cache_dir: str) -> None:
    """Annuncia con Piper, se c'è. È solo una comodità: senza, restano i bip."""
    path = os.path.join(cache_dir, "say-" + text.replace(" ", "_") + ".wav")
    if not os.path.exists(path):
        try:
            from piper import PiperVoice, SynthesisConfig
        except ImportError:
            return
        model = os.path.join(REPO_ROOT, ".piper-voices", "it_IT-paola-medium.onnx")
        if not os.path.exists(model):
            return
        voice = PiperVoice.load(model)
        frames = bytearray()
        for chunk in voice.synthesize(text, syn_config=SynthesisConfig()):
            frames += chunk.audio_int16_bytes
            rate = chunk.sample_rate
        with wave.open(path, "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(rate)
            w.writeframes(bytes(frames))
    _play(path)


def run_auto(args, todo, entries, known, manifest_path) -> None:
    """Registra tutta la lista senza chiedere niente.

    Serve perché il modo interattivo vuole un terminale vero: lanciato da dove
    lo stdin non è un tty (il `!` di Claude Code, una pipe, un hook) ``input()``
    prende EOF e la sessione muore alla prima frase, che è esattamente come è
    stata scoperta questa modalità. Qui le istruzioni sono **sonore**, perché
    l'unico canale che arriva comunque a chi sta parlando è l'altoparlante:
    annuncio, bip acuto = parla, doppio bip grave = ho chiuso.
    """
    tmp = os.path.join(args.out, ".tones")
    os.makedirs(tmp, exist_ok=True)
    # Il bip di via è lungo e acuto, quelli di chiusura corti e gravi: chi
    # registra sta dall'altra parte della stanza, ed è l'unico segnale che gli
    # arriva. 120 ms si perdono; 300 no. Che ``_play`` sia bloccante NON basta
    # a tenerlo fuori dalla clip — vedi la pausa più sotto, e il picco misurato
    # che l'ha fatta aggiungere.
    go = _tone(os.path.join(tmp, "go.wav"), 880, 300, vol=0.5)
    stop = _tone(os.path.join(tmp, "stop.wav"), 440, 110, vol=0.4)
    results = []
    for take in range(args.take, args.take + args.takes):
        for num, text, expect, _artist, kind, _foreign, _why in todo:
            name = f"{num}-{take}.wav"
            path = os.path.join(args.out, name)
            print(f"\n[{num} · presa {take}] «{text}»", flush=True)
            _say(f"frase {int(num)}", tmp)
            _play(go)
            # Il bip finisce nell'altoparlante DOPO che paplay è tornato: il
            # player consegna al sink, il sink ha la sua latenza, e senza
            # questa pausa la coda a 880 Hz entra nella clip — misurata, il
            # picco passava da 3300 (stanza) a 7675. Il VAD di Whisper la
            # scarterebbe quasi sempre, ma «quasi» non è una proprietà che si
            # vuole all'inizio di ogni registrazione del banco.
            time.sleep(0.3)
            if not record(path, args.seconds, args.device):
                return
            _play(stop)
            _play(stop)
            secs, rms, peak, clipped = level(path)
            v = verdict(secs, rms, peak, clipped)
            print(f"    {secs:.1f}s · RMS {rms} · picco {peak} · "
                  f"al limite {100*clipped:.1f}% → {v}", flush=True)
            results.append((num, name, v))
            if name not in known:
                entries.append({"file": name, "text": text, "expect": expect,
                                "kind": kind, "n": num})
                known.add(name)
            _save(manifest_path, entries)

    bad = [r for r in results if r[2] != "ok"]
    print(f"\n{len(results)} clip, {len(bad)} da rifare")
    for num, name, v in bad:
        print(f"  {num}  {name}: {v}")
    if bad:
        nums = ",".join(sorted({r[0] for r in bad}))
        print(f"\nrifai solo quelle:  --out {args.out} --auto --only {nums}")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--out", required=True, help="cartella di destinazione")
    ap.add_argument("--auto", action="store_true",
                    help="non chiede niente: annuncia a voce, bip, registra. "
                         "Da usare quando lo stdin non è un terminale.")
    ap.add_argument("--takes", type=int, default=1,
                    help="quante volte registrare l'intera lista (default 1). "
                         "Due prese in momenti diversi dicono quanto del "
                         "risultato è la frase e quanto è stata la giornata.")
    ap.add_argument("--take", type=int, default=1,
                    help="da quale numero di presa partire (default 1). "
                         "--take 2 registra NN-2.wav e lascia intatta la "
                         "prima presa, che è l'unico modo di confrontarle.")
    ap.add_argument("--seconds", type=int, default=6,
                    help="durata di ogni registrazione (default 6)")
    ap.add_argument("--device", default="", help="dispositivo ALSA (-D)")
    ap.add_argument("--only", default="",
                    help="solo questi numeri, es. 02,04,11")
    args = ap.parse_args()

    os.makedirs(args.out, exist_ok=True)
    wanted = {n.strip() for n in args.only.split(",") if n.strip()}
    todo = [s for s in SENTENCES if not wanted or s[0] in wanted]

    print(f"\n{len(todo)} frasi × {args.takes} pres{'e' if args.takes > 1 else 'a'}"
          f" → {args.out}")
    print("Dille come le diresti all'impianto, dal punto in cui parli davvero.")
    print("Per due o tre, lascia la musica accesa a volume normale: è la "
          "condizione che non si può simulare.\n")

    manifest_path = os.path.join(args.out, "manifest.json")
    entries = []
    if os.path.exists(manifest_path):
        with open(manifest_path, encoding="utf-8") as f:
            entries = json.load(f)
    known = {e["file"] for e in entries}

    if args.auto or not sys.stdin.isatty():
        if not args.auto:
            print("(stdin non è un terminale: passo in modalità --auto)\n")
        run_auto(args, todo, entries, known, manifest_path)
        return

    for take in range(args.take, args.take + args.takes):
        for num, text, expect, _artist, kind, _foreign, why in todo:
            name = f"{num}-{take}.wav"
            path = os.path.join(args.out, name)
            while True:
                print(f"\n[{num}/{len(SENTENCES)} · presa {take}]  «{text}»")
                print(f"         ({why})")
                try:
                    cmd = input("  Invio per registrare · [s] salta · [q] esci > ")
                except (EOFError, KeyboardInterrupt):
                    print("\ninterrotto.")
                    cmd = "q"
                if cmd.strip().lower() == "q":
                    _save(manifest_path, entries)
                    return
                if cmd.strip().lower() == "s":
                    break
                print(f"  registro {args.seconds}s… parla ora.")
                if not record(path, args.seconds, args.device):
                    return
                secs, rms, peak, clipped = level(path)
                v = verdict(secs, rms, peak, clipped)
                print(f"  {secs:.1f}s · RMS {rms} · picco {peak} · "
                      f"al limite {100*clipped:.1f}% → {v}")
                again = input("  [Invio] tieni · [r] rifai > ").strip().lower()
                if again == "r":
                    continue
                if name not in known:
                    entries.append({"file": name, "text": text,
                                    "expect": expect, "kind": kind, "n": num})
                    known.add(name)
                _save(manifest_path, entries)
                break

    _save(manifest_path, entries)
    print(f"\n{len(entries)} clip in {args.out}")
    print("Ora:  python tools/asr_titles_bench.py --clips "
          f"{args.out} --models small,medium,large-v3-turbo")


def _save(path: str, entries) -> None:
    # Riscritto dopo ogni clip, non alla fine: una sessione interrotta a metà
    # deve lasciare misurabile quel che è già stato detto.
    with open(path, "w", encoding="utf-8") as f:
        json.dump(entries, f, ensure_ascii=False, indent=2)


if __name__ == "__main__":
    main()
