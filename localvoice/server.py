#!/usr/bin/env python3
"""Local voice web server — no cloud, no accounts.

Serves a page with a microphone button (browser speech recognition, it-IT) that
posts the transcript to ``/command``; the ``actions.py``/``lms.py`` engine
drives LMS/Daphile over the LAN. Runs entirely at home.

    python localvoice/server.py            # auto-discovers LMS on the LAN
    python localvoice/server.py --lms http://192.168.1.50:9000   # or point it
    python -m localvoice                   # same thing, module form

Then open http://<this-pc-ip>:8730 from a phone/tablet/PC on the same network.
(The mic needs HTTPS from another device — pass --cert/--key; see README. The
text box works everywhere.)

This module is the startup half — CLI, LMS discovery/wait, wiring — plus the
process entry point. The HTTP surface lives in ``http_api.py``, the web
assets in ``staticfiles.py``, TLS in ``tls.py``.
"""

from __future__ import annotations

import argparse
import json
import os
import socket
import sys
import time
import urllib.parse
from http.server import ThreadingHTTPServer

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, "engine"))  # actions, lms
sys.path.insert(0, HERE)  # router, http_api, ...

import appdata  # noqa: E402
import discovery  # noqa: E402
import licensing  # noqa: E402
import tls  # noqa: E402
from http_api import make_handler  # noqa: E402,F401  (re-exported for tests)
from lms import SERVICES, LMSClient, LMSError  # noqa: E402


def lan_ips() -> list:
    """This machine's primary LAN IPv4, for printing a ready-to-open URL.

    Best-effort, used only for display (never to bind). Uses the default-route
    address — the one a phone on the same LAN should target — which naturally
    skips virtual adapters (WSL/Hyper-V vEthernet). No packet is actually sent;
    the UDP connect just makes the OS pick the outgoing route. Falls back to a
    non-loopback hostname address only if the route probe fails.
    """
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return [ip]
    except OSError:
        pass
    try:
        for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            ip = info[4][0]
            if not ip.startswith("127."):
                return [ip]
    except OSError:
        pass
    return []


def wait_for_players(lms_url: str, delay: float = 5.0, sleep=time.sleep) -> list:
    """The LMS player list, retrying until the LMS answers.

    Il PC che ospita questo server spesso si risveglia (o fa boot) PRIMA che
    la rete sia tornata su: un LMS irraggiungibile in quel momento non è un
    errore fatale ma uno stato transitorio. Invece di morire con un traceback
    (costringendo a rilanciare a mano finché non va), aspetta e riprova.
    Ctrl+C esce.
    """
    waited = False
    while True:
        try:
            players = LMSClient(lms_url, "0").get_players()
            if waited:
                print("LMS raggiunto.")
            return players
        except LMSError as exc:
            if not waited:
                print(f"LMS non raggiungibile: {exc}")
                print(f"Aspetto che {lms_url} risponda, riprovo ogni "
                      f"{delay:g} secondi (Ctrl+C per uscire)...")
                waited = True
            sleep(delay)


# -- Cache della discovery ----------------------------------------------------
# L'ultimo LMS trovato viene ricordato nella cartella dati (in Docker: il
# volume persistente): al riavvio niente broadcast né sweep unicast, il server
# riparte subito. Se l'LMS non risponde più, la cache viene ignorata e la
# discovery ricomincia da capo.

def _lms_cache_path(data_dir: str) -> str:
    return os.path.join(data_dir, "discovery_cache.json")


def _cached_lms(data_dir: str) -> str:
    try:
        with open(_lms_cache_path(data_dir), encoding="utf-8") as f:
            return json.load(f).get("lms") or ""
    except (OSError, ValueError):
        return ""


def _save_cached_lms(data_dir: str, url: str) -> None:
    try:
        with open(_lms_cache_path(data_dir), "w", encoding="utf-8") as f:
            json.dump({"lms": url}, f)
    except OSError:
        pass  # cartella read-only: pazienza, si riscopre al prossimo avvio


def _lms_reachable(url: str, timeout: float = 2.0) -> bool:
    parts = urllib.parse.urlsplit(url)
    if not parts.hostname:
        return False
    try:
        socket.create_connection((parts.hostname, parts.port or 9000),
                                 timeout=timeout).close()
        return True
    except OSError:
        return False


# Solo le fasi che meritano una riga: il passaggio allo sweep (il broadcast non
# esce dai bridge Docker, è il caso normale in container) e l'ultima risorsa.
_DISCOVERY_PHASES = {
    "sweep": "Nessuna risposta al broadcast (normale dentro Docker): "
             "discovery unicast, subnet per subnet...",
    "full": "Non ancora trovato: scansione completa di 192.168.*...",
}


def _discovery_progress(phase: str) -> None:
    line = _DISCOVERY_PHASES.get(phase)
    if line:
        print(line)


