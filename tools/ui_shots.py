"""Screenshot harness for the localvoice UI (visual review loop).

Serves localvoice/ statically and captures the key UI states at a phone
viewport with Playwright. Screenshots land in tools/shots/.

The page's JS is now ES modules, so nothing leaks into the global scope: the
harness drives the UI through the ``window.vivavoce`` test hook (app.js) and
stubs the backend endpoints with ``page.route`` — the same real fetch paths
the app uses at home, just answered from here.
"""
import http.server
import json
import pathlib
import threading

from playwright.sync_api import sync_playwright

ROOT = pathlib.Path(__file__).resolve().parent.parent / "localvoice"
OUT = pathlib.Path(__file__).resolve().parent / "shots"
OUT.mkdir(exist_ok=True)
PORT = 8931

# Simulate a conversation so bubbles/chips render (backend is not running).
FILL_LOG = """
const { bubble } = window.vivavoce;
bubble("metti Wish You Were Here dei Pink Floyd", "you");
const p = bubble("", "sys"); p.classList.add("pending");
bubble("Riproduco: Wish You Were Here — Pink Floyd", "sys");
bubble("volume al 40", "you");
bubble("Volume impostato al 40%.", "sys");
bubble("Non ho capito il comando.", "sys").classList.add("warn");
"""

# Feed the now-playing panel directly (route answers agree, see NOWPLAYING).
FILL_NOWPLAYING = """
window.vivavoce.renderNowPlaying({mode: "play", title: "Wish You Were Here",
                  artist: "Pink Floyd", album: "Wish You Were Here",
                  duration: 334, elapsed: 128, volume: 40,
                  artwork: "/icon-192.png"});
"""

NOWPLAYING = {"mode": "play", "title": "Wish You Were Here",
              "artist": "Pink Floyd", "album": "Wish You Were Here",
              "duration": 334, "elapsed": 128, "volume": 40,
              "artwork": "/icon-192.png"}

PLAYERS = {"ok": True, "pro": False, "current": "aa:bb",
           "players": [{"id": "aa:bb", "name": "Salotto"},
                       {"id": "cc:dd", "name": "Cucina"}]}


class _Handler(http.server.SimpleHTTPRequestHandler):
    """Static file server that fills the server-side placeholders: served raw,
    ``__SERVICES__`` is a SyntaxError that kills the inline config script and
    leaves the source selector empty."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(ROOT), **kwargs)

    def do_GET(self):
        if self.path in ("/", "/index.html"):
            page = (ROOT / "index.html").read_text(encoding="utf-8")
            page = page.replace("__SERVICES__", '["tidal", "qobuz"]')
            page = page.replace("__MATERIAL_URL__", "#")
            data = page.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
            return
        super().do_GET()

    def log_message(self, *args):
        pass


def serve():
    httpd = http.server.ThreadingHTTPServer(("127.0.0.1", PORT), _Handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()


def fulfill_json(state):
    """Route handler answering with the CURRENT content of ``state`` (a dict
    mutated between shots)."""
    return lambda route: route.fulfill(
        status=200, content_type="application/json", body=json.dumps(state))


def main():
    serve()
    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        for scheme in ("dark", "light"):
            # Backend state per scheme run; mutated in place between shots so
            # the already-registered routes serve the new answers.
            license_state = {"pro": False}
            kidsafe_state = {"pro": False, "enabled": False}
            asr_state = {"available": False}
            np_state = {"mode": "stop"}
            ctx = browser.new_context(
                viewport={"width": 390, "height": 844},
                device_scale_factor=2,
                is_mobile=True,
                has_touch=True,
                color_scheme=scheme,
            )
            page = ctx.new_page()
            # Exact paths (+ query variants): a loose "**/nowplaying*" would
            # also swallow /static/js/nowplaying.js and kill the module load.
            page.route("**/license", fulfill_json(license_state))
            page.route("**/kidsafe", fulfill_json(kidsafe_state))
            page.route("**/kidsafe?*", fulfill_json(kidsafe_state))
            page.route("**/asr", fulfill_json(asr_state))
            page.route("**/nowplaying", fulfill_json(np_state))
            page.route("**/nowplaying?*", fulfill_json(np_state))
            page.route("**/players", fulfill_json(PLAYERS))
            page.goto(f"http://127.0.0.1:{PORT}/index.html")
            page.wait_for_function("!!window.vivavoce")
            page.wait_for_timeout(400)  # let the lamp's .3s color fade finish
            page.screenshot(path=OUT / f"01-empty-{scheme}.png")
            page.evaluate(FILL_LOG)
            page.wait_for_timeout(300)
            page.screenshot(path=OUT / f"02-conversation-{scheme}.png")
            page.evaluate("document.getElementById('mic').classList.add('listening')")
            page.wait_for_timeout(300)
            page.screenshot(path=OUT / f"03-listening-{scheme}.png")
            page.evaluate("document.getElementById('mic').classList.remove('listening')")
            np_state.update(NOWPLAYING)  # the 5 s poll agrees with the shot
            page.evaluate(FILL_NOWPLAYING)
            page.wait_for_timeout(300)
            page.screenshot(path=OUT / f"04-nowplaying-{scheme}.png")
            np_state["mode"] = "pause"
            page.evaluate(FILL_NOWPLAYING.replace('"play"', '"pause"'))
            page.wait_for_timeout(300)
            page.screenshot(path=OUT / f"04b-nowplaying-paused-{scheme}.png")
            np_state["mode"] = "play"
            page.evaluate(FILL_NOWPLAYING)
            # Pro states: locked (free tier, settings open on the pitch) and
            # active (mic unlocked, license line in settings).
            page.evaluate("window.vivavoce.showProUpsell()")
            page.wait_for_timeout(400)
            page.screenshot(path=OUT / f"05-pro-locked-{scheme}.png")
            license_state.update({"pro": True, "key": "****ABCD"})
            page.evaluate("window.vivavoce.refreshLicense()")
            page.wait_for_timeout(300)
            page.screenshot(path=OUT / f"06-pro-active-{scheme}.png")
            # Kid-safe: unlocked parent view with a couple of blocked terms.
            kidsafe_state.update({"pro": True, "enabled": True, "haspin": True,
                                  "locked": False,
                                  "terms": ["Bad Song", "Explicit Artist"]})
            page.evaluate(
                "window.vivavoce.refreshKidsafe().then(() =>"
                " document.getElementById('kidsafebox').scrollIntoView())")
            page.wait_for_timeout(300)
            page.screenshot(path=OUT / f"07-kidsafe-{scheme}.png")
            # Local speech recognition row (Pro, shown when /asr is available).
            asr_state.update({"available": True, "model": "small"})
            page.evaluate(
                "window.vivavoce.refreshAsr().then(() => {"
                " document.getElementById('localasr').checked = true;"
                " document.getElementById('settings').open = true;"
                " document.getElementById('localasrrow')"
                "   .scrollIntoView({block: 'center'}); })")
            page.wait_for_timeout(300)
            page.screenshot(path=OUT / f"08-localasr-{scheme}.png")
            # LMS unreachable: red header lamp + warning status line.
            np_state.clear()
            np_state["mode"] = "unknown"
            page.evaluate("window.scrollTo(0, 0); window.vivavoce.setLmsDown(true)")
            page.wait_for_timeout(300)
            page.screenshot(path=OUT / f"09-lmsdown-{scheme}.png")
            ctx.close()
        browser.close()
    print("done ->", OUT)


if __name__ == "__main__":
    main()
