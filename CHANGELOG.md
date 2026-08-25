# Changelog

## Unreleased

### New

- **14 days of full Pro on every install**, microphone included — no key, no
  card, no account, and no network call: the window is one timestamp in the
  data directory, opened the first time the server starts. Because it lives
  server-side it also unlocks the features enforced there (local speech
  recognition, server-side wake word), and clearing the browser's storage does
  not re-arm it. When it ends, typed commands keep working exactly as before —
  nothing breaks, nothing is deleted. The settings panel says how many days
  are left rather than claiming a license nobody bought, and after a command
  you typed, the page points out — at most once per session, and never in the
  first two days — that you could have simply said it.
- **Queue management** (free): «aggiungi X alla coda» / "add X to the queue"
  queues a song at the end; «metti X dopo questa» / "play X next" queues it
  right after the current track; «svuota la coda» / "clear the queue"; «cosa
  c'è in coda» / "what's in the queue" reads back what's coming up. Reuses
  the existing title/artist parsing and "did you mean" disambiguation — a
  queue command that opens a numbered list queues (not plays) whichever one
  you pick — and works with multi-room («aggiungi X alla coda in cucina»).
- **Favorites & radio** (free): «riproduci i preferiti» / "play my favorites"
  plays a saved LMS favorite; «metti la radio X» / "play the radio X"
  searches your favorites for a matching station name. Built on the LMS core
  Favorites API (not a specific radio plugin), so it works with however you
  already saved your stations — TuneIn, a plugin, or a raw stream URL.
- **Server-side wake word** (Pro, optional install — `uv sync --group
  wakeword`, its own group, see DEPLOY.md): an alternative to the browser's
  continuous-listening mode that eliminates the Android beep — the single
  most-cited launch complaint — by streaming mic audio to the server, which
  runs openWakeWord (CPU, no GPU) instead of restarting Web Speech every few
  seconds. Trade-off, upfront: only a fixed English phrase ("hey jarvis")
  today, not the free-text wake word — offered as an *additional* choice
  next to it, not a replacement. A new settings switch appears once the
  server reports the engine installed.
- **"Report a misunderstood phrase"** (free, privacy-first): when a command
  isn't understood, the reply offers a button that saves the report on your
  device and opens a pre-filled GitHub issue (phrase, language, source,
  version) for you to review and submit. Nothing is ever sent by the app
  itself — see PRIVACY.md.

### Fixed

- **`/command`, `/kidsafe`, `/player` and `/license` no longer drop the
  connection on a non-object JSON body** (`null`, a bare number, a string, a
  list): `json.loads` accepted it without raising, and the unguarded
  `.get(...)` that followed crashed with an uncaught `AttributeError`,
  contradicting each endpoint's own "never a 5xx" design — on `/license`,
  the one endpoint that handles a paid key. Pre-existing (found during a
  post-phase review of the Fase 1 diff, not introduced by it); now covered
  by tests on all four routes.

### Internal

- **Frontend split**: the 1.700-line `index.html` is now a markup shell plus
  native ES modules (`localvoice/static/js/`) and a real stylesheet — no
  bundler, no new dependencies. The installed PWA refetches the shell once.
- **Browser end-to-end tests**: seven Playwright flows (page load, command
  round trip, "did you mean" tap, license activation, now-playing, the report
  button, settings persistence) run headless in CI against the same fake-LMS
  stack as the rest of the suite.
- **Plug-in languages**: the router's IT/EN patterns moved into per-language
  packs (`localvoice/lang/`); adding a language is now one file plus its
  messages and tests — groundwork for German.
- **Server split**: `server.py` (startup/CLI) now stands apart from
  `http_api.py` (routes), `staticfiles.py` (assets) and `tls.py`;
  `python -m localvoice` works as a second entry point.

## 0.2.0 — August 2026

### SqueezeSay is now Vivavoce

The project is renamed **Vivavoce** (Italian for "hands-free / speakerphone").
"Squeeze-" echoed the Logitech Squeezebox trademark — the same reason the LMS
project itself renamed to Lyrion. What this means for existing installs:

