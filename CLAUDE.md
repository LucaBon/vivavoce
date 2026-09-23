# Vivavoce — notes for contributors

Local voice control for an LMS/Daphile hi-fi. Open-core: everything is
AGPL-3.0 except `localvoice/pro/`, which is proprietary (see
`licenses/README.md`).

## Releasing

**Read [`RELEASING.md`](RELEASING.md) before bumping any version.** The short
version: the version lives in *two* files (`pyproject.toml` and
`ha-addon/config.yaml`) and the git tag is mandatory — `ha-addon/Dockerfile`
installs `refs/tags/v${BUILD_VERSION}`, so a bump without its tag breaks every
Home Assistant add-on build with a 404.

## Layout

| Path | What |
|---|---|
| `engine/` | Business logic: `actions.py`, `lms.py`, `discovery.py`, `messages.py` |
| `engine/player/` | The player layer: `protocols.py` (what the engine needs), `registry.py`, one module per backend or spoken library, `composite.py` (a library heard through a backend) |
| `localvoice/` | The web app: `server.py` (HTTP), `router.py` (intents), `index.html` |
| `localvoice/lmsproxy.py` | Reverse proxy to the LMS: Material Skin framed inside the page |
| `localvoice/pro/` | Pro features (proprietary): kid-safe, multi-room, local ASR |
| `tests/` | pytest, no network — a simulated transport per backend |

## Constraints worth knowing

- **The core is stdlib-only.** `engine/` and `localvoice/` import nothing
  third-party; optional extras (`cryptography`, `faster-whisper`) are lazy
  imports guarded by try/except. Keep it that way — it is why the app installs
  anywhere. Backends included: Music Assistant is driven over its plain
  `POST /api`, not its websocket, precisely so this stays true.
- **The engine never names a backend.** `engine/` calls methods on whatever
  object it is handed — see `engine/player/protocols.py`, and
  `engine/matching.py` for the older comment that says the same thing. A
  feature a backend may not have is gated on `Capabilities`, never on
  `isinstance` or a backend name.
- **Python 3.9 is the supported floor** (`requires-python`), and CI enforces it.
  Every module carries `from __future__ import annotations`.
- **No test may touch the network.** `LicenseManager` takes an injectable
  `http_post`; `VIVAVOCE_NO_REVALIDATE=1` disables the license re-check.
- **`messages.set_lang()` is a `ContextVar`, not a process global.** Two
  concurrent requests in two languages cannot mix: the HTTP server is
  thread-per-request and a `ContextVar` is per execution context. What it
  *does* leak across is a keep-alive connection — the thread that served an
  English request keeps the English value until something sets it again — so
  every entry point sets the language before it answers, and one that forgets
  answers in the last caller's. Under pytest there is one thread and one
  context, so a test that speaks English would leak English into every test
  after it: an autouse fixture in `conftest.py` resets it to Italian after
  every test, and no test may rely on module order.

## Tests

```bash
uv run pytest        # the whole suite: minutes, not seconds — allow 10
```

**No test count lives on this page, on purpose.** It moves with almost every
commit, so a number written here is wrong the week after — this line has
already said "~35s", and then a count that was stale before anyone read it.
`uv run pytest --collect-only` prints the real one in well under a second.

A good part of the run is `tests/e2e/`, which drives a real headless browser.
That directory **skips cleanly when the Chromium binary is missing**, so a
run without a browser still reports green having tested no frontend at all.
**The wall-clock does not tell the two apart** — the rest of the suite is by
itself slow enough to pass for a full run. The tell is the summary line: with
no browser every `tests/e2e/` test becomes a skip. `uv run playwright install
chromium` enables it, and `VIVAVOCE_REQUIRE_BROWSER=1` turns every such skip
into a failure — CI sets it.

`conftest.py` owns the shared scaffolding — `live_server()` runs the real
handler on an ephemeral port and returns a client with
`get`/`post`/`json_get`/`json_post` (plus `try_*` variants that keep a 4xx
instead of raising). Use it rather than standing up a `ThreadingHTTPServer` by
hand.

`tests/test_player_protocol.py` holds every registered backend to the
protocols and to its own declared capabilities — a capability set to True with
no method behind it is how a clean "this player cannot search" turns into an
`AttributeError` reported as "the hi-fi is not answering". Catalogues that
play nothing — `SPOKEN_LIBRARY` declarations, Audiobookshelf today — are held
there too, to `SpokenLibrary` and to `streamable`; they are named by
`--library` beside the backend, never by `--backend`.

`tests/test_packaging.py` guards what the suite otherwise cannot see: Dockerfile
`COPY` sources exist, the two version files agree, and the add-on installs a
tag rather than a branch.
