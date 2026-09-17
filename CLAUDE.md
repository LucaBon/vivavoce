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
| `engine/player/` | The player layer: `protocols.py` (what the engine needs), `registry.py`, one module per backend |
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
- **`messages.set_lang()` is process-global.** An autouse fixture in
  `conftest.py` resets it to Italian after every test; do not rely on module
  order.

## Tests

```bash
uv run pytest        # the whole suite, ~35s
```

`conftest.py` owns the shared scaffolding — `live_server()` runs the real
handler on an ephemeral port and returns a client with
`get`/`post`/`json_get`/`json_post` (plus `try_*` variants that keep a 4xx
instead of raising). Use it rather than standing up a `ThreadingHTTPServer` by
hand.

`tests/test_player_protocol.py` holds every registered backend to the
protocols and to its own declared capabilities — a capability set to True with
no method behind it is how a clean "this player cannot search" turns into an
`AttributeError` reported as "the hi-fi is not answering". A capability no
backend claims yet — `streamable` — is covered by a synthetic pair at the foot
of that file, so its row in the table is exercised instead of merely written.

`tests/test_packaging.py` guards what the suite otherwise cannot see: Dockerfile
`COPY` sources exist, the two version files agree, and the add-on installs a
tag rather than a branch.
