# Third-party models

Vivavoce ships **no model weights**. Its own package carries none, and the
default container image (`ASR=0 WAKEWORD_VOSK=0`, see `Dockerfile`) contains
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

## Vosk — optional server-side wake word (Pro)

- Installed only with `uv sync --group wakeword-vosk` or
  `--build-arg WAKEWORD_VOSK=1`. It replaced openWakeWord, whose pretrained
  models were CC-BY-NC-SA behind a paid tier — a licence this one does not
  carry, which is half the reason for the swap.
- Runtime: [vosk-api](https://github.com/alphacep/vosk-api), Apache-2.0.
- Weights: the **small** model for the configured language, Apache-2.0 for
  `it` and `en-us` — check [the model list](https://alphacephei.com/vosk/models)
  before adding a language, because a few entries there (some French ones)
  are CC-BY-NC-SA and would not be usable in a paid feature.
- **Downloaded once at start-up**, from `https://alphacephei.com/vosk/models`
  into `<data_dir>/vosk-models/` — so in Docker it lands in the persistent
  volume and survives image updates, like the Whisper weights. At start-up and
  not on first use, unlike Whisper: the wake word's first request is a 320 ms
  audio chunk in a stream of them, and a 50 MB fetch inside it would time the
  request out and read as a broken engine rather than a slow one.
  `--wakeword-no-download` (or `VIVAVOCE_WAKEWORD_NO_DOWNLOAD`) turns it off
  for an offline install; `--wakeword-vosk-model` points at a directory you
  manage yourself, and is never downloaded over.
- This is the engine that hears the phrase the household typed. It is
  open-vocabulary in the sense that any phrase can be *configured*, not that
  any phrase can be *heard* — Kaldi only produces words in its lexicon, so
  `POST /wakeword/phrase` refuses a coined name rather than accepting one
  that would never fire.

## Not shipped, not used

`tools/sherpa_bench.py` downloads sherpa-onnx keyword-spotting, Silero VAD and
NeMo Parakeet models into a git-ignored directory. It is a benchmark harness
used once to choose between engines. Nothing under `engine/` or `localvoice/`
imports `sherpa_onnx`.
