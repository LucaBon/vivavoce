# Deploy & setup

The web app runs on your LAN and talks straight to LMS: no cloud account, no
tunnel.

Wherever you see `http://<IP-LMS>:9000` or a player MAC `aa:bb:cc:dd:ee:ff`, substitute
your own. The web app can usually **auto-discover** the LMS, so you may not need
the address at all.

### Docker — one command, HTTPS included (Linux / NAS / Raspberry Pi)

No clone, no build. The image is published on GHCR for **amd64 and arm64** on
every release:

```bash
docker run -d --name vivavoce --network host --restart unless-stopped \
  -v vivavoce-data:/data ghcr.io/lucabon/vivavoce:latest
# open https://<ip-of-this-host>:8730 and accept the certificate warning once
```

Or the same thing as a compose file you can paste anywhere — you do not need
this repository for it:

```yaml
services:
  vivavoce:
    image: ghcr.io/lucabon/vivavoce:latest
    container_name: vivavoce
    network_mode: host
    restart: unless-stopped
    volumes:
      - vivavoce-data:/data
volumes:
  vivavoce-data:
```

Pin a version (`:0.4.0`, or `:0.4` to follow patches) instead of `:latest` if
you would rather choose when to move.

> [!NOTE]
> Working from a checkout? [docker-compose.yml](docker-compose.yml) in this
> repo builds from source instead (`build: .`), which is what you want while
> changing the code. Both produce the same container, and both use the
> `vivavoce-data` volume, so you can move between them without losing the
> certificate, the licence activation or the kid-safe list.

> [!IMPORTANT]
> Installed before 0.3 and have a `squeezesay-data` volume? Copy it across
> once, then start as above:
>
> ```bash
> docker run --rm -v squeezesay-data:/from -v vivavoce-data:/to \
>   alpine sh -c "cp -a /from/. /to/"
> ```
>
> Skipping this is not destructive — you just start from scratch: every phone
> re-trusts the certificate, one of your five activations is spent, and an
> enabled kid-safe blocklist comes back switched off.

That's it: LMS is auto-discovered on the LAN, the TLS certificate is generated on
first start into a persistent volume (so the browser warning is one-time), and the
container restarts on boot (`restart: unless-stopped` — no systemd/autostart needed).
Everything is configured via environment variables (all optional; the pre-rename
`SQUEEZESAY_*` names still work for one release, with a deprecation note) — in
[docker-compose.yml](docker-compose.yml) if you use it, or `-e` flags on
`docker run`:

| Variable | Meaning | Default |
|---|---|---|
| `VIVAVOCE_LMS` | LMS URL, e.g. `http://192.168.1.50:9000` | auto-discovery (UDP) |
| `VIVAVOCE_PLAYER` | player MAC | first player found |
| `VIVAVOCE_PORT` | listen port | `8730` |
| `VIVAVOCE_HTTPS` | `0` = plain HTTP (mic on localhost only) | `1` |
| `VIVAVOCE_CERT_HOSTS` | extra SANs for the certificate (comma-separated) | — |
| `VIVAVOCE_MATERIAL_URL` | URL for the "Material Skin" link | `<lms>/material/` |

> [!NOTE]
> Auto-discovery works in any network mode: broadcast first, and where broadcast
> can't leave the container (Docker bridge/NAT) the server falls back to a
> unicast sweep of the LAN, then remembers the LMS in the volume so restarts are
> instant. The compose file still uses `network_mode: host` (Linux — fine on
> NAS/Raspberry Pi) because it also puts the right IPs in the certificate. On
> **Docker Desktop (Windows/Mac)** or bridge networks, follow the comments in
> [docker-compose.yml](docker-compose.yml): map the port and put the host's LAN
> IP in `VIVAVOCE_CERT_HOSTS`.

> **Architecture.** The published image covers amd64 and arm64; the app itself
> is stdlib-only, so building it from source runs anywhere Python does —
> including a 32-bit Raspberry Pi, which has no published image and needs
> `docker build` (or the no-Docker route below). The two *optional* Pro engines (local speech recognition, server-side
> wake word) need a **64-bit** OS; see their sections below for why, and what
> a 32-bit box gets instead.

### Home Assistant app

