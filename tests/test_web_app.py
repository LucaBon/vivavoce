"""The web app's static shell and the page/server contract.

These are the surfaces the app cannot start without, and the ones a refactor
breaks silently: the PWA shell, the placeholder substitution in the page, and
the routes the page's own JavaScript calls. Nothing here asserts on wording —
only that the wiring holds.

Why each check earns its place:

* ``sw.js`` pre-caches a fixed shell list with ``caches.addAll()``, which is
  atomic — one 404 rejects the whole service-worker install and the app
  silently stops being installable. Renaming an icon would do it.
* ``index.html`` is served with ``__MATERIAL_URL__`` / ``__SERVICES__``
  substituted at request time; a typo in either token ships a page with a raw
  placeholder in it.
* the page reaches the server through ~10 hard-coded ``fetch()`` paths. Nothing
  but a test ties those strings to the handler's routing table.
"""

import json
import os
import re

import pytest

from conftest import DEFAULT_MATERIAL_URL, FakeLicense

HERE = os.path.dirname(os.path.abspath(__file__))
WEB_DIR = os.path.join(os.path.dirname(HERE), "localvoice")


def _asset(name):
    with open(os.path.join(WEB_DIR, name), encoding="utf-8") as f:
        return f.read()


def _js_modules():
    """Every ES module of the UI, as ``(relative_path, source)`` pairs."""
    js_dir = os.path.join(WEB_DIR, "static", "js")
    return [(os.path.join("static", "js", name), _asset(os.path.join("static", "js", name)))
            for name in sorted(os.listdir(js_dir)) if name.endswith(".js")]


# -- the PWA shell -------------------------------------------------------------

def _shell_paths():
    """The SHELL list the service worker actually pre-caches.

    Parsed from sw.js rather than hard-coded, so the test keeps tracking the
    real list when someone adds an asset to it.
    """
    match = re.search(r"const SHELL = \[(.*?)\]", _asset("sw.js"), re.S)
    assert match, "sw.js no longer declares a SHELL array"
    return re.findall(r'"([^"]+)"', match.group(1))


def test_service_worker_shell_is_fully_served(live_server):
    # caches.addAll() is atomic: one 404 here and the PWA stops installing.
    srv = live_server()
    paths = _shell_paths()
    assert paths, "parsed an empty SHELL out of sw.js"
    missing = [p for p in paths if srv.try_get(p).status != 200]
    assert missing == []


def test_service_worker_itself_is_served(live_server):
    resp = live_server().get("/sw.js")
    assert resp.status == 200
    # Served as JavaScript or the browser refuses to register it.
    assert resp.headers["Content-Type"].startswith("text/javascript")


def test_manifest_icons_all_resolve(live_server):
    srv = live_server()
    resp = srv.get("/manifest.webmanifest")
    assert resp.status == 200
    assert resp.headers["Content-Type"].startswith("application/manifest+json")
    manifest = resp.json()
    icons = {icon["src"] for icon in manifest["icons"]}
    assert icons, "the manifest declares no icons"
    for src in sorted(icons):
        icon = srv.try_get(src)
        assert icon.status == 200, f"manifest icon {src} is not served"
        # startswith: _send() tacks "; charset=utf-8" onto every type,
        # binary ones included. Harmless for images, so just tolerate it.
        assert icon.headers["Content-Type"].startswith("image/png")
        assert icon.body[:8] == b"\x89PNG\r\n\x1a\n", f"{src} is not a PNG"


def test_manifest_start_url_is_served(live_server):
    srv = live_server()
    start_url = srv.get("/manifest.webmanifest").json()["start_url"]
    assert srv.try_get(start_url).status == 200


# -- the page ------------------------------------------------------------------

def test_index_substitutes_its_placeholders(live_server):
    srv = live_server(material_url="http://lms.local:9000/material/",
                      services=("tidal", "qobuz"))
    resp = srv.get("/")
    assert resp.status == 200
    assert resp.headers["Content-Type"].startswith("text/html")
    page = resp.text
    assert "http://lms.local:9000/material/" in page
    # The services list reaches the page as JSON the browser can parse.
    assert json.dumps(["tidal", "qobuz"]) in page


def test_index_leaves_no_placeholder_behind(live_server):
    # A renamed token would otherwise ship a page with a literal
    # __SOMETHING__ in it, which no other test would notice.
    page = live_server().get("/").text
    leftovers = set(re.findall(r"__[A-Z][A-Z0-9_]*__", page))
    assert leftovers == set()


def test_index_html_path_serves_the_same_page(live_server):
    srv = live_server()
    assert srv.get("/index.html").body == srv.get("/").body


def test_index_reflects_the_configured_services(live_server):
    page = live_server(services=("qobuz",)).get("/").text
    assert json.dumps(["qobuz"]) in page
    assert json.dumps(["tidal", "qobuz"]) not in page


def test_index_default_material_url_reaches_the_page(live_server):
    assert DEFAULT_MATERIAL_URL in live_server().get("/").text


# -- the static assets (CSS + ES modules) --------------------------------------

def _page_asset_refs():
    """Every /static/... URL the page markup references (stylesheet, module)."""
    return sorted(set(re.findall(r'(?:href|src)="(/static/[^"]+)"',
                                 _asset("index.html"))))


def test_page_static_references_are_served(live_server):
    # A renamed CSS/JS file would ship a page that loads without style or
    # without behavior, with nothing failing at build time.
    srv = live_server()
    refs = _page_asset_refs()
    assert refs, "the page references no static assets"
    missing = [ref for ref in refs if srv.try_get(ref).status != 200]
    assert missing == []


