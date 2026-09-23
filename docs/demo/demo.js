// The public demo: the real Vivavoce Router, in the browser, on a pretend hi-fi.
//
// This file decides nothing. It loads Pyodide, writes the core files listed in
// core-files.json (fetched from jsDelivr at the commit Pages serves, `main`)
// and the demo's own two (boot.py, hifi.py, from this site), then hands every
// phrase to boot.Demo.turn_json and draws what comes back. What the demo does
// lives in boot.py, where tests/test_demo.py can see it without a browser.
"use strict";

// The one place the Pyodide version is written: tools/fetch_pyodide.py reads it
// from here, so the browser tests always run the version the page loads.
const PYODIDE_VERSION = "0.29.5";
const PYODIDE_URL = `https://cdn.jsdelivr.net/pyodide/v${PYODIDE_VERSION}/full/`;
const CORE_URL = "https://cdn.jsdelivr.net/gh/LucaBon/vivavoce@main/";
const ROOT = "/home/pyodide/vivavoce";
const DEMO = "/home/pyodide/demo";

// `?core=../../` loads the core from a relative path instead: serve the repo
// root with any static server and open /docs/demo/?core=../../ to try the
// page against a working tree. Relative paths only — a link must not be able
// to point this page at somebody else's Python.
function coreUrl() {
  const asked = new URLSearchParams(location.search).get("core");
  if (asked && !/^[a-z][a-z0-9+.-]*:|^\/\//i.test(asked)) {
    return new URL(asked.endsWith("/") ? asked : asked + "/", location.href).href;
  }
  return CORE_URL;
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
    const [, files, phraseText] = await Promise.all([
      loadScript(PYODIDE_URL + "pyodide.js"),
      fetchText("core-files.json").then(JSON.parse),
      fetchText("phrases.json"),
    ]);
    phrases = JSON.parse(phraseText);
    const core = coreUrl();
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
    setStatus("ready", `Ready in ${secs} s. Everything runs in this tab.`);
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

function renderNow(now) {
  const box = $("#now");
  if (!now || !now.title) {
    box.replaceChildren(el("span", "muted", "Nothing playing."));
    return;
  }
  const state = { play: "▶", pause: "❚❚", stop: "■" }[now.mode] || "";
  box.replaceChildren(
    el("div", "np-title", `${state} ${now.title}`),
    el("div", "muted", `${now.artist} · ${now.album}`),
    el("div", "muted", `${fmt(now.elapsed)} / ${fmt(now.duration)} · volume ${now.volume}`),
  );
}

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
  const out = JSON.parse(demo.turn_json(text, lang()));
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
  mic.onclick = () => {
    if (!demo) return;
    const rec = new Rec();
    rec.lang = LOCALES[lang()];
    rec.interimResults = false;
    rec.onresult = (e) => send(e.results[0][0].transcript);
    rec.onend = () => mic.classList.remove("on");
    mic.classList.add("on");
    rec.start();
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
