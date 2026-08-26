"""Tests for localvoice/appdata.py: env-var namespace with legacy fallback,
data-dir resolution order, and atomic JSON read/write fail-open behavior."""

import os

import pytest

import appdata


# -- env() -------------------------------------------------------------------

def test_env_reads_primary_prefix():
    environ = {f"{appdata.PRIMARY_PREFIX}_LMS": "http://x:9000"}
    assert appdata.env("LMS", environ=environ) == "http://x:9000"


def test_env_default_when_missing():
    assert appdata.env("LMS", default="fallback", environ={}) == "fallback"
    assert appdata.env("LMS", environ={}) is None


def test_env_legacy_fallback(monkeypatch, capsys):
    monkeypatch.setattr(appdata, "LEGACY_PREFIX", "OLDNAME")
    monkeypatch.setattr(appdata, "_warned_legacy", set())
    environ = {"OLDNAME_PORT": "9999"}
    assert appdata.env("PORT", environ=environ) == "9999"
    assert "deprecata" in capsys.readouterr().out
    # The deprecation note prints once per variable, not once per read.
    assert appdata.env("PORT", environ=environ) == "9999"
    assert capsys.readouterr().out == ""


def test_env_primary_wins_over_legacy(monkeypatch):
    monkeypatch.setattr(appdata, "LEGACY_PREFIX", "OLDNAME")
    environ = {f"{appdata.PRIMARY_PREFIX}_PORT": "1", "OLDNAME_PORT": "2"}
    assert appdata.env("PORT", environ=environ) == "1"


# -- data_dir() ---------------------------------------------------------------

def test_data_dir_cli_wins(tmp_path):
    target = str(tmp_path / "cli-dir")
    environ = {f"{appdata.PRIMARY_PREFIX}_DATA_DIR": str(tmp_path / "env-dir")}
    assert appdata.data_dir(target, environ=environ) == target
    assert os.path.isdir(target)


def test_data_dir_env_fallback(tmp_path):
    target = str(tmp_path / "env-dir")
    environ = {f"{appdata.PRIMARY_PREFIX}_DATA_DIR": target}
    assert appdata.data_dir(None, environ=environ) == target
    assert os.path.isdir(target)


def test_data_dir_platform_default(tmp_path, monkeypatch):
    # Senza CLI né env si ripiega sulla cartella di piattaforma: qui basta
    # verificare che usi la base giusta (APPDATA su Windows, XDG altrove).
    if os.name == "nt":
        environ = {"APPDATA": str(tmp_path)}
        expected = os.path.join(str(tmp_path), appdata.APP_DIR_NAME)
    else:
        environ = {"XDG_DATA_HOME": str(tmp_path)}
        expected = os.path.join(str(tmp_path), appdata.APP_DIR_NAME.lower())
    assert appdata.data_dir(None, environ=environ) == expected
    assert os.path.isdir(expected)


# -- JSON helpers -------------------------------------------------------------

def test_json_roundtrip(tmp_path):
    path = str(tmp_path / "state.json")
    appdata.atomic_write_json(path, {"k": "à", "n": [1, 2]})
    assert appdata.read_json(path) == {"k": "à", "n": [1, 2]}
    assert not os.path.exists(path + ".tmp")  # no leftover temp file


def test_read_json_fails_open(tmp_path):
    missing = str(tmp_path / "missing.json")
    assert appdata.read_json(missing) is None
    assert appdata.read_json(missing, default={}) == {}
    corrupt = tmp_path / "corrupt.json"
    corrupt.write_text("{not json", encoding="utf-8")
    assert appdata.read_json(str(corrupt), default=[]) == []


def test_atomic_write_replaces_existing(tmp_path):
    path = str(tmp_path / "state.json")
    appdata.atomic_write_json(path, {"v": 1})
    appdata.atomic_write_json(path, {"v": 2})
    assert appdata.read_json(path) == {"v": 2}


# -- atomic writes are actually atomic, and durable ---------------------------

def test_two_writers_never_promote_a_half_written_file(tmp_path):
    """The temp file used to be a FIXED `<path>.tmp` name: two threads each
    opened it, each truncated it, and one renamed whatever was there — or
    lost the race with FileNotFoundError."""
    import threading

    path = str(tmp_path / "state.json")
    appdata.atomic_write_json(path, {"v": 0})
    errors = []
    payloads = [{"v": i, "pad": "x" * 20_000} for i in range(1, 9)]

    def writer(payload):
        for _ in range(20):
            try:
                appdata.atomic_write_json(path, payload)
            except Exception as exc:       # noqa: BLE001 - the bug was a raise
                errors.append(exc)
                return
            # Every read must see one of the whole payloads, never a splice.
            got = appdata.read_json(path)
            if not isinstance(got, dict) or got not in payloads:
                errors.append(AssertionError(f"torn read: {str(got)[:60]}"))
                return

    threads = [threading.Thread(target=writer, args=(p,)) for p in payloads]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert errors == []
    assert appdata.read_json(path) in payloads


def test_no_temp_files_are_left_behind(tmp_path):
    appdata.atomic_write_json(str(tmp_path / "state.json"), {"v": 1})
    assert [p.name for p in tmp_path.iterdir()] == ["state.json"]


def test_a_failed_write_leaves_the_old_file_and_no_debris(tmp_path):
    path = str(tmp_path / "state.json")
    appdata.atomic_write_json(path, {"v": 1})

    class Unserialisable:
        pass

    with pytest.raises(TypeError):
        appdata.atomic_write_json(path, {"v": Unserialisable()})
    assert appdata.read_json(path) == {"v": 1}
    assert sorted(p.name for p in tmp_path.iterdir()) == ["state.json"]


@pytest.mark.skipif(os.name == "nt",
                    reason="POSIX permission bits; Windows os.chmod only "
                           "toggles read-only, so 0600 is not representable "
                           "and st_mode comes back 0666")
def test_secrets_can_be_written_unreadable_by_others(tmp_path):
    import stat
    path = str(tmp_path / "license.json")
    appdata.atomic_write_json(path, {"key": "SECRET"}, mode=0o600)
    assert stat.S_IMODE(os.stat(path).st_mode) == 0o600


def test_the_mode_argument_is_harmless_where_it_cannot_be_honoured(tmp_path):
    # The call site passes mode= unconditionally (kidsafe.json, license.json),
    # so on Windows it has to be a no-op rather than an error.
    path = str(tmp_path / "license.json")
    appdata.atomic_write_json(path, {"key": "SECRET"}, mode=0o600)
    assert appdata.read_json(path) == {"key": "SECRET"}