def main() -> int:
    # Ogni opzione ha un gemello d'ambiente (PREFIX_LMS, PREFIX_PORT, ...):
    # Docker/HA configurano via env, la riga di comando vince quando presente.
    ap = argparse.ArgumentParser(description="Server vocale locale per LMS/Daphile.")
    ap.add_argument("--lms", default=appdata.env("LMS"),
                    help="es. http://192.168.1.50:9000 "
                         "(auto-rilevato sulla rete se omesso)")
    ap.add_argument("--player", default=appdata.env("PLAYER"),
                    help="MAC del player; default: il primo trovato")
    ap.add_argument("--host", default="0.0.0.0")
    ap.add_argument("--port", type=int, default=int(appdata.env("PORT", "8730")))
    ap.add_argument("--cert", help="certificato TLS (per il mic da altri device)")
    ap.add_argument("--key", help="chiave TLS")
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
                         "tidal,qobuz. Default 'auto': rileva i plugin "
                         "installati sull'LMS (fallback: tidal).")
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
    args = ap.parse_args()
    data_dir = appdata.data_dir(args.data_dir)
    license_mgr = licensing.LicenseManager(data_dir)
    license_mgr.revalidate_async()  # settimanale, best-effort, mai bloccante
    from pro.kidsafe import KidSafe
    kidsafe = KidSafe(data_dir, license_mgr)
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
              "il riconoscimento del browser. Per attivarlo: uv sync --group asr")
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

    lms_url = args.lms
    if not lms_url:
        cached = _cached_lms(data_dir)
        if cached and _lms_reachable(cached):
            lms_url = cached
            print(f"LMS: {lms_url} (ricordato dall'ultimo avvio)")
    if not lms_url:
        print("Cerco un server LMS sulla rete (UDP 3483)...")
        lms_url = discovery.discover_base_url(on_progress=_discovery_progress)
        if not lms_url:
            print("Nessun LMS trovato. Riprova indicando l'indirizzo: "
                  "--lms http://IP-DEL-SERVER:9000")
            return 1
        print(f"LMS trovato: {lms_url}")
        _save_cached_lms(data_dir, lms_url)

    # Aspetta che l'LMS risponda anche quando --player è già noto: subito dopo
    # c'è la rilevazione dei servizi streaming, che con la rete giù ripiegherebbe
    # in silenzio sul solo TIDAL.
    try:
        players = wait_for_players(lms_url)
    except KeyboardInterrupt:
        print("\nStop.")
        return 1

    player = args.player
    if not player:
        if not players:
            print(f"Nessun player trovato su {lms_url}")
            return 1
        player = players[0]["playerid"]
        print(f"Player: {players[0].get('name')} ({player})")

    client = LMSClient(lms_url, player)
    # Multi-stanza (Pro): come il kid-safe, il modulo vive in pro/ e il core
    # riceve solo l'oggetto col suo piccolo contratto.
    from pro.multiroom import MultiRoom
    multiroom = MultiRoom(license_mgr, client.get_players)

    # Which streaming services the source selector offers. "auto" asks the LMS
    # which plugins are installed; an explicit list skips the detection (the
    # escape hatch if the apps query misbehaves on some LMS version).
    if args.services.strip().lower() == "auto":
        try:
            services = client.installed_services()
        except Exception:
            services = []
        if services:
            print(f"Servizi streaming rilevati: {', '.join(services)}")
        else:
            services = ["tidal"]
            print("Nessun servizio streaming rilevato: assumo TIDAL "
                  "(indica i tuoi con --services tidal,qobuz).")
    else:
        services = [s.strip().lower() for s in args.services.split(",") if s.strip()]
        unknown = [s for s in services if s not in SERVICES]
        if unknown or not services:
            print(f"--services non valido: {args.services!r} "
                  f"(disponibili: {', '.join(SERVICES)})")
            return 1

    default_service = args.default_service.strip().lower()
    if default_service not in services:
        default_service = services[0]
        print(f"--default-service non tra i servizi attivi: uso {default_service}")

    material_url = args.material_url or (lms_url.rstrip("/") + "/material/")
    httpd = ThreadingHTTPServer(
        (args.host, args.port),
        make_handler(client, material_url, services, default_service,
                     ca_path=tls.find_ca(args.cert), license_mgr=license_mgr,
                     kidsafe=kidsafe, transcriber=transcriber,
                     multiroom=multiroom),
    )

    scheme = "http"
    if args.cert and args.key:
        tls.wrap_server(httpd, args.cert, args.key)
        scheme = "https"

    # Print the real address to open, not a placeholder. If --host pins a
    # specific interface, show that; otherwise (0.0.0.0) show this PC's LAN IP.
    if args.host not in ("0.0.0.0", "", "::"):
        hosts = [args.host]
    else:
        hosts = lan_ips() or ["<ip-di-questo-pc>"]
    print(f"Pronto: {scheme}://{hosts[0]}:{args.port}   (LMS {lms_url})")
    for extra in hosts[1:]:
        print(f"        {scheme}://{extra}:{args.port}")
    print("Apri l'indirizzo qui sopra dal telefono/PC sulla stessa rete.")
    if scheme == "http":
        # Web Speech (il microfono) richiede un contesto sicuro: da un altro
        # device serve HTTPS. La casella di testo invece funziona anche in HTTP.
        print("Nota: in HTTP il microfono funziona solo su questo PC (localhost); "
              "la casella di testo funziona ovunque.")
        print("      Per il microfono dal telefono serve HTTPS con certificato:")
        print("        uv run python tools/make_cert.py")
        print(f"        uv run python localvoice/server.py --lms {lms_url} "
              "--cert cert.pem --key key.pem")
    else:
        print("Microfono disponibile anche dal telefono (HTTPS). Al primo accesso "
              "accetta una volta l'avviso del certificato self-signed.")
        if tls.find_ca(args.cert):
            print("Per togliere l'avviso e installare la pagina come app: scarica "
                  f"https://{hosts[0]}:{args.port}/ca.pem sul telefono e installala "
                  "come certificato CA (una volta sola).")
    print("Ctrl+C per fermare.")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nStop.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
