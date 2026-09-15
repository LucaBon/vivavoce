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
from player.registry import BACKENDS

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
    # The wake word is gated on its OWN "wakeword-vosk" group (not "asr" — an
    # optional engine that fails to install must not take a working one down
    # with it), so every message telling the user how to install it must say
    # so; a copy-paste from the ASR messages would send them to
    # `uv sync --group asr`, which never installs it.
    result_help = subprocess.run(
        [sys.executable, "-m", "localvoice", "--help"],
        cwd=ROOT, capture_output=True, text=True, timeout=30)
    assert "--wakeword-vosk-model" in result_help.stdout
    # Whitespace-normalised: argparse wraps help text at the terminal width,
    # and "uv sync --group wakeword-vosk" is long enough to be split across
    # two lines — which the old spelling of this assertion was one character
    # away from hitting too.
    flat = " ".join(result_help.stdout.split())
    assert "uv sync --group wakeword-vosk" in flat
    # The flag's own description, not everything after it: the FIRST mention
    # is in the usage line at the top, and slicing from there swept in
    # --asr-model's help — which of course names the asr group.
    body = flat[flat.rindex("--wakeword-vosk-model"):]
    body = body[:body.index("--wakeword-no-download")]
    assert "uv sync --group wakeword-vosk" in body
    assert "uv sync --group asr" not in body


def test_the_retired_openwakeword_flags_are_gone():
    # --wakeword-model chose between openWakeWord's bundled English models.
    # A flag that survives the engine it configured is a flag that silently
    # does nothing, and this one would have sat right next to three that do.
    result_help = subprocess.run(
        [sys.executable, "-m", "localvoice", "--help"],
        cwd=ROOT, capture_output=True, text=True, timeout=30)
    assert "--wakeword-model" not in result_help.stdout.replace(
        "--wakeword-vosk-model", "")


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
# `asr` reaches onnxruntime through CTranslate2, and onnxruntime has never
# published a 32-bit wheel. On a Raspberry Pi running a 32-bit image,
# "uv sync --group asr" is therefore an instruction that cannot succeed — and
# that is exactly the machine most likely to read it, since four places in the
# docs advertise the Pi. The message earns its keep only if it fires on the
# right machines and stays silent on the rest, so both directions are checked.
#
# `wakeword-vosk` is the counter-example: vosk ships an armv7l wheel, so on
# that same Pi it installs, and it must NOT carry this note. It has no note of
# its own — there is no supported platform it fails on — so what is checked
# below is the targeting: the asr message carries the note, the wake-word
# message does not, and the note itself really fires on armv7l.

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
    assert "unavailable_note" not in message


def test_the_onnxruntime_note_still_fires_where_it_should(monkeypatch):
    # The other half of the rule above, as behaviour rather than spelling: the
    # note the wake word must NOT carry is a real note that really fires, so
    # the assertion above is about targeting, not about a dead string.
    #
    # There is no counterpart for vosk any more. It used to have one, saying
    # "no macOS wheel" — true of 0.3.45 and of nothing else, since the floor
    # dropped to 0.3.44 where the universal2 wheel still exists. A function
    # enumerating the platforms a package cannot install on, with no members
    # left in it, is a comment pretending to be code.
    monkeypatch.setattr(server.platform, "machine", lambda: "armv7l")
    assert server.optional_groups_unavailable_here() != ""


def test_the_architecture_note_actually_reaches_the_engine_messages():
    # The half the source scan above can no longer see. Those messages append
    # a note that is now a PARAMETER, so the note can be present in every
    # message and still be empty on every machine if server.py stops passing
    # it — a seam that did not exist while both halves were one file.
    with open(os.path.join(ROOT, "localvoice", "server.py"), encoding="utf-8") as f:
        source = f.read()
    call = source[source.index("audio_engines.build("):]
    assert "optional_groups_unavailable_here()" in call.split(")\n")[0]


# -- --services is validated by the backend, not by LMS ------------------------
# The list somebody types is a list of names the music system in front of us
# has to recognise. Held against the LMS table on a MusicAssistant, a provider
# that server really has was refused before the app had started once, and the
# alternatives printed underneath were the wrong music system's.

def test_a_music_assistant_provider_is_not_measured_against_the_lms_table(
        ma, ma_transport):
    ma_transport.responses["config/providers"] = [
        {"domain": "apple_music", "enabled": True},
        {"domain": "filesystem", "enabled": True},
    ]
    services, complaint = server.explicit_services(
        ma, BACKENDS["musicassistant"], "apple_music")
    assert complaint == ""
    assert services == ["apple_music"]


def test_a_name_this_music_assistant_has_not_got_is_still_refused(
        ma, ma_transport):
    # "spotify" is a perfectly good LMS service and a perfectly good MA
    # provider — and not one THIS server has, which is the only question.
    ma_transport.responses["config/providers"] = [
        {"domain": "apple_music", "enabled": True}]
    services, complaint = server.explicit_services(
        ma, BACKENDS["musicassistant"], "spotify")
    assert services == []
    assert "spotify" in complaint and "apple_music" in complaint


def test_a_provider_switched_off_does_not_stop_the_app_from_starting(
        ma, ma_transport):
    # The escape hatch again, from the other side: a provider mid-re-auth
    # answers `enabled: false`, and refusing to boot the voice assistant over
    # it would be calling an outage a misspelling.
    ma_transport.responses["config/providers"] = [
        {"domain": "tidal", "enabled": False},
        {"domain": "qobuz", "enabled": True},
    ]
    services, complaint = server.explicit_services(
        ma, BACKENDS["musicassistant"], "tidal")
    assert (services, complaint) == (["tidal"], "")


def test_the_lms_list_is_the_lms_table_and_costs_no_round_trip(lms, transport):
    # Unchanged, and deliberately still answered offline: --services is the
    # escape hatch for when asking the server misbehaves.
    services, complaint = server.explicit_services(
        lms, BACKENDS["lms"], "tidal,qobuz")
    assert (services, complaint) == (["tidal", "qobuz"], "")
    assert transport.commands() == []


def test_a_name_no_lms_has_is_refused_with_the_lms_list(lms, transport):
    services, complaint = server.explicit_services(lms, BACKENDS["lms"], "spotty")
    assert services == []
    assert "tidal" in complaint


def test_a_server_that_will_not_answer_does_not_get_to_refuse(ma, ma_transport):
    # An escape hatch that needs the detection to work is not one: with no
    # answer to validate against, the list is taken as typed.
    ma_transport.raise_on.add("config/providers")
    services, complaint = server.explicit_services(
        ma, BACKENDS["musicassistant"], "apple_music")
    assert (services, complaint) == (["apple_music"], "")


def test_an_empty_list_is_still_refused(lms, transport):
    services, complaint = server.explicit_services(lms, BACKENDS["lms"], " , ")
    assert services == []
    assert complaint.startswith("--services non valido")
