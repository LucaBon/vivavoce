// Multilingual read-back: natural browser voices, one per language, and the
// voice-settings panel. The reply frame is spoken in the language the SERVER
// answered in (replyLang, not the page chrome — a German session gets German
// replies inside an English page); the foreign terms (title/artist) each by
// their own language's voice.

import { $ } from "./util.js";
import { LANGS, ui, uiLang, recLang, replyLang, foreignDefault, detectLang, applyUI } from "./i18n.js";

const NATURAL = /natural|neural|online|google|siri|premium|enhanced/i;
let VOICES = [];

function voicesFor(lang) {
  return VOICES.filter(v => (v.lang || "").toLowerCase().startsWith(lang));
}
function pickDefaultVoice(lang) {
  const cand = voicesFor(lang);
  return cand.find(v => NATURAL.test(v.name)) || cand[0] || null;
}
function chosenVoice(lang) {
  const saved = localStorage.getItem("voice_" + lang);
  if (saved) {
    const v = VOICES.find(x => x.name === saved && (x.lang || "").toLowerCase().startsWith(lang));
    if (v) return v;
  }
  return pickDefaultVoice(lang);
}

// Split the reply into its frame vs the foreign terms (in order), so each part
// is spoken by the right-language voice. The frame's language is the one the
// server replied in: it was hard-coded to Italian, which meant an English
// session heard "Playing" and "by" read out by an Italian voice — and German,
// arriving third, made that impossible to keep calling a detail.
function splitByTerms(speech, terms) {
  const frame = replyLang();
  const marks = [];
  let from = 0;
  (terms || []).forEach(term => {
    if (!term) return;
    const pos = speech.toLowerCase().indexOf(String(term).toLowerCase(), from);
    if (pos >= 0) { marks.push([pos, pos + term.length, detectLang(term)]); from = pos + term.length; }
  });
  if (!marks.length) return [{ text: speech, lang: frame }];
  const segs = [];
  let cur = 0;
  marks.forEach(([start, end, lang]) => {
    if (start > cur) segs.push({ text: speech.slice(cur, start), lang: frame });
    segs.push({ text: speech.slice(start, end), lang });
    cur = end;
  });
  if (cur < speech.length) segs.push({ text: speech.slice(cur), lang: frame });
  return segs;
}

function utter(text, lang) {
  const u = new SpeechSynthesisUtterance(text);
  const v = chosenVoice(lang);
  if (v) { u.voice = v; u.lang = v.lang; } else { u.lang = (LANGS[lang] || LANGS.it).tag; }
  speechSynthesis.speak(u);
}

export function speak(text, terms) {
  try {
    speechSynthesis.cancel();
    for (const seg of splitByTerms(text, terms)) {
      if (seg.text.trim()) utter(seg.text, seg.lang);
    }
  } catch (e) { /* TTS optional */ }
}

// --- Art. 50(1) AI Act: the spoken half of the disclosure -------------------
//
// The standing notice lives on the page, under the microphone. Hands-free
// listening is the case that notice cannot reach: somebody talks to the room
// and never looks at the screen. Commission guidelines C(2026) 5054 §37 name
// exactly this — "explicit spoken statements at the beginning of the
// interaction" — and §143 asks for it "at least once at the start of an
// interactive session".
//
// Once per page load, then, not once per tap: §39 warns that a disclosure
// repeated past the point of being heard stops being one. The flag remembers
// the language it was said in, so switching the mic language says it again in
// the language the household is actually speaking. Reloading the page starts
// a new session and says it again.
let noticeSaidIn = "";  // "" = not said yet in this page session

export function speakAiNotice() {
  if (!("speechSynthesis" in window)) return;
  const lang = uiLang();
  if (noticeSaidIn === lang) return;
  noticeSaidIn = lang;
  try { utter(ui("ai_notice_spoken"), lang); } catch (e) { /* TTS optional */ }
}

// --- voice settings UI ---
export function buildVoicePickers() {
  const box = $("voiceSettings");
  if (!box) return;
  box.innerHTML = "";
  for (const lang of Object.keys(LANGS)) {
    const row = document.createElement("label");
    row.className = "vrow";
    row.append(LANGS[lang].name + " ");
    const sel = document.createElement("select");
    const vs = voicesFor(lang);
    if (!vs.length) {
      sel.innerHTML = "<option>" + ui("no_voice") + "</option>";
      sel.disabled = true;
    } else {
      const cur = (chosenVoice(lang) || {}).name;
      for (const v of vs) {
        const o = document.createElement("option");
        o.value = v.name;
        o.textContent = v.name + (NATURAL.test(v.name) ? " ⭐" : "");
        if (v.name === cur) o.selected = true;
        sel.appendChild(o);
      }
      sel.onchange = () => localStorage.setItem("voice_" + lang, sel.value);
    }
    row.appendChild(sel);
    box.appendChild(row);
  }
  const opts = Object.keys(LANGS).map(l => `<option value="${l}">${LANGS[l].name}</option>`).join("");
  const rl = $("reclang"), fd = $("foreign");
  if (rl && !rl.dataset.done) {
    rl.innerHTML = opts; rl.value = recLang(); rl.dataset.done = "1";
    rl.onchange = () => { localStorage.setItem("reclang", rl.value); applyUI(); };
  }
  if (fd && !fd.dataset.done) {
    // foreign default excludes Italian (the frame is always Italian)
    fd.innerHTML = Object.keys(LANGS).filter(l => l !== "it")
      .map(l => `<option value="${l}">${LANGS[l].name}</option>`).join("");
    fd.value = foreignDefault(); fd.dataset.done = "1";
    fd.onchange = () => localStorage.setItem("foreign_default", fd.value);
  }
}

function loadVoices() { VOICES = speechSynthesis.getVoices() || []; buildVoicePickers(); }

// --- read-back toggle (silent by default): the reply is spoken only when on,
// and the voice/language panel is shown only then (it configures nothing else). ---
export const readbackOn = () => $("readback").checked;
export function syncVoicePanel() {
  $("voicepanel").style.display = readbackOn() ? "" : "none";
}

export function initTts() {
  if ("speechSynthesis" in window) {
    loadVoices();
    speechSynthesis.onvoiceschanged = loadVoices;
  }
  document.addEventListener("DOMContentLoaded", buildVoicePickers);
  const tv = $("testvoice");
  if (tv) tv.onclick = () => {
    speechSynthesis.cancel();
    const samples = { it: "Ciao, voce italiana.", en: "Hello, English voice.",
      es: "Hola, voz española.", fr: "Bonjour, voix française.", de: "Hallo, deutsche Stimme." };
    for (const lang of Object.keys(samples)) utter(samples[lang], lang);
  };

  $("readback").checked = localStorage.getItem("readback") === "1";
  $("readback").onchange = () => {
    localStorage.setItem("readback", readbackOn() ? "1" : "0");
    if (!readbackOn()) { try { speechSynthesis.cancel(); } catch (e) {} }
    syncVoicePanel();
  };
  syncVoicePanel();
}
