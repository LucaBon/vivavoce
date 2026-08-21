# Privacy

Vivavoce runs **in your home**. This page lists, exhaustively, every way data
moves — including the one part that is *not* local.

## The one honest caveat: browser speech recognition

The microphone uses the browser's **Web Speech API**. On Chrome (desktop and
Android) the audio of what you say is sent to **Google's** speech servers for
transcription; on Safari/iOS it goes to **Apple**. This is how the browser
implements speech recognition — Vivavoce receives only the resulting text and
sends **none of it** anywhere.

If you don't want any audio leaving your home:

- use the **text box** (free tier, works everywhere) — fully local;
- turn on **local speech recognition** (Pro, optional install — see
  [DEPLOY.md](DEPLOY.md)): a Whisper model on *your* server transcribes the
  mic audio you send by tapping the mic or after a wake word fires, so that
  voice goes browser → your machine and no further. The only network touch
  is the one-time model download (listed below). On its own, this does
  **not** change how the wake word itself is *detected* — see the next
  bullet for that;
- turn on **server-side wake word** (Pro, a separate optional install, see
  DEPLOY.md — a fixed English phrase, not the free-text one): this is the
  one that changes wake-word *detection* specifically — the continuous-
  listening audio goes to *your* server instead of the browser's speech
  engine. Every model it uses ships inside the package, so there is no
  download at all, not even a one-time one.

Without the server-side wake word install specifically, the wake word's
continuous listening relies on the browser engine (Google/Apple, as above)
even if local speech recognition is installed — the two are separate
installs for separate parts of the pipeline.

## What stays on your LAN

- Every command, transcript, search and playback request: browser → Vivavoce
  server (your machine) → your LMS. Nothing is proxied through any cloud.
- The kid-safe blocklist and its PIN (hashed, PBKDF2-SHA256): a JSON file in
  the server's data directory.
- No telemetry, no analytics, no accounts, no cookies beyond `localStorage`
  preferences on your own devices.
- The **"report a misunderstood phrase"** button stores the report on your
  device only and — only when you tap it — opens a pre-filled GitHub issue in
  your browser for you to review and submit. The app itself sends nothing.

## The only outbound connections

1. **Pro license activation** — when *you* enter a key, one HTTPS request to
   `api.lemonsqueezy.com` (the merchant of record). The response is cached in
   `license.json` in the data directory: the key (shown masked in the UI),
   an instance id, and timestamps. Nothing else is sent.
2. **License re-validation** — at most **once a week**, at server startup, the
   cached key is re-checked. A network failure changes nothing (an offline
   household keeps Pro forever); only a definitive "disabled/refunded" answer
   turns Pro off. Opt out entirely with `VIVAVOCE_NO_REVALIDATE=1`.
3. **Album artwork** — fetched by the server from your LMS (or from the URL
   your streaming plugin reports) and proxied to the page.
4. **Whisper model download** — only if you enable local speech recognition:
   the first transcription downloads the chosen model once from Hugging Face
   into the data directory. After that it loads from disk, fully offline.

## Payments

Purchases happen on **Lemon Squeezy** (merchant of record): they process the
payment, handle EU VAT and invoices, and store your payment data under
[their privacy policy](https://www.lemonsqueezy.com/privacy). Vivavoce never
sees your payment details — only the license key works locally.

## Questions

Open an issue: https://github.com/LucaBon/vivavoce/issues