If you run Home Assistant OS/Supervised, Vivavoce installs as an app
(same engine, wrapped for the Supervisor — see [ha-addon/](ha-addon/)):

1. **Settings → Apps → App store → ⋮ → Repositories** → add
   `https://github.com/LucaBon/vivavoce`. Home Assistant renamed add-ons to
   apps in 2026.2; on anything older the menu still says *Add-ons → Add-on
   store*.
2. Install **Vivavoce** and start it. LMS is auto-discovered; the options
   (all optional: `lms_url`, `player`, `port`, `https`, `cert_hosts`,
   `material_url`) mirror the Docker environment variables above.
3. Open `https://<home-assistant-ip>:8730` and accept the certificate warning
   once. Full details in the app's Documentation tab
   ([ha-addon/DOCS.md](ha-addon/DOCS.md)).

### Home Assistant voice — talking to Vivavoce through Assist

The app above gives you the web page. This gives you the voice: say «metti
Comfortably Numb dei Pink Floyd» to Assist — a voice satellite, the phone app,
the dashboard — and Vivavoce answers with *what actually started playing*.

It is one blueprint,
[`blueprints/vivavoce_assist.yaml`](blueprints/vivavoce_assist.yaml), plus one
block in `configuration.yaml`. Nothing is replaced and no integration is
disabled; uninstalling is deleting one automation.

**1. Add the REST command** to `configuration.yaml` (this is the part a
blueprint cannot ship, because `rest_command` is configured in YAML):

```yaml
rest_command:
  vivavoce_command:
    url: "{{ base_url | trim | regex_replace('/$', '') }}/api/v1/command"
    method: post
    content_type: "application/json"
    verify_ssl: false          # the server's certificate is self-signed
    timeout: 20
    payload: >-
      {"text": {{ text | to_json }}, "lang": {{ lang | to_json }},
       "conversation_id": {{ conversation_id | to_json }},
       "player": {{ player | to_json }}}
```

`verify_ssl: false` is not laziness: Vivavoce serves HTTPS with the certificate
it generates for itself, the same one your browser asks you to accept once.
Home Assistant is talking to a machine on your own LAN, over a name you typed.
Restart Home Assistant (or **Developer tools → YAML → All YAML configuration**).

**2. Import the blueprint.** **Settings → Automations & scenes → Blueprints →
Import blueprint**, and paste:

```
https://github.com/LucaBon/vivavoce/blob/main/blueprints/vivavoce_assist.yaml
```

Or copy the file to `config/blueprints/automation/vivavoce/` yourself and
reload automations.

**3. Create the automation** from the blueprint. One setting matters: the
**Vivavoce server** URL. `https://localhost:8730` is right on Home Assistant
OS/Supervised with the Vivavoce app installed — the app runs in the host
network namespace, so `localhost` really is the same machine, and its default is
`https: true` on port 8730. Anywhere else, including a plain Docker Home
Assistant (which is usually bridged), use `https://<ip>:8730`. Use `http://`
only if you started the server with `VIVAVOCE_HTTPS=0`. Leave **LMS player** empty unless you have
several players and want this automation pinned to one — that is the multi-room
Pro feature.

Say «metti Comfortably Numb dei Pink Floyd». If two songs genuinely match,
Vivavoce reads them out and you answer «la 2» — and on a voice satellite it is
meant to ask out loud and wait, which is the one part of this that has not been
tried on real hardware (see the limit below).

#### What it takes over, and what it leaves alone

Home Assistant tries sentence triggers **before** its own intents, so the split
is decided by the list of sentences in the blueprint and by nothing else.

**Vivavoce takes**: playing by title, artist, album, playlist, radio,
favourites and mood; the numbered "which one did you mean?" and its answer
(«la 2» … «la 5», and the ordinals); adding to the queue and clearing it;
"what's playing", «quali album ho di X» and «quali brani di X»; the music sleep
timer; the kid-safe blocklist. In Italian and English only.

Each of those sentences was checked against the grammar in
`localvoice/lang/`, and phrasings the engine does not parse are deliberately
**not** claimed — «che brano è questo», «quali album hai di X», «what songs by
X». A sentence claimed but unparsed is worse than one never claimed: the trigger
beats Home Assistant's own intent, and the phrase then dies as a failed library
search instead of being answered by whoever could.

