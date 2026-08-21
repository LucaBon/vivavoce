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
 * Start streaming the microphone to /wakeword/chunk. Returns a handle with
 * .stop() (async — tears down the mic, audio graph, and tells the server to
 * release this client's session). Errors (no mic permission, fetch
 * failures) go to opts.onError; opts.onTriggered() fires each time a chunk
 * comes back with triggered:true.
 */
export async function startWakeStream({ clientId, onTriggered, onError }) {
  let stopped = false;
  let ctx, source, processor, stream;
  try {
    stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    ctx = new (window.AudioContext || window.webkitAudioContext)();
    source = ctx.createMediaStreamSource(stream);
    const bufferSize = 4096;
    processor = (ctx.createScriptProcessor || ctx.createJavaScriptNode)
      .call(ctx, bufferSize, 1, 1);
    processor.onaudioprocess = (event) => {
      if (stopped) return;
      const float32 = event.inputBuffer.getChannelData(0);
      const resampled = resample(float32, ctx.sampleRate, TARGET_RATE);
      const pcm16 = floatTo16BitPCM(resampled);
      fetch("/wakeword/chunk?client=" + encodeURIComponent(clientId), {
        method: "POST",
        headers: { "Content-Type": "application/octet-stream" },
        body: pcm16.buffer,
      }).then((r) => r.json()).then((d) => {
        if (d && d.triggered) onTriggered();
      }).catch((e) => { if (onError) onError(e); });
    };
    source.connect(processor);
    // A ScriptProcessor must be connected to a destination to fire
    // onaudioprocess in every browser; muted so nothing is heard twice.
    const mute = ctx.createGain();
    mute.gain.value = 0;
    processor.connect(mute);
    mute.connect(ctx.destination);
  } catch (e) {
    if (onError) onError(e);
    throw e;
  }

  return {
    stop() {
      stopped = true;
      try { processor && processor.disconnect(); } catch (e) {}
      try { source && source.disconnect(); } catch (e) {}
      try { stream && stream.getTracks().forEach((t) => t.stop()); } catch (e) {}
      try { ctx && ctx.close(); } catch (e) {}
      return fetch("/wakeword/stop?client=" + encodeURIComponent(clientId), {
        method: "POST",
      }).catch(() => {});  // best-effort: the server also just leaks memory, not state
    },
  };
}
