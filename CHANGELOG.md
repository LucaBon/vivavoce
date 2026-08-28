# Changelog

## Unreleased

### New

- **German, the third language.** Pick *Deutsch* as the mic language and
  Vivavoce parses and answers in German: «spiel Time von Pink Floyd», «mach die
  Musik aus», «schalt in 30 Minuten aus», «spiel etwas Entspannendes», «spiel
  Time im Wohnzimmer». One pattern pack (`localvoice/lang/de.py`), one message
  catalog, and a test suite of its own — no other module learned a word of
  German.

  Three things German does that neither Italian nor English does, and each one
  decided a pattern rather than being translated into it:

  * **The verb comes in two pieces.** «leg Time auf», «mach die Musik an» and
    «ich möchte Time hören» wrap the title in a verb and its particle, so the
    plain-verb pattern would have searched for "die Musik an". The split forms
    have their own pattern — the one English already uses for "put Dark Side
    on" — and the plain verbs deliberately do not list «leg»/«mach», which is
    what lets «spiel Wach Auf» keep its "auf".
  * **«mach» heads three different commands.** «mach lauter» is volume, «mach
    aus» is stop, «mach die Musik an» is play. The play reading is recognised
    only *with* its particle, so the other two stay reachable.
  * **The adjective changes sides.** «etwas Entspannendes» puts the mood after
    the marker noun, «etwas entspannende Musik» before it. Both reach the mood
    table; both still require the marker, so «stopp die entspannende Musik»
    keeps stopping the music.

  Not included: the page chrome, which is Italian or English only — a German
  session gets German answers inside an English page. The phrasings have not
  yet been reviewed by a native speaker.

### Fixed

- **Read-back spoke the reply frame with the wrong voice.** The split between
  "the frame" and "the foreign terms" was right; the frame's language was
  hard-coded to Italian, so an English session heard "Playing" and "by" read
  out by an Italian voice, and only the title and the artist got an English
  one. The frame now follows the language the *server* answered in, which the
  page learns from the server (`window.VIVAVOCE_CFG.langs`) instead of
  guessing: it is not the page language — the chrome is Italian or English
  only — and it is not the mic language either, since a mic language with no
  catalog behind it (Spanish, French) is answered in Italian. German is what
  made this impossible to keep filing as a detail: its replies are German
  inside an English page, so neither of the two languages already on the page
  was the right one.

### Changed

- **The message catalogs moved to `engine/catalogs/`**, one module per
  language, discovered the way `localvoice/lang/` discovers its packs.
  `messages.py` is now the twenty lines that *select* a catalog rather than the
  five hundred that *are* one; `messages.IT`/`.EN`/`.DE` and `msg()` are
  unchanged for every caller.

- **Spotify, through the LMS Spotty plugin.** «da spotify metti Comfortably
  Numb» now works the way «da tidal …» and «da qobuz …» do, the source selector
  lists it when the plugin is installed, and the Home Assistant blueprint
  accepts it too. **It needs Spotify Premium**: Spotty plays through Spotify
  Connect, which free accounts cannot use, and its login will not complete
  without one. This reverses a documented decision: the README said "No
  Spotify" because Spotify Lossless is not delivered to third-party Connect
  clients, so Spotty/librespot still gets lossy Ogg Vorbis 320 kbps. That is
  still true and still says TIDAL or Qobuz is the better source on a
  bit-perfect chain — it is just no longer a reason to refuse to reach a
  service you already pay for.

  **Spotty's feed is not shaped like the other two**, and the support is
  written to what it actually answers, read off a live LMS 9.0.3 on
  2026-08-28: there is no "Songs" category — the search node returns the
  category links with the matching tracks as their siblings — a track carries
  no url at all (it is the name of its single audio child, one level down), and
  title, artist and album arrive as one string, "T by A from B". The url is
  fetched for the track actually being played rather than for all twenty that
  were searched.

  **One behaviour is deliberately different from TIDAL and Qobuz.** Vivavoce
  normally falls back to "nothing matched, so trust the search engine's ranking
  and act on the top result". That is safe where an empty answer is possible —
  TIDAL and Qobuz return *nothing* for «zzzzqqqxyzzy» — and unsafe on Spotify,
  which answers every query with a full page of tracks, albums, artists and
  playlists. On Spotify the fallback is off for all four: if nothing matches,
  Vivavoce says so. Acting on something nobody asked for, silently, is the one
  failure this project is built to avoid, and a service whose search never says
  "no" would have introduced it — in four places, not one.