def test_es_module_imports_all_resolve(live_server):
    # Modules load as a unit: one bad `import "./x.js"` and the whole page
    # is dead. Tie every import specifier to a served file.
    srv = live_server()
    for name, source in _js_modules():
        for target in re.findall(r'from\s+"\./([^"]+)"', source):
            assert srv.try_get("/static/js/" + target).status == 200, (
                f"{name} imports ./{target}, which is not served")


def test_es_modules_are_served_as_javascript(live_server):
    # Wrong MIME type and the browser refuses to run the module at all.
    resp = live_server().get("/static/js/app.js")
    assert resp.status == 200
    assert resp.headers["Content-Type"].startswith("text/javascript")


def test_static_serving_refuses_path_traversal(live_server):
    srv = live_server()
    assert srv.try_get("/static/../server.py").status == 404
    assert srv.try_get("/static/js/../../index.html").status == 404


# -- the page/server contract --------------------------------------------------

def _fetch_paths():
    """Every same-origin path the UI fetches, as written in the page and in
    its ES modules (static/js/)."""
    sources = [_asset("index.html")] + [src for _name, src in _js_modules()]
    paths = set()
    for source in sources:
        for raw in re.findall(r'fetch\(\s*"(/[^"]*)"', source):
            paths.add(raw.split("?")[0])
        # Concatenated query strings: fetch("/kidsafe?client=" + ...)
        for raw in re.findall(r'fetch\(\s*"(/[^"?]*)\?', source):
            paths.add(raw)
    return sorted(paths)


def test_page_fetches_only_routes_the_server_answers(live_server):
    # The page's fetch() strings are the real API contract; a renamed route
    # would 404 at runtime with nothing failing at build time.
    srv = live_server()
    paths = _fetch_paths()
    assert paths, "found no fetch() calls in the UI sources"
    unrouted = []
    for path in paths:
        # A route is "answered" if it is not the catch-all 404 — GET or POST,
        # since the page uses both and this test is about routing, not method.
        if (srv.try_get(path).status == 404
                and srv.try_post_json(path, {}).status == 404):
            unrouted.append(path)
    assert unrouted == []


def test_unknown_get_is_a_plain_404(live_server):
    resp = live_server().try_get("/nope")
    assert resp.status == 404
    assert resp.headers["Content-Type"].startswith("text/plain")


def test_unknown_post_is_a_json_404(live_server):
    resp = live_server().try_post_json("/nope", {"text": "ciao"})
    assert resp.status == 404
    assert "speech" in resp.json()


# -- non-object JSON bodies -----------------------------------------------------
# json.loads happily parses `null`/a number/a list/a bare string: none of
# those raise ValueError, so a bare `.get()` on the result would raise
# AttributeError uncaught by an `except (ValueError, UnicodeDecodeError)` —
# dropping the connection with no response, breaking every endpoint's own
# "never a 5xx" guarantee.

NON_OBJECT_BODIES = ["null", "5", '"just a string"', "[1, 2, 3]"]


@pytest.mark.parametrize("body", NON_OBJECT_BODIES)
def test_command_survives_a_non_object_json_body(live_server, body):
    resp = live_server().post("/command", data=body.encode("utf-8"))
    assert resp.status == 200
    assert resp.json()["ok"] is False


@pytest.mark.parametrize("body", NON_OBJECT_BODIES)
def test_kidsafe_survives_a_non_object_json_body(live_server, body, tmp_path):
    from pro.kidsafe import KidSafe

    kidsafe = KidSafe(str(tmp_path), FakeLicense(pro=True))
    resp = live_server(kidsafe=kidsafe).post("/kidsafe",
                                             data=body.encode("utf-8"))
    assert resp.status == 200
    assert resp.json()["ok"] is False


@pytest.mark.parametrize("body", NON_OBJECT_BODIES)
def test_player_survives_a_non_object_json_body(live_server, body):
    resp = live_server().post("/player", data=body.encode("utf-8"))
    assert resp.status == 200
    assert resp.json()["ok"] is False


@pytest.mark.parametrize("body", NON_OBJECT_BODIES)
def test_license_survives_a_non_object_json_body(live_server, body, tmp_path):
    # FakeLicense has no .activate() (only GET /license needs one); POST
    # exercises the real manager, with no http_post call expected — the
    # non-object body degrades to an empty key, which activate() rejects
    # locally before touching the network.
    import licensing

    def unexpected_post(url, fields):
        raise AssertionError("should not reach the network on an empty key")

    mgr = licensing.LicenseManager(str(tmp_path), http_post=unexpected_post)
    resp = live_server(license_mgr=mgr).post("/license",
                                             data=body.encode("utf-8"))
    assert resp.status == 200
    assert resp.json()["ok"] is False


# -- /ca.pem -------------------------------------------------------------------

def test_ca_pem_is_served_when_configured(live_server, tmp_path):
    # The local CA the phone installs once to get a green padlock. Written
    # into tmp_path: *.pem is gitignored and must never be committed.
    ca = tmp_path / "ca.pem"
    ca.write_bytes(b"-----BEGIN CERTIFICATE-----\nfake\n")
    resp = live_server(ca_path=str(ca)).get("/ca.pem")
    assert resp.status == 200
    assert resp.headers["Content-Type"].startswith("application/x-pem-file")
    assert resp.body == ca.read_bytes()


def test_ca_pem_is_404_without_a_certificate(live_server):
    assert live_server().try_get("/ca.pem").status == 404


def test_ca_pem_is_404_when_the_file_is_missing(live_server, tmp_path):
    # Configured but not yet generated: a 404 beats a traceback.
    absent = str(tmp_path / "never-made.pem")
    assert live_server(ca_path=absent).try_get("/ca.pem").status == 404
