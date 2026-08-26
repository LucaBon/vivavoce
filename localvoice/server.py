#!/usr/bin/env python3
"""Local voice web server — no cloud, no accounts.

Serves a page with a microphone button (browser speech recognition, it-IT) that
posts the transcript to ``/api/v1/command``; the ``actions.py``/``lms.py`` engine
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
import os
import platform
import socket
import sys
import time
import urllib.parse

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, "engine"))  # actions, lms
sys.path.insert(0, HERE)  # router, http_api, ...

import appdata  # noqa: E402
import discovery  # noqa: E402
from httpbase import BoundedThreadingHTTPServer  # noqa: E402
import licensing  # noqa: E402
import tls  # noqa: E402
import webguard  # noqa: E402
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
    cached = appdata.read_json(_lms_cache_path(data_dir), {})
    return (cached.get("lms") or "") if isinstance(cached, dict) else ""


def _save_cached_lms(data_dir: str, url: str) -> None:
    try:
        appdata.atomic_write_json(_lms_cache_path(data_dir), {"lms": url})
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
    "wide": "Non ancora trovato: provo le altre subnet della tua rete...",
    "full": "Non ancora trovato: scansione completa di 192.168.*...",
}


def optional_groups_unavailable_here() -> str:
    """Why neither optional group can be installed on this machine, or ``""``.

    Both rest on onnxruntime — openWakeWord directly, faster-whisper through
    CTranslate2 — and neither project has *ever* published a 32-bit wheel:
    not on PyPI (checked across every release of both), and not on piwheels
    either, the extra index Raspberry Pi OS configures by default and which
    does carry numpy/scipy/scikit-learn for armv7l. So on a Pi running a
    32-bit image, "uv sync --group wakeword" sends pip into a source build
    that cannot succeed, and the printed instruction is a dead end.

    A 64-bit OS on the same hardware has wheels for everything (aarch64 is
    fully supported); this is a userland word-size limit, not an ARM one.
    """
    machine = platform.machine().lower()
    thirty_two_bit_arm = machine.startswith(("armv6", "armv7")) or machine == "armhf"
    if not thirty_two_bit_arm:
        return ""
    return (" Su questa macchina non è installabile: il sistema è ARM a 32 bit "
            f"({platform.machine()}) e onnxruntime non pubblica wheel a 32 bit. "
            "Serve un sistema operativo a 64 bit (aarch64) sullo stesso hardware.")


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
    ap.add_argument("--wakeword-model",
                    default=appdata.env("WAKEWORD_MODEL"),
                    help="modello openWakeWord per la parola chiave lato "
                         "server, senza il beep Android (default: hey_jarvis; "
                         "solo poche frasi in inglese sono disponibili "
                         "pronte all'uso — non è personalizzabile come la "
                         "parola chiave del browser). Serve il gruppo: "
                         "uv sync --group wakeword")
    args = ap.parse_args()
    data_dir = appdata.data_dir(args.data_dir)
    license_mgr = licensing.LicenseManager(data_dir)
    license_mgr.revalidate_async()  # settimanale, best-effort, mai bloccante
    # La finestra di prova parte qui — all'installazione — e non da una
    # richiesta del browser: così l'orologio non si riarma svuotando i dati
    # del sito, e nessun client può farla ripartire. Idempotente.
    trial_opened, waiting_for_clock = license_mgr.start_trial_async()
    if waiting_for_clock is not None:
        print("Orologio di sistema non ancora sincronizzato: apro la prova Pro "
              "appena l'ora è corretta (niente panico, non hai perso giorni).")
    if trial_opened:
        print(f"Prova Pro: {licensing.TRIAL_DAYS} giorni con tutte le "
              f"funzioni attive (microfono compreso). Alla scadenza restano "
              f"i comandi scritti, e nulla si rompe.")
    else:
        trial = license_mgr.trial_status()
        if trial["active"] and not license_mgr.status()["key"]:
            print(f"Prova Pro: restano {trial['days_left']} giorni.")
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
              "il riconoscimento del browser. Per attivarlo: uv sync --group asr"
              + optional_groups_unavailable_here())
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

    # Parola chiave lato server (Pro): elimina il beep Android della
    # continua-ascolto del browser, ma solo con poche frasi inglesi pronte
    # all'uso (non personalizzabile come quella del browser — vedi
    # pro/wakeword.py). Gruppo opzionale SEPARATO da "asr" apposta (vedi
    # pro/wakeword.py: openwakeword>=0.5 rompe su Python 3.12+ per una
    # dipendenza rigida da tflite-runtime).
    from pro.wakeword import DEFAULT_MODEL as WAKEWORD_DEFAULT_MODEL
    from pro.wakeword import ServerWakeWordSessions
    wakeword_model = args.wakeword_model or WAKEWORD_DEFAULT_MODEL
    wakeword_sessions = ServerWakeWordSessions(wakeword_model)
    if not wakeword_sessions.available():
        print("Parola chiave lato server non installata: l'ascolto continuo "
              "usa il riconoscimento del browser (col beep su Android). "
              "Per attivarla: uv sync --group wakeword"
              + optional_groups_unavailable_here())
    else:
        print(f"Parola chiave lato server attiva (openWakeWord, modello "
              f"{wakeword_model}): nessun beep durante l'ascolto continuo.")

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
    multiroom = MultiRoom(license_mgr, client.get_players, lms=client)

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
    ca_path = tls.find_ca(args.cert)
    httpd = BoundedThreadingHTTPServer(
        (args.host, args.port),
        make_handler(client, material_url, services, default_service,
                     ca_path=ca_path, license_mgr=license_mgr,
                     kidsafe=kidsafe, transcriber=transcriber,
                     multiroom=multiroom, app_version=appdata.app_version(),
                     wakeword_sessions=wakeword_sessions,
                     allowed_hosts=webguard.parse_hosts(args.allowed_hosts)),
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
        if ca_path:
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
