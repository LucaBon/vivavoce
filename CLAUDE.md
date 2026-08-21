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
| `localvoice/` | The web app: `server.py` (HTTP), `router.py` (intents), `index.html` |
| `localvoice/pro/` | Pro features (proprietary): kid-safe, multi-room, local ASR |
| `tests/` | pytest, no network — a simulated LMS transport throughout |

## Constraints worth knowing

- **The core is stdlib-only.** `engine/` and `localvoice/` import nothing
  third-party; optional extras (`cryptography`, `faster-whisper`) are lazy
  imports guarded by try/except. Keep it that way — it is why the app installs
  anywhere.
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

`tests/test_packaging.py` guards what the suite otherwise cannot see: Dockerfile
`COPY` sources exist, the two version files agree, and the add-on installs a
tag rather than a branch.
