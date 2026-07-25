# Changelog

## 0.2.0 — July 2026

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
- **Artist-or-song disambiguation** (free): «metti Beatrice» used to silently
  play the streaming service's first hit (songs by Beatrice Egli) even though
  the name could equally mean an artist or a song title. When a bare query also
  matches an artist name, Vivavoce now asks — «1: Beatrice di Sam Rivers,
  2: Beatrice di Joe Henderson, 3: l'artista Beatrice Egli. Quale metto?» —
  on TIDAL/Qobuz and in the local library, searching deep enough to surface
  same-titled songs the service buries under the artist's own catalog.
  Unambiguous requests («metti Bohemian Rhapsody») still play instantly, with
  no extra lookup.
- **Catalog-aware phonetic correction** (free): the recognizer garbles foreign
  titles into native-sounding words («Comfortably Numb» → «fatta blina»); the
  server now indexes how *your* library sounds (artists/albums/titles, rebuilt
  in background every 6 h) and quietly retries a mangled play command with the
  sound-alike library name. Corrections run only after the original transcript
  misses, so nothing changes for queries that already work.
- **Queue commands** (free): «aggiungi X in coda» / "add X to the queue"
  appends without touching what's playing, «metti X subito dopo» / "play X
  next" inserts after the current track, plus «shuffle» / «mescola tutto» and
  «ripeti tutto» / "repeat" toggles — on streaming and on the local library.
- **Genre & era on the local library** (free): «metti del jazz» / "play some
  jazz" plays the library *genre* shuffled; «metti musica anni 80» / "play 80s
  music" queues the decade (only years actually present). Fully offline; a
  genre only wins on a confident match, so real titles are never stolen.
- **Edition awareness** (free): "X" and "X (Live)" are editions of one song,
  not a "did you mean" — «metti comfortably numb live» plays the Live cut,
  a plain request no longer asks a useless «1: X, 2: X (Live)».
- **Choice memory** (free): answering a «quale metto?» once is enough — the
  next identical ambiguous query plays your usual pick straight away. Stored
  transparently in `choices.json` in the data dir; a follow-up «metti la N»
  overrides and re-teaches it.
- **More like this** (free): «metti qualcosa di simile» / "play something like
  this" starts the streaming service's Artist Mix/radio for the now-playing
  artist (top tracks when the service has no mix).
- **Self-adapting TLS certificate** (free): a container behind NAT can't know
  the address clients will use, so the SANs of a pre-generated certificate
  were wrong there unless you set `VIVAVOCE_CERT_HOSTS` by hand. The server
  now learns each new address from the request's Host header, re-issues the
  certificate with the reused local CA (installed devices keep trusting) and
  reloads it live. `VIVAVOCE_CERT_HOSTS` remains as an optional pre-seed.

### Removed

- **The Alexa skill.** It required an always-on HTTPS tunnel and a developer
  account per household — unmaintainable, and the web app does the job
  without any cloud. The engine lives on under `engine/` (was `lambda/`).
