// The public demo: the real Vivavoce Router, in the browser, on a pretend hi-fi.
//
// This file decides nothing. It loads Pyodide, writes the core files listed in
// core-files.json (fetched from jsDelivr at the release tag it names — the tag
// RELEASING.md puts on the main commit Pages serves)
// and the demo's own two (boot.py, hifi.py, from this site), then hands every
// phrase to boot.Demo.turn_json and draws what comes back. What the demo does
// lives in boot.py, where tests/test_demo.py can see it without a browser.
"use strict";

// The one place the Pyodide version is written: tools/fetch_pyodide.py reads it
// from here, so the browser tests always run the version the page loads.
const PYODIDE_VERSION = "0.29.5";
const PYODIDE_URL = `https://cdn.jsdelivr.net/pyodide/v${PYODIDE_VERSION}/full/`;
const CORE_REPO = "https://cdn.jsdelivr.net/gh/LucaBon/vivavoce@";
const ROOT = "/home/pyodide/vivavoce";
const DEMO = "/home/pyodide/demo";

// `?core=../../` loads the core from this site instead: serve the repo root
// with any static server and open /docs/demo/?core=../../ to try the page
// against a working tree. Checked on the URL as the browser resolves it, not
// on the string: `\\host/`, a leading tab, `/\host` all read as relative to a
// pattern and resolve to somebody else's server — which would then be running
// its Python, and through it JavaScript, on this origin.
function coreUrl(ref) {
  const asked = new URLSearchParams(location.search).get("core");
  if (asked) {
    const url = new URL(asked.endsWith("/") ? asked : asked + "/", location.href);
    if (url.origin === location.origin) return url.href;
  }
  return CORE_REPO + ref + "/";
}

const $ = (sel) => document.querySelector(sel);
let demo = null;
let phrases = null;

function setStatus(state, text) {
  const el = $("#status");
  el.dataset.state = state;
  el.textContent = text;
}

function loadScript(src) {
  return new Promise((resolve, reject) => {
    const s = document.createElement("script");
    s.src = src;
    s.onload = resolve;
    s.onerror = () => reject(new Error("could not load " + src));
    document.head.appendChild(s);
  });
}

async function fetchText(url) {
  const r = await fetch(url);
  if (!r.ok) throw new Error(`${r.status} for ${url}`);
  return r.text();
}

function write(py, path, text) {
  py.FS.mkdirTree(path.slice(0, path.lastIndexOf("/")));
  py.FS.writeFile(path, text);
}

async function boot() {
  const t0 = performance.now();
  try {
    setStatus("loading", "Loading Python in your browser (about 5 MB, once)…");
    const [, listing, phraseText] = await Promise.all([
      loadScript(PYODIDE_URL + "pyodide.js"),
      fetchText("core-files.json").then(JSON.parse),
      fetchText("phrases.json"),
    ]);
    phrases = JSON.parse(phraseText);
    const files = listing.files;
    const core = coreUrl(listing.ref);
    const [py, sources, own] = await Promise.all([
      loadPyodide({ indexURL: PYODIDE_URL }),
      Promise.all(files.map((f) => fetchText(core + f))),
      Promise.all(["boot.py", "hifi.py"].map(fetchText)),
    ]);
    setStatus("loading", "Starting the Router…");
    files.forEach((f, i) => write(py, `${ROOT}/${f}`, sources[i]));
    write(py, `${DEMO}/boot.py`, own[0]);
    write(py, `${DEMO}/hifi.py`, own[1]);
    py.runPython(`
import sys
sys.path.insert(0, ${JSON.stringify(DEMO)})
import boot
boot.install(${JSON.stringify(ROOT)})
demo = boot.Demo()
`);
    demo = py.globals.get("demo");
    renderCatalogue(JSON.parse(py.runPython("boot.catalogue_json()")));
    renderChips();
    $("#say").disabled = false;
    $("#send").disabled = false;
    const secs = ((performance.now() - t0) / 1000).toFixed(1);
    setStatus("ready", `Ready in ${secs} s. The engine runs in this tab.`);
    $("#say").focus();
  } catch (err) {
    setStatus("error", "The demo could not load: " + err.message +
      ". It needs cdn.jsdelivr.net; try again in a moment.");
  }
}

function lang() {
  return $("#lang").value;
}

function el(tag, cls, text) {
  const e = document.createElement(tag);
  if (cls) e.className = cls;
  if (text !== undefined) e.textContent = text;
  return e;
}

function renderCatalogue(rows) {
  const list = $("#shelf");
  list.replaceChildren(...rows.map((r) => {
    const li = el("li");
    li.append(el("b", "", r.title), " — " + r.artist, el("span", "album", " · " + r.album));
    return li;
  }));
}

function renderChips() {
  const box = $("#chips");
  box.replaceChildren(...phrases.langs[lang()].map((p) => {
    const b = el("button", "chip", p.say);
    b.type = "button";
    b.onclick = () => send(p.say);
    return b;
  }));
}

