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

import os
import platform
import socket
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, "engine"))  # actions, lms
sys.path.insert(0, HERE)  # router, http_api, ...

import appdata
import audio_engines  # noqa: E402
import book_progress  # noqa: E402
import cli  # noqa: E402
from httpbase import BoundedThreadingHTTPServer  # noqa: E402
import licensing  # noqa: E402
import pro_features  # noqa: E402
import servicestate  # noqa: E402
# Re-exported: ``explicit_services`` was here until the 400-line rule
# asked for the split, and tests reach it through this module.
from services import explicit_services  # noqa: E402,F401
import setupserver  # noqa: E402
import spoken_library  # noqa: E402
import tls  # noqa: E402
import webguard  # noqa: E402
from http_api import make_handler  # noqa: E402,F401  (re-exported for tests)
from player import registry as player_registry  # noqa: E402


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
    """Why the onnxruntime-backed optional group cannot be installed, or ``""``.

    ``asr``, not ``wakeword-vosk`` — that group rests on nothing of the sort.
    vosk ships wheels for linux x86_64/aarch64/**armv7l**, win_amd64 and
    macOS universal2, so there is no supported platform it cannot install on
    and this note would be exactly backwards for it: it would tell a 32-bit
    Pi that the one optional engine which works there is impossible.

    One group, since openWakeWord was retired: ``asr``, which reaches
    onnxruntime through CTranslate2. Neither project has *ever* published a
    32-bit wheel:
    not on PyPI (checked across every release of both), and not on piwheels
    either, the extra index Raspberry Pi OS configures by default and which
    does carry numpy/scipy/scikit-learn for armv7l. So on a Pi running a
    32-bit image, "uv sync --group asr" sends pip into a source build
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
    ap = cli.build_parser()
    args = ap.parse_args()
    # Convalidato come --services: un nome sbagliato e' un refuso all'avvio, e
    # la risposta deve dire cosa si poteva scrivere al suo posto.
    try:
        backend = player_registry.get(args.backend)
    except ValueError as exc:
        print(exc)
        return 1
    backend_url = args.backend_url or (args.lms if backend.name == "lms" else "")
    if backend.discover is None and not backend_url:
        print(f"{backend.label} non si annuncia sulla rete: indica dove "
              f"trovarlo con --backend-url.")
        return 1
    # Audiobooks (--library) sit beside the music system, never in its place:
    # without the option nothing is built. Checked before the setup page can
    # block, so a typo is reported at once. Every router is handed it, and
    # the sentences that reach a book are in intents_spoken.py.
    books, complaint = spoken_library.open_library(args)
    if complaint:
        print(complaint)
        return 1
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
    kidsafe = pro_features.build_kidsafe(data_dir, license_mgr)
    if kidsafe is None:
        print("Kid-safe non incluso in questa build: i comandi funzionano, "
              "la lista dei brani bloccati no.")
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

    lms_url = backend_url
    # Where that address came from, which is not a detail: see
    # lmsproxy.browse_path and appdata.remembered_from_page.
    from_page = False
    if not lms_url and backend.name == "lms":
        # L'indirizzo ricordato e' quello di un LMS: un altro backend non lo
        # eredita, o il primo avvio con Music Assistant proverebbe a parlare
        # all'hi-fi dell'avvio precedente. Ripassa dalla stessa verifica di
        # un indirizzo scritto a mano: il file l'ha riempito una risposta UDP.
        lms_url = setupserver.normalize_lms_url(
            appdata.remembered_lms(data_dir))
        from_page = bool(lms_url) and appdata.remembered_from_page(data_dir)
        if lms_url:
            # Not probed here: serve_setup probes every address it is given,
            # so checking it twice would only be a slower way to be wrong.
            print(f"LMS: {lms_url} (ricordato dall'ultimo avvio)")

    said = []

    def discover() -> str:
        # The searching narration is worth one line, not one per round: this
        # runs on a loop for as long as the LMS stays missing, which can be
        # all night. The progress phases below are already one-shot per run.
        if backend.discover is None:
            return ""  # a system that has to be told where it is
        if not said:
            said.append(1)
            print("Cerco un server LMS sulla rete (UDP 3483)...")
        found = backend.discover(on_progress=_discovery_progress)
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
        lms_url, players, from_page = setupserver.serve_setup(
            args.host, args.port, lms_url, discover,
            pinned=bool(backend_url), require_player=not args.player,
            from_page=from_page,
            backend=backend.name, token=args.backend_token,
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
    if backend.name == "lms":
        appdata.remember_lms(data_dir, lms_url, from_page=from_page)

    # The engine talks to whatever this hands back, and has no idea which of
    # them it got (see engine/player/protocols.py).
    client = backend.client(lms_url, player, token=args.backend_token)
    # What the app learned about which services actually play, kept next to
    # the licence so no household buys the same silent play twice
    # (engine/player/silence.py). Behind the capability, like every other
    # feature a backend may not have: a music system with a single source has
    # nothing to choose between and nothing to remember.
    if backend.capabilities.services:
        client.remember_silence_in(servicestate.SilenceFile(data_dir))
    multiroom = pro_features.build_multiroom(license_mgr, client)

    # Which streaming services the source selector offers. "auto" asks the
    # music system what it has; an explicit list is the escape hatch for when
    # that answer misbehaves — it is still checked against the names the
    # system recognises, which costs no round trip on LMS and one on
    # MusicAssistant (see explicit_services).
    if args.services.strip().lower() == "auto":
        try:
            services = client.installed_services()
        except Exception:
            services = []
        if services:
            print(f"Servizi streaming rilevati: {', '.join(services)}")
        else:
            # No invented list: assuming TIDAL was a guess printed as a
            # fact, and got a selector offering a plugin this house has never
            # had plus «TIDAL non è collegato» to every request aimed at it.
            print("Nessun servizio streaming rilevato: restano la libreria "
                  "locale e i comandi di riproduzione (se l'impianto ne ha "
                  "uno, indicalo con --services tidal,qobuz).")
    else:
        services, complaint = explicit_services(client, backend, args.services)
        if complaint:
            print(complaint)
            return 1

    silent = client.silent_services() if backend.capabilities.services else {}
    muted = [s for s in services if s in silent]
    if muted:
        # Said out loud, because a service quietly missing from the answers is
        # the kind of thing a household should be told about rather than
        # discover. Both ways back are in the sentence.
        print(f"Non suonano dall'ultima volta: {', '.join(muted)}. Non li "
              f"propongo finché non tornano — per riprovare subito basta "
              f"nominarne uno («metti ... da {muted[0]}»).")

    # Empty when nothing streams here: ``SourceChoice`` reads that as "no
    # service to aim at" rather than aiming at a name nobody configured.
    default_service = args.default_service.strip().lower()
    if not services:
        default_service = ""
    elif default_service not in services:
        default_service = services[0]
        print(f"--default-service non tra i servizi attivi: uso {default_service}")

    # Material Skin is a plugin of the LMS, so only an LMS has one to default
    # to. Empty switches the in-page panel and its reverse proxy off, which is
    # what browse_path() already answers for a UI living somewhere else.
    material_url = args.material_url or (
        lms_url.rstrip("/") + "/material/" if backend.name == "lms" else "")
    ca_path = tls.find_ca(args.cert)
    BoundedThreadingHTTPServer.allow_public_peers = args.allow_public_peers
    httpd = BoundedThreadingHTTPServer(
        (args.host, args.port),
        make_handler(client, material_url, services, default_service,
                     lms_from_page=from_page, api_token=args.api_token,
                     ca_path=ca_path, license_mgr=license_mgr,
                     kidsafe=kidsafe, transcriber=transcriber,
                     multiroom=multiroom, app_version=appdata.app_version(),
                     wakeword_sessions=wakeword_sessions,
                     wake_phrase_store=wake_phrase_store,
                     allowed_hosts=webguard.parse_hosts(args.allowed_hosts),
                     books=books),
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
    if books is not None:
        # Where each book is, saved to Audiobookshelf every half minute — so
        # that music started from anywhere, Material Skin included, costs the
        # book at most that (see book_progress.py). Only with --library.
        book_progress.start(books)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nStop.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
