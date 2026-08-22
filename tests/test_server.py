"""Startup resilience of the local web server (localvoice/server.py).

The hosting PC often wakes from sleep (or boots) before the network is back:
an unreachable LMS at that moment is transient, so startup must wait and
retry instead of dying with a traceback.
"""

import os
import subprocess
import sys

from lms import LMSError

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


def test_wait_for_players_retries_until_lms_answers(monkeypatch, capsys):
    sala = [{"playerid": "aa:bb:cc:dd:ee:ff", "name": "Sala"}]
    outcomes = [LMSError("rete giu"), LMSError("rete giu"), sala]

    class FlakyClient:
        def __init__(self, url, player_id):
            pass

        def get_players(self):
            out = outcomes.pop(0)
            if isinstance(out, Exception):
                raise out
            return out

    monkeypatch.setattr(server, "LMSClient", FlakyClient)
    naps = []
    players = server.wait_for_players("http://lms:9000", delay=5,
                                      sleep=naps.append)
    assert players == sala
    assert naps == [5, 5]  # one nap per failed attempt, then success
    out = capsys.readouterr().out
    assert "LMS non raggiungibile" in out
    assert "LMS raggiunto" in out


def test_wait_for_players_immediate_hit_stays_quiet(monkeypatch, capsys):
    sala = [{"playerid": "aa:bb:cc:dd:ee:ff", "name": "Sala"}]

    class HealthyClient:
        def __init__(self, url, player_id):
            pass

        def get_players(self):
            return sala

    monkeypatch.setattr(server, "LMSClient", HealthyClient)
    players = server.wait_for_players(
        "http://lms:9000", sleep=lambda s: (_ for _ in ()).throw(AssertionError))
    assert players == sala
    assert capsys.readouterr().out == ""  # no retry chatter when all is well


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
    # either a live LMS or mocking discovery/wait_for_players in ways that
    # risk hanging on real network calls for no extra safety over this.
    with open(os.path.join(ROOT, "localvoice", "server.py"), encoding="utf-8") as f:
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


def test_both_unavailable_messages_carry_the_architecture_note():
    # Source scan, for the same reason as the test above it: the prints sit
    # before LMS discovery. Whichever engine the user is missing, they must
    # learn on a 32-bit box that the install can't work — not just one of them.
    with open(os.path.join(ROOT, "localvoice", "server.py"), encoding="utf-8") as f:
        source = f.read()
    for marker in ("Riconoscimento vocale locale non installato",
                   "Parola chiave lato server non installata"):
        assert marker in source
        message = source[source.index(marker):source.index(marker) + 400]
        assert "optional_groups_unavailable_here()" in message, marker
