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
    # continuo del browser, e sente la frase che la casa ha scritto. Gruppo
    # opzionale SEPARATO da "asr", perché un motore opzionale che non si
    # installa non deve portarsi dietro quello che già funziona.
    #
    # Un motore solo, ora. openWakeWord stava qui come ripiego e se n'è
    # andato: sentiva unicamente le poche frasi inglesi per cui spedisce un
    # modello, e quei modelli sono CC-BY-NC-SA dietro un livello a pagamento.
    # Dove vosk non si installa (macOS: nessun wheel) non resta un ripiego che
    # ascolta un'altra frase in un'altra lingua — resta il motore del browser,
    # che su quelle macchine non ha nemmeno il beep che questa funzione esiste
    # per togliere.
    from pro.vosk_wake import ServerVoskWakeSessions
    from pro.vosk_wake import available as vosk_available
    from pro.vosk_wake import models_dir as vosk_models_dir
    from pro.vosk_wake import resolve_model as vosk_resolve_model
    from pro.vosk_wake import wheels_unavailable_here

    wake_phrase_store = appdata.WakePhraseStore(data_dir)
    # Fetched here, before the server accepts anything, and only when the
    # package is installed and the model is genuinely absent — see
    # pro/vosk_model.py for why this cannot be lazy like the Whisper one.
    # Never for an explicit --wakeword-vosk-model: that names a directory the
    # administrator manages, and downloading over it would be answering a
    # question nobody asked.
    if (vosk_available() and not args.wakeword_no_download
            and not args.wakeword_vosk_model
            and not vosk_resolve_model(args.wakeword_lang, data_dir)):
        from pro.vosk_model import ensure_model
        ensure_model(args.wakeword_lang, data_dir)

    wakeword_sessions = ServerVoskWakeSessions(
        lang=args.wakeword_lang, data_dir=data_dir,
        phrase=wake_phrase_store.get(),
        explicit_model=args.wakeword_vosk_model)

    if wakeword_sessions.available():
        print(f"Parola chiave lato server attiva (Vosk "
              f"{args.wakeword_lang}, frase «{wake_phrase_store.get()}»): "
              f"nessun beep, e la frase è quella scelta in casa.")
    elif vosk_available():
        # Il pacchetto c'è ma il modello no: è a un download di distanza, e
        # dirlo con il percorso esatto è tutta la differenza fra «si sistema»
        # e «non funziona».
        print(f"Parola chiave lato server non attiva: manca il modello Vosk "
              f"per «{args.wakeword_lang}» in {vosk_models_dir(data_dir)} "
              f"(indicane uno con --wakeword-vosk-model, o togli "
              f"--wakeword-no-download per scaricarlo all'avvio).")
    else:
        # NON `unavailable_note`: quella parla per i gruppi che poggiano su
        # onnxruntime, e vosk spedisce un wheel armv7l. Su un Pi a 32 bit —
        # la macchina per cui quella nota esiste — questo gruppo è l'unico
        # motore opzionale che si installa.
        print("Parola chiave lato server non installata: l'ascolto continuo "
              "usa il riconoscimento del browser (col beep su Android). "
              "Per attivarla: uv sync --group wakeword-vosk"
              + wheels_unavailable_here())

    return transcriber, wakeword_sessions, wake_phrase_store
