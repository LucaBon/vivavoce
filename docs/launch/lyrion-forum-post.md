# Lyrion forum launch post — draft

> Post to: forums.lyrion.org → 3rd party software. Title suggestion:
> **[ANNOUNCE] Vivavoce — say a song, the exact song plays (local web app, IT+EN, TIDAL/Qobuz)**
>
> **Before posting, two things only Luca can fill:**
> 1. the Lemon Squeezy checkout link (marked `<<LEMON SQUEEZY LINK>>` below —
>    the same URL also has to replace `PRO_STORE_URL` in
>    `localvoice/static/js/pro.js`, which still points at a placeholder);
> 2. 2–3 screenshots (`tools/shots/`) and ideally a 20-second GIF of
>    "metti Comfortably Numb dei Pink Floyd" → playing.
>
> The repo link is filled in. Everything else here matches what ships.

---

Hi all — long-time LMS household here. I built the thing I couldn't find
anywhere: **actually starting music by voice**, not just pause/skip.

**Vivavoce** is a small web app that runs next to your LMS. One command, no
clone, no build:

```
docker run -d --network host --restart unless-stopped \
  -v vivavoce-data:/data ghcr.io/lucabon/vivavoce:latest
```

(Home Assistant add-on and plain Python work too.) You open it on any
phone/tablet on your LAN, tap the mic (or type), and say:

- *"play Comfortably Numb by Pink Floyd"* → plays **that** recording, from
  your library or TIDAL/Qobuz (it detects which plugins you have);
- *"which albums do I have by Yes"* → reads the top 3, you say *"play number
  2"* or just tap the button;
- *"add X to the queue"*, *"play X next"*, *"what's in the queue"*,
  *"play my favourites"*, *"play the radio X"*;
- *"play X in the kitchen"*, *"turn off in 30 minutes"*;
- when several songs genuinely match, it **asks** instead of silently playing
  the wrong one. Matching is deterministic (rules + scoring, ~735 tests, no
  LLM, no cloud in the loop) — audio keeps flowing LMS → player, bit-perfect.

It speaks **Italian and English** (parsing and replies follow the language you
pick). There's a now-playing card with artwork, but for browsing it
deliberately links out to Material Skin instead of reinventing it.

**The honest bits**, because you'd find them anyway:

- By default the mic uses the browser's speech engine, so Chrome sends the
  audio to Google (Apple on iOS) for transcription. If that's a dealbreaker,
  there's now a switch: **local speech recognition** runs Whisper on your own
  server and the audio never leaves the LAN. It's an optional install
  (`--group asr`) and needs a 64-bit OS — a 64-bit Pi 4/5 is fine, a 32-bit
  image is not, and DEPLOY.md says exactly why.
- Wake-word mode on Android used to beep at every listen restart — a browser
  limitation and the most-cited complaint I got. There's now a **server-side
  wake word** (openWakeWord on the server, CPU only) that has no beep at all.
  Trade-off stated upfront: it hears a fixed English phrase ("hey jarvis"),
  not the free-text keyword, so it's offered *alongside* the browser engine
  rather than replacing it.
- The mic needs HTTPS, which means a certificate warning on a home LAN. The
  app now walks you through installing the local CA — steps for *your* device
  only, and it checks by itself that it worked. If you already own a domain,
  DEPLOY.md documents the ACME route that needs no install on any device.
- Nothing else ever leaves your LAN: no telemetry, no accounts. When it
  mishears something there's a "report this phrase" button that saves the
  report **on your device** and opens a pre-filled GitHub issue you can read
  before sending — nothing is sent by itself. (Full PRIVACY.md in the repo.)

**Model**: the core is free and **open source (AGPL)** — typed commands, all
the search/playback, transport, now-playing, queue, favourites. The hands-free
extras (mic, wake word, read-back voices, local speech recognition, multi-room,
PIN-protected kid-safe) are a one-time **Pro license: 11,90 €, launch price
8,90 €** for the household, up to 5 devices, no subscription, works offline
forever.

**Every install starts with 14 days of full Pro**, microphone included — no
key, no card, no account, and no network call: it's a timestamp in the data
directory. When it ends nothing breaks and nothing is deleted, you're just back
to typed commands. And if you buy and change your mind, Lemon Squeezy refunds
within **14 days, no questions asked** — I never see your payment data.

The license check is deliberately trust-based and unobfuscated — the key is
simply how you keep the project alive. This community runs on donations and
fair one-time apps (Material, iPeng, Orange Squeeze); I tried to price it in
that same spirit.

- Repo & docs: **https://github.com/LucaBon/vivavoce**
- Pro license: **<<LEMON SQUEEZY LINK>>** (launch price applied automatically)

I'd genuinely love your first impressions — especially misheard phrases (the
matching is deterministic, so one phrase is usually enough to reproduce and
fix). What I'm weighing next: a **Home Assistant Assist integration** so you
can use it from HA's own voice pipeline, **German** as a third language, and
better handling of vague requests ("play something relaxing"). Which of those
would actually matter to you?
