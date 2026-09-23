// The public demo: the real Vivavoce Router, in the browser, on a pretend hi-fi.
//
// This file decides nothing. It loads Pyodide, writes the core files listed in
// core-files.json (fetched from jsDelivr at the release tag it names — the tag
// RELEASING.md puts on the main commit Pages serves)
// and the demo's own three (boot.py, hifi.py, naive.py, from this site), then hands every
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
const OWN = ["boot.py", "hifi.py", "naive.py"];

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
      Promise.all(OWN.map(fetchText)),
    ]);
    setStatus("loading", "Starting the Router…");
    files.forEach((f, i) => write(py, `${ROOT}/${f}`, sources[i]));
    OWN.forEach((f, i) => write(py, `${DEMO}/${f}`, own[i]));
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
    const b = el("button", p.naive === "differs" ? "chip hot" : "chip", p.say);
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

// A cover drawn from the record's name: the same album always gets the same
// colours, and the page fetches no image from anybody.
function hue(text) {
  let h = 0;
  for (const ch of text) h = (h * 31 + ch.codePointAt(0)) % 360;
  return h;
}

function cover(now) {
  const box = el("div", "cover", now.album);
  const h = hue(now.album + now.artist);
  box.style.background =
    `linear-gradient(135deg, hsl(${h} 55% 42%), hsl(${(h + 70) % 360} 60% 22%))`;
  box.setAttribute("aria-hidden", "true");
  return box;
}

function bar(fraction) {
  const b = el("div", "bar");
  const fill = el("i");
  fill.style.width = `${Math.round(Math.max(0, Math.min(1, fraction)) * 100)}%`;
  b.appendChild(fill);
  return b;
}

function drawNow() {
  const now = shown;
  const box = $("#now");
  if (!now || !now.title) {
    const idle = el("div", "cover idle", "♪");
    idle.setAttribute("aria-hidden", "true");
    box.replaceChildren(idle, el("p", "muted", "Nothing playing."));
    drawQueue([]);
    return;
  }
  const state = { play: "▶", pause: "❚❚", stop: "■" }[now.mode] || "";
  const ran = now.mode === "play" ? (performance.now() - shownAt) / 1000 : 0;
  const at = Math.min((now.elapsed || 0) + ran, now.duration || 0);
  const times = el("div", "times");
  times.append(el("span", "", fmt(at)), el("span", "", fmt(now.duration)));
  const vol = el("div", "vol");
  vol.append(el("span", "", "🔈"), bar((now.volume || 0) / 100), el("span", "", `${now.volume}`));
  box.replaceChildren(
    cover(now),
    el("div", "np-title", `${state} ${now.title}`),
    el("div", "muted", `${now.artist} · ${now.album}`),
    bar(now.duration ? at / now.duration : 0),
    times,
    vol,
  );
  drawQueue(now.upcoming || []);
}

function drawQueue(upcoming) {
  $("#upnext").hidden = !upcoming.length;
  $("#queue").replaceChildren(...upcoming.map((t) => {
    const li = el("li");
    li.append(el("b", "", t.title), ` — ${t.artist}`);
    return li;
  }));
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

let avoided = 0;

// The other column: what the first search hit would have been. The verdict
// is computed in Python (boot.verdict), where the tests can see it.
function typicalColumn(out) {
  const col = el("div", "col typical" + (out.verdict === "differs" ? " wrong" : ""));
  const who = el("div", "who", "Typical assistant ");
  who.appendChild(el("small", "", "· plays the first search hit"));
  col.appendChild(who);
  if (out.naive) {
    col.appendChild(el("div", "what", `▶ ${out.naive.title} — ${out.naive.artist}`));
  } else {
    col.appendChild(el("div", "what", "Finds nothing to play"));
  }
  if (out.verdict === "differs") col.appendChild(el("div", "mark", "✗ Not what you asked for"));
  // Vivavoce missed, and the first hit looks right: said as it is, and
  // not counted — the counter is for wrong songs, not for points.
  if (out.verdict === "lucky") col.appendChild(el("div", "lucky", "✓ Probably right this time"));
  return col;
}

function send(text) {
  text = (text || "").trim();
  if (!text || !demo) return;
  const log = $("#log");
  const card = el("article", "exchange");
  const asked = el("div", "asked");
  asked.append(el("span", "t", "You "), el("q", "", text));
  card.appendChild(asked);
  log.appendChild(card);
  let out;
  try {
    out = JSON.parse(demo.turn_json(text, lang()));
  } catch (err) {
    // A Python exception is a bug in the demo or the engine, not an answer;
    // it is shown as one, never dressed up as something the app said.
    console.error(err);
    const col = el("div", "col viva solo");
    col.append(el("div", "who", "Vivavoce"), el("div", "app err",
      "(the demo hit an error — please report it on GitHub)"));
    const versus = el("div", "versus");
    versus.appendChild(col);
    card.appendChild(versus);
    return;
  }
  const versus = el("div", "versus");
  const viva = el("div", "col viva");
  viva.appendChild(el("div", "who", "Vivavoce"));
  const said = el("div", "app" + (out.ok ? "" : " no"), `«${out.speech}»`);
  viva.appendChild(said);
  if (out.verdict === "lucky") {
    versus.append(typicalColumn(out), viva);
  } else if (out.verdict === "differs") {
    versus.append(typicalColumn(out), viva);
    avoided += 1;
    $("#avoided").textContent = String(avoided);
    const score = $("#score");
    score.classList.remove("bump");
    void score.offsetWidth;  // restart the animation
    score.classList.add("bump");
  } else {
    viva.classList.add("solo");
    versus.appendChild(viva);
  }
  card.appendChild(versus);
  if (out.verdict === "same") {
    card.appendChild(el("div", "agree", "A typical assistant would have done the same here."));
  }
  if (out.choices.length) renderChoices(said, out.choices);
  speak(out.speech);
  renderNow(out.now_playing);
  renderTold(out.told);
  log.scrollTop = log.scrollHeight;
  $("#say").value = "";
}

// The reply, said aloud: the one sound this pretend hi-fi makes. On by
// default, since every phrase arrives from a tap or a keypress, which is
// the gesture browsers ask for; the choice is remembered where storage works.
const VOICE_KEY = "vivavoce-demo-voice";
let voiceOn = true;

function speak(text) {
  if (!voiceOn || !window.speechSynthesis) return;
  const synth = window.speechSynthesis;
  synth.cancel();
  const u = new SpeechSynthesisUtterance(text);
  u.lang = LOCALES[lang()];
  const voice = synth.getVoices().find((v) => v.lang === u.lang) ||
    synth.getVoices().find((v) => v.lang.slice(0, 2) === lang());
  if (voice) u.voice = voice;
  synth.speak(u);
}

function setupVoice() {
  if (!window.speechSynthesis) return;
  const button = $("#voice");
  try {
    voiceOn = localStorage.getItem(VOICE_KEY) !== "off";
  } catch (err) { /* no storage: keep the default */ }
  const draw = () => {
    button.textContent = voiceOn ? "🔊" : "🔇";
    button.setAttribute("aria-pressed", String(voiceOn));
  };
  button.hidden = false;
  draw();
  button.onclick = () => {
    voiceOn = !voiceOn;
    if (!voiceOn) window.speechSynthesis.cancel();
    try {
      localStorage.setItem(VOICE_KEY, voiceOn ? "on" : "off");
    } catch (err) { /* no storage: it lasts this visit */ }
    draw();
  };
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
  setupVoice();
  boot();
});
