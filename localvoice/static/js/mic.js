// Microphone input: the engines that turn a command into text.
//
// * Web Speech (the browser's recognition, default) — tap-to-talk and the
//   continuous wake-word mode (see wakeword.js).
// * Local speech recognition (Pro), in localasr.js — recorded here, sent to
//   the server's Whisper. This module chooses between the two and owns the
//   mic button, the wake-mode checkbox and the engine choice; it does not
//   own either engine's insides.
//
// Who *holds* the microphone is miccapture.js's business: it runs the
// server-side wake word and owns the start/end of a command capture. This
// module asks it to start and stop listening, and tells it when a capture is
// over; it never reaches into that state itself.

import { $ } from "./util.js";
import { LANGS, ui, recLang, setStatusBase, refreshStatus } from "./i18n.js";
import { isPro, showProUpsell } from "./pro.js";
import { handleManualFinal, autosendFollowWakeMode,
         isAwaitingReview, clearAwaitingReview } from "./chat.js";
import { wakeWord } from "./settings.js";
import { createWakeHandler } from "./wakeword.js";
import { micUI, serverWakeOn, syncWakePhrase,
         serverWakeRunning, serverWakeStartPending, startServerWake,
         restartServerWake, stopServerWake,
         endCommandCapture } from "./miccapture.js";
import { localAsrOn, startLocalRec, cancelLocalRec } from "./localasr.js";

export { refreshServerWake } from "./miccapture.js";
export { refreshAsr } from "./localasr.js";

