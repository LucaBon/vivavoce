// Who holds the microphone, and when one command capture begins and ends.
//
// Split out of mic.js, which had grown past the 400-line ceiling the repo
// sets itself (see tests/test_packaging.py). The seam is ownership of the
// input device: this module runs the server-side wake word (the beep-free
// engine, see localvoice/pro/wakeword.py) and therefore owns the two facts
// every other engine has to ask about —
//
// * is a continuous stream holding the device right now, and
// * has the command capture it opened finished yet?
//
// mic.js keeps the engines that transcribe a command (Web Speech, local ASR)
// and calls in here to start/stop listening and to report a capture's end.
// The dependency runs one way only: nothing here imports mic.js.

import { $, clientId } from "./util.js";
import { ui } from "./i18n.js";
import { setWakeWordOverride } from "./settings.js";
import { beep } from "./wakeword.js";
import { startWakeStream } from "./serverwake.js";

// --- Screen wake lock -------------------------------------------------------
// Hands-free listening dies when the screen sleeps: the tab is frozen, the
// recogniser stops, and the page comes back saying "In ascolto" over nothing.
// A wake lock is exactly the promise being made — "leave this on the counter
// and talk to it" — and it is released the moment listening stops, so a phone
// left on a table does not stay lit.
let wakeLock = null;

async function acquireWakeLock() {
  if (wakeLock || !navigator.wakeLock) return;
  try {
    wakeLock = await navigator.wakeLock.request("screen");
    // The system drops the lock on its own when the tab is hidden; take it
    // back when the page is shown again (below).
    wakeLock.addEventListener("release", () => { wakeLock = null; });
  } catch (e) { /* denied, low battery, unsupported: listening still works */ }
}

function releaseWakeLock() {
  const held = wakeLock;
  wakeLock = null;
  if (held) { try { held.release(); } catch (e) {} }
}

document.addEventListener("visibilitychange", () => {
  if (document.visibilityState !== "visible") return;
  // Re-acquire only if something is still meant to be listening.
  if (serverWakeRunning() || $("mic").classList.contains("listening")) {
    acquireWakeLock();
  }
});

export function micUI(listening) {
  if (listening) acquireWakeLock(); else releaseWakeLock();
  $("mic").classList.toggle("listening", listening);
  $("mic").setAttribute("aria-pressed", listening ? "true" : "false");
  $("micstate").textContent = listening ? ui("micstate_listening") : ui("micstate_idle");
}

// How long one capture may last, for either engine. Web Speech auto-stops on
// its own; MediaRecorder does not, so it needs an explicit cap.
export const LOCALREC_MAX_MS = 30000;

// --- Server-side wake word (Pro): the beep-free alternative to Web Speech's
// continuous listening (see localvoice/pro/wakeword.py). Fixed to whichever
// English phrase the server's model detects ("hey jarvis" by default) — NOT
// the free-text wakeWord() field, which only makes sense for the Web Speech
// fuzzy-text engine. Offered as an extra choice alongside it, not instead.
let SERVERWAKE = { available: false, model: null };
let serverWakeStream = null;  // the active startWakeStream() handle, or null

const serverWakeCanUse = () => !!(navigator.mediaDevices && window.AudioContext);
export const serverWakeOn = () =>
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
export function syncWakePhrase() {
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

// mode/active (in mic.js, inside initMic) track the Web Speech `rec` object;
// server-side streaming has no such object, so its state lives here and its
// start/stop are wired into the same mic button and wakemode checkbox.
// serverWakeStarting covers the async gap while getUserMedia/startWakeStream
// is still pending: without it, a second click in that window (e.g. while
// the permission prompt is up) sees serverWakeStream still null and starts a
// SECOND concurrent stream, leaking the first one's mic/AudioContext forever.
let serverWakeStarting = false;

/** Is a server-side wake stream listening right now? */
export const serverWakeRunning = () => serverWakeStream !== null;
/** Is one still opening (getUserMedia/startWakeStream pending)? */
export const serverWakeStartPending = () => serverWakeStarting;

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

export async function startServerWake(onCommand) {
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

export function stopServerWake() {
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
export function endCommandCapture() {
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
