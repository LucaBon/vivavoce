// Microphone input: the engines that turn a command into text.
//
// * Web Speech (the browser's recognition, default) — tap-to-talk and the
//   continuous wake-word mode (see wakeword.js).
// * Local speech recognition (Pro): record with MediaRecorder and let the
//   server's Whisper transcribe (/transcribe) — the audio never leaves the
//   LAN, unlike Web Speech which ships it to Google/Apple.
//
// Who *holds* the microphone is miccapture.js's business: it runs the
// server-side wake word and owns the start/end of a command capture. This
// module asks it to start and stop listening, and tells it when a capture is
// over; it never reaches into that state itself.

import { $ } from "./util.js";
import { LANGS, ui, recLang, getStatusBase, setStatusBase, refreshStatus } from "./i18n.js";
import { isPro, showProUpsell } from "./pro.js";
import { handleManualFinal, autosendFollowWakeMode } from "./chat.js";
import { wakeWord } from "./settings.js";
import { createWakeHandler } from "./wakeword.js";
import { micUI, LOCALREC_MAX_MS, serverWakeOn, syncWakePhrase,
         serverWakeRunning, serverWakeStartPending, startServerWake,
         stopServerWake, endCommandCapture } from "./miccapture.js";

export { refreshServerWake } from "./miccapture.js";

// --- Local speech recognition (Pro): the toggle appears only when GET /asr
// says the engine is installed; Web Speech stays the default and takes back
// over for the session on any /transcribe failure.
let ASR = { available: false };
let asrFailed = false;   // one failure = fall back to Web Speech until reload
let localRec = null;     // the active MediaRecorder while capturing
let localRecTimer = null;

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

// "(re)start continuous listening with whichever engine is selected now",
// filled in by whichever branch of initMic() set the recogniser up. The
// engine checkbox is wired outside those branches and used to only write to
// localStorage: flipping it while already listening changed nothing until
// wake mode was switched off and on again, which looked exactly like the
// engine choice being ignored. Stays null where there is no wake mode to
// restart at all (insecure context).
let restartWakeListening = null;

// The wake-mode checkbox behaves identically in both branches below; only
// the restart it triggers differs, and that is already behind the variable
// above by the time this runs.
function wireWakeModeToggle() {
  $("wakemode").onchange = () => {
    const on = $("wakemode").checked;
    localStorage.setItem("wakemode", on ? "1" : "0");
    $("wakeopts").style.display = on ? "" : "none";
    autosendFollowWakeMode(on);
    restartWakeListening();
  };
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
        if (serverWakeRunning()) stopServerWake();
        else if (!serverWakeStartPending()) startServerWake(captureCommandNoSR);
        return;
      }
      if (localAsrOn()) startLocalRec(); else refreshStatus();
    };
    // No Web Speech here, so continuous listening only exists via the
    // server-side engine; without it selected, there is nothing to start.
    restartWakeListening = () => {
      stopServerWake();
      if ($("wakemode").checked && serverWakeOn() && !serverWakeStartPending()) {
        startServerWake(captureCommandNoSR);
      }
    };
    wireWakeModeToggle();
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
    // Chrome ends a silent continuous session with `no-speech` roughly every
    // 8 seconds, and `aborted` whenever a session is replaced. Neither is
    // something to tell the user about: printing them made wake mode flip
    // between "Errore microfono: no-speech" and "In ascolto…" forever, with
    // an earcon each time — the app looked broken while working exactly as
    // designed. They are silent; the ones that mean something are not.
    const ROUTINE_ERRORS = new Set(["no-speech", "aborted"]);
    // A real fault (network, audio-capture) restarted just as blindly, so a
    // failing mic looped without ever saying why. After this many in a row,
    // wake mode stops and says what happened.
    const MAX_WAKE_FAILURES = 5;
    let wakeFailures = 0;
    // Set when a live session is torn down deliberately (see stopAll), cleared
    // when the next one actually starts. There is only ONE recogniser object,
    // reused for every mode, so a late onend/onerror carries nothing that says
    // which session it belongs to — and the one we just killed must not write
    // over the status line whoever replaced it has since claimed. Concretely:
    // switching to the server engine tears this down and then reports a
    // getUserMedia rejection, and the dying session's own error ("network",
    // "aborted") was erasing that message, intermittently.
    let tornDown = false;
    const wake = createWakeHandler(rec);

    function configure(continuous) {
      rec.continuous = continuous;
      rec.lang = (LANGS[recLang()] || LANGS.it).tag;  // match the language I'll speak
    }
    function startManual() {
      if (active) { rec.stop(); return; }  // second tap stops
      mode = "manual"; configure(false); tornDown = false;
      try { rec.start(); } catch (e) {}
    }
    function startWake() {
      mode = "wake"; configure(true); tornDown = false;
      try { rec.start(); } catch (e) {}
    }
    function stopAll() {
      mode = "off"; wake.clearCap();
      // Unconditionally, not just when `active`: a session that never reached
      // onstart can still fail afterwards, and that is precisely the case
      // that bit — a start() whose error arrives later reports it against a
      // status line the next engine has already claimed. Cleared by whoever
      // starts the recogniser again, so its own errors are reported normally.
      tornDown = true;
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
          if (serverWakeRunning()) stopServerWake();
          else if (!serverWakeStartPending()) startServerWake(captureCommand);
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
      active = true; tornDown = false; wakeFailures = 0; micUI(true);
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
        setTimeout(() => {
          if (mode !== "wake" || active) return;
          try {
            rec.start();
          } catch (e) {
            // iOS Safari refuses to reopen the microphone outside a user
            // gesture, and the throw was swallowed: the panel kept saying
            // "In ascolto" over a recogniser that had stopped for good.
            statusEl.textContent = ui("tap_to_resume");
            micUI(false);
          }
        }, 350);
      } else if (tornDown) {
        mode = "off";  // torn down on purpose: whoever did it owns the status
      } else {
        // A plain tap-to-talk shot goes idle; a shot captured after a
        // server-wake trigger (mode "manual" via captureCommand) instead
        // falls back to "still listening for hey jarvis" when that's true.
        mode = "off";
        endCommandCapture();
      }
    };
    function leaveWakeMode() {
      mode = "off";
      $("wakemode").checked = false;
      $("wakeopts").style.display = "none";
      localStorage.setItem("wakemode", "0");
      micUI(false);
    }
    rec.onerror = (e) => {
      if (tornDown) return;  // an error about the session we just killed
      // A denied/blocked mic would otherwise restart-loop in wake mode: turn it off.
      if (e.error === "not-allowed" || e.error === "service-not-allowed") {
        statusEl.textContent = ui("mic_error") + e.error;
        leaveWakeMode();
        return;
      }
      if (mode === "wake") {
        // The routine end-of-session errors say nothing; onend restarts.
        if (ROUTINE_ERRORS.has(e.error)) return;
        // Anything else is a real fault. Give it a few restarts (a Wi-Fi
        // blip recovers), then stop and say so rather than loop in silence.
        if (++wakeFailures < MAX_WAKE_FAILURES) return;
        statusEl.textContent = ui("wake_gave_up")(e.error);
        leaveWakeMode();
        return;
      }
      statusEl.textContent = ui("mic_error") + e.error;
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
      if (serverWakeOn()) { if (!serverWakeStartPending()) startServerWake(captureCommand); }
      else startWake();
    };
    wireWakeModeToggle();
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