// Switching continuous listening off — by tap, by engine switch, or because
// the recogniser gave up — has to end the command capture the wake word
// opened, not just the stream that opened it. The capture outlives that
// stream: the recorder runs on to LOCALREC_MAX_MS and then transcribes and
// (auto-send being what wake mode implies) answers the room, thirty seconds
// after the UI went dark and said "tap the microphone".
//
// `stopWebSpeech` is initMic()'s branch-local teardown for the Web Speech
// recogniser, which only exists in one of its branches.
function stopWakeListening(stopWebSpeech) {
  cancelLocalRec();
  if (stopWebSpeech) stopWebSpeech();
  stopServerWake();
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
        // A tap during the opening window counts as "stop": the cancel flag
        // in miccapture.js makes the pending start land on the floor.
        if (serverWakeRunning() || serverWakeStartPending()) stopWakeListening();
        else startServerWake(captureCommandNoSR);
        return;
      }
      if (localAsrOn()) startLocalRec(); else refreshStatus();
    };
    // No Web Speech here, so continuous listening only exists via the
    // server-side engine; without it selected, there is nothing to start.
    restartWakeListening = () => {
      cancelLocalRec();
      if ($("wakemode").checked && serverWakeOn()) {
        restartServerWake(captureCommandNoSR);  // stops first; queues if opening
        return;
      }
      stopServerWake();
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
    // Which start attempt is current: a recovery scheduled below must not
    // fire behind a later tap that has already moved on.
    let startAttempt = 0;

    // Ask the recogniser for a session, recovering from one that never began.
    //
    // Dismissing the permission prompt — a tap OUTSIDE it rather than an
    // answer — is what this exists for, and it is the easiest thing in the
    // world to do by accident. Chrome sends nothing back for it: no onstart,
    // no onerror, no onend. The recogniser is left in its starting state,
    // where every later start() throws InvalidStateError, and that throw used
    // to be swallowed right here — so the microphone was dead for the rest of
    // the page's life. Tapping it did nothing at all, the prompt never came
    // back, and reloading was the only cure, which is exactly what a reload
    // is: a new recogniser object.
    //
    // abort() discards the stranded session. start() cannot follow it
    // immediately (it would throw for the same reason), so the retry waits
    // for the abort to land — and marks the session torn down first, so the
    // dying one's events are not mistaken for this one's.
    function startSession(nextMode, continuous) {
      mode = nextMode; configure(continuous); tornDown = false;
      const attempt = ++startAttempt;
      try { rec.start(); return; } catch (e) { /* stranded; recover below */ }
      tornDown = true;
      try { rec.abort(); } catch (e) {}
      setTimeout(() => {
        if (attempt !== startAttempt) return;  // a later tap owns the mic now
        mode = nextMode; configure(continuous); tornDown = false;
        try {
          rec.start();
        } catch (e) {
          // Twice is not a hiccup. Say so instead of leaving a dead button.
          statusEl.textContent = ui("mic_error") + (e.name || e);
          micUI(false);
        }
      }, 200);
    }

    function startManual() {
      if (active) { rec.stop(); return; }  // second tap stops
      clearAwaitingReview();  // a new capture: whatever is in the box is moot
      startSession("manual", false);
    }
    function startWake() {
      startSession("wake", true);
    }
    function stopAll() {
      mode = "off"; wake.clearCap();
      startAttempt++;  // drop any recovery scheduled by startSession
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
          // A tap during the opening window counts as "stop": the cancel flag
          // in miccapture.js makes the pending start land on the floor.
          if (serverWakeRunning() || serverWakeStartPending()) {
            stopWakeListening(stopAll);
          } else startServerWake(captureCommand);
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
      active = true; tornDown = false; wakeFailures = 0;
      wake.newSession();  // before micUI: it is micUI that starts the app talking
      micUI(true);
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
        endCommandCapture(isAwaitingReview());
      }
    };
    function leaveWakeMode() {
      mode = "off";
      // Not just the checkbox: unticking it while the server-side stream (and
      // the capture it lent the microphone to) keeps running leaves the page
      // listening — and POSTing chunks — under a panel that says it isn't.
      stopWakeListening(stopAll);
      $("wakemode").checked = false;
      $("wakeopts").style.display = "none";
      localStorage.setItem("wakemode", "0");
      micUI(false);
    }
    rec.onerror = (e) => {
      if (tornDown) return;  // an error about the session we just killed
      if (e.error === "not-allowed" || e.error === "service-not-allowed") {
        // Teardown first, message second: it resets the status line
        // unconditionally, so the error has to be the last write (the same
        // ordering miccapture.js's onError documents). stopAll() is what
        // makes that hold — it marks the session torn down, so the onend
        // that follows leaves the message alone.
        //
        // Only WAKE mode is switched off. There a denied mic would
        // restart-loop, which is what turning it off buys. On tap-to-talk
        // the same error is most often a prompt the user dismissed by
        // tapping beside it, and unticking continuous listening — a
        // preference they set deliberately — is no answer to that.
        if (mode === "wake" || $("wakemode").checked) leaveWakeMode();
        else { stopAll(); micUI(false); }
        statusEl.textContent = ui("mic_error") + e.error;
        return;
      }
      if (mode === "wake") {
        // The routine end-of-session errors say nothing; onend restarts.
        if (ROUTINE_ERRORS.has(e.error)) return;
        // Anything else is a real fault. Give it a few restarts (a Wi-Fi
        // blip recovers), then stop and say so rather than loop in silence.
        if (++wakeFailures < MAX_WAKE_FAILURES) return;
        leaveWakeMode();
        statusEl.textContent = ui("wake_gave_up")(e.error);
        return;
      }
      statusEl.textContent = ui("mic_error") + e.error;
    };
    rec.onresult = (e) => {
      if (mode === "wake") { wake.wakeResult(e); return; }
      // A result from a session torn down on purpose (engine switch, listening
      // switched off) is not a command anyone asked for — and with auto-send
      // on, acting on it answers the room after the UI said it had stopped.
      if (tornDown) return;
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
      cancelLocalRec();
      stopAll();
      if ($("wakemode").checked && serverWakeOn()) {
        restartServerWake(captureCommand);  // stops first; queues if opening
        return;
      }
      stopServerWake();
      if ($("wakemode").checked) startWake();
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
