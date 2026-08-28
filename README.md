# 🎵 Vivavoce

[![CI](https://github.com/LucaBon/vivavoce/actions/workflows/ci.yml/badge.svg)](https://github.com/LucaBon/vivavoce/actions/workflows/ci.yml)

> Say **«metti Comfortably Numb dei Pink Floyd»** — and the *exact* song plays on your hi-fi.

**Hands-free voice control — in Italian, English, French or German — for a [Daphile](https://www.daphile.com/) /
[Lyrion Music Server](https://lyrion.org/) (LMS / Squeezebox) system — TIDAL and
Qobuz included.**
No cloud required, no LLM, no compromise on sound: Vivavoce sends **only control
commands**, while the audio keeps flowing LMS → Squeezelite → your DAC, bit-perfect.

```text
You:  «vivavoce, metti Comfortably Numb dei Pink Floyd»
App:  «Riproduco Comfortably Numb di Pink Floyd.»

You:  «metti Love»
App:  «Quale intendi? 1: Love di Lana Del Rey, 2: Love di John Lennon, 3: …»
You:  «la 2»            ← or just tap the "2" button on screen
App:  «Riproduco Love di John Lennon.»
```

## The idea

Great visual apps for this ecosystem already exist — Vivavoce deliberately does
**not** reinvent browsing, queueing, or now-playing. It's a **companion**:

- 👀 **See & touch** with **[Material Skin](https://github.com/CDrummond/lms-material)**
  (web) or **[Squeezer](https://f-droid.org/en/packages/uk.org.ngo.squeezer/)** (Android)
  — browse, queue, artwork, multi-room.
- 🗣️ **Speak** with **Vivavoce** — the one thing those don't do well hands-free.

The app is a **local web app** (`localvoice/`) over a tested engine
(`engine/actions.py` + `engine/lms.py`): a browser mic/text page on your LAN
that talks straight to LMS. No cloud, no account.

## Free and Pro

The core is free and open source (AGPL-3.0), forever. A one-time **Pro
license** — **11,90 €** per household (**8,90 €** at launch), no subscription —
unlocks the hands-free features and funds development:

| Free | Pro (one-time license) |
|---|---|
| Typed commands (the text box, works on every device over plain HTTP) | 🎙️ **Microphone** tap-to-talk |
| All search & playback: local library, TIDAL, Qobuz, Spotify, "did you mean" with tappable choices | 🪄 **Wake word** («vivavoce metti Time») |
| Transport, volume slider, sleep timer, now-playing panel with artwork | 🌍 **Multilingual read-back voices** |
| Docker / Home Assistant app / bare Python, HTTPS + PWA install | 🧒 **Kid-safe**: PIN-protected blocklist, enforced server-side for every device *asking Vivavoce*[^kidsafe] |
| Updates | 🛋️ **Multi-room**: room selector + «metti X **in cucina**» voice targeting |
| | 🏠 **Local speech recognition**: Whisper on *your* server — mic audio never leaves the LAN |
| | Future Pro features — and priority on your feedback |

[^kidsafe]: To be exact about what it covers, because a child-safety promise
    deserves it: the blocklist is enforced on the server, so it holds for
    every phone, tablet and PC that asks *Vivavoce* — no browser setting or
    cleared storage gets around it. It is not a lock on the hi-fi: LMS's own
    web UI, Material Skin and apps like Squeezer talk to LMS directly and
    never pass through here, so they can still play anything. Kid-safe makes
    the voice assistant safe to hand to a child; it does not make the whole
    system child-proof.

**Every install starts with 14 days of full Pro**, microphone included — no
key, no card, no account. The window opens the first time the server starts
and is stored next to the license, so it cannot be re-armed by clearing the
browser. When it ends nothing breaks and nothing is deleted: you are back to
the free column, which is the whole left-hand side of that table.

Activation is once, online, from the page settings (sold via Lemon Squeezy,
which handles VAT/invoices); after that the license is cached locally and
**works offline forever** — there is no phone-home requirement. The license
check is deliberately simple and unobfuscated: the key is how you support the
project ([the honest details](licenses/PRO-EULA.md)).

## Why it doesn't play the wrong song

The whole point: *say a song and the exact song plays* — or you get an honest
question, **never a silent wrong pick**. Matching is deterministic (rules + scoring,
no LLM), so behaviour is testable and repeatable.

| | |
|---|---|
| 🧠 **Title / artist / album parsing** | "metti Comfortably Numb **dei** Pink Floyd" → title + artist; "… **dall'album** X" → album. |
| 🎯 **Artist-aware ranking** | Streaming results are read in *menu mode*, which carries the **artist** — so among three "Comfortably Numb" it plays *Pink Floyd's* edition and confirms it out loud. |
| 🎼 **Three streaming services** | **TIDAL**, **Qobuz** and **Spotify** (plus your local library): pick one in the page's source selector — it only lists the plugins your LMS actually has — or just say «da qobuz metti …» (or «metti … da qobuz»). If one of them is logged out, the request goes to a service that isn't, and the reply says which one played. "Auto" tries your library first, then the default service. Spotify goes through the *Spotty* plugin, needs **Premium**, and is 320 kbps Ogg rather than lossless; see the caveats. |
| ❓ **"Did you mean" (top 3)** | When genuinely different songs match, it reads back the top three and you answer «metti la 2» — the choices are also **tappable buttons**. Exact matches just play; junk never wins. |
| 📀 **Local library scored too** | A generic word like "love" never plays an unrelated album, and "aerosmith" plays the *artist*, not a random album. |
| 👂 **Mishearing resilience** | The web app tries the browser's alternative transcriptions until one hits (English names that it-IT often mangles). |
| 🏠 **Local speech recognition (Pro)** | By default the mic uses the browser's engine (audio goes to Google/Apple — the one non-local step). One switch in settings moves transcription to a **Whisper** model on your own server instead: voice never leaves your LAN. Optional install, see [DEPLOY.md](DEPLOY.md). |
| 🛋️ **Multi-room (Pro)** | With more than one player, pick the room in settings — or retarget a single command by voice: «metti Time **in cucina**», «pausa in salotto». A follow-up «metti la 2» stays in that room. |
| 😴 **Sleep timer** | «spegni tra 30 minuti» · «stop in half an hour» · «annulla il timer» — the LMS native sleep, armed by voice. |
| 🪄 **Wake word (web app)** | Optionally arm a spoken keyword ("vivavoce" by default): «vivavoce metti Time» — no touching the screen. Off by default; otherwise the mic is tap-to-talk. |
| 🌍 **Natural multilingual read-back** | Optional, off by default (the transcript is on screen). When on, the Italian frame is spoken by an Italian voice and the title/artist in *their* language (English/Spanish/French/German), with the best natural voices your browser offers — pickable in settings. |

## Quick start — local web app

Prereqs: an LMS/Daphile on the LAN with the TIDAL, Qobuz and/or Spotty plugin installed
and logged in, and at least one active player.

**With Docker** (Linux / NAS / Raspberry Pi — easiest, HTTPS included):

```bash
docker compose up -d
# open https://<this-host-ip>:8730 from a phone/tablet/PC on the same network
# (accept the self-signed certificate warning once — the mic then works)
```

**As a Home Assistant app**: add this repo's URL under *Settings → Apps → App
store → ⋮ → Repositories* (before Home Assistant 2026.2, when apps were called
add-ons: *Settings → Add-ons → Add-on store*), then install **Vivavoce** — see
[DEPLOY.md](DEPLOY.md).

**…and then talk to it through Assist**: import
[`blueprints/vivavoce_assist.yaml`](blueprints/vivavoce_assist.yaml) and say
«metti Comfortably Numb dei Pink Floyd» to a voice satellite, the phone app or
the dashboard — the answer names the song that actually started. Home Assistant
keeps everything Vivavoce doesn't claim, and uninstalling is deleting one
automation. Setup:
[DEPLOY.md](DEPLOY.md#home-assistant-voice--talking-to-vivavoce-through-assist).


**Without Docker** (Python ≥ 3.9 + [uv](https://docs.astral.sh/uv/)):

```bash
uv sync
uv run python localvoice/server.py          # auto-discovers LMS on the LAN
# open http://<this-pc-ip>:8730 from a phone/tablet/PC on the same network
```

Then say (or type), in Italian — or in English, French or German, after
picking the mic language on the page (the page labels are Italian or English;
a French or German session gets its answers inside the English page):

> «metti Comfortably Numb dei Pink Floyd» · «metti l'album The Wall» ·
> «dalla mia musica metti Aerosmith» · «da qobuz metti Time» · «metti Time da qobuz» ·
> «quali album ho di Yes» → «metti la 2» ·
> «pausa» · «alza il volume» · «cosa sta suonando» ·
> «spegni tra 30 minuti» · «metti Time in cucina»

> [!NOTE]
> The browser microphone needs **HTTPS** when used from another device — the Docker
> image sets this up automatically (certificate generated once into a volume);
> without Docker, start the server with a certificate (`--cert/--key`, auto-generated
> by the helper scripts). Install the generated **local CA** once per phone (page
> panel *"📱 Installa come app"*) for a green lock and a real **installable PWA**.
> The **text box works everywhere**, even plain HTTP. Full setup — Docker, HTTPS,
> autostart on Windows/Linux — is in **[DEPLOY.md](DEPLOY.md)**.

There's a link to Material Skin right in the page for when you want to browse visually.

## Repo layout

| Path | What |
|---|---|
| `engine/actions.py` | Voice-action business logic (matching, ranking, did-you-mean) |
| `engine/lms.py` | LMS JSON-RPC client + TIDAL search/playback |
| `engine/discovery.py` | LMS LAN auto-discovery (UDP) |
| `engine/blocklist_store.py` | Kid-safe blocklist (store contract) |
| `localvoice/` | Local web app: `server.py`, `router.py`, `index.html` |
| `tools/probe_lms.py` | Validate search/playback against a real LMS |
| `tests/` | pytest suite (simulated LMS transport, no network) |
| `RELEASING.md` | How to cut a release (the version lives in two files + a tag) |
| `docs/api.md` | The HTTP API: `POST /api/v1/command` for external clients, and what every other route is |
| `tests/conftest.py` | Shared fakes + `live_server` (the real handler on a port) |

## Tests

```bash
uv run pytest        # 531 tests, no network — uses a simulated LMS transport
```

Every push and pull request runs the suite on Python 3.9–3.14 (plus one Windows
job, for the `%APPDATA%` branch), byte-compiles every module, and builds the
Docker image — see [`.github/workflows/ci.yml`](.github/workflows/ci.yml).

Validate against a real LMS (read-only, or `--play` to actually play):

```bash
uv run python tools/probe_lms.py --query "Comfortably Numb dei Pink Floyd"
uv run python tools/probe_lms.py --service qobuz --query "Pink Floyd"
```

## Honest caveats

- **The voice interface speaks Italian, English, French and German.** Pick the
  mic language on the page — commands are parsed and answered in that language.
  The page labels are Italian or English only, so a French or German session
  gets its answers inside an English page. Other languages fall back to Italian
  for now. The French and German phrasings have not yet been reviewed by a
  native speaker.
- **Wake-word mode on Android beeps**: the browser plays its own earcon every time
  continuous listening restarts — a platform behaviour Vivavoce can't silence
  (the app warns about it in-page).
- Streaming free-text search quality depends on the plugin; matching is deterministic
  (no LLM). Natural TTS voices depend on your device/browser.
- **Qobuz login on LMS can be flaky**: Qobuz has been tightening authentication
  for third-party clients (mid-2026), so the plugin's email+password login may
  fail with 401 a few times before it sticks — retry, or check the
  troubleshooting notes in DEPLOY.md. Once logged in, the stored token keeps
  working. (Vivavoce's Qobuz support itself is verified against a live
  LMS 9 + plugin-Qobuz 3.7.0.)
- **Spotify is supported, and needs Spotify Premium.** Vivavoce drives it
  through the LMS **Spotty** plugin, so «da spotify metti Comfortably Numb»
  works like the other two — but Spotty plays through Spotify Connect, which
  free accounts cannot use, and the plugin refuses to log in without Premium.
  The audio is the second caveat: Spotify Lossless is not delivered to
  third-party Connect clients, so Spotty/librespot still receives lossy Ogg
  Vorbis 320 kbps. On a bit-perfect chain TIDAL or Qobuz is the better source,
  and Vivavoce will not pretend otherwise — it just no longer refuses to reach
  a service you already pay for. One behaviour differs on purpose: Spotify's
  search answers *every* query, gibberish included, where TIDAL and Qobuz
  return nothing. So on Spotify Vivavoce never falls back to "play the top
  result" — for a song, an album, an artist or a playlist alike. If nothing
  matches your words it says so instead of guessing.
- Bit-perfect: Vivavoce sends **only commands**; ensure LMS doesn't resample to the player.

## Privacy, honestly

- **Voice recognition happens in your browser** via the Web Speech API — which
  means Chrome/Android sends the audio to **Google** and Safari/iOS to
  **Apple** for transcription. That is the browser's doing, not ours, and we
  say it plainly. If that bothers you, the **text box** is 100% local.
- Commands go straight to your LMS. No telemetry, no account, no analytics —
  and nothing is logged: the server keeps no access log and writes no audio and
  no transcript to disk, ever.
- Four things do reach the internet, and only these four: the
  **user-initiated** Pro license activation and an at-most-**weekly** license
  re-check (opt out with `VIVAVOCE_NO_REVALIDATE=1`; going offline never
  disables a paid license — the machine's hostname goes along as the
  activation's `instance_name`); album **artwork**, which for TIDAL/Qobuz is
  whatever CDN URL the streaming plugin reports; and, if you turn on local
  speech recognition, the **one-time Whisper model download** from Hugging
  Face.

Full details in [PRIVACY.md](PRIVACY.md).

## What is AI in Vivavoce, and what isn't

Worth being precise about, and the AI Act now expects it (art. 4). The line
falls in an unexpected place:

- **AI:** turning your voice into text. That is a neural speech model — the
  browser's by default (Google's or Apple's, see above), or Whisper on your own
  server with the Pro local-recognition install. The optional server-side wake
  word is a small ONNX classifier listening for one fixed phrase. Reading the
  reply aloud uses your device's own voice synthesis.
- **Not AI:** everything that decides *what you meant*. Once the words are
  text, Vivavoce is rules a person wrote — ordered regexes per language, string
  similarity scoring with fixed thresholds, and a hand-written table of moods
  to music genres. No LLM, no model that learns from you, no profile of you or
  of anyone in your house. It never tries to work out **who** is speaking: the
  kid-safe gate knows only whether *this device* has typed the PIN.

Because it does recognise speech, Vivavoce is an AI system under the EU AI Act
and says so on screen. The full assessment — which articles apply, which don't,
and why — is in [docs/ai-act.md](docs/ai-act.md). Households using it at home
have no obligations of their own under the Act (art. 2(10)).

## Support

Best-effort via [GitHub Issues](https://github.com/LucaBon/vivavoce/issues) —
one-author project, honest expectations in [SUPPORT.md](SUPPORT.md). Refunds
for Pro follow the Lemon Squeezy 14-day policy.

## License

Open-core. The engine, the web server and the free features are **AGPL-3.0**
([LICENSE](LICENSE)). The files under `localvoice/pro/` are proprietary,
covered by the [Pro EULA](licenses/PRO-EULA.md) and unlocked by a one-time
Pro license key. Details in [licenses/README.md](licenses/README.md).

Contributions are welcome on the AGPL core; by opening a PR you agree to the
Developer Certificate of Origin (sign-off), which keeps the open-core split
legally clean.
