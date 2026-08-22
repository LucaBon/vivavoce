// Microphone input, both engines:
//
// * Web Speech (the browser's recognition, default) — tap-to-talk and the
//   continuous wake-word mode (see wakeword.js).
// * Local speech recognition (Pro): record with MediaRecorder and let the
//   server's Whisper transcribe (/transcribe) — the audio never leaves the
//   LAN, unlike Web Speech which ships it to Google/Apple.

import { $, clientId } from "./util.js";
import { LANGS, ui, recLang, getStatusBase, setStatusBase, refreshStatus } from "./i18n.js";
import { isPro, showProUpsell } from "./pro.js";
import { handleManualFinal, autosendFollowWakeMode } from "./chat.js";
import { wakeWord, setWakeWordOverride } from "./settings.js";
import { createWakeHandler, beep } from "./wakeword.js";
import { startWakeStream } from "./serverwake.js";

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

// --- Server-side wake word (Pro): the beep-free alternative to Web Speech's
// continuous listening (see localvoice/pro/wakeword.py). Fixed to whichever
// English phrase the server's model detects ("hey jarvis" by default) — NOT
// the free-text wakeWord() field, which only makes sense for the Web Speech
// fuzzy-text engine. Offered as an extra choice alongside it, not instead.
let SERVERWAKE = { available: false, model: null };
let serverWakeStream = null;  // the active startWakeStream() handle, or null

const serverWakeCanUse = () => !!(navigator.mediaDevices && window.AudioContext);
const serverWakeOn = () =>
  SERVERWAKE.available && serverWakeCanUse() && $("serverwake").checked;

// "hey_jarvis" -> "Hey Jarvis", for the status line.
function modelDisplayName(name) {
  return (name || "").split("_").map(w => w[0] ? w[0].toUpperCase() + w.slice(1) : w)
    .join(" ");
}

function renderServerWakeRow() {
  $("serverwakerow").style.display =
    (SERVERWAKE.available && serverWakeCanUse()) ? "" : "none";
  syncWakePhrase();
}

// The two engines don't just hear different phrases, they are SPOKEN
// differently — one sentence ("vivavoce metti i Pink Floyd") for Web Speech,
// two steps (phrase, beep, command) for the server one, because openWakeWord
// detects the trigger and nothing after it. One shared hint had testers
// saying "hey jarvis pausa" in a single breath, which can never work: the
// command capture only opens once the trigger has fired. So the panel shows
// the hint for the engine actually selected, and names the phrase that engine
// can actually hear.
function syncWakePhrase() {
  const server = serverWakeOn();
  setWakeWordOverride(server ? modelDisplayName(SERVERWAKE.model) : "");
  $("wakehint").style.display = server ? "none" : "";
  $("wakehint_server").style.display = server ? "" : "none";
  // Not merely greyed: a row labelled "keyword to say" above a box holding
  // "vivavoce" contradicts the hint next to it, which says the phrase is
  // fixed. The field comes back, with its value, on switching engine again.
  $("wakewordrow").style.display = server ? "none" : "";
}

export async function refreshServerWake() {
  try {
    const r = await fetch("/wakeword");
    SERVERWAKE = await r.json();
  } catch (e) { SERVERWAKE = { available: false }; }
  renderServerWakeRow();
}

// mode/active (below, inside initMic) track the Web Speech `rec` object;
// server-side streaming has no such object, so its state lives here and its
// start/stop are wired into the same mic button and wakemode checkbox.
// serverWakeStarting covers the async gap while getUserMedia/startWakeStream
// is still pending: without it, a second click in that window (e.g. while
// the permission prompt is up) sees serverWakeStream still null and starts a
// SECOND concurrent stream, leaking the first one's mic/AudioContext forever.
let serverWakeStarting = false;

// "(re)start continuous listening with whichever engine is selected now",
// filled in by whichever branch of initMic() set the recogniser up. The
// engine checkbox is wired outside those branches and used to only write to
// localStorage: flipping it while already listening changed nothing until
// wake mode was switched off and on again, which looked exactly like the
// engine choice being ignored. Stays null where there is no wake mode to
// restart at all (insecure context).
let restartWakeListening = null;

// A command capture is open right now (started by a wake trigger). Chunks go
// out every ~85 ms without waiting for the previous answer, so several are in
// flight at once and more than one can come back triggered:true for the same
// "hey jarvis" — and the second onTriggered ran captureCommand() again, which
// with Web Speech already running means startManual() -> rec.stop(): the
// capture that had just opened was closed a moment later, and the command was
// never heard. pause() narrows that window, this closes it.
let capturing = false;
let captureWatchdog = null;
// Every way a capture normally ends routes through endCommandCapture(). Every
// way it can fail to start does not: rec.start() throwing is swallowed, so no
// onstart/onend ever comes and the flag above would stay raised forever —
// deafening the wake word for the rest of the session, with the mic still on
// loan. Slightly longer than LOCALREC_MAX_MS, the longest legitimate capture.
const CAPTURE_MAX_MS = LOCALREC_MAX_MS + 5000;