**Home Assistant keeps everything else**, and that deliberately includes
**transport** — pause, resume, next, previous, volume. Home Assistant covers
those in both languages already, and covers them *better*, because its version
knows which room you are in and Vivavoce's would always reach one configured
player. Taking "pause" would also have stopped your television.

**Search is the opposite case, and it is why this blueprint exists.** Home
Assistant's built-in `HassMediaSearchAndPlay` starts the first result without
asking, cannot filter by artist — and, checked in the 2026.8 intent packs, **is
not in the Italian pack at all**. In Italian there is no built-in music search
to coexist with; in English there is one that guesses.

A few overlaps are known and accepted, all of them consequences of «metti X»
and "play X" being the ordinary way to ask for music, which leaves no way to
narrow them:

| You say | Vivavoce answers | Say this instead for Home Assistant's |
|---|---|---|
| «metti in pausa la musica» | pauses, but on its own player | «pausa la musica» |
| «metti un timer di 5 minuti» | "no such song" | «imposta un timer di 5 minuti» |
| «metti in pausa il timer» | "no such song" | «pausa il timer» |
| "play the previous song" | searches for a song by that name | "previous track" |

Nothing is lost in any of them — each has a phrasing that reaches Home
Assistant — but they are worth knowing before you wonder why.

#### The limit worth knowing before you install it

A conversation opened by a sentence trigger **cannot hold the turn open** —
Home Assistant's trigger result has no way to say "I am waiting for an answer".
So "which one did you mean?" is a real back-and-forth only on an
`assist_satellite`, which has `ask_question`. From the phone app or the
dashboard, Vivavoce reads the numbered list and the turn closes; you answer by
starting a new one, which is why «la 2» is a sentence the blueprint listens for.

