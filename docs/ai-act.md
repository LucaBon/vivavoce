# Vivavoce and the EU AI Act

**Assessment date:** 27 August 2026 · **Version assessed:** 0.3.0 ·
**Author:** Luca Bonura

References below name files and symbols rather than line numbers: this is a
document that has to stay true across refactors, and a line number stops being
evidence the moment somebody splits a module.

This is the record behind one line of text in the app. Article 50(1) of the AI
Act obliges the *provider* to be able to show that it assessed whether the
obligation applies, and how it is met; the Commission's guidelines put that
burden squarely on the provider (C(2026) 5054, §42 and §45). A voice assistant
that says nothing about being one, with nothing written down about why, is the
shape of the problem the article was written for.

The short version: **one obligation applies — art. 50(1) — and it is met by the
notice under the microphone and the sentence spoken at the start of a hands-free
session.** Everything else in the Act is out of scope, and the reasons are below,
because an unargued "not applicable" is worth nothing to anyone reading this
later.

---

## 1. Legal basis, as at the assessment date

| Instrument | Bearing on this project |
|---|---|
| [Regulation (EU) 2024/1689](https://eur-lex.europa.eu/eli/reg/2024/1689/oj) (AI Act) | The base text |
| **Regulation (EU) 2026/1744** ("Digital Omnibus on AI"), OJ 24.7.2026, in force 27.7.2026 | Defers Annex III high-risk to **2 December 2027** and Annex I to **2 August 2028**; rewrites art. 4; leaves art. 50(1) untouched; grants one three-month grandfathering, for art. 50(2) marking only, to 2 December 2026 |
| **[C(2026) 5054 final, 20.7.2026](https://digital-strategy.ec.europa.eu/en/library/guidelines-transparency-obligations-providers-and-deployers-ai-systems)** — Commission guidelines on art. 50 | The operative document. Every § cited below is from it |
| [C(2025) 5053 final, 29.7.2025](https://ai-act-service-desk.ec.europa.eu/) — guidelines on the definition of an AI system | Excludes systems "based on the rules defined solely by natural persons" |
| [Code of Practice on Transparency of AI-Generated Content](https://digital-strategy.ec.europa.eu/en/policies/guidelines-transparency-ai-generated-content), June 2026 | Voluntary; relevant only to art. 50(2), which does not apply here |
| Legge 23 settembre 2025, n. 132 (Italy) | Designates **ACN** as market surveillance authority (inspection and sanction) and **AgID** for notification/accreditation. Implementing decrees still pending |

Article 50 has applied since **2 August 2026**, and §153 of the guidelines is
explicit that it binds every in-scope system on the market "regardless of their
date of placement on the market or putting into service". There is no
grandfathering for 50(1).

## 2. Who and what is being assessed

Vivavoce is developed by one person and made available in the Union under his
own name, so he is a **provider** (art. 3(3)) and the software is **placed on
the market** (art. 3(9)) through:

- the container image `ghcr.io/lucabon/vivavoce`;
- a Home Assistant add-on repository (`repository.yaml`, `ha-addon/config.yaml`);
- the GitHub source tree;
- a paid one-time **Pro** licence sold through Lemon Squeezy as merchant of
  record (`localvoice/static/js/pro.js`, `localvoice/licensing.py`).

The paid tier settles any doubt about "in the course of a commercial activity".

Households running it are **deployers acting in a purely personal,
non-professional capacity** and therefore carry no obligations of their own
(art. 2(10); guidelines §19). Nothing in this document asks anything of users.

The **free and open-source exemption of art. 2(12) does not help**: it is
expressly disapplied to art. 5 and art. 50, and guidelines §23 spells it out —
"providers and deployers of open-source AI systems within the scope of Article
50 AI Act still need to ensure compliance". `localvoice/pro/` is proprietary in
any case.

## 3. What is AI here, and what is not

The distinction matters more than the label, so both halves are listed.

### AI components

| Component | What it is | Where it runs | Ships by default |
|---|---|---|---|
| Browser Web Speech API (`static/js/mic.js`, `window.SpeechRecognition`) | The browser vendor's neural ASR | **Off-device** — Google on Chrome/Android, Apple on Safari/iOS | Yes, it is the default microphone |
| faster-whisper (`pro/asr.py`, `WhisperModel`) | Whisper, CTranslate2, int8 on CPU | On the household's own server | No — optional `asr` install, Pro |
| openWakeWord (`pro/wakeword.py`, `openwakeword.model.Model`) | Small ONNX keyword classifier, threshold `DETECT_THRESHOLD` 0.5 | On the household's own server | No — optional `wakeword` install, Pro |
| Browser `speechSynthesis` (`static/js/tts.js`, `speechSynthesis.speak`) | The browser vendor's TTS | On device, sometimes via the vendor's cloud voices | Present, opt-in, off by default |

Vivavoce provides none of these models. It integrates them.

### Not AI, by the Commission's own test

Everything between the transcript and the music server is rules written by a
person, which C(2025) 5053 places outside the definition of an AI system:

- **Intent routing** — an ordered ladder of compiled regexes, `intents.py`, `IntentTable._route`,
  with the patterns hand-written per language in `localvoice/lang/`.
- **Title matching** — `0.6 × containment + 0.4 × difflib.SequenceMatcher`,
  `engine/matching.py`, `_score`, with fixed thresholds.
- **"Moods"** — `engine/moods.py`'s `MOODS` is a static hand-written dict mapping the
  words *the user said* onto LMS genre tags and playlist names. It classifies
  **music**, not the listener. Nothing infers a mood, an emotion or any other
  attribute of a person.
- **Kid-safe** — `engine/guard.py`'s `is_blocked` is a whole-word regex match against a
  parent-authored blocklist; the gate itself (`pro/kidsafe.py`, `guard_for`) turns on
  whether *this browser* has entered the PIN in the last fifteen minutes.
- **Room targeting** — `pro/multiroom.py` fuzzy-matches LMS *player* names.

There is no LLM, no remote inference API, and no training of anything.

## 4. Article-by-article assessment

### Article 50(1) — interaction with natural persons: **APPLIES**

All four cumulative elements of guidelines §30 are present:

1. **An AI system.** Voice input is transcribed by a neural ASR in every
   configuration. The microphone is a Pro feature (`static/js/pro.js`, `applyPro`), but
   **every installation starts with fourteen days of full Pro**
   (`licensing.py`, `TRIAL_DAYS`), so the product as placed on the market has a voice for
   everyone who installs it.
2. **Intended to interact.** A genuine bidirectional exchange, multi-turn: the
   app offers a numbered list of candidates and the user answers "the second
   one" (`localvoice/router.py`).
3. **Directly.** No human intermediary.
4. **With natural persons.** It is a household appliance.

Guidelines §3.1.1 lists "**AI-enabled voice assistants**" as its first example
of a system in scope. There is no reading of that sentence that leaves Vivavoce
out.

**The "obvious" exception is not relied on.** It could be argued — a page
titled "comando vocale locale" that answers in a robot voice is not pretending
to be a person — but §45 requires it to be construed restrictively, and §44
requires the assessment to be made against the *foreseeable* audience, whose
expected level of circumspection drops when minors are part of it. Kid-safe
exists precisely because children are part of it. Arguing the exception here
would cost more than complying with the rule.

**How the obligation is met.**

- A standing line in the interaction area of the page (`localvoice/index.html`,
  `#ainotice`): *"Assistente automatico: stai parlando con un software, non con
  una persona."* / *"Automated assistant: you are talking to software, not to a
  person."* It sits with the microphone and the text box, per §37; it is not in
  a menu, which §38 rules out; it is unconditional, so no state can hide it.
- A spoken sentence at the start of a voice session, when the app has a voice
  at all or is listening continuously (`static/js/tts.js`, `speakAiNotice`,
  called from `micUI()` in `static/js/miccapture.js`): *"Assistente vocale
  automatico."* / *"Automated voice assistant."* This is the §37 "auditory
  disclosure", for the hands-free case where nobody looks at a screen. Said
  once per page session per language rather than once per command — §39 warns
  that a disclosure repeated past the point of being heard stops being one.
  It names no product: the product name is also the default wake word, and a
  notice that says the wake word into a live microphone wakes the app up. It
  is spoken below the read-back volume (`NOTICE_VOLUME`) — §37 asks that the
  disclosure be made plainly at the start of the interaction, not that it be
  the loudest thing in the room.
- Wording is deliberately short and plain. Guidelines §34 and footnote 40 ask
  for child-friendly, age-appropriate text in the official language of the
  Member State where the service is offered when minors are foreseeably in the
  audience; the notice is Italian on an Italian page and English on an English
  one.

Art. 50(5) is met on all three counts: clear and distinguishable (its own boxed
line, not prose in a paragraph), at the first interaction (before any command
can be typed or spoken), and accessible (real text in the document, read by
screen readers in document order, no colour-only signal).

`tests/test_ai_act_disclosure.py` pins the properties this rests on: that the
notice exists, sits in the interaction area, cannot be switched off by markup,
stylesheet or script, exists in both languages, and is still wired to the start
of listening.

### Article 50(2) — marking of synthetic content: **does not apply**

Vivavoce generates no synthetic audio, image, video or text.

- **Transcription is not generation.** Guidelines §4.3 lists "transcriptions of
  conversations" among the outputs outside the article, since they do not alter
  the semantics of the input.
- **Read-back is not generation either.** The spoken reply is a template string
  from `engine/messages.py` rendered by the *browser's* `speechSynthesis`
  (`static/js/tts.js`, `speechSynthesis.speak`). Vivavoce is not the provider of that engine, and
  reading a text aloud does not substantially alter the input data or its
  semantics — the exception at §56(iv)(2), which the guidelines reason the same
  way for assistive voice technologies. No realistic speech in any particular
  person's voice is produced; there is no voice cloning of any kind.
- The only audio the app synthesises itself is an 880 Hz beep
  (`static/js/wakeword.js`).

The three-month grandfathering the Omnibus grants for 50(2) is therefore moot.

### Article 50(3) — emotion recognition and biometric categorisation: **does not apply**

Neither is present. There is no speaker identification, no diarisation, no voice
embedding, no enrolment, no voice profile, and no inference of age, gender,
emotion or any other attribute of a person. See §3 above on `engine/moods.py`,
which classifies music, and on kid-safe, which is a device-state gate.

### Article 50(4) — deep fakes and public-interest text: **does not apply**

No content is generated or manipulated.

### Article 5 — prohibited practices: **does not apply**

No subliminal or manipulative technique, no exploitation of vulnerabilities, no
social scoring, no biometric categorisation inferring protected attributes, no
emotion recognition in workplaces or schools, and none of the generative
prohibitions the Omnibus added to art. 5. Kid-safe restricts *content* on a
parent's instruction; it does not profile the child.

### Article 6 and Annex III — high-risk: **does not apply**

Vivavoce falls in no Annex III area. It is not a safety component of a product
under Annex I. Independently of that, Regulation (EU) 2026/1744 defers those
obligations to 2 December 2027 and 2 August 2028 respectively.

### Article 4 — AI literacy: **applies, as an obligation of means**

Guidelines §25 confirms art. 4 reaches providers of art. 50 systems. Regulation
(EU) 2026/1744 rewrote it: providers now "take measures to **support the
development of** AI literacy", and the article expressly "does not require
providers or deployers to guarantee any specific level of AI literacy of any
individual". For a single-author project with no staff, the measure that fits is
telling users plainly what is AI here and what is not — the "What is AI in
Vivavoce" section of `README.md`, and this document.

### Articles 51–55 — general-purpose AI models: **does not apply**

Vivavoce provides no GPAI model. It is a downstream integrator of third-party
speech models.

## 5. Penalties, for the record

Non-compliance with art. 50 is sanctioned under art. 99(4) at up to €15 000 000
or 3 % of worldwide annual turnover, whichever is **higher** — except for SMEs
and start-ups, where art. 99(6) applies whichever is **lower**. Enforcement is
by the national market surveillance authority; in Italy that is ACN
(L. 132/2025, art. 20).

## 6. Model provenance

Vivavoce ships no weights. See [`../licenses/MODELS.md`](../licenses/MODELS.md)
for what the optional installs pull in, from where, and under which licence.

## 7. Review

This assessment is tied to a version and a date. Revisit it when any of these
changes:

- a new AI component is added — anything that infers rather than follows rules,
  in particular anything generative, anything that recognises *who* is speaking,
  or any remote inference API;
- the free/Pro line moves in a way that changes what a default install can do;
- the Commission revises the art. 50 guidelines, which §155 says it will;
- and in any case before **2 December 2027**, when the deferred Annex III
  obligations begin to apply.
