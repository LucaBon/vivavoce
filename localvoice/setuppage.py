"""What a household sees while Vivavoce has nothing to control yet.

The strings, the markup and the little script that polls until the answer
changes. Split from ``setupserver.py``, which owns the other half — deciding
*which* of the three things is missing and going on looking for it — so that
neither file has to be read to change the other.

Self-contained on purpose: no ``index.html``, no ``app.css``, none of the JS
modules. All of those assume a resolved player and a services list, which is
exactly what does not exist when this page is the one being served.
"""

from __future__ import annotations

import json

#: How often the page asks. Shorter than the server's probe interval on
#: purpose: the page is reading an answer the server already has, not causing
#: a new one.
POLL_INTERVAL_MS = 1500

NO_LMS = "no_lms"
LMS_DOWN = "lms_down"
NO_PLAYER = "no_player"

_STRINGS = {
    "it": {
        "title": "Vivavoce — configurazione",
        NO_LMS: "Non trovo nessun server musicale (LMS) sulla rete.",
        LMS_DOWN: "Conosco l'indirizzo del server musicale, ma non risponde.",
        NO_PLAYER: "Il server musicale risponde, ma non c'è nessun player acceso.",
        "hint_lms": "Se conosci il suo indirizzo, scrivilo qui. Intanto continuo "
                    "a cercarlo da solo.",
        "hint_down": "Controlla che sia acceso e sulla stessa rete. Continuo a "
                     "riprovare da solo; puoi anche indicarne un altro.",
        "hint_player": "Accendi uno Squeezebox, un Daphile o uno Squeezelite: "
                       "la pagina va avanti da sola appena lo vede.",
        "placeholder": "http://192.168.1.50:9000",
        "save": "Prova questo indirizzo",
        "looking": "Sto cercando…",
        "bad": "A quell'indirizzo non risponde un LMS.",
        "found": "Trovato. Apro l'app…",
        "server": "Server musicale",
    },
    "en": {
        "title": "Vivavoce — setup",
        NO_LMS: "I can't find a music server (LMS) on this network.",
        LMS_DOWN: "I know the music server's address, but it isn't answering.",
        NO_PLAYER: "The music server answers, but no player is switched on.",
        "hint_lms": "If you know its address, type it here. I'll keep looking "
                    "on my own in the meantime.",
        "hint_down": "Check it's switched on and on this network. I'll keep "
                     "retrying on my own; you can also point me at another.",
        "hint_player": "Switch on a Squeezebox, a Daphile or a Squeezelite: "
                       "this page moves on by itself as soon as it sees one.",
        "placeholder": "http://192.168.1.50:9000",
        "save": "Try this address",
        "looking": "Looking…",
        "bad": "Nothing at that address answers like an LMS.",
        "found": "Found it. Opening the app…",
        "server": "Music server",
    },
}

# Self-contained on purpose: the app's stylesheet and its JS modules assume a
# resolved player and a services list, neither of which exists yet. Same
# palette and the same 44px touch targets, written out rather than imported,
# because this page has to render when the rest of the app cannot be built.
_PAGE = """<!doctype html>
<html lang="it"><head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<title>Vivavoce</title>
<style>
  :root { color-scheme: light dark; }
  body { margin: 0; font: 16px/1.5 system-ui, -apple-system, "Segoe UI", sans-serif;
         background: #f6f6f4; color: #16181d;
         padding: max(24px, env(safe-area-inset-top)) 20px 24px; }
  @media (prefers-color-scheme: dark) {
    body { background: #131417; color: #e9eaee; }
    .card { background: #1c1e23 !important; }
    input { background: #131417 !important; color: inherit !important;
            border-color: #3a3d45 !important; }
  }
  main { max-width: 34rem; margin: 0 auto; }
  h1 { font-size: 1.35rem; margin: 0 0 1.25rem; }
  .card { background: #fff; border-radius: 14px; padding: 20px;
          box-shadow: 0 1px 3px rgba(0,0,0,.12); }
  .what { font-weight: 600; margin: 0 0 .5rem; }
  .hint { margin: 0 0 1rem; opacity: .8; }
  form { display: flex; gap: 8px; flex-wrap: wrap; }
  input { flex: 1 1 14rem; min-height: 44px; padding: 0 12px; font: inherit;
          border: 1px solid #c9ccd4; border-radius: 10px; }
  button { min-height: 44px; min-width: 44px; padding: 0 16px; font: inherit;
           border: 0; border-radius: 10px; background: #2f6df6; color: #fff;
           cursor: pointer; }
  .status { margin-top: 1rem; min-height: 1.5em; opacity: .8; }
  .spin { display: inline-block; width: .7em; height: .7em; margin-right: .5em;
          border: 2px solid currentColor; border-right-color: transparent;
          border-radius: 50%; animation: t 900ms linear infinite;
          vertical-align: baseline; }
  @keyframes t { to { transform: rotate(360deg); } }
  @media (prefers-reduced-motion: reduce) { .spin { animation: none; } }
</style>
</head><body>
<main>
  <h1>Vivavoce</h1>
  <div class="card">
    <p class="what" id="what"></p>
    <p class="hint" id="hint"></p>
    <form id="f" hidden>
      <input id="url" type="url" inputmode="url" autocomplete="off"
             autocapitalize="off" spellcheck="false" aria-label="LMS">
      <button type="submit" id="save"></button>
    </form>
    <p class="status" id="status" role="status" aria-live="polite"></p>
  </div>
</main>
<script>
const S = __STRINGS__, POLL = __POLL__;
const lang = (navigator.language || "it").toLowerCase().startsWith("it") ? "it" : "en";
const T = S[lang];
const $ = (id) => document.getElementById(id);
document.documentElement.lang = lang;
document.title = T.title;
$("save").textContent = T.save;
$("url").placeholder = T.placeholder;
let busy = false;

function spin(text) { return '<span class="spin"></span>' + text; }

const HINT = { no_lms: "hint_lms", lms_down: "hint_down", no_player: "hint_player" };

function render(state) {
  const what = T[state.reason] || "";
  $("what").textContent = state.lms ? what + " (" + state.lms + ")" : what;
  $("hint").textContent = T[HINT[state.reason] || "hint_lms"];
  // The address box is offered whenever naming one could help — which is
  // both "nothing found" and "the one I have is silent", not just the first.
  $("f").hidden = state.reason === "no_player";
  if (!busy) $("status").innerHTML = spin(T.looking);
}

async function poll() {
  try {
    const r = await fetch("/setup", { cache: "no-store" });
    const state = await r.json();
    if (state.ready) {
      $("status").textContent = T.found;
      location.reload();
      return;
    }
    render(state);
  } catch (e) { /* server restarting: the next tick tries again */ }
  setTimeout(poll, POLL);
}

$("f").addEventListener("submit", async (ev) => {
  ev.preventDefault();
  busy = true;
  $("status").innerHTML = spin(T.looking);
  try {
    const r = await fetch("/setup", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ lms: $("url").value.trim() }),
    });
    const out = await r.json();
    if (out.ready) { $("status").textContent = T.found; location.reload(); return; }
    $("status").textContent = T.bad;
  } catch (e) {
    $("status").textContent = T.bad;
  }
  busy = false;
});

poll();
</script>
</body></html>
"""




def setup_page() -> str:
    """The page, with its strings and poll interval baked in."""
    return (_PAGE
            .replace("__STRINGS__", json.dumps(_STRINGS, ensure_ascii=False))
            .replace("__POLL__", str(POLL_INTERVAL_MS)))