| You use | What to do |
|---|---|
| Docker compose | `docker compose pull && docker compose up -d`. The data volume keeps its old internal name on purpose: your certificate (and license, see below) survive. Container/service are now called `vivavoce`. |
| Env variables | New names are `VIVAVOCE_*`. The old `SQUEEZESAY_*` names keep working **for this release only**, printing a deprecation note. |
| Home Assistant add-on | The add-on slug changed, so the Supervisor sees a **new add-on**: uninstall the old "SqueezeSay" one, add the repo again (`https://github.com/LucaBon/vivavoce`) and install **Vivavoce**. The old `/data` is not migrated — you'll re-accept the certificate once and re-enter your license key (this consumes one of your 5 activations). |
| Windows autostart | Re-run `tools/install_autostart.ps1`; `tools/uninstall_autostart.ps1` cleans up both the old and the new task/firewall names. |
| systemd | The unit is now `deploy/vivavoce.service`. |
| Installed PWA | The app updates itself on the next online open; the icon label may show the old name until you reinstall it (cosmetic). |
| Wake word | The default is now "vivavoce"; if you had saved a custom wake word (including "impianto"), it is preserved. |

### New

- **Now-playing panel** (free): artwork, title/artist/album, play/pause lamp,
  transport buttons, a draggable seek bar and a **volume slider**, at the top
  of the page.
- **Multi-room** (Pro, `localvoice/pro/multiroom.py`): a "Dove suona la
  musica" selector appears in settings when the LMS has more than one player,
  and any command can target a room on the fly: «metti Time **in cucina**»,
  «pausa in salotto» ("play … in the kitchen"). A follow-up «metti la 2»
  keeps playing in that room. Enforced server-side, like kid-safe.
- **Sleep timer** (free): «spegni tra 30 minuti», «stop in half an hour»,
  «annulla il timer» — the LMS native sleep timer, armed by voice.
- **Local speech recognition** (Pro, `localvoice/pro/asr.py`, optional
  install): the mic can transcribe on *your* server with **faster-whisper**
  instead of the browser's cloud engine — the audio never leaves the LAN,
  closing the one non-local step in the privacy story. Enable with
  `uv sync --group asr` (or the Docker `--build-arg ASR=1` image) and flip
  «riconoscimento vocale locale» in settings; Web Speech remains the default
  and the automatic fallback. Model configurable with `--asr-model` /
  `VIVAVOCE_ASR_MODEL`, cached in the data directory; the default is
  RAM-aware — `small` on ~4 GB+ machines, off below that (the smaller models
  mangle English song titles; an explicit `--asr-model` always wins). As a
  bonus, the mic now also works on browsers without Web Speech (Firefox).
- **LMS status lamp** (free): the header LED turns red — with a clear message —
  when the music server is unreachable, instead of failing silently.
- **Vivavoce Pro** — one-time license (11,90 €; launch price 8,90 €) that
  unlocks the microphone, the wake word, the multilingual read-back voices and
  kid-safe. Activation is once-online, then cached: offline never disables it.
  The core stays free (text commands, all search/playback, transport) and is
  now formally **AGPL-3.0** (the repo previously had no license).
- **Kid-safe on the web app** (Pro): PIN-protected blocklist, enforced
  server-side for every device on the LAN, editable by voice («blocca …»,
  «sblocca …», «quali brani sono bloccati») or from settings.
- **Auto-discovery from inside Docker bridge/NAT** (free): when the UDP
  broadcast can't leave the container (Docker Desktop on Windows/Mac, bridge
  networks), the server now falls back to a **unicast sweep** of the LAN — LMS
  answers the same discovery request sent host-by-host — and remembers the
  server in the data volume, so restarts skip discovery entirely.
  `docker compose up` is zero-config everywhere, not just with host networking.

### Removed

- **The Alexa skill.** It required an always-on HTTPS tunnel and a developer
  account per household — unmaintainable, and the web app does the job
  without any cloud. The engine lives on under `engine/` (was `lambda/`).

### Internal

- **CI** (GitHub Actions): every push and pull request runs the test suite on
  Python 3.9–3.14 plus a Windows job (the `%APPDATA%` data-directory branch a
  Linux-only matrix never executes), byte-compiles every module — `tools/` is
  imported by no test, so a syntax error there used to reach the user — and
  builds the Docker image, which is the only thing that catches a `COPY`
  pointing at a moved file.
- **Integration tests** (489 → 531): the PWA shell (`sw.js` pre-caches its
  asset list atomically, so a single 404 silently stopped the app being
  installable), the `/command` path end-to-end from HTTP down to the commands
  the LMS actually receives, and the release descriptors — the add-on version
  must match `pyproject.toml`, and every Dockerfile `COPY` source must exist.
