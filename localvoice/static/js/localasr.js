// Local speech recognition (Pro): record the command with MediaRecorder and
// let the server's Whisper transcribe it (POST /transcribe). The audio never
// leaves the LAN, unlike Web Speech — which ships it to Google/Apple.
//
// Split out of mic.js, which had grown back past the 400-line ceiling the
// repo sets itself (see tests/test_packaging.py). The seam is the engine:
// everything here is one way of turning speech into text, start to finish,
// and it knows nothing about the wake word or about who asked for a capture.
// mic.js keeps the Web Speech engine and the wiring that chooses between the
// two; miccapture.js still owns who holds the microphone.

import { $ } from "./util.js";
import { ui, recLang, getStatusBase, setStatusBase, refreshStatus } from "./i18n.js";
import { handleManualFinal, clearAwaitingReview } from "./chat.js";
import { micUI, LOCALREC_MAX_MS, endCommandCapture } from "./miccapture.js";

// The toggle appears only when GET /asr says the engine is installed; Web
// Speech stays the default and takes back over for the session on any
// /transcribe failure.
let ASR = { available: false };
let asrFailed = false;   // one failure = fall back to Web Speech until reload
let localRec = null;     // the active MediaRecorder while capturing
let localRecTimer = null;
// The getUserMedia/MediaRecorder equivalents of miccapture.js's
// serverWakeStarting / serverWakeCancelled, and for the same two reasons:
// `localRec` is only assigned once the permission prompt has been answered,
// so everything between the tap and that answer is a window in which the
// guards below see "nothing is recording".
let localRecStarting = false;   // getUserMedia pending: one is already opening
let localRecCancelled = false;  // torn down on purpose: throw the audio away

export const canRecord = () => !!(navigator.mediaDevices && window.MediaRecorder);
// The engine could take a command right now, whatever the toggle says: what
// mic.js falls back to when the browser has no recogniser of its own, or one
// that cannot reach its cloud service.
export const localAsrUsable = () => ASR.available && !asrFailed && canRecord();
export const localAsrOn = () => localAsrUsable() && $("localasr").checked;

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
// Stop a capture and discard what it recorded, for when listening is called
// off rather than finished. A plain stopLocalRec() transcribes and — with
// auto-send on — SENDS whatever the room happened to be saying, which is
// what tapping the mic to switch listening off used to do: the UI went dark
// and thirty seconds later the house was answered anyway.
export function cancelLocalRec() {
  if (!localRec && !localRecStarting) return;
  localRecCancelled = true;
  stopLocalRec();
}
// End of speech. Web Speech decides it on its own; MediaRecorder never does,
// so a capture used to run to LOCALREC_MAX_MS: thirty seconds between saying
// "cosa sta suonando" after the wake word and hearing the answer, which is
// exactly how the hands-free path on Edge ran once it fell back to this
// engine. Watch the level instead: stop ~1 s after speech goes quiet, and
// give up (without uploading anything) if nobody speaks at all. A room that
// is never quiet — the hi-fi itself playing loud — still ends at the cap.
const SILENCE_MS = 1200;
// Not heard at all for this long after the start. After a wake trigger the
// first things in the recording are the tail of the wake phrase (the server
// fires mid-word) and the beep: counted as speech, they made the natural
// pause before the command look like its end, and "vivavoce" was all that
// got transcribed.
const DEAF_MS = 800;
const NO_SPEECH_MS = 8000;
const SPEECH_RMS = 0.02;  // ~ -34 dBFS, after the browser's noise suppression

/** Call `onDone(spoke)` once, when the speaker has finished or never began.
 *  Returns the function that stops watching. */
function watchForSilence(stream, onDone) {
  const AC = window.AudioContext || window.webkitAudioContext;
  if (!AC) return () => {};
  const ctx = new AC();
  const analyser = ctx.createAnalyser();
  analyser.fftSize = 1024;
  ctx.createMediaStreamSource(stream).connect(analyser);
  const buf = new Float32Array(analyser.fftSize);
  const start = performance.now();
  let spoke = false, quietSince = start, timer = null;
  const stop = () => { clearInterval(timer); ctx.close().catch(() => {}); };
  timer = setInterval(() => {
    analyser.getFloatTimeDomainData(buf);
    let sum = 0;
    for (const v of buf) sum += v * v;
    const now = performance.now();
    if (now - start < DEAF_MS) return;
    if (Math.sqrt(sum / buf.length) > SPEECH_RMS) { spoke = true; quietSince = now; return; }
    if (spoke ? now - quietSince > SILENCE_MS : now - start > NO_SPEECH_MS) {
      stop();
      onDone(spoke);
    }
  }, 100);
  return stop;
}

export async function startLocalRec() {
  if (localRec) { stopLocalRec(); return; }  // second tap stops, like Web Speech
  if (localRecStarting) return;              // one is opening; see the flags above
  localRecStarting = true;
  // Cleared HERE, not only where it is consumed: a cancel that arrives while
  // nothing is open (the tap that stops listening, landing before the
  // permission prompt is answered) raises it with no capture to spend it on,
  // and it would then swallow the NEXT capture instead — silently, since
  // that branch throws the audio away by design.
  localRecCancelled = false;
  let stream;
  try {
    stream = await navigator.mediaDevices.getUserMedia({ audio: true });
  } catch (e) {
    localRecCancelled = false;
    // Give the microphone back before saying anything: a wake trigger lent
    // it to this capture, and without this the stream stays paused — alive
    // but deaf — until the capture watchdog fires half a minute later.
    // endCommandCapture() rewrites the status line, so the error goes last.
    endCommandCapture();
    $("status").textContent = ui("mic_error")(e);
    return;
  } finally {
    localRecStarting = false;
  }
  if (localRecCancelled) {  // cancelled while the permission prompt was up
    localRecCancelled = false;
    stream.getTracks().forEach(t => t.stop());
    return;
  }
  const mime = ["audio/webm;codecs=opus", "audio/webm", "audio/mp4"]
    .find(t => MediaRecorder.isTypeSupported(t)) || "";
  const rec = new MediaRecorder(stream, mime ? { mimeType: mime } : undefined);
  const chunks = [];
  let unwatch = () => {};
  rec.ondataavailable = (e) => { if (e.data && e.data.size) chunks.push(e.data); };
  rec.onstop = () => {
    unwatch();
    stream.getTracks().forEach(t => t.stop());
    localRec = null;
    clearTimeout(localRecTimer);
    const blob = new Blob(chunks, { type: rec.mimeType || "audio/webm" });
    // Cancelled: still give the microphone back (the wake stream may still
    // want it), but the audio goes nowhere.
    if (localRecCancelled) { localRecCancelled = false; endCommandCapture(); return; }
    endCommandCapture();
    transcribeBlob(blob);
  };
  localRec = rec;
  clearAwaitingReview();
  rec.start();
  micUI(true);
  $("status").textContent = ui("listening");
  localRecTimer = setTimeout(stopLocalRec, LOCALREC_MAX_MS);
  // Silence only: nothing said is thrown away, not sent to be transcribed.
  unwatch = watchForSilence(stream, (spoke) => (spoke ? stopLocalRec() : cancelLocalRec()));
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