async function startServerWake(onCommand) {
  const statusEl = $("status");
  serverWakeStarting = true;
  try {
    serverWakeStream = await startWakeStream({
      clientId: clientId(),
      onTriggered: () => {
        if (capturing) return;  // a duplicate trigger for the same phrase
        capturing = true;
        clearTimeout(captureWatchdog);
        captureWatchdog = setTimeout(endCommandCapture, CAPTURE_MAX_MS);
        beep();
        // Lend the microphone to the command capture for the length of one
        // command. The input device is exclusive (see startWakeStream): with
        // this stream still holding it, Web Speech / MediaRecorder heard
        // silence and nothing said after "hey jarvis" was ever understood.
        // endCommandCapture() takes it back when the capture finishes.
        if (serverWakeStream) serverWakeStream.pause();
        onCommand();
      },
      onError: (e) => {
        // stop first: it unconditionally resets the status text, and the
        // error message must be the last write, not the one stopped clobbers.
        stopServerWake();
        statusEl.textContent = ui("mic_error") + ((e && e.message) || e);
      },
    });
  } catch (e) {
    return;  // onError above already reported it; getUserMedia denied, etc.
  } finally {
    serverWakeStarting = false;
  }
  micUI(true);
  statusEl.textContent = ui("listening_wake")(modelDisplayName(SERVERWAKE.model));
}

function stopServerWake() {
  capturing = false;
  clearTimeout(captureWatchdog);
  if (serverWakeStream) {
    const s = serverWakeStream;
    serverWakeStream = null;
    s.stop();
  }
  micUI(false);
  $("status").textContent = ui("tap_mic");
}

