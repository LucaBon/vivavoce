// Microphone input, both engines:
//
// * Web Speech (the browser's recognition, default) — tap-to-talk and the
//   continuous wake-word mode (see wakeword.js).
// * Local speech recognition (Pro): record with MediaRecorder and let the
//   server's Whisper transcribe (/transcribe) — the audio never leaves the
//   LAN, unlike Web Speech which ships it to Google/Apple.

import { $ } from "./util.js";
import { LANGS, ui, recLang, getStatusBase, setStatusBase, refreshStatus } from "./i18n.js";
import { isPro, showProUpsell } from "./pro.js";
import { handleManualFinal } from "./chat.js";
import { wakeWord } from "./settings.js";
import { createWakeHandler } from "./wakeword.js";

function micUI(listening) {
  $("mic").classList.toggle("listening", listening);
  $("mic").setAttribute("aria-pressed", listening ? "true" : "false");
  $("micstate").textContent = listening ? ui("micstate_listening") : ui("micstate_idle");
}

// --- Local speech recognition (Pro): the toggle appears only when GET /asr
// says the engine is installed; Web Speech stays the default and takes back
// over for the session on any /transcribe failure.
let ASR = { available: false };
let asrFailed = false;   // one failure = fall back to Web Speech until reload
let localRec = null;     // the active MediaRecorder while capturing
let localRecTimer = null;
const LOCALREC_MAX_MS = 30000;  // Web Speech auto-stops; we need our own cap

const canRecord = () => !!(navigator.mediaDevices && window.MediaRecorder);
const localAsrOn = () =>
  ASR.available && !asrFailed && canRecord() && $("localasr").checked;

function renderAsrRow() {
  $("localasrrow").style.display = (ASR.available && canRecord()) ? "" : "none";
  // A browser without Web Speech (e.g. Firefox) showed "no mic support":
  // with the server engine there IS a working mic — clear the warning.
  if (ASR.available && canRecord() && getStatusBase() === "nomic") {
    setStatusBase("default");
    refreshStatus();
  }
}
export async function refreshAsr() {
  try {
    const r = await fetch("/asr");
    ASR = await r.json();
  } catch (e) { ASR = { available: false }; }
  renderAsrRow();
}

function stopLocalRec() {
  clearTimeout(localRecTimer);
  if (localRec && localRec.state !== "inactive") localRec.stop();
}
async function startLocalRec() {
  if (localRec) { stopLocalRec(); return; }  // second tap stops, like Web Speech
  let stream;
  try {
    stream = await navigator.mediaDevices.getUserMedia({ audio: true });
  } catch (e) {
    $("status").textContent = ui("mic_error") + (e.name || e);
    return;
  }
  const mime = ["audio/webm;codecs=opus", "audio/webm", "audio/mp4"]
    .find(t => MediaRecorder.isTypeSupported(t)) || "";
  const rec = new MediaRecorder(stream, mime ? { mimeType: mime } : undefined);
  const chunks = [];
  rec.ondataavailable = (e) => { if (e.data && e.data.size) chunks.push(e.data); };
  rec.onstop = () => {
    stream.getTracks().forEach(t => t.stop());
    localRec = null;
    clearTimeout(localRecTimer);
    micUI(false);
    transcribeBlob(new Blob(chunks, { type: rec.mimeType || "audio/webm" }));
  };
  localRec = rec;
  rec.start();
  micUI(true);
  $("status").textContent = ui("listening");
  localRecTimer = setTimeout(stopLocalRec, LOCALREC_MAX_MS);
}
async function transcribeBlob(blob) {
  $("status").textContent = ui("asr_working");
  try {
    const r = await fetch("/transcribe?lang=" + encodeURIComponent(recLang()), {
      method: "POST",
      headers: { "Content-Type": blob.type || "application/octet-stream" },
      body: blob
    });
    const d = await r.json();
    if (!d.ok) throw new Error(d.error || "transcribe failed");
    const text = (d.text || "").trim();
    if (!text) { $("status").textContent = ui("tap_mic"); return; }  // silence
    const alts = (d.alternatives || []).filter(a => a && a.trim());
    handleManualFinal(text, alts.length ? alts : [text]);
  } catch (e) {
    asrFailed = true;  // Web Speech takes over for the rest of the session
    $("status").textContent = ui("asr_failed");
  }
}

