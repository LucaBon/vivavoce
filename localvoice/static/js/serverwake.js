// Server-side wake-word streaming client: captures the microphone with the
// Web Audio API, resamples to the 16 kHz mono 16-bit PCM openWakeWord wants
// (see localvoice/pro/wakeword.py), and POSTs small chunks to
// /wakeword/chunk in a loop until stopped — no beep, no Web Speech restart
// cycle. Self-contained: no dependency on mic.js's internals, only on
// getUserMedia + fetch.
//
// ScriptProcessorNode is deprecated in favor of AudioWorkletNode, but it's
// what openWakeWord's own reference web client uses (a worklet would need a
// separate file served and loaded through audioWorklet.addModule, for a
// feature this narrow — one fixed English phrase — that's not worth the
// extra moving part yet); every browser this app targets still supports it.

const TARGET_RATE = 16000;

// How much audio goes in one POST. A ScriptProcessor hands us 4096 frames at
// a time — ~85 ms at 48 kHz — and each of those used to be its own request:
// twelve TCP+TLS handshakes a second, per phone, on a machine that may be a
// Raspberry Pi. Worse, they were fired without waiting, so several were in
// flight at once and the server received them out of order, scrambling the
// mel frames across chunk boundaries. Buffering to ~320 ms and sending one
// at a time fixes both, and openWakeWord is perfectly happy with the larger
// window (its own reference client uses 1280-sample chunks in-process).
const CHUNK_MS = 320;

// Linear-interpolation downsampler: browsers rarely honor a requested
// AudioContext sampleRate (Safari/iOS especially keeps the hardware rate),
// so this runs whenever the actual context rate isn't already 16 kHz —
// getting this wrong doesn't error, it just makes detection silently never
// fire, so it's worth doing properly rather than hoping the hint is honored.
function resample(float32, fromRate, toRate) {
  if (fromRate === toRate) return float32;
  const ratio = fromRate / toRate;
  const outLen = Math.floor(float32.length / ratio);
  const out = new Float32Array(outLen);
  for (let i = 0; i < outLen; i++) {
    const srcPos = i * ratio;
    const i0 = Math.floor(srcPos);
    const i1 = Math.min(i0 + 1, float32.length - 1);
    const frac = srcPos - i0;
    out[i] = float32[i0] * (1 - frac) + float32[i1] * frac;
  }
  return out;
}

function floatTo16BitPCM(float32) {
  const out = new Int16Array(float32.length);
  for (let i = 0; i < float32.length; i++) {
    const s = Math.max(-1, Math.min(1, float32[i]));
    out[i] = s < 0 ? s * 0x8000 : s * 0x7fff;
  }
  return out;
}

/**
 * Start streaming the microphone to /wakeword/chunk. Returns a handle with:
 *
 * * ``.pause()`` / ``.resume()`` — release and re-take the *microphone*
 *   while keeping the server session (see "the microphone is exclusive"
 *   below). Both are safe to call redundantly.
 * * ``.stop()`` (async) — tear down the mic and audio graph for good and
 *   tell the server to release this client's detector.
 *
 * Errors (no mic permission, fetch failures) go to opts.onError;
 * opts.onTriggered() fires each time a chunk comes back with triggered:true.
 *
 * **The microphone is exclusive.** This stream and the command capture that
 * follows a trigger (Web Speech, or MediaRecorder for local ASR — see
 * mic.js) cannot both hold the input device: on Android the system speech
 * recogniser takes the mic exclusively, so with this stream still holding it
 * the capture heard silence and *no command after "hey jarvis" was ever
 * understood*. Hence pause/resume rather than "just keep streaming":
 * mic.js lends the device out for the length of one command and takes it
 * back afterwards. Tearing the whole thing down instead would work too, but
 * would drop the server-side detector and pay to reload the ONNX model on
 * every single command.
 */