// The end of a command capture (Web Speech one-shot or local ASR), whatever
// started it. Two things have to happen here, and both were missing:
//
// * give the microphone back to the server-side wake stream, which lent it
//   out at the trigger (see onTriggered) — without this the stream stayed
//   alive but deaf, so "hey jarvis" worked exactly once per tap;
// * tell the truth in the UI: if that stream is still running in the
//   background (it never stops just because one command was captured), the
//   button and status line must keep showing "listening for hey jarvis"
//   instead of going idle, or every command made the mic look switched off.
//
// Called on plain tap-to-talk too, where there is no wake stream and both
// steps degrade to the idle UI: resume() is a no-op unless paused.
function endCommandCapture() {
  capturing = false;
  clearTimeout(captureWatchdog);
  if (serverWakeStream) {
    serverWakeStream.resume();
    micUI(true);
    $("status").textContent = ui("listening_wake")(modelDisplayName(SERVERWAKE.model));
  } else {
    micUI(false);
    $("status").textContent = ui("tap_mic");
  }
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
    endCommandCapture();
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

  // Restore the wake-mode toggle for every branch below (needs a tap to
  // actually start: browsers require a user gesture to open the mic). Kept
  // unconditional — not just inside the Web-Speech branch — so a browser
  // without Web Speech (e.g. Firefox) doesn't silently drop a saved
  // preference on every reload even though server-side wake word (which
  // never needed Web Speech) could otherwise still honor it there.
  $("wakemode").checked = localStorage.getItem("wakemode") === "1";
  $("wakeopts").style.display = $("wakemode").checked ? "" : "none";

  const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
  const mic = $("mic");
  const statusEl = $("status");
  if (!SR) {
    setStatusBase("nomic");
    // No Web Speech (e.g. Firefox): the mic can still work through the server's
    // local recognition once /asr says it's installed and the toggle is on.
    // Server-side wake word also works here (it never needed Web Speech for
    // detection) — but without Web Speech, the post-trigger command capture
    // can only be local ASR, never the one-shot fallback the other branch has.
    const captureCommandNoSR = () => {
      if (localAsrOn()) startLocalRec();
      else $("status").textContent = ui("say_command");
    };
    mic.onclick = () => {
      if (!isPro()) { showProUpsell(); return; }
      if ($("wakemode").checked && serverWakeOn()) {
        if (serverWakeStream) stopServerWake();
        else if (!serverWakeStarting) startServerWake(captureCommandNoSR);
        return;
      }
      if (localAsrOn()) startLocalRec(); else refreshStatus();
    };
    // No Web Speech here, so continuous listening only exists via the
    // server-side engine; without it selected, there is nothing to start.
    restartWakeListening = () => {
      stopServerWake();
      if ($("wakemode").checked && serverWakeOn() && !serverWakeStarting) {
        startServerWake(captureCommandNoSR);
      }
    };
    $("wakemode").onchange = () => {
      const on = $("wakemode").checked;
      localStorage.setItem("wakemode", on ? "1" : "0");
      $("wakeopts").style.display = on ? "" : "none";
      autosendFollowWakeMode(on);
      restartWakeListening();
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

    // The post-trigger command capture for server-side wake word: openWakeWord
    // only detects the trigger, not the words that follow, so this reuses
    // whichever single-shot engine tap-to-talk already prefers.
    function captureCommand() {
      if (localAsrOn()) startLocalRec(); else startManual();
    }

    mic.onclick = () => {
      // Il microfono è una funzione Pro: da bloccato porta al pannello licenza.
      if (!isPro()) { showProUpsell(); return; }
      if ($("wakemode").checked) {
        if (serverWakeOn()) {
          if (serverWakeStream) stopServerWake();
          else if (!serverWakeStarting) startServerWake(captureCommand);
        } else if (active) stopAll();
        else startWake();
      }
      // The local-recognition toggle only replaces tap-to-talk: the wake word
      // needs continuous listening, which stays on Web Speech (unless the
      // server-side engine above is chosen instead).
      else if (localAsrOn()) startLocalRec();
      else startManual();
    };
    rec.onstart = () => {
      active = true; micUI(true);
      if (mode !== "wake") { statusEl.textContent = ui("listening"); return; }
      // A restart in the middle of "yes? tell me the command" — or of "check
      // the text and press Send" — must not answer its own question with
      // "listening…": the wake handler is still waiting on the user.
      if (!wake.isArmed() && !wake.isAwaitingReview()) {
        statusEl.textContent = ui("listening_wake")(wakeWord());
      }
    };
    rec.onend = () => {
      active = false;
      if (mode === "wake") {  // keep listening (mobile/Chrome auto-stop after a pause)
        // Brief flicker while Chrome cycles the continuous session — except
        // while a command has been asked for and not yet given, where going
        // dark reads as "it stopped listening" exactly when it hasn't.
        if (!wake.isArmed()) micUI(false);
        setTimeout(() => { if (mode === "wake" && !active) { try { rec.start(); } catch (e) {} } }, 350);
      } else {
        // A plain tap-to-talk shot goes idle; a shot captured after a
        // server-wake trigger (mode "manual" via captureCommand) instead
        // falls back to "still listening for hey jarvis" when that's true.
        mode = "off";
        endCommandCapture();
      }
    };
    rec.onerror = (e) => {
      statusEl.textContent = ui("mic_error") + e.error;
      // A denied/blocked mic would otherwise restart-loop in wake mode: turn it off.
      if (e.error === "not-allowed" || e.error === "service-not-allowed") {
        mode = "off"; $("wakemode").checked = false; $("wakeopts").style.display = "none";
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

    // Stop whichever engine is running before starting the selected one:
    // both are wired to the same button and checkbox, and leaving the old one
    // alive would mean two things holding the microphone. startWake() right
    // after stopAll() throws (the session is still ending) and is swallowed,
    // but rec.onend then restarts it 350 ms later — the same self-healing
    // cycle continuous mode already relies on.
    restartWakeListening = () => {
      stopAll();
      stopServerWake();
      if (!$("wakemode").checked) return;
      if (serverWakeOn()) { if (!serverWakeStarting) startServerWake(captureCommand); }
      else startWake();
    };
    $("wakemode").onchange = () => {
      const on = $("wakemode").checked;
      localStorage.setItem("wakemode", on ? "1" : "0");
      $("wakeopts").style.display = on ? "" : "none";
      autosendFollowWakeMode(on);
      restartWakeListening();
    };
  }

  // Which engine detects the wake word, available whenever GET /wakeword said
  // so (see refreshServerWake) — independent of whether Web Speech exists at
  // all, EXCEPT that the post-trigger command capture above falls back to Web
  // Speech's one-shot recognition when local ASR isn't installed, so it still
  // needs the `else` branch above to have set up `rec`. Flipping it applies
  // immediately, mid-session: it is a choice about the listening happening
  // right now, not a preference read at some later start.
  $("serverwake").checked = localStorage.getItem("serverwake") === "1";
  $("serverwake").onchange = () => {
    localStorage.setItem("serverwake", $("serverwake").checked ? "1" : "0");
    syncWakePhrase();
    if (restartWakeListening) restartWakeListening();
  };
  syncWakePhrase();
}
