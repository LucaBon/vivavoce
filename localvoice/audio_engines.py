"""Which optional audio engines this box actually has, and which one wins.

Lifted out of ``server.py``, which the wake-word engine choice pushed past
the 400-line ceiling the repo sets itself (see ``tests/test_packaging.py``).
The seam is real rather than arithmetic: everything here answers one question
— *given what is installed on this machine, what can the app hear?* — and all
of it shares the same shape. Each engine is optional, each is probed rather
than imported at start-up, each degrades to a working default instead of an
error, and each has to say so out loud, because an engine that quietly is not
running is the most expensive kind of silence in this app.

The imports of ``pro.*`` live inside :func:`build`, not at module scope, for
the same reason they do in ``server.py``: those modules are cheap to import
but the packages behind them are not, and nothing here should cost anything
on a box that never switches these features on.
"""

from __future__ import annotations

import os

import appdata


def build(args, data_dir: str, unavailable_note: str = ""):
    """Construct the optional engines and report them.

    Returns ``(transcriber, wakeword_sessions, wake_phrase_store)``. Any of
    the first two may be ``None`` or an unavailable engine — every caller
    downstream already treats that as a normal answer.
    """
    # Riconoscimento vocale locale (Pro): il modello si carica solo al primo
    # /transcribe; i modelli finiscono nella cartella dati (in Docker: il
    # volume persistente), non nell'immagine. Il default è RAM-aware: sotto
    # ~4 GB resta spento (tiny/base storpiano i titoli inglesi, small non ci
    # sta) a meno che --asr-model non lo forzi esplicitamente.
    from pro.asr import (WhisperTranscriber, default_model, total_ram_gib)
    asr_model = args.asr_model or default_model()
    transcriber = None
    if not WhisperTranscriber().available():
        print("Riconoscimento vocale locale non installato: il microfono usa "
              "il riconoscimento del browser. Per attivarlo: uv sync --group asr"
              + unavailable_note)
    elif asr_model:
        transcriber = WhisperTranscriber(
            asr_model, cache_dir=os.path.join(data_dir, "asr-models"))
        print(f"Riconoscimento vocale locale attivo (faster-whisper, modello "
              f"{asr_model}): l'audio del microfono resta in casa.")
    else:
        print(f"Riconoscimento vocale locale spento: questa macchina ha "
              f"~{total_ram_gib():.1f} GiB di RAM — il modello 'small' vuole "
              "~1 GB al picco e quelli più piccoli storpiano i titoli "
              "inglesi. Per forzarlo comunque: --asr-model tiny "
              "(o VIVAVOCE_ASR_MODEL).")

    # Parola chiave lato server (Pro): elimina il beep Android dell'ascolto
    # continuo del browser. Gruppi opzionali SEPARATI da "asr" e fra loro
    # (vedi pro/wakeword.py: openwakeword>=0.5 rompe su Python 3.12+ per una
    # dipendenza rigida da tflite-runtime).
    #
    # Two engines can fill this slot, and they are NOT equivalent: Vosk hears
    # the phrase the household actually typed, openWakeWord only the English
    # phrase it ships a model for. So Vosk wins whenever it is installed and
    # has a model on disk, and openWakeWord stays as the fallback for boxes
    # that already have it. Both expose the same available()/get_or_create()/
    # stop() surface, which is why audio_api.py needs to know nothing here.
    from pro.wakeword import DEFAULT_MODEL as WAKEWORD_DEFAULT_MODEL
    from pro.wakeword import ServerWakeWordSessions
    from pro.vosk_wake import ServerVoskWakeSessions
    from pro.vosk_wake import available as vosk_available
    from pro.vosk_wake import models_dir as vosk_models_dir

    wake_phrase_store = appdata.WakePhraseStore(data_dir)
    vosk_sessions = ServerVoskWakeSessions(
        lang=args.wakeword_lang, data_dir=data_dir,
        phrase=wake_phrase_store.get(),
        explicit_model=args.wakeword_vosk_model)
    wakeword_model = args.wakeword_model or WAKEWORD_DEFAULT_MODEL

    if vosk_sessions.available():
        wakeword_sessions = vosk_sessions
        print(f"Parola chiave lato server attiva (Vosk "
              f"{args.wakeword_lang}, frase «{wake_phrase_store.get()}»): "
              f"nessun beep, e la frase è quella scelta in casa.")
    else:
        wakeword_sessions = ServerWakeWordSessions(wakeword_model)
        if vosk_available() and not vosk_sessions.model_dir:
            # The package is there but the model is not, which is the one
            # degraded state worth naming: it is a download away, and the
            # alternative silently listens for a different phrase in another
            # language. Not fetched automatically — 50 MB inside the first
            # 320 ms audio chunk would time the request out and read as a
            # broken engine.
            print(f"Parola chiave libera lato server non attiva: manca il "
                  f"modello Vosk per «{args.wakeword_lang}». Scaricalo in "
                  f"{vosk_models_dir(data_dir)} (o indicane uno con "
                  f"--wakeword-vosk-model).")
        if not wakeword_sessions.available():
            print("Parola chiave lato server non installata: l'ascolto "
                  "continuo usa il riconoscimento del browser (col beep su "
                  "Android). Per attivarla: uv sync --group wakeword-vosk"
                  + unavailable_note)
        else:
            print(f"Parola chiave lato server attiva (openWakeWord, modello "
                  f"{wakeword_model}): nessun beep durante l'ascolto "
                  f"continuo, ma la frase è fissa e in inglese.")
    return transcriber, wakeword_sessions, wake_phrase_store