- **Vivavoce answers Home Assistant's voice assistant.** One blueprint,
  [`blueprints/vivavoce_assist.yaml`](blueprints/vivavoce_assist.yaml), and one
  `rest_command` block: say «metti Comfortably Numb dei Pink Floyd» to Assist —
  a voice satellite, the phone app, the dashboard — and the reply names the song
  that *actually started*, not the words the microphone thought it heard. The
  "which one did you mean?" list works too — «la 2» through «la 5», and the
  ordinals — and on a voice satellite it is meant to be asked out loud and
  waited for, which is the one branch no one here could test without a
  satellite to test it on. Setup is in
  [DEPLOY.md](DEPLOY.md#home-assistant-voice--talking-to-vivavoce-through-assist).

  It coexists by construction: Home Assistant tries sentence triggers before its
  own intents, so the blueprint only ever sees the music sentences it lists, and
  uninstalling is deleting one automation. Transport — pause, resume, next,
  volume — is deliberately **left to Home Assistant**, which already covers it
  in both languages and does it room-aware. Search is the opposite case:
  `HassMediaSearchAndPlay` starts the first result without asking, cannot filter
  by artist, and is missing from the Italian intent pack entirely.

## 0.4.0 — August 2026

### New

- **Vivavoce now says it is a machine.** A line under the microphone —
  «Assistente automatico: stai parlando con un software, non con una persona» —
  and, when the read-back voice or continuous listening is on, one sentence
  spoken at the start of a session. This is Article 50(1) of the EU AI Act,
  applicable since 2 August 2026 to any system that interacts directly with
  people, and it binds software already on the market. The Commission's
  guidelines open their list of examples with "AI-enabled voice assistants",
  and speech reaches this app through a neural model in every configuration —
  the browser's by default, Whisper on your own server with the Pro install —
  so the obligation is ours. The notice sits with the controls rather than in
  a menu, and nothing can switch it off: a disclosure reachable only from the
  settings is not one.

- **[`docs/ai-act.md`](docs/ai-act.md) — where the app stands under the AI Act,
  article by article.** The guidelines put the burden of that assessment on
  the provider, and the interesting half is the negatives: transcription is
  not synthetic content, so nothing needs marking; `engine/moods.py`
  classifies music and not the mood of the listener; nothing anywhere
  recognises *who* is speaking; and the regex-and-`difflib` router is not an
  AI system at all under the Commission's own definition. Households running
  Vivavoce at home carry no obligations of their own (art. 2(10)).

- **[`licenses/MODELS.md`](licenses/MODELS.md)** records which speech models
  the optional installs pull in, from where, and under which licence.
  Vivavoce ships no weights of its own.

### Changed

- **Kid-safe says why a song is refused, not how old you are.** «Questa canzone
  c'è, ma non è adatta alla tua età» claimed to know something the gate cannot
  know: nothing here recognises who is speaking. The decision is three facts —
  kid-safe is on, *this browser* has not typed the PIN in the last fifteen
  minutes, a blocklist term matched — and every one of them is about a device
  and a list. It now names the real reason, which is also the actionable one.

- **GET routes are now held to the Host allow-list.** Only `do_POST` consulted
  it, so the check added against DNS rebinding was protecting no readable
  route: under rebinding the attacker's page is same-origin with us and could
  read `/license`, `/players`, `/kidsafe` and `/nowplaying`. **If you reach
  Vivavoce through a DNS name of your own, put it in
  `VIVAVOCE_ALLOWED_HOSTS`** — such a setup now gets a 403 on the page itself
  where before the page loaded and only the commands failed. Nothing that
  worked stops working (POST always required the same list, so those installs
  could never issue a command), but the failure is louder and looks worse.

- **The container renews its TLS certificate on every boot** instead of
  generating one only when the files are missing. The server leaf now runs 800
  days rather than to a fixed date — Apple refuses any server certificate
  valid for longer — which turned "generate if absent" into a time bomb with
  nothing to defuse it. Only certificates our own CA signed are reissued, and
  the CA itself is reused, so nobody reinstalls anything on their phones. It
  does mean the container writes to your data directory on every start.

- **The README's privacy section matches the code again.** "Everything else
  never leaves your LAN" did not cover the artwork proxy, which for TIDAL and
  Qobuz fetches whatever CDN URL the plugin reports, nor the one-time Whisper
  model download, nor the machine's hostname, which rides along with a licence
  activation as its `instance_name`. `PRIVACY.md` said "nothing else is sent"
  about that same activation. All three are now stated where the claim is.

### Fixed

- **The five-attempt PIN gate allowed a great many more than five.**
  `verify_pin` read the counter, spent ~100 ms in PBKDF2, and only then
  incremented it, with no lock held across the two — so every request that
  arrived before the first write saw zero attempts. The server runs one thread
  per connection and allows 128 of them.

- **A room command no longer aims everybody else's music.** «metti Time in
  cucina» retargeted the turn by swapping `self.lms` and restoring it in a
  `finally` — correct for one turn at a time, and this `Router` is not one turn
  at a time: `http_api` caches one per conversation and the server is threaded.

- **`kidsafe.json` had two writers and no shared lock.** The PIN half and the
  blocklist half each read the whole file and wrote the whole file back, so
  whichever read first wrote last and silently dropped the other's changes. A
  save that fails is now reported instead of swallowed.

- **Switching continuous listening off takes the command capture with it.**
  Only the wake stream was stopped; the capture it had opened ran to its
  30-second cap, transcribed, and — with auto-send on, which wake mode implies
  — answered whatever the room happened to be saying, long after the panel had
  gone dark and said "tap the microphone".

- **The whole continuous-listening block is put away when the trial ends**, not
  just its hint paragraph: engine choice, keyword field and both hints used to
  stay on screen under a checkbox that had just been disabled.

- **The wake word picks the entry that contains it**, rather than any entry
  merely longer than the stray interim result the fallback was holding — and a
  stray is routinely longer than the command it interrupts.

- **A server-side wake word that cannot resolve its model no longer reports
  itself as available.** `--wakeword-model hey_vivavoce` printed "attiva" and
  then detected nothing, because the check only asked whether `openwakeword`
  imports.

- **An expired install is no longer told at every boot that it has fourteen
  fresh trial days.**

- **`https: false` is honoured in the Home Assistant app.** The add-on reads
  its options with `jq -r '.[$k] // empty'`, and `//` falls through on `false`
  as readily as on a missing key — `https` being the only boolean option we
  expose.

- **The Docker healthcheck reads the same variable names the entrypoint still
  answers to.** A container still setting `SQUEEZESAY_HTTPS=0` served plain
  HTTP correctly and was reported unhealthy for it.

- **The service worker no longer caches an error page as a version of the
  app.** A 403, 404 or 500 could land under `/` or under a module's key and
  replace what the install had put there.

- **The seek bar survives losing the track under a finger.** The five-second
  poll, a `visibilitychange` or a failed fetch could drop the now-playing state
  mid-drag, and the next pointer event threw.

- **A blank alternative is not an alternative.** `alternatives: [""]` on
  `/api/v1/command` is a `str`, passed the type check, and became a one-item
  list that replaced the text instead of refining it.

- **A decade is no longer read out in a foreign voice.** The year went into the
  list of foreign names in the sentence, and the language guesser has nothing
  to go on in "1985", so «Ho messo qualcosa del 1985» broke mid-sentence into
  an English voice.

- **The systemd unit's startup lines reach `journalctl`.** No `-u`, so under
  systemd — where stdout is a pipe — Python buffered the server's ~700 bytes of
  startup diagnostics in 4 KiB blocks and showed none of it. **Existing
  installs need to re-copy `deploy/vivavoce.service` and `daemon-reload`** for
  this to take effect.

### Internal

- **`mic.js` outgrew the repo's own 400-line ceiling** during the wake-mode
  work; the local-recognition engine now lives in
  `localvoice/static/js/localasr.js`, which is in the service worker's shell.
  `VERSION` went to `vivavoce-v11`, so installed PWAs pick the new module up on
  activation.

- **`tests/test_ai_act_disclosure.py`** pins what a refactor could quietly
  undo: that the notice exists, sits in the interaction area, cannot be
  switched off by markup, stylesheet or script, exists in both languages, and
  is still wired to the start of listening. The wording is deliberately not
  asserted — it should stay free to improve.

- **A review pass over this release's own commits** closed five findings, four
  of them regressions the work had introduced itself — among them
  `tools/make_cert.py` truncating `key.pem` in place.

- **`RELEASING.md` step 6 expected four entries from `ls /app`** where the
  add-on Dockerfile copies five.

## 0.3.0 — August 2026

### Fixed

- **An apostrophe no longer hides a blocked name from kid-safe.** Text is
  normalised before the blocklist is checked, and that normalisation deletes
  apostrophes — deliberately, because the recogniser writes «dont stop me now»
  and the title is *Don't Stop Me Now*. Deleting also welds the character's
  neighbours into a single word, and a blocked term then has no boundary left
  to match on: a list holding *Eminem* stopped seeing "Eminem's Greatest Hits",
  one holding *Estasi* stopped seeing "L'Estasi dell'Oro". Italian elision —
  l', dell', un', sull' — put a blocked name one article away from being
  unreachable, and albums were the worst of it, because the title is the only
  field a streaming result carries a name in. Both spellings are now checked,
  so the recogniser's version and the elided one both match, and a blocked
  «ass» still does not match «bassista».

- **A song whose title contains «di», «della» or «by» plays again.** The parser
  reads the last connector in a request as the boundary between title and
  artist, which is what makes «Stand By Me by Ben E. King» find the right song
  — and it invented an artist for every title that merely contains one:
  «Cuore di Vetro» became *Cuore* by *Vetro*, «Notte Prima degli Esami» became
  *Notte Prima* by *Esami*. That used to cost nothing, until the app learned to
  say so when a named artist is nowhere in the results; the two together turned
  «metti Cuore di Vetro» into «Non ho trovato Cuore di Vetro» with the right
  track sitting first in the list, and spent the recogniser's next
  transcription on it too. Nine of nineteen real titles tried failed this way,
  most of them Italian. A request that matches a title whole, connector
  included, is now taken as the title it is. «Yesterday di Vasco Rossi» still
  refuses when only The Beatles are in the results, and still finds Vasco's
  edition when it is there.

  Titles that *open* with a connector were losing their first word for a
  related reason — «By the Way» searched for "the Way" — and no longer do.

- **A refusal no longer reports itself as a success — and no longer gets
  retried past.** Every reply carries a flag saying whether it acted on your
  request; for some replies that flag was not set but *guessed*, from whether
  the sentence began with «Non ». Plenty of refusals do not. «Per farlo in
  Cucina serve Pro» is one, and it was being handed to callers of
  `POST /api/v1/command` marked as a success, so a Home Assistant automation
  branching on it took the wrong branch.

  Fixing that flag uncovered the worse half. The app tries several of the
  recogniser's transcriptions in turn, stopping at the first that works — and
  a refusal now looked like something to try again. So «metti Beatles in
  salotto» on the free tier was refused, and then the second-best
  transcription, «metti Beatles», carried no room name, sailed past the very
  refusal that had just stopped it, and started the music in whichever room
  the selector pointed at. You never heard why. Kid-safe had the same hole and
  had had it longer: a blocked singer could be asked for repeatedly until one
  spelling slipped through.

  Refusals about *who is asking* — no Pro, not the parent, not for this
  listener — now end the turn, because no re-transcription of your words buys
  a license. Refusals about the *words* are still retried, which is the whole
  reason that machinery exists: «metti sfigati» becoming «metti Audioslave» on
  the second attempt still works exactly as before.

- **Blocklist replies no longer claim a room they do not have.** «blocca
  Eminem in salotto» answered «Ok, ho bloccato Eminem in Salotto», which
  describes a per-room blocked-songs list that does not exist — the list is
  the whole house. The read-out was worse: «Brani bloccati: Eminem in Salotto»
  reads as though «Eminem in Salotto» were the blocked term.

- **A player named after a word of a song no longer swallows the song.** If one
  of your players is called «America» and your library has *Breakfast in
  America*, «metti breakfast in america» used to be heard as a command for that
  room — and on an installation without Pro that meant an answer about Pro and
  no music at all: a record you own, served with an advertisement. Same for a
  player called «Bianco» and *Notte in bianco*, or «Paradise» and *Lost in
  Paradise*.

  A room name was only ever a *guess* about what the words meant, and it was
  being spent as if it were a fact. Both readings of the sentence — with the
  room and without it — are now looked up in your local library, and the one
  the library actually recognises wins. «breakfast in america» is the name of a
  record and «breakfast» merely resembles one, so the record plays; «bollicine
  in cucina» is the other way round, so it stays a room command and behaves
  exactly as before. A tie keeps the room, which is the safe direction: being
  told no costs you a turn, while music starting in the wrong room costs you a
  trip to go and stop it.

  The same reading applies with or without Pro, deliberately — which record
  your words name is not something a license should have an opinion about. And
  when Pro is active and a room you said out loud gets overruled this way, the
  answer says so («… — l'ho preso come titolo, quindi suona qui»), because a
  room that simply vanishes from the reply is a wrong guess you cannot see.
  «pausa in cucina» and «in cucina metti X» are untouched and do not even ask
  the library: there is no title in either of them to weigh.

  Three things this does not do. It needs a **local** library to consult, so an
  installation that only streams still gets the old answer. When your library
  holds *both* readings — a track called *Notte* and one called *Notte in
  bianco*, with a player called «Bianco» — the sentence really is ambiguous,
  and the room keeps it. And a title that resembles the whole sentence wins
  even when you meant the room: if you own an album called *Musica in Cucina*,
  «metti musica in cucina» plays it. With Pro the answer tells you that is what
  happened, so the correction is one sentence away.

### New

- **A documented API for other programs: `POST /api/v1/command`.** Vivavoce's
  command endpoint was always reachable — it is how the page itself works —
  but it was the web app talking to itself, free to change shape with the page
  it serves. It is now a versioned contract with `docs/api.md` behind it, so a
  Home Assistant blueprint, a script or an automation can send a sentence and
  get a structured answer back without reading the source to find out what the
  fields mean.

  Two things the contract adds. **`needs_choice`** says outright that the
  answer asked a question — «Ne ho diversi per Love. 1: … 2: … Quale metto?» —
  instead of leaving a caller to infer it from a list being non-empty.
  **`conversation_id`** names the session that the numbered list belongs to,
  and `docs/api.md` writes down how long it lasts (five minutes) and what
  happens when it runs out; the old field name `client` still works. The error
  branch was also brought in line: the reply used to drop `choices` when
  something went wrong, which is the worst moment for a field to vanish, and
  now every answer carries every field.

  `POST /command` keeps working, unversioned, answering exactly the same
  thing — nothing that already calls it has to move. The web app itself now
  goes through `/api/v1/command`, which is the only honest way to know the
  contract works. There is deliberately **no `room` field** yet, and
  `docs/api.md` says why rather than leaving it to be guessed at.

- **Vague requests now play something, and say what.** «metti qualcosa di
  rilassante», «musica per cena», «metti un po' di jazz» / "play something
  relaxing", "play some music for dinner" used to be searched for as if they
  were song titles, and of course nothing was ever called that. They now
  resolve through your library's own genres first — real music you own — and
  fall back to the streaming service's curated playlists only when the library
  has nothing to offer; asking for your own library keeps the answer local.
  The load asks LMS for a random album order, so a mood does not open on the
  same track every evening — it is the album order that is randomised, not the
  tracks inside an album, and it is scoped to that one request: your player's
  own shuffle setting is never touched.

  It also answers the axes your library already tags: **a decade** («metti
  musica anni ottanta» / "play some eighties music" — one year out of it, said
  out loud, and «un'altra» gives another year of the same decade), **Christmas
  music**, **instrumental** / "without words", and **summery**. A decade the
  library has nothing from says so rather than playing the nearest thing.

  Every reply reads back what it started («Ho messo un po' di Ambient») and
  invites «un'altra» / "another one", which picks something different until
  the ideas run out and it says so. Choosing is only allowed here because
  nothing was named: a request that names a song, an album or an artist is
  untouched — «metti Bollicine di Vasco» behaves exactly as before, and so
  does a song whose title happens to be a mood word. Still deterministic,
  still no model anywhere: a lookup table and your library's metadata.

- **The container image is published**, so "Docker — one command" is finally
  one command: `docker run … ghcr.io/lucabon/vivavoce:latest`, no clone and no
  build. Every release tag publishes for **amd64 and arm64** as `:X.Y.Z`,
  `:X.Y` and `:latest`. Building from a checkout is unchanged — the compose
  file in the repo still builds from source, with the published image as a
  commented alternative — and a 32-bit Raspberry Pi still builds its own, which
  DEPLOY.md now says instead of implying otherwise.

- **Guided certificate setup.** The mic needs HTTPS, so the browser's "your
  connection is not private" warning stood exactly in front of the feature
  people pay for. The *"Installa come app"* panel now recognises that state and
  opens by itself, shows the two steps for **your** device only (Android,
  iPhone/iPad, Windows, macOS, Linux — the others are one tap away for when you
  are setting up a phone from a laptop), and checks by itself that it worked.
  The check is not a guess: a browser refuses to register a service worker on
  an untrusted certificate, so a registration that succeeds *is* the proof the
  CA is installed. It also knows the cases where there is nothing to do —
  you are on the server machine, the server serves plain HTTP, or it uses a
  certificate of its own — and asks for nothing in each. DEPLOY.md additionally
  documents the ACME/DNS-01 route for households that own a domain and would
  rather install nothing on any device.

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

### Changed

- **Asking for another room without Pro now says which room it heard**, and how
  to get the music anyway: «Per farlo in Cucina serve Pro. Dillo senza la
  stanza e lo faccio qui.» It used to answer with the same generic sentence
  that answers kid-safe, which told you neither. Naming the room is the useful
  part — a room name is only ever a guess about what the words meant, so
  hearing it back is what lets you see a wrong guess. If you have a player
  called *America*, «metti breakfast in america» is read as a room command, and
  now you can tell at once why a song you own was answered with a Pro notice
  instead of music. That it is read as a room command at all is a separate
  problem, still open.

- **The Docker data volume is now `vivavoce-data`**, not `squeezesay-data`. It
  holds the TLS certificate, the licence, the trial window and the kid-safe
  blocklist, so a `docker compose pull && up -d` that silently starts on an
  empty one looks like the app forgot everything it knew. Nothing is deleted:
  the old volume is still there, and `DEPLOY.md` has the two commands that copy
  it across. Only Docker is affected — the Home Assistant app keeps using the
  Supervisor's own storage, which never had the old name.

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

- **The browser suite can no longer skip in silence.** `playwright install`
  exits 0 when it fails — it prints "Failed to install browsers" and returns
  success — so a broken install left a green CI job in which every browser test
  had skipped, which is exactly what had been happening locally. CI now sets
  `VIVAVOCE_REQUIRE_BROWSER=1`, under which those skips become failures, proves
  a browser really launches instead of trusting the installer's exit code, and
  falls back to `PLAYWRIGHT_HOST_PLATFORM_OVERRIDE` on platforms Playwright
  does not recognise yet (Ubuntu 26.04 already refuses; `ubuntu-latest` will
  get there). Three packaging tests keep CI from quietly dropping any of it.
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
- **The Home Assistant app is a declared channel now**, not something that
  merely exists: it has the icon and logo the store requires, and the changelog it recommends
  (`ha-addon/`, artwork generated by `tools/make_icons.py`), and the docs
  follow Home Assistant 2026.2, which renamed *add-ons* to *apps* in the
  interface — menu paths name the new label and the old one, since nothing in
  the file names or config schema changed. `DEPLOY.md` also stopped
  recommending `:0.3.0`, a tag that was never released; a new packaging test
  checks every version the install docs quote against `pyproject.toml`, which
  is how it drifted unnoticed.

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
