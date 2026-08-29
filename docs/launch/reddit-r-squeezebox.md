# r/squeezebox launch post — draft

> Title: **I built Vivavoce: say "play Comfortably Numb by Pink Floyd" and
> your Squeezebox plays exactly that (local web app, free core + one-time Pro)**
> Flair/format: text post with 2–3 screenshots.
>
> **Before posting:** replace `<<LEMON SQUEEZY LINK>>` (the same URL also has
> to replace `PRO_STORE_URL` in `localvoice/static/js/pro.js`) and attach the
> screenshots. The repo link is filled in.

---

Voice control for LMS that can actually **start** music has always been the
gap — Home Assistant/Music Assistant do transport only, and the certified
Alexa option is subscription + cloud. So I built a local one.

**What it is:** a web app that runs next to your LMS. One command, nothing to
clone or build:

```
docker run -d --network host --restart unless-stopped \
  -v vivavoce-data:/data ghcr.io/lucabon/vivavoce:latest
```

(HA app and plain Python also work.) Any phone on your Wi-Fi opens it, you
tap the mic or type:

- "play Comfortably Numb by Pink Floyd" → the exact track, from your library
  or TIDAL/Qobuz;
- "which albums do I have by Yes" → top-3 list, "play number 2" or tap;
- "add X to the queue" / "play X next" / "what's in the queue" / "play my
  favourites" / "play the radio X" / "play X in the kitchen" / "turn off in
  30 minutes";
- ambiguous match → it asks you, never silently plays the wrong thing.
  Deterministic matching (no LLM), ~735 tests, commands only — your
  bit-perfect chain is untouched.

Works in English and Italian. Now-playing card with artwork; browsing stays
Material Skin's job — your own installed copy, opened *inside* the page so the
mic never leaves the screen. Not a clone and not a fork: the app just serves it
from its own address, because a HTTPS page can't frame a plain-HTTP one.

**Honesty corner:** by default the mic uses the browser's speech engine
(Chrome → Google, iOS → Apple, transcription only). If that bothers you,
there's a switch for **local speech recognition** — Whisper on your own
server, audio never leaves the LAN (optional install, needs a 64-bit OS; a
64-bit Pi 4/5 is fine). Wake-word mode used to beep on every Android restart;
there's now a **server-side wake word** with no beep, at the cost of a fixed
English phrase ("hey jarvis") rather than a custom one — both engines are
offered, pick either. The mic needs HTTPS, so the app walks you through
installing the local CA for *your* device and verifies by itself that it
worked. No telemetry, no account, nothing leaves your LAN.

**Price:** core is free and open source (AGPL) — typing, all search/playback,
transport, now-playing, queue, favourites. Hands-free (mic, wake word,
read-back voices, local speech recognition, multi-room, PIN-protected
kid-safe) is a one-time **Pro license, 11.90 € (8.90 € at launch)** per
household, 5 devices, offline forever, no subscription. The gate is
trust-based and unobfuscated by design.

**You don't have to decide up front:** every install gets
**14 days of full Pro**, mic included, with no key and no card. When it ends
nothing breaks — typed commands keep working. And Lemon Squeezy refunds within
14 days, no questions asked.

Repo: **https://github.com/LucaBon/vivavoce** · Pro: **<<LEMON SQUEEZY LINK>>**

Feedback very welcome — especially phrases it mishears. Next up, and genuinely
undecided: a Home Assistant Assist integration, German as a third language, or
smarter handling of vague requests ("play something relaxing"). Opinions?
