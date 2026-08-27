# Third-party models

Vivavoce ships **no model weights**. Its own package carries none, and the
default container image (`ASR=0 WAKEWORD=0`, see `Dockerfile`) contains
neither of the two engines below. This page exists because "what is inside the
speech recognition" is a fair question, and because the AI Act assessment in
[`../docs/ai-act.md`](../docs/ai-act.md) says which of these Vivavoce provides
(none) and which it merely integrates (all of them).

## Browser speech recognition — the default microphone

The Web Speech API. Whatever engine the browser ships: **Google's** on Chrome
and Android, **Apple's** on Safari and iOS. Not distributed by this project, not
configurable from it, and — as [`../PRIVACY.md`](../PRIVACY.md) says up front —
the one part of Vivavoce that is not local. Their terms, not ours.

## Browser speech synthesis — the read-back voice

Same story: `speechSynthesis` and whichever voices the device has installed.
Some "natural"/"neural" voices are themselves cloud services of the OS vendor.
Off by default.

## faster-whisper — optional local speech recognition (Pro)

- Installed only with `uv sync --group asr` or `--build-arg ASR=1`.
- Runtime: [faster-whisper](https://github.com/SYSTRAN/faster-whisper), MIT,
  over [CTranslate2](https://github.com/OpenNMT/CTranslate2), MIT.
- Weights: OpenAI **Whisper**, MIT. Downloaded once, on the first
  transcription, from Hugging Face into `<data_dir>/asr-models/`
  (`localvoice/pro/asr.py`, `download_root`). Default size `small`; override
  with `--asr-model` / `VIVAVOCE_ASR_MODEL`.
- After that first download it loads from disk and needs no network.

## openWakeWord — optional server-side wake word (Pro)

- Installed only with `uv sync --group wakeword` or `--build-arg WAKEWORD=1`,
  pinned to `openwakeword==0.4.0` (see the comment in `pyproject.toml` for
  why the pin is exact).
- [openWakeWord](https://github.com/dscripka/openWakeWord), Apache-2.0. The
  pretrained ONNX models are bundled in the wheel itself, so there is **no
  download at all** — not even a one-time one.
- Phrases are fixed and English ("hey jarvis" by default); the model decides
  them, not this project.

## Not shipped, not used

`tools/sherpa_bench.py` downloads sherpa-onnx keyword-spotting, Silero VAD and
NeMo Parakeet models into a git-ignored directory. It is a benchmark harness
used once to choose between engines. Nothing under `engine/` or `localvoice/`
imports `sherpa_onnx`.
