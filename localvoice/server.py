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

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, "engine"))  # actions, lms
sys.path.insert(0, HERE)  # router, http_api, ...

import appdata  # noqa: E402
import audio_engines  # noqa: E402
import discovery  # noqa: E402
from httpbase import BoundedThreadingHTTPServer  # noqa: E402
import licensing  # noqa: E402
import setupserver  # noqa: E402
import tls  # noqa: E402
import webguard  # noqa: E402
from http_api import make_handler  # noqa: E402,F401  (re-exported for tests)
from lms import SERVICES, LMSClient  # noqa: E402


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


# Solo le fasi che meritano una riga: il passaggio allo sweep (il broadcast non
# esce dai bridge Docker, è il caso normale in container) e l'ultima risorsa.
_DISCOVERY_PHASES = {
    "sweep": "Nessuna risposta al broadcast (normale dentro Docker): "
             "discovery unicast, subnet per subnet...",
    "wide": "Non ancora trovato: provo le altre subnet della tua rete...",
    "full": "Non ancora trovato: scansione completa di 192.168.*...",
}


def optional_groups_unavailable_here() -> str:
    """Why the onnxruntime-backed optional groups cannot be installed, or ``""``.

    ``asr`` and ``wakeword``, not ``wakeword-vosk`` — that third group rests
    on nothing of the sort and answers for itself in
    ``pro/vosk_wake.wheels_unavailable_here``, because vosk *does* ship an
    armv7l wheel and this note would be exactly backwards for it.

    Both of the two rest on onnxruntime — openWakeWord directly,
    faster-whisper through CTranslate2 — and neither project has *ever*
    published a 32-bit wheel:
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


def _announce_setup(scheme: str, hosts: list, port: int, line: str) -> None:
    """Say where the setup page is before blocking on it.

    Printed only when there IS a setup page — i.e. when something is missing.
    A normal start never reaches here.
    """
    print(f"Pronto (configurazione): {scheme}://{hosts[0]}:{port}")
    for extra in hosts[1:]:
        print(f"                        {scheme}://{extra}:{port}")
    print(line)


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
                    # would have switched it off and got "Hey Jarvis" instead.
                    default=appdata.env("WAKEWORD_NO_DOWNLOAD") == "1",
                    help="non scaricare il modello Vosk mancante all'avvio. "
                         "Per installazioni senza rete o dove il modello lo "
                         "mette l'amministratore: senza modello la parola "
                         "chiave libera resta spenta, e nient'altro cambia.")
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
    # The optional audio engines (local ASR, server-side wake word) and
    # the household's wake phrase, in audio_engines.py — including which
    # of the two wake-word engines this box can actually run.
    transcriber, wakeword_sessions, wake_phrase_store = audio_engines.build(
        args, data_dir, optional_groups_unavailable_here())

    # Where the app will be reachable, worked out before anything can fail:
    # the setup page below is served at this same address, and a household
    # that cannot be told where to look cannot fix anything.
    scheme = "https" if (args.cert and args.key) else "http"
    if args.host not in ("0.0.0.0", "", "::"):
        hosts = [args.host]
    else:
        hosts = lan_ips() or ["<ip-di-questo-pc>"]

    lms_url = args.lms
    if not lms_url:
        lms_url = appdata.remembered_lms(data_dir)
        if lms_url:
            # Not probed here: serve_setup probes every address it is given,
            # so checking it twice would only be a slower way to be wrong.
            print(f"LMS: {lms_url} (ricordato dall'ultimo avvio)")

    said = []

    def discover() -> str:
        # The searching narration is worth one line, not one per round: this
        # runs on a loop for as long as the LMS stays missing, which can be
        # all night. The progress phases below are already one-shot per run.
        if not said:
            said.append(1)
            print("Cerco un server LMS sulla rete (UDP 3483)...")
        found = discovery.discover_base_url(on_progress=_discovery_progress)
        if found:
            print(f"LMS trovato: {found}")
            appdata.remember_lms(data_dir, found)
        return found or ""

    # Nothing below this point can hard-exit for a missing LMS or a player
    # switched off. serve_setup looks once — the usual case, where it returns
    # straight away — and otherwise binds THIS port, serves a page saying
    # which of the two is missing, and keeps looking until it isn't. Switch
    # the Squeezebox on and the page walks itself into the app.
    #
    # An explicit --player is trusted the way it always was: it means the LMS
    # has to answer, not that the list has to be non-empty.
    try:
        lms_url, players = setupserver.serve_setup(
            args.host, args.port, lms_url, discover,
            pinned=bool(args.lms), require_player=not args.player,
            allowed_hosts=webguard.parse_hosts(args.allowed_hosts),
            wrap=(lambda httpd: tls.wrap_server(httpd, args.cert, args.key))
            if scheme == "https" else None,
            announce=lambda line: _announce_setup(scheme, hosts, args.port, line))
    except KeyboardInterrupt:
        print("\nStop.")
        return 1

    player = args.player
    if not player:
        player = players[0]["playerid"]
        print(f"Player: {players[0].get('name')} ({player})")
    appdata.remember_lms(data_dir, lms_url)

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
                     wake_phrase_store=wake_phrase_store,
                     allowed_hosts=webguard.parse_hosts(args.allowed_hosts)),
    )

    if scheme == "https":
        tls.wrap_server(httpd, args.cert, args.key)

    # The real address to open, not a placeholder — worked out above, before
    # the setup page needed it.
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