// --- Speech recognition (Web Speech API) ---
export function initMic() {
  $("localasr").checked = localStorage.getItem("localasr") === "1";
  $("localasr").onchange = () =>
    localStorage.setItem("localasr", $("localasr").checked ? "1" : "0");

  const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
  const mic = $("mic");
  const statusEl = $("status");
  if (!SR) {
    setStatusBase("nomic");
    // No Web Speech (e.g. Firefox): the mic can still work through the server's
    // local recognition once /asr says it's installed and the toggle is on.
    mic.onclick = () => {
      if (!isPro()) { showProUpsell(); return; }
      if (localAsrOn()) startLocalRec(); else refreshStatus();
    };
  } else if (!window.isSecureContext && location.hostname !== "localhost"
             && location.hostname !== "127.0.0.1") {
    setStatusBase("nohttps");
  } else {
    const rec = new SR();
    rec.maxAlternatives = 5;  // hands-free: the server tries these in order
    rec.interimResults = true;  // show words live while speaking

    // mode: "off" (idle) | "manual" (one tap-to-talk shot) | "wake" (continuous,
    // listening for the wake word). `active` mirrors whether the recogniser runs.
    let mode = "off", active = false;
    const wake = createWakeHandler(rec);

    function configure(continuous) {
      rec.continuous = continuous;
      rec.lang = (LANGS[recLang()] || LANGS.it).tag;  // match the language I'll speak
    }
    function startManual() {
      if (active) { rec.stop(); return; }  // second tap stops
      mode = "manual"; configure(false);
      try { rec.start(); } catch (e) {}
    }
    function startWake() {
      mode = "wake"; configure(true);
      try { rec.start(); } catch (e) {}
    }
    function stopAll() {
      mode = "off"; wake.clearCap();
      try { rec.stop(); } catch (e) {}
    }

    mic.onclick = () => {
      // Il microfono è una funzione Pro: da bloccato porta al pannello licenza.
      if (!isPro()) { showProUpsell(); return; }
      if ($("wakemode").checked) { if (active) stopAll(); else startWake(); }
      // The local-recognition toggle only replaces tap-to-talk: the wake word
      // needs continuous listening, which stays on Web Speech.
      else if (localAsrOn()) startLocalRec();
      else startManual();
    };
    rec.onstart = () => {
      active = true; micUI(true);
      statusEl.textContent = mode === "wake" ? ui("listening_wake")(wakeWord()) : ui("listening");
    };
    rec.onend = () => {
      active = false; micUI(false);
      if (mode === "wake") {  // keep listening (mobile/Chrome auto-stop after a pause)
        setTimeout(() => { if (mode === "wake" && !active) { try { rec.start(); } catch (e) {} } }, 350);
      } else { mode = "off"; statusEl.textContent = ui("tap_mic"); }
    };
    rec.onerror = (e) => {
      statusEl.textContent = ui("mic_error") + e.error;
      // A denied/blocked mic would otherwise restart-loop in wake mode: turn it off.
      if (e.error === "not-allowed" || e.error === "service-not-allowed") {
        mode = "off"; $("wakemode").checked = false; $("wakehint").style.display = "none";
      }
    };
    rec.onresult = (e) => {
      if (mode === "wake") { wake.wakeResult(e); return; }
      // Manual mode: single-shot, show interim live, act on the final result.
      let finalTxt = "", finalAlts = null, interim = "";
      for (let i = e.resultIndex; i < e.results.length; i++) {
        const r = e.results[i];
        if (r.isFinal) { finalTxt = r[0].transcript; finalAlts = Array.from(r, (a) => a.transcript); }
        else interim += r[0].transcript;
      }
      if (interim && !finalTxt) { $("text").value = interim; return; }  // live feedback
      if (finalTxt) handleManualFinal(finalTxt, finalAlts);
    };

    // Restore the wake-mode toggle (needs a tap to actually start: browsers require
    // a user gesture to open the mic).
    $("wakemode").checked = localStorage.getItem("wakemode") === "1";
    $("wakehint").style.display = $("wakemode").checked ? "" : "none";
    $("wakemode").onchange = () => {
      const on = $("wakemode").checked;
      localStorage.setItem("wakemode", on ? "1" : "0");
      $("wakehint").style.display = on ? "" : "none";
      if (on) startWake(); else stopAll();
    };
  }
}
