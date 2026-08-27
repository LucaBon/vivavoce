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
export const localAsrOn = () =>
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
export async function startLocalRec() {
  if (localRec) { stopLocalRec(); return; }  // second tap stops, like Web Speech
  if (localRecStarting) return;              // one is opening; see the flags above
  localRecStarting = true;
  let stream;
  try {
    stream = await navigator.mediaDevices.getUserMedia({ audio: true });
  } catch (e) {
    $("status").textContent = ui("mic_error") + (e.name || e);
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
  rec.ondataavailable = (e) => { if (e.data && e.data.size) chunks.push(e.data); };
  rec.onstop = () => {
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
