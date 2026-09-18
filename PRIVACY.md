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
  DEPLOY.md): this is the one that changes wake-word *detection*
  specifically — the continuous-listening audio goes to *your* server
  instead of the browser's speech engine, and it answers to the phrase you
  typed. The only network touch is the one-time model download at first
  start-up (~47 MB, listed below); after that it needs no network.

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
   `api.lemonsqueezy.com` (the merchant of record). It carries the key and, as
   the activation's `instance_name`, this machine's **hostname** — so you can
   tell your five activations apart. Nothing else: no command, no transcript,
   no usage data. The response is cached in `license.json` in the data
   directory (the key, shown masked in the UI, an instance id, and timestamps).
2. **License re-validation** — at most **once a week**, at server startup, the
   cached key is re-checked. A network failure changes nothing (an offline
   household keeps Pro forever); only a definitive "disabled/refunded" answer
   turns Pro off. Opt out entirely with `VIVAVOCE_NO_REVALIDATE=1`.
3. **Album artwork** — fetched by the server from your LMS (or from the URL
   your streaming plugin reports) and proxied to the page.
4. **Whisper model download** — only if you enable local speech recognition:
   the first transcription downloads the chosen model once from Hugging Face
   into the data directory. After that it loads from disk, fully offline.
5. **Vosk model download** — only if you install the server-side wake word
   (`uv sync --group wakeword-vosk`): at the **first start** after that, the
   model for your wake-word language is downloaded once from
   `alphacephei.com/vosk/models` into the data directory, and unpacked there.
   It carries nothing about you — a language code is the whole request — and
   it happens at start-up rather than lazily because the engine cannot be
   loaded without it. Skip it with `--wakeword-no-download`, or point
   `--wakeword-vosk-model` at a directory you populated yourself. After that
   it loads from disk, fully offline, and no audio ever leaves the machine.

## Payments

Purchases happen on **Lemon Squeezy** (merchant of record): they process the
payment, handle EU VAT and invoices, and store your payment data under
[their privacy policy](https://www.lemonsqueezy.com/privacy). Vivavoce never
sees your payment details — only the license key works locally.

## What the models are

Vivavoce ships no model weights of its own. Which speech models the optional
installs use, where they come from and under which licence:
[licenses/MODELS.md](licenses/MODELS.md). Which parts of the app are AI at all
and what that means under the EU AI Act: [docs/ai-act.md](docs/ai-act.md).

## Questions

Open an issue: https://github.com/LucaBon/vivavoce/issues