export async function startWakeStream({ clientId, onTriggered, onError }) {
  let stopped = false;   // stop() was called: this handle never comes back
  let paused = false;    // the mic is on loan to a command capture
  let resuming = null;   // in-flight resume(), so two calls can't open two graphs
  let ctx, source, processor, stream;
  // One chunk in flight at a time, and the samples that arrive meanwhile
  // waiting their turn — see CHUNK_MS.
  let pending = [];      // Int16Array pieces not yet sent
  let pendingSamples = 0;
  let inFlight = false;

  function queue(pcm16) {
    pending.push(pcm16);
    pendingSamples += pcm16.length;
    flush();
  }

  function takeChunk() {
    const out = new Int16Array(pendingSamples);
    let at = 0;
    for (const part of pending) { out.set(part, at); at += part.length; }
    pending = [];
    pendingSamples = 0;
    return out;
  }

  function flush() {
    if (inFlight || stopped) return;
    if (pendingSamples < (TARGET_RATE * CHUNK_MS) / 1000) return;
    inFlight = true;
    const chunk = takeChunk();
    fetch("/wakeword/chunk?client=" + encodeURIComponent(clientId), {
      method: "POST",
      headers: { "Content-Type": "application/octet-stream" },
      body: chunk.buffer,
    })
      .then((r) => r.json())
      .then((d) => { if (d && d.triggered) onTriggered(); })
      .catch((e) => { if (onError) onError(e); })
      .finally(() => { inFlight = false; flush(); });
  }

  // ONE AudioContext for the life of this handle. Creating a new one per
  // resume() meant creating it outside a user gesture, and on iOS Safari such
  // a context stays suspended for good: hands-free died silently after the
  // first command while the panel still said "In ascolto". Chrome also caps a
  // page at ~6 live contexts and then throws.
  function audioContext() {
    if (!ctx) ctx = new (window.AudioContext || window.webkitAudioContext)();
    return ctx;
  }

  async function openMic() {
    const media = await navigator.mediaDevices.getUserMedia({ audio: true });
    if (stopped) {  // stop() landed while getUserMedia was still pending
      media.getTracks().forEach((t) => t.stop());
      return;
    }
    stream = media;
    ctx = audioContext();
    // A context created (or left) suspended produces no audio at all and
    // reports no error; resume() is a no-op on a running one.
    if (ctx.state === "suspended") {
      try { await ctx.resume(); } catch (e) { /* reported by the caller */ }
    }
    source = ctx.createMediaStreamSource(stream);
    const bufferSize = 4096;
    processor = (ctx.createScriptProcessor || ctx.createJavaScriptNode)
      .call(ctx, bufferSize, 1, 1);
    processor.onaudioprocess = (event) => {
      if (stopped || paused) return;
      const float32 = event.inputBuffer.getChannelData(0);
      const resampled = resample(float32, ctx.sampleRate, TARGET_RATE);
      queue(floatTo16BitPCM(resampled));
    };
    source.connect(processor);
    // A ScriptProcessor must be connected to a destination to fire
    // onaudioprocess in every browser; muted so nothing is heard twice.
    const mute = ctx.createGain();
    mute.gain.value = 0;
    processor.connect(mute);
    mute.connect(ctx.destination);
  }

  // Release the microphone and the graph, but NOT the AudioContext: it is
  // kept for the life of the handle (see audioContext) so a resume() outside
  // a user gesture still has a running one. Buffered audio is dropped —
  // whatever was said while the mic was on loan is not for this detector.
  function closeMic(keepContext) {
    try { processor && processor.disconnect(); } catch (e) {}
    try { source && source.disconnect(); } catch (e) {}
    try { stream && stream.getTracks().forEach((t) => t.stop()); } catch (e) {}
    processor = source = stream = null;
    pending = [];
    pendingSamples = 0;
    if (keepContext) return;
    try { ctx && ctx.close(); } catch (e) {}
    ctx = null;
  }

  try {
    await openMic();
  } catch (e) {
    if (onError) onError(e);
    throw e;
  }

  return {
    pause() {
      if (stopped || paused) return;
      paused = true;
      closeMic(true);   // keep the context: resume() may be gesture-less
    },
    resume() {
      if (stopped || !paused) return resuming || Promise.resolve();
      paused = false;
      resuming = openMic()
        .catch((e) => {
          paused = true;  // the mic is genuinely gone; report, stay paused
          if (onError) onError(e);
        })
        .then(() => { resuming = null; });
      return resuming;
    },
    stop() {
      stopped = true;
      paused = false;
      closeMic();
      return fetch("/wakeword/stop?client=" + encodeURIComponent(clientId), {
        method: "POST",
      }).catch(() => {});  // best-effort: the server also just leaks memory, not state
    },
  };
}