function renderChoices(after, choices) {
  const row = el("div", "choices");
  const pick = phrases.pick[lang()];
  choices.forEach((c) => {
    const b = el("button", "choice", c.say ? c.label : `${c.n} · ${c.label}`);
    b.type = "button";
    b.onclick = () => send(c.say || pick.replace("{n}", c.n));
    row.appendChild(b);
  });
  after.after(row);
}

function fmt(secs) {
  const s = Math.max(0, Math.floor(secs || 0));
  return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`;
}

// The pretend record plays on between two phrases; the clock on the page
// follows it locally instead of asking Python every second.
let shown = null;
let shownAt = 0;

function renderNow(now) {
  shown = now;
  shownAt = performance.now();
  drawNow();
}

function drawNow() {
  const now = shown;
  const box = $("#now");
  if (!now || !now.title) {
    box.replaceChildren(el("span", "muted", "Nothing playing."));
    return;
  }
  const state = { play: "▶", pause: "❚❚", stop: "■" }[now.mode] || "";
  const ran = now.mode === "play" ? (performance.now() - shownAt) / 1000 : 0;
  const at = Math.min((now.elapsed || 0) + ran, now.duration || 0);
  box.replaceChildren(
    el("div", "np-title", `${state} ${now.title}`),
    el("div", "muted", `${now.artist} · ${now.album}`),
    el("div", "muted", `${fmt(at)} / ${fmt(now.duration)} · volume ${now.volume}`),
  );
}

// When a record would have ended, ask Python what the hi-fi did next.
setInterval(() => {
  if (!shown || shown.mode !== "play" || !demo) return;
  const ran = (performance.now() - shownAt) / 1000;
  if ((shown.elapsed || 0) + ran >= (shown.duration || 0)) {
    renderNow(JSON.parse(demo.status_json()));
  } else {
    drawNow();
  }
}, 1000);

function renderTold(told) {
  const list = $("#told");
  if (!told.length) {
    const li = el("li", "muted", "Nothing was sent to the hi-fi.");
    li.dataset.empty = "";
    list.replaceChildren(li);
    return;
  }
  list.replaceChildren(...told.map((c) =>
    el("li", "", `${c.name}(${c.args.join(", ")})`)));
}

function send(text) {
  text = (text || "").trim();
  if (!text || !demo) return;
  const log = $("#log");
  const you = el("div", "turn");
  you.append(el("span", "t", "You "), el("span", "you", `«${text}»`));
  log.appendChild(you);
  let out;
  try {
    out = JSON.parse(demo.turn_json(text, lang()));
  } catch (err) {
    // A Python exception is a bug in the demo or the engine, not an answer;
    // it is shown as one, never dressed up as something the app said.
    console.error(err);
    const oops = el("div", "turn");
    oops.append(el("span", "t", "App "), el("span", "app err",
      "(the demo hit an error — please report it on GitHub)"));
    log.appendChild(oops);
    return;
  }
  const app = el("div", "turn");
  app.append(el("span", "t", "App "), el("span", "app" + (out.ok ? "" : " no"), `«${out.speech}»`));
  log.appendChild(app);
  if (out.choices.length) renderChoices(app, out.choices);
  renderNow(out.now_playing);
  renderTold(out.told);
  log.scrollTop = log.scrollHeight;
  $("#say").value = "";
}

// Speech, where the browser has it. Chrome and Safari send the audio to their
// own recogniser — the installed app can instead run Whisper on your LAN.
const LOCALES = { it: "it-IT", en: "en-GB", de: "de-DE", fr: "fr-FR", es: "es-ES" };

function setupMic() {
  const Rec = window.SpeechRecognition || window.webkitSpeechRecognition;
  const mic = $("#mic");
  if (!Rec) return;
  mic.hidden = false;
  $("#mic-note").hidden = false;
  let rec = null;
  mic.onclick = () => {
    if (!demo) return;
    if (rec) { rec.stop(); return; }
    rec = new Rec();
    rec.lang = LOCALES[lang()];
    rec.interimResults = false;
    rec.onresult = (e) => send(e.results[0][0].transcript);
    rec.onerror = (e) => { $("#mic-note").textContent = "Microphone: " + e.error + "."; };
    rec.onend = () => { rec = null; mic.classList.remove("on"); };
    mic.classList.add("on");
    try {
      rec.start();
    } catch (err) {
      rec = null;
      mic.classList.remove("on");
    }
  };
}

function initialLang() {
  const nav = (navigator.language || "en").slice(0, 2).toLowerCase();
  return LOCALES[nav] ? nav : "en";
}

document.addEventListener("DOMContentLoaded", () => {
  $("#lang").value = initialLang();
  $("#lang").onchange = () => { if (phrases) renderChips(); };
  $("#ask").onsubmit = (e) => { e.preventDefault(); send($("#say").value); };
  setupMic();
  boot();
});