**And that satellite branch is the one part of this that has not been run on
real hardware.** Its templates are checked — against Home Assistant's own
template engine and the real schema of `assist_satellite.ask_question` — but
nobody here owns a voice satellite, so whether Home Assistant is happy to make
a satellite ask a question while that same satellite's pipeline is waiting on
this automation is unproven. If it misbehaves, the failure is contained: you
get the numbered list read out and the turn closes, exactly as on the phone.
Please [open an issue](https://github.com/LucaBon/vivavoce/issues) if you try
it — that report is the only way this line gets to change.

### Without Docker

```bash
uv sync
uv run python localvoice/server.py            # auto-discovers LMS on the LAN
# or pin it:  uv run python localvoice/server.py --lms http://<IP-LMS>:9000
```

Open `http://<this-pc-ip>:8730` from a phone/tablet/PC on the same network → tap the mic
and speak, or type. The player is auto-detected (override with `--player <MAC>`).

### Microphone from other devices = HTTPS required

The browser mic works without a certificate only on `localhost`. From a phone the browser
requires **HTTPS**. Generate the certificate and start in HTTPS:

```bash
uv run python tools/make_cert.py     # writes ca.pem + cert.pem/key.pem (SAN = this PC's IP)
uv run python localvoice/server.py --cert cert.pem --key key.pem
# open https://<this-pc-ip>:8730  (accept the warning once)
```

`make_cert.py` creates a private **"Vivavoce Local CA"** (reused on every rerun)
and signs the server certificate with it. You can stop at the one-time browser
warning — everything works as before — or go one step further:

**Install the CA once per device → green lock + installable app.** You do not
have to follow this from here: open the page on the device itself and the
*"📱 Installa come app"* panel walks you through it. It opens by itself when
the certificate is not trusted, shows the steps for **that** device only
(Android, iPhone/iPad, Windows, macOS, Linux), and — this is the part that
used to be missing — **checks for you that it worked**. That check is not a
guess: a browser refuses to register a service worker on an untrusted
certificate even after you click through the warning, so if the service worker
registers, the CA is genuinely installed. Which is also why the CA is what
makes *Install app / Add to Home Screen* give a real fullscreen PWA with an
offline shell.

Re-issuing the server cert for new IPs reuses the CA, so devices stay trusted.
The server offers the CA at **`/ca.pem`**; `GET /tls` says whether there is one
to offer.

The **text box works everywhere**, even over HTTP.

#### Or skip the warning entirely: a real certificate

Installing a CA is a per-device chore, and on some managed or work phones it is
not permitted at all. If you already own a domain, ACME (Let's Encrypt) gives a
certificate every browser trusts with nothing to install anywhere — including
the ones where the CA route is blocked.

The catch is that it cannot be done from inside this app, which is why it is
documented rather than implemented: a LAN server has no public address, so the
HTTP-01 challenge cannot reach it. The route that does work is **DNS-01**, and
it needs three things this project deliberately does not have — a domain, API
credentials for its DNS provider, and a renewal job. Vivavoce would also have
to grow an ACME client (a runtime dependency, against the stdlib-only rule) or
shell out to one.

So it stays a documented recipe, with the ACME client outside the app:

1. Own a domain and point a name at the server's **LAN** address —
   `vivavoce.example.com → 192.168.1.20`. Public DNS pointing at a private IP
   is fine and common; nothing outside your network can reach it.
2. Get a certificate over **DNS-01** with your provider's plugin, e.g.
   `certbot certonly --dns-cloudflare -d vivavoce.example.com`. No inbound
   port, no port forwarding, nothing exposed.
3. Start the server with it:
   `--cert /etc/letsencrypt/live/vivavoce.example.com/fullchain.pem
   --key .../privkey.pem`, and open the page at that **name** (not the IP —
   the certificate is for the name).
4. Renew on a timer (certbot installs one) and restart the server after.

Trade-offs, honestly: 90-day certificates that must keep renewing, DNS API
credentials on the machine, and a dependency on your domain and DNS provider
staying put — against never touching a device again. The local CA has none of
those and costs one install per device. Neither is wrong; households with a
domain already will find the second obviously better, and everyone else the
first.

With a real certificate the page's panel simply reports the certificate as
trusted and asks for nothing — there is no local CA to install, and it does not
invent one to offer.

### Local speech recognition (Pro, optional)

By default the mic uses the browser's speech engine, which sends the audio to
Google (Chrome) or Apple (Safari) for transcription — the one non-local step in
the whole app. Installing the optional **asr** group moves transcription onto
*your* server with [faster-whisper](https://github.com/SYSTRAN/faster-whisper):
the page records the command and POSTs it to `/transcribe`, and no audio ever
leaves the LAN. A new settings switch («🎙 riconoscimento vocale locale»)
appears once the server reports the engine installed; the browser engine stays
the default and the automatic fallback if a transcription fails.

```bash
uv sync --group asr                      # the core stays dependency-free without it
uv run python localvoice/server.py       # "Riconoscimento vocale locale attivo"
```

- **Needs a 64-bit OS.** x86-64 and **aarch64** (a Raspberry Pi 4/5 running a
  64-bit image) are fine. On a **32-bit** system — Raspberry Pi OS's 32-bit
  image, still the default download for older Pis — this group **cannot be
  installed at all**: faster-whisper rests on CTranslate2 and onnxruntime, and
  neither has ever published a 32-bit wheel, on any release. Nor does
  [piwheels](https://www.piwheels.org), the extra index Raspberry Pi OS
  configures by default. `uv sync --group asr` fails outright rather than
  degrading quietly, and the server says why at startup. Same hardware with a
  64-bit image: everything works — CI installs this group and loads the
  native libraries on a real aarch64 runner on every push. The core app is
  stdlib-only either way, so a 32-bit box still runs Vivavoce — just with the
  browser's speech engine.
- **Model & RAM**: `--asr-model` or `VIVAVOCE_ASR_MODEL`. The default is
  **RAM-aware**: on machines with ~4 GB or more, `small`; on smaller boxes
  local recognition **stays off** unless you set a model explicitly. That's a
  measured call, not caution: `tiny` and `base` transcribe pure-Italian
  commands perfectly but mangle English song titles («Comfortably Numb» →
  "fatta blina") — and titles are the whole point — while `small` peaks at
  ~1 GB, which a 2 GB box running OS + LMS doesn't have. If you're on 2 GB
  and mostly speak transport/volume commands, `--asr-model tiny` (~300 MB)
  is a reasonable opt-in. Check your total RAM in Daphile's settings page —
  remember the OS and LMS live in the same total. Runs int8 on CPU, no GPU
  needed. The model is downloaded once, on the first transcription, into the
  data directory (`asr-models/`), so in Docker it lands in the persistent
  volume.
- **Docker**: build the ASR variant with
  `docker build --build-arg ASR=1 -t vivavoce:asr .` (adds ~600 MB to the
  image), or add the build arg under `build:` in your compose file. The
  standard image ships without it and reports `/asr` as unavailable.
- **Home Assistant app**: the published app image doesn't include the
  engine (it would double its size for everyone). If you want it on HA, build
  the app locally with the same `ASR=1` build arg, or run the ASR Docker
  image alongside HA.
- **Hardware expectations**: with the default `small` model, a 3–5 s spoken
  command transcribes in roughly **2–4 s on an Intel N100 / Raspberry Pi 5**
  class box, using ~0.7–1 GB of RAM during the call (nothing while idle:
  the model loads lazily on first use, which also adds a one-time delay).
  `base` roughly halves latency and memory at some accuracy cost — a good
  fit for a Pi 4. Language follows the page's mic-language selector (it/en).

### Server-side wake word (Pro, optional)

The default "activate with a keyword" mode listens continuously through the
browser's speech engine — which on Android plays an audible tone every few
seconds when the recognizer restarts, the single most-cited complaint in
launch feedback, and a browser limitation the default mode can't route
around. Installing the optional **wakeword** group offers an alternative:
the browser streams raw microphone audio to the server, which runs
[openWakeWord](https://github.com/dscripka/openWakeWord) (CPU, a tiny ONNX
model, no GPU) continuously — no restart cycle, no beep, and the audio never
leaves the LAN either (an improvement over the default mode, which — like
the browser mic elsewhere in the app — sends audio to Google/Apple). A new
settings switch («🔈 parola chiave lato server») appears once the server
reports the engine installed.

```bash
uv sync --group wakeword                 # deliberately its own group, not "asr" — see below
uv run python localvoice/server.py       # "Parola chiave lato server attiva"
```

- **Needs a 64-bit OS.** x86-64 and **aarch64** (a Raspberry Pi 4/5 running a
  64-bit image) are fine. On a **32-bit** system — Raspberry Pi OS's 32-bit
  image, still the default download for older Pis — this group **cannot be
  installed at all**: openWakeWord rests on onnxruntime, which has never
  published a 32-bit wheel on any release. [piwheels](https://www.piwheels.org),
  the extra index Raspberry Pi OS configures by default, doesn't save it
  either: it carries armv7l builds of scipy and scikit-learn (openWakeWord's
  other compiled dependencies) but none of onnxruntime. `uv sync --group
  wakeword` fails outright rather than degrading quietly, and the server says
  why at startup. Same hardware with a 64-bit image: everything works —
  CI runs the real openWakeWord model against real audio frames on an aarch64
  runner on every push — and a 32-bit box still gets the browser's own wake
  word, beep and all.
- **Fixed phrase, English only.** openWakeWord ships pretrained models for a
  handful of English phrases; it has no support for an arbitrary typed
  phrase like the default mode's free-text field, and training a custom
  model (e.g. an Italian "vivavoce") needs a separate offline pipeline this
  project doesn't provide today. The default and only currently supported
  phrase is **"hey jarvis"** (`--wakeword-model` / `VIVAVOCE_WAKEWORD_MODEL`
  if a future release ships another bundled model). This is offered as an
  *additional* choice next to the free-text browser wake word, not a
  replacement — pick whichever trade-off fits: your own phrase with the
  Android beep, or a fixed English phrase without it.
- **Why its own dependency group.** `openwakeword` is pinned to an exact,
  deliberately old version (`0.4.0`): every release from 0.5.0 on requires
  `tflite-runtime` on Linux, which has no published wheel past Python 3.11 —
  bundling it into the `asr` group would have broken `uv sync --group asr`
  (and the already-working local-ASR feature with it) for anyone on a
  current Python. Kept separate, a failure here can't touch that.
- **Docker**: build the variant with
  `docker build --build-arg WAKEWORD=1 -t vivavoce:wakeword .`. The standard
  image ships without it and reports `/wakeword` as unavailable; combine
  with `--build-arg ASR=1` if you want both.
- **Not available on the Home Assistant app**, for the same reason local
  ASR isn't (see above).
- **What this hasn't been tested against**: the browser-to-server audio
  pipeline is covered by the test suite (including a real headless-browser
  capture test), but real acoustic detection accuracy, the sub-second
  wake-to-listening latency, and "truly no beep" can only be confirmed on
  real Android hardware — try it and see how it holds up on yours.

### Autostart

- **Docker:** nothing to do — `restart: unless-stopped` in the compose file already
  restarts the container on boot and on failure.
- **Windows:** `tools/run_local.ps1` (starts HTTPS, generates the cert if missing) and
  `tools/install_autostart.ps1` (scheduled task at logon + firewall rule; run **as
  Administrator**). `tools/uninstall_autostart.ps1` removes it.
- **Linux** (Raspberry Pi / mini-PC): `deploy/vivavoce.service` (systemd). Copy to
  `/etc/systemd/system/`, adapt `WorkingDirectory`/paths, then
  `sudo systemctl enable --now vivavoce`.

### Using it from a phone
1. Same Wi-Fi as the server PC.
2. Open **Chrome/Edge** at `https://<this-pc-ip>:8730`.
3. First time: "connection not private" (self-signed cert) → **Advanced → Proceed**, once.
4. The page opens the *"📱 Installa come app"* panel by itself, because it can tell the
   certificate is not trusted. Follow its two steps — they are the ones for **your**
   phone, not a list of four platforms — then tap **"L'ho installata — ricontrolla"**:
   the page reloads and tells you whether it worked. After that: green lock, no
   warnings, and **Install app / Add to Home Screen** gives a fullscreen app icon.
   (Prefer a certificate no device has to trust? See *"Or skip the warning entirely"*
   above.)
5. Tap the **mic**, allow the permission, speak in Italian — or use the text box. The
   reply shows on screen (silent by default). When the reply offers a numbered list, its
   choices appear as **tappable buttons** — tap instead of saying "metti la 2".
6. Optional, hands-free: tick **"attiva a voce con una parola chiave"** and start commands
   with the wake word ("vivavoce" by default) — «vivavoce metti Time».
7. Want the reply read aloud too? Tick **"🔊 leggi la risposta ad alta voce"**; the
   **Voci & lingue** panel then lets you pick natural per-language voices.

### Streaming services (TIDAL / Qobuz)

Install and log in the plugin(s) on LMS/Daphile first (**LMS Settings → Plugins**:
*TIDAL* and/or *Qobuz*). Then:

By default the server **auto-detects** the installed plugins and the
page's "Sorgente musica" selector only shows what's really there. Override with
`--services tidal,qobuz` (skips detection) and pick which one "auto" mode falls
back to with `--default-service qobuz`. Spoken phrases «da tidal …» / «da qobuz …»
always win over the selector. (Docker needs nothing: detection is the default.)

> [!NOTE]
> Qobuz support is verified against a live LMS 9.0.3 + plugin-Qobuz 3.7.0. If the
> plugin's **login fails with "authorization failed"** despite correct credentials:
> Qobuz has been tightening third-party authentication (mid-2026) and the
> email+password login can 401 intermittently — make sure the account has a real
> password (accounts created via Google/Apple sign-in need one set on qobuz.com),
> then simply retry a few times; once a login succeeds the stored token keeps
> working. To debug, set `plugin.qobuz` to Debug in LMS Settings → Advanced →
> Logging (and set it back afterwards: at Debug level the plugin writes your
> password's MD5 hash into server.log). To validate the Vivavoce side, run
> `uv run python tools/probe_lms.py --service qobuz --query "Pink Floyd"`.

---

## Updating
Running the published image: `docker compose pull && docker compose up -d`, or
`docker pull ghcr.io/lucabon/vivavoce:latest` and recreate the container. Your
`/data` volume — certificate, licence, kid-safe list — is untouched by an
update. Home Assistant: update the app. Working from a checkout: edit files
in `engine/`/`localvoice/` and restart the server.

## Audio quality
Vivavoce sends **only commands**: audio flows LMS → Squeezelite (Daphile) →
DAC as always, so hi-res quality is unchanged. Make sure LMS doesn't resample to the player.
