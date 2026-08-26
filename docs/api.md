# Vivavoce HTTP API

Vivavoce's server answers exactly one endpoint that outside programs are
invited to call:

```
POST /api/v1/command
```

Everything else it serves is the web app talking to itself. Those routes are
listed further down, each with the reason it is not part of this contract,
because "not documented" and "deliberately excluded" look identical from
outside and only one of them is a decision.

There is **no authentication**, by design: the server lives on your LAN, has
no accounts, and answers whoever asks. What it does refuse is a *cross-site*
request — see [Cross-site protection](#cross-site-protection) below, which
matters if you are writing a client.

---

## `POST /api/v1/command`

One spoken (or typed) sentence in, one answer out. The sentence is parsed the
same way the web app's own commands are: this is not a remote-control API with
one call per action, it is the whole voice interface behind one route.

### Request

`Content-Type: application/json` (required — see cross-site protection).

| Field | Type | Default | Meaning |
|---|---|---|---|
| `text` | string | `""` | The sentence to execute: «metti Comfortably Numb dei Pink Floyd», "pause", «metti la 2». |
| `conversation_id` | string | `"default"` | The conversation this sentence belongs to. See [Conversation state](#conversation-state). |
| `client` | string | — | Accepted as an alias for `conversation_id`, which wins when both are sent. The web app has always used this name; new clients should use `conversation_id`. |
| `lang` | string | `"it"` | `it` or `en`. The language the sentence is *in*, and the language the answer comes back in. Anything else falls back to Italian. |
| `source` | string | `"auto"` | Where music comes from when the sentence does not say: `auto` (the local library first, then the streaming service), `local`, or a service name (`tidal`, `qobuz`). Phrases like «dalla mia musica» / «da tidal» override it. |
| `player` | string | `""` | The LMS player id to command, instead of the server's default player. Requires Pro (multi-room); ignored otherwise. |
| `alternatives` | string[] | `[text]` | Speech-recognition alternatives, best first. Each is tried until one is understood; only an understood one ever plays anything, so a wrong guess has no side effect. `used` says which one won. |

Unknown fields are ignored. A body that is not a JSON object (empty, malformed,
a bare list) is read as `{}` and answered normally — see
[Failure modes](#failure-modes).

### Response

Always `200 OK`, always `application/json`, and **always these keys** — the
shape does not narrow when something goes wrong:

| Field | Type | Meaning |
|---|---|---|
| `speech` | string | What to say to the user, already in `lang`. Ready to hand to a TTS engine or print. |
| `ok` | bool | Did the request get acted on? A question ("which one?") counts as acted on — it is `true`. |
| `needs_choice` | bool | This answer read out a numbered list and is **waiting for a pick**. See below. |
| `choices` | array | The same list, machine-readable: `[{"n": 1, "label": "Love di X"}, …]`. Empty unless `needs_choice` is true. |
| `used` | string | Which of the `alternatives` was actually executed (the first one when nothing else matched). |
| `terms` | string[] | The foreign-language names inside `speech` (song, album, artist). A TTS engine that pronounces "Bohemian Rhapsody" with an Italian voice needs to know which words are not Italian. |
| `unmatched` | bool | Nothing in the parser matched: this is a **gap in the grammar**, not a failed action. The web app offers a "report this phrase" button on it; a headless client can log it. |
| `error` | string | *Only present* when an unexpected exception was caught. `ok` is `false` and `speech` explains. Never a 5xx — see [Failure modes](#failure-modes). |

### `needs_choice`

Vivavoce asks instead of guessing. «metti Love» with two different songs called
"Love" in the library does not play the first one; it answers

> «Ne ho diversi per Love. 1: Love di X, 2: Love di Y. Quale metto?»

and waits. That answer carries `needs_choice: true` and a `choices` list. The
user's next sentence — «la 2», «metti la seconda», or the title itself — picks
from it, in the **same `conversation_id`**.

`needs_choice` is `true` exactly when the answer just opened a numbered list,
and it exists so that a client never has to derive that meaning from
`choices` being non-empty. A blueprint, an automation or an agent reading a
flag is reading a promise; the same code reading a list's length is reading an
implementation detail.

Note that `needs_choice` describes **this answer**, not the session: the
answer to the question does not carry it (the question is closed), even though
the list itself stays pickable for a while longer.

### Conversation state

The open list lives on the server, keyed by `conversation_id`. Two ids never
see each other's list — that is what keeps the kitchen from answering the
study's question — and an unknown id simply starts a fresh conversation.

**Time limits.** They were always there; here they are, in writing:

| Window | Duration | What it governs |
|---|---|---|
| Open list | **300 s** (`CANDIDATES_TTL`) | How long after a question a pick («la 2») is still understood. |
| List after a pick | **up to 30 s** (`CANDIDATES_GRACE`) | A picked list stays pickable briefly, so the buttons still on a phone's screen keep working — then it is gone. It is a ceiling, not a duration: the grace is `min(what was left, 30 s)`, so a pick made late in the 300 s window leaves whatever remained of it. |
| Open mood | **300 s** (`MOOD_TTL`) | How long «un'altra» / "another one" keeps re-rolling a vague request («metti qualcosa di rilassante»). |

**When a window expires, nothing fails loudly**: the list is simply forgotten,
and «metti la 2» becomes a sentence about nothing — Vivavoce answers that it
has no list open rather than playing a stale second item. That is deliberate.
A client with its own conversation timeout should keep it *shorter* than 300
seconds if it wants the two to agree; there is no way to query or extend the
window from outside, and no plan to add one.

There is a cap of **64 live conversations**, least-recently-used evicted
first. On Pro the key is `conversation_id` plus the `player` it targeted, so a
conversation that commands three players occupies three slots; without Pro the
player is collapsed and one conversation is always one slot.

**The 64 slots are shared with the web app and every other caller**, and this
is the part worth designing around: eviction does not fall on whoever caused
it. A client that mints a fresh `conversation_id` per turn — which is what
Home Assistant does — will push other conversations out, including the phone
in the kitchen that is halfway through answering «quale intendi?». That phone
gets «Prima chiedimi un elenco» and no explanation. An evicted conversation
loses its open list and nothing else, so nothing breaks; it just forgets. If
you can reuse a conversation id across turns, do.

### Why there is no `room` in v1

The roadmap sketched a `room` field and the Home Assistant spike identified its
first real use — the HA area a command came from. It is deliberately **not** in
v1, and here is why:

* rooms already work, **inside the sentence**: «metti X in cucina» is parsed
  and routed by the router today (Pro, multi-room). A `room` field would be a
  second way to say something the grammar already says;
* the explicit selector that exists is `player`, and it takes an **LMS player
  id** — an unambiguous handle, not a name that has to be resolved;
* a `room` field would need a name→player resolver (fuzzy, localised, and
  wrong in a household with a player called "Salotto" and an HA area called
  "Living room"). Designing that against no real client is designing against a
  guess.

T3.3 implements the actual Home Assistant integration. If a room field is
still the right answer with a real HA in front of it, it arrives then — as an
**addition**, which this contract allows, rather than a rename, which it does
not.

### Failure modes

Vivavoce never answers a 5xx on this route. Specifically:

* **LMS unreachable, nothing found, command not understood** → `200` with
  `ok: false` and a `speech` that says so. These are answers, not errors.
* **An unexpected exception** → `200` with `ok: false`, an `error` string, and
  every other field still present.
* **A malformed or empty body** → `200` with `ok: false` ("I heard nothing").
* **A cross-site request** → `403` with `{"ok": false, "error": "…"}`; see
  below. This is the one non-200 this route produces.

### Compatibility promise

Within `v1`: fields may be **added**, never removed or repurposed, and
`/api/v1/command` keeps its path. Parse the response as an open object and
ignore what you do not know. A breaking change gets `/api/v2/command`, and v1
keeps answering.

### `POST /command` — the unversioned alias

The original path. It is the **same implementation** — byte for byte the same
response — and it stays: the web app's own service worker may still hold a
cached page that calls it, and anything already integrated should not have to
move. It carries no version, so it carries no promise; new clients should use
`/api/v1/command`.

Decided now rather than argued later: **`/command` tracks the newest version.**
The day `/api/v2/command` exists, `/command` answers whatever v2 answers. That
is the only reading under which "the same implementation" stays true, and it is
why it carries no promise — a caller who needs a stable shape is asking for a
versioned path, which is what versioned paths are.

### Example

```bash
curl -s http://vivavoce.local:8730/api/v1/command \
  -H 'Content-Type: application/json' \
  -d '{"text": "metti Love dalla mia musica", "conversation_id": "ha-42"}'
```

```json
{
  "speech": "Ne ho diversi per Love. 1: Love di X, 2: Love di Y. Quale metto?",
  "used": "metti Love dalla mia musica",
  "ok": true,
  "terms": ["Love", "X", "Love", "Y"],
  "choices": [{"n": 1, "label": "Love di X"}, {"n": 2, "label": "Love di Y"}],
  "needs_choice": true,
  "unmatched": false
}
```

```bash
curl -s http://vivavoce.local:8730/api/v1/command \
  -H 'Content-Type: application/json' \
  -d '{"text": "la 2", "conversation_id": "ha-42"}'
```

```json
{
  "speech": "Riproduco Love dalla tua musica.",
  "used": "la 2",
  "ok": true,
  "terms": ["Love"],
  "choices": [],
  "needs_choice": false,
  "unmatched": false
}
```

---

## Cross-site protection

The server has no auth, so every state-changing POST is a CSRF target. Four
checks apply (`localvoice/webguard.py`), and a client that is not a browser
passes all four without doing anything special:

1. `Content-Type: application/json` is **required** on `/api/v1/command`
   (and on the other JSON POST routes). Anything else is `403`
   `{"error": "content_type"}`. This is what forces a real browser preflight,
   which the server then refuses.
2. `Sec-Fetch-Site: cross-site` is refused outright, whatever the
   Content-Type and whether or not there is an `Origin`. Worth knowing because
   it is the one check that can `403` a request that looks otherwise perfect:
   if you are debugging a `cross_site` error with no `Origin` header in your
   request, this is why. Browsers set the header; nothing else does.
3. If an `Origin` header is present, its host must equal the `Host`. `curl`,
   a `rest_command`, or any non-browser client sends no `Origin`, so this does
   not apply to them.
4. The `Host` must be an IP literal, `localhost`, this machine's own name, or
   a `.local`/`.lan`/`.home`/`.home.arpa`/`.internal`/`.localdomain` name.
   Fronting the server with a public DNS name requires
   `VIVAVOCE_ALLOWED_HOSTS`.

---

## The whole surface, and what each route is

Everything the server answers, from `localvoice/http_api.py` and
`localvoice/audio_api.py`. Three verdicts:

* **v1** — part of the contract above.
* **internal** — the web app's own plumbing. It works, you may call it, and it
  may change shape in any release without notice, because the page that calls
  it ships in the same commit. Not versioned, on purpose.
* **private** — Pro features gated server-side; they exist to serve the page
  and are not offered as an interface at all.

### GET

| Route | Verdict | What it is, and why |
|---|---|---|
| `/`, `/index.html` | internal | The web app itself. |
| `/static/…` | internal | The page's JS, CSS and images. Re-read from disk per request. |
| `/manifest.webmanifest`, `/sw.js`, `/icon-192.png`, `/icon-512.png` | internal | The PWA shell. |
| `/ca.pem` | internal | The local CA to install on a phone, from the certificate onboarding. Served only when the server actually has one; otherwise it falls through to the `404`, which is a healthy server and not a fault. **T0.2 declared this internal**; it is a setup flow for a browser, not a client interface. |
| `/tls` | internal | Whether a local CA exists at all, so the page knows whether to offer the walkthrough. Internal for the same reason as `/ca.pem` (T0.2). |
| `/license` | internal | Pro/trial status for the settings panel. **T0.1 declared this internal**: it drives what the page shows, and it is not a licence check anyone else should be building on. |
| `/nowplaying` | internal | The now-playing panel's poll. A courtesy `media_player` for Home Assistant would want something like it, and that is a T3.3 conversation with a real client in front of it — not a promise made in advance. |
| `/artwork` | internal | Server-side cover proxy (the page is HTTPS, LMS is not). Takes no URL from the caller, by design. |
| `/players` | internal | The room selector's player list. Same note as `/nowplaying`. |
| `/kidsafe` | internal | Kid-safe state for the settings panel (Pro). The gate itself is enforced inside the router, so this route is a view, not the lock. |
| `/asr` | private | Whether the local speech-recognition engine is installed, so the page can show its switch (Pro). Note the GET itself is **not** gated — it answers anyone; the gate is on the action (`POST /transcribe`). It is filed private because it exists only to drive a Pro switch. |
| `/wakeword` | private | Same, for the server-side wake word (Pro) — and ungated in the same way, for the same reason. |
| anything else | — | `404`, `text/plain`. |

### POST

| Route | Verdict | What it is, and why |
|---|---|---|
| `/api/v1/command` | **v1** | The contract. |
| `/command` | v1 alias | Unversioned, same implementation. |
| `/license` | internal | One-off key activation from the settings panel (T0.1). |
| `/kidsafe` | internal | Enable/disable, PIN unlock, term list edits (Pro). Not an interface: a PIN prompt for the person holding the phone. |
| `/player` | internal | Transport for the mini-player (pause, skip, seek, volume). Deliberately *not* in v1: it is a second way to do what a sentence already does, and duplicating it in the contract would mean maintaining two. |
| `/transcribe` | private | Audio in, text out (Pro, server CPU). Serves the page's microphone. |
| `/wakeword/chunk`, `/wakeword/stop` | private | The server-side wake-word stream (Pro). Serves the page's microphone. |
| anything else | — | `404` with a JSON body. |

---

## Where this is decided

* The contract lives in `localvoice/api_v1.py`; the fields it returns come
  from `Router.handle_many` (`localvoice/router.py`).
* `tests/test_api_v1.py` is the executable half of this document — the shape,
  the flag, the session and the alias.
* The reasoning behind versioning this route at all is in
  `docs/ha-integration-design.md` §5.
