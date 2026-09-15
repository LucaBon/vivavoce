"""Every option the server takes, and its environment twin.

Split out of ``server.py`` for the reason the 400-line rule exists: what the
command line OFFERS and what the server DOES with it are two subjects, and the
first one is a list. Docker and the Home Assistant add-on configure through the
environment (``PREFIX_LMS``, ``PREFIX_PORT``, ...); the command line wins when
both are present, which is what every ``default=appdata.env(...)`` below says.
"""

from __future__ import annotations

import argparse

import appdata
from player import registry as player_registry


def build_parser() -> argparse.ArgumentParser:
    """The parser ``server.main`` fills in."""
    ap = argparse.ArgumentParser(description="Server vocale locale per LMS/Daphile.")
    ap.add_argument("--lms", default=appdata.env("LMS"),
                    help="es. http://192.168.1.50:9000 "
                         "(auto-rilevato sulla rete se omesso)")
    ap.add_argument("--player", default=appdata.env("PLAYER"),
                    help="MAC del player; default: il primo trovato")
    ap.add_argument("--backend", default=appdata.env("BACKEND", "lms"),
                    help="quale sistema musicale pilotare: "
                         + ", ".join(sorted(player_registry.BACKENDS))
                         + " (default: lms). Con un backend diverso da lms "
                           "servono --backend-url e, dove previsto, "
                           "--backend-token.")
    ap.add_argument("--backend-url", default=appdata.env("BACKEND_URL"),
                    help="indirizzo del backend quando non e' un LMS, es. "
                         "http://192.168.1.50:8095 per Music Assistant. "
                         "Per lms usa --lms, che resta il nome documentato.")
    ap.add_argument("--backend-token", default=appdata.env("BACKEND_TOKEN"),
                    help="token di accesso del backend, se ne vuole uno. "
                         "Music Assistant lo crea in Impostazioni -> Profilo.")
    ap.add_argument("--host", default="0.0.0.0")
    ap.add_argument("--port", type=int, default=int(appdata.env("PORT", "8730")))
    ap.add_argument("--cert", help="certificato TLS (per il mic da altri device)")
    ap.add_argument("--key", help="chiave TLS")
    ap.add_argument("--allowed-hosts", default=appdata.env("ALLOWED_HOSTS"),
                    help="nomi host extra accettati nell'header Host, separati "
                         "da virgola. Servono solo dietro un dominio pubblico: "
                         "IP, localhost e .local sono gi\u00e0 ok (webguard.py).")
    ap.add_argument("--data-dir", default=None,
                    help="cartella per lo stato persistente del server "
                         "(licenza, kid-safe). Default: PREFIX_DATA_DIR, poi "
                         "%%APPDATA%% su Windows o ~/.local/share altrove.")
    ap.add_argument("--material-url", default=appdata.env("MATERIAL_URL"),
                    help="URL della UI da aprire col link 'Material Skin'. "
                         "Default: <lms>/material/ . Se Material Skin non è "
                         "installato, punta alla UI classica (es. <lms>/).")
    ap.add_argument("--services", default=appdata.env("SERVICES", "auto"),
                    help="servizi streaming offerti nel selettore, es. "
                         "tidal,qobuz. Default 'auto': chiede all'impianto "
                         "quali ha (fallback: tidal). Una lista esplicita "
                         "viene controllata contro i nomi che l'impianto "
                         "attivo riconosce, non contro quelli di LMS.")
    ap.add_argument("--default-service",
                    default=appdata.env("DEFAULT_SERVICE", "tidal"),
                    help="servizio streaming usato in modalità automatica e "
                         "quando la frase non ne nomina uno (default: tidal)")
    ap.add_argument("--asr-model",
                    default=appdata.env("ASR_MODEL"),
                    help="modello Whisper per il riconoscimento vocale locale "
                         "(tiny/base/small/medium...). Default: small, ma su "
                         "macchine sotto ~4 GB di RAM resta spento se non "
                         "indicato qui. Serve il gruppo: uv sync --group asr")
    ap.add_argument("--wakeword-lang",
                    default=appdata.env("WAKEWORD_LANG", "it"),
                    help="lingua del modello Vosk per la parola chiave libera "
                         "lato server (it/en/fr/de/es, default: it). Il "
                         "modello e' una risorsa di processo da ~50 MB, quindi "
                         "e' scelto qui e non per richiesta come la lingua "
                         "delle risposte.")
    ap.add_argument("--wakeword-vosk-model",
                    default=appdata.env("WAKEWORD_VOSK_MODEL"),
                    help="cartella del modello Vosk da usare per la parola "
                         "chiave libera, se non quella predefinita sotto "
                         "<dati>/vosk-models/. Serve il gruppo: "
                         "uv sync --group wakeword-vosk")
    ap.add_argument("--wakeword-no-download", action="store_true",
                    # == "1", like every other boolean env in this repo
                    # (licensing.py): bool("0") is True, so an add-on setting
                    # VIVAVOCE_WAKEWORD_NO_DOWNLOAD=0 to *enable* the fetch
                    # would have switched it off, and the wake word would have
                    # stayed silently on the browser engine, beep and all.
                    default=appdata.env("WAKEWORD_NO_DOWNLOAD") == "1",
                    help="non scaricare il modello Vosk mancante all'avvio. "
                         "Per installazioni senza rete o dove il modello lo "
                         "mette l'amministratore: senza modello la parola "
                         "chiave libera resta spenta, e nient'altro cambia.")
    return ap
