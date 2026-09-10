"""Startup resilience of the local web server (localvoice/server.py).

The hosting PC often wakes from sleep (or boots) before the network is back,
and a household switches its hi-fi off at night. Neither is a reason for the
process to die, and — since the web app is the only thing anyone looks at —
neither is a reason for it not to come up: see ``tests/test_setupserver.py``
for the page that says which of the two it is.
"""

import os
import subprocess
import sys

import server

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def test_python_dash_m_entry_point_works():
    # Both documented launch forms must keep working after the server split:
    # `python localvoice/server.py` and `python -m localvoice`. --help exits 0
    # without touching the network.
    result = subprocess.run([sys.executable, "-m", "localvoice", "--help"],
                            cwd=ROOT, capture_output=True, text=True,
                            timeout=30)
    assert result.returncode == 0, result.stderr
    assert "--lms" in result.stdout


def test_wakeword_help_points_at_the_right_group():
    # The wake-word feature is gated on its OWN "wakeword" group (not "asr" —
    # see pro/wakeword.py for why), so every message that tells the user how
    # to install it must say so; a copy-paste from the ASR messages would
    # send them to `uv sync --group asr`, which never installs it.
    result_help = subprocess.run(
        [sys.executable, "-m", "localvoice", "--help"],
        cwd=ROOT, capture_output=True, text=True, timeout=30)
    assert "--wakeword-model" in result_help.stdout
    help_text = result_help.stdout[result_help.stdout.index("--wakeword-model"):]
    assert "uv sync --group wakeword" in help_text
    assert "uv sync --group asr" not in help_text.split("\n\n")[0]


def test_wakeword_unavailable_message_points_at_the_right_group():
    # Source scan rather than driving main() end-to-end: the wake-word print
    # sits before LMS discovery, but exercising that path for real would mean
    # either a live LMS or mocking discovery/serve_setup in ways that
    # risk hanging on real network calls for no extra safety over this.
    #
    # audio_engines.py, not server.py: the engine choice moved there when it
    # pushed server.py past the 400-line ceiling.
    with open(os.path.join(ROOT, "localvoice", "audio_engines.py"),
              encoding="utf-8") as f:
        source = f.read()
    marker = "Parola chiave lato server non installata"
    assert marker in source
    message = source[source.index(marker):source.index(marker) + 200]
    assert "uv sync --group wakeword" in message
    assert "uv sync --group asr" not in message


# -- 32-bit machines -----------------------------------------------------------
#
# Both optional groups rest on onnxruntime (openWakeWord directly,
# faster-whisper through CTranslate2), which has never published a 32-bit
# wheel. On a Raspberry Pi running a 32-bit image, "uv sync --group wakeword"
# is therefore an instruction that cannot succeed — and that is exactly the
# machine most likely to read it, since four places in the docs advertise the
# Pi. The message earns its keep only if it fires on the right machines and
# stays silent on the rest, so both directions are checked.

def test_thirty_two_bit_arm_is_told_why_the_group_will_not_install(monkeypatch):
    for machine in ("armv7l", "armv6l", "armhf"):
        monkeypatch.setattr(server.platform, "machine", lambda m=machine: m)
        note = server.optional_groups_unavailable_here()
        assert "32 bit" in note, machine
        assert "onnxruntime" in note, machine
        assert "aarch64" in note, machine  # says what to do about it


def test_sixty_four_bit_machines_get_no_such_note(monkeypatch):
    # aarch64 above all: a Pi 4/5 on a 64-bit image installs both groups
    # perfectly well, and telling it otherwise would send users chasing a
    # limit they don't have.
    for machine in ("x86_64", "AMD64", "aarch64", "arm64"):
        monkeypatch.setattr(server.platform, "machine", lambda m=machine: m)
        assert server.optional_groups_unavailable_here() == "", machine


def _engine_message(marker, span=500):
    with open(os.path.join(ROOT, "localvoice", "audio_engines.py"),
              encoding="utf-8") as f:
        source = f.read()
    assert marker in source
    return source[source.index(marker):source.index(marker) + span]


def test_the_asr_message_carries_the_architecture_note():
    # Source scan, for the same reason as the test above it: the prints sit
    # before LMS discovery. faster-whisper reaches onnxruntime through
    # CTranslate2, so on a 32-bit box its instruction is a dead end and has
    # to say so.
    assert "unavailable_note" in _engine_message(
        "Riconoscimento vocale locale non installato")


def test_the_wake_word_message_does_NOT_carry_the_onnxruntime_note():
    # The one that used to, and was wrong to. That note speaks for the groups
    # resting on onnxruntime; the wake word now points at `wakeword-vosk`,
    # and vosk ships an armv7l wheel. On the 32-bit Pi the note exists for,
    # appending it announced that the only optional engine that CAN install
    # there is impossible — a worse answer than silence. It answers for its
    # own platforms instead.
    message = _engine_message("Parola chiave lato server non installata")
    assert "wheels_unavailable_here()" in message
    assert "unavailable_note" not in message


def test_the_two_notes_disagree_about_a_32_bit_pi(monkeypatch):
    # The behaviour behind the rule above, not just the spelling of it.
    from pro.vosk_wake import wheels_unavailable_here

    monkeypatch.setattr(server.platform, "machine", lambda: "armv7l")
    assert server.optional_groups_unavailable_here() != ""   # onnxruntime: no
    assert wheels_unavailable_here() == ""                   # vosk: yes


def test_vosk_says_where_it_really_cannot_install(monkeypatch):
    from pro import vosk_wake

    monkeypatch.setattr(vosk_wake.sys, "platform", "darwin")
    assert "macOS" in vosk_wake.wheels_unavailable_here()
    monkeypatch.setattr(vosk_wake.sys, "platform", "linux")
    assert vosk_wake.wheels_unavailable_here() == ""


def test_the_architecture_note_actually_reaches_the_engine_messages():
    # The half the source scan above can no longer see. Those messages append
    # a note that is now a PARAMETER, so the note can be present in every
    # message and still be empty on every machine if server.py stops passing
    # it — a seam that did not exist while both halves were one file.
    with open(os.path.join(ROOT, "localvoice", "server.py"), encoding="utf-8") as f:
        source = f.read()
    call = source[source.index("audio_engines.build("):]
    assert "optional_groups_unavailable_here()" in call.split(")\n")[0]
