"""LMS discovery (``engine/discovery.py``) and the remembered address.

Broadcast is the fast path; the unicast sweep is what keeps `docker compose up`
zero-config inside a bridge/NAT (the broadcast never leaves the container, but
LMS answers the same TLV request sent unicast). The sweep tests talk to a fake
LMS bound on loopback — no real network involved.
"""

import json
import socket
import threading

import pytest

import appdata
import discovery


def _tlv(**fields) -> bytes:
    out = b""
    for tag, value in fields.items():
        raw = value.encode()
        out += tag.encode() + bytes([len(raw)]) + raw
    return out


# -- protocollo TLV -----------------------------------------------------------

def test_request_asks_the_expected_fields():
    req = discovery._request()
    assert req[:1] == b"e"
    assert req[1:] == b"NAME\x00IPAD\x00JSON\x00VERS\x00"


def test_parse_tlv_roundtrip():
    parsed = discovery._parse_tlv(_tlv(NAME="daphile", JSON="9000", VERS="9.0.3"))
    assert parsed == {"NAME": "daphile", "JSON": "9000", "VERS": "9.0.3"}


def test_server_from_accepts_only_e_replies():
    good = discovery._server_from(b"E" + _tlv(NAME="x"), "10.0.0.9")
    assert good == {"ip": "10.0.0.9", "NAME": "x"}
    assert discovery._server_from(b"?" + _tlv(NAME="x"), "10.0.0.9") is None
    assert discovery._server_from(b"", "10.0.0.9") is None


def test_base_url_uses_json_port_with_9000_fallback():
    assert discovery.base_url({"ip": "1.2.3.4", "JSON": "9002"}) == "http://1.2.3.4:9002"
    assert discovery.base_url({"ip": "1.2.3.4"}) == "http://1.2.3.4:9000"
    assert discovery.base_url({"ip": "1.2.3.4", "JSON": ""}) == "http://1.2.3.4:9000"


@pytest.mark.parametrize("junk", [
    '9000/"><svg onload=alert(1)>', "0", "65536", "-1", "90 00", "abc"])
def test_a_port_that_is_not_a_port_is_not_believed(junk):
    # Anything on the LAN can answer the broadcast, and this value becomes an
    # address that is remembered and written into the page.
    assert discovery.base_url({"ip": "1.2.3.4", "JSON": junk}) == \
        "http://1.2.3.4:9000"


# -- ordine delle subnet candidate --------------------------------------------

def test_candidate_phases_order_and_dedup(monkeypatch):
    # L'interfaccia locale coincide con una subnet comune: non va ripetuta.
    monkeypatch.setattr(discovery, "_local_prefixes",
                        lambda: ["192.168.1", "172.17.0"])
    phases = dict(discovery._candidate_phases())
    assert list(phases) == ["local", "common", "wide", "full"]
    assert phases["local"] == ["192.168.1", "172.17.0"]
    assert "192.168.1" not in phases["common"]          # già in "local"
    assert "10.0.0" in phases["common"]
    assert "192.168.1" not in phases["full"]            # niente doppioni
    assert "192.168.123" in phases["full"]              # il resto del /16 c'è
    all_prefixes = sum(phases.values(), [])
    assert len(all_prefixes) == len(set(all_prefixes))


def test_a_wide_local_range_is_swept_beyond_its_own_24(monkeypatch):
    # Una rete piatta 10.0.0.0/16 (NAS, switch gestito): l'LMS sta in una /24
    # vicina alla nostra, e prima della fase "wide" non veniva mai trovato.
    monkeypatch.setattr(discovery, "_local_prefixes", lambda: ["10.0.1"])
    phases = dict(discovery._candidate_phases())
    assert "10.0.7" in phases["wide"]
    assert "10.0.1" not in phases["wide"]               # già in "local"
    assert "10.0.0" not in phases["wide"]               # già in "common"


def test_a_192_168_local_range_adds_no_wide_phase(monkeypatch):
    # Lì il /24 del router è la regola e la fase "full" copre già il /16.
    monkeypatch.setattr(discovery, "_local_prefixes", lambda: ["192.168.1"])
    assert "wide" not in dict(discovery._candidate_phases())


# -- i router sul percorso -----------------------------------------------------

# Misurati davvero (novembre 2026), dal container in WSL mirrored: il router di
# casa, il modem del provider, un salto muto, poi la rete del provider.
HOST_HOPS = {1: "192.168.2.1", 2: "192.168.1.1",
             4: "172.16.20.114", 5: "93.186.128.82"}
# Lo stesso, dietro il bridge di Docker: un salto in più davanti.
BRIDGE_HOPS = {1: "172.17.0.1", 2: "192.168.2.1", 3: "192.168.1.1",
               5: "172.16.20.116", 6: "93.186.128.82"}


_REAL_PATH_HOPS = discovery._path_hops


@pytest.fixture(autouse=True)
def path(monkeypatch):
    """What ``_path_hops`` sees, for every test here: no probe leaves the
    machine, and by default no router answers."""
    monkeypatch.delenv("VIVAVOCE_DISCOVERY_FULL", raising=False)
    hops = {}
    monkeypatch.setattr(discovery, "_path_hops", lambda *a, **k: dict(hops))
    return hops


def test_the_routers_are_read_off_the_path_and_the_provider_is_not():
    # 172.16.20.x è privato, ma è dentro il provider: dopo il salto muto.
    assert discovery._router_prefixes(HOST_HOPS) == ["192.168.2", "192.168.1"]
    assert discovery._router_prefixes(BRIDGE_HOPS) == \
        ["172.17.0", "192.168.2", "192.168.1"]


def test_a_public_hop_ends_the_household_and_a_silent_first_one_does_not():
    assert discovery._router_prefixes({1: "192.168.0.1", 2: "10.20.0.1",
                                       3: "100.64.0.1", 4: "10.9.9.9"}) == \
        ["192.168.0", "10.20.0"]
    assert discovery._router_prefixes({2: "192.168.5.1"}) == ["192.168.5"]
    assert discovery._router_prefixes({}) == []


def test_known_routers_replace_the_full_sweep(path, monkeypatch):
    # Docker bridge davanti alla LAN: niente 192.168/16 e niente 172.17/16.
    path.update(BRIDGE_HOPS)
    monkeypatch.setattr(discovery, "_local_prefixes", lambda: ["172.17.0"])
    phases = dict(discovery._candidate_phases())
    assert list(phases) == ["local", "routers", "common"]
    assert phases["routers"] == ["192.168.2", "192.168.1"]   # 172.17.0 è local
    assert sum(len(p) for p in phases.values()) < 20


def test_a_flat_10_network_keeps_its_wide_sweep(path, monkeypatch):
    # Il router sta in un'altra /24 della stessa /16: lì l'LMS può essere
    # in una /24 vicina, che è il caso per cui "wide" esiste.
    path.update({1: "10.0.0.1", 2: "192.168.1.1", 3: "93.186.128.82"})
    monkeypatch.setattr(discovery, "_local_prefixes", lambda: ["10.0.7"])
    phases = dict(discovery._candidate_phases())
    assert "10.0.42" in phases["wide"]
    assert "full" not in phases


def test_unknown_routers_keep_the_old_phases(path, monkeypatch):
    # Nessuna risposta ICMP (non Linux, firewall): come prima.
    monkeypatch.setattr(discovery, "_local_prefixes", lambda: ["172.29.240"])
    assert list(dict(discovery._candidate_phases())) == \
        ["local", "common", "wide", "full"]


def test_the_full_sweep_can_still_be_asked_for(path, monkeypatch):
    path.update(HOST_HOPS)
    monkeypatch.setenv("VIVAVOCE_DISCOVERY_FULL", "1")
    monkeypatch.setattr(discovery, "_local_prefixes", lambda: ["192.168.2"])
    assert "full" in dict(discovery._candidate_phases())


def test_path_hops_never_raises_and_says_unknown(monkeypatch):
    # Senza rete (o senza IP_RECVERR) la risposta è "non so", non un errore.
    class Broken:
        def __init__(self, *a, **k):
            raise OSError("no network")
    monkeypatch.setattr(discovery.socket, "socket", Broken)
    assert _REAL_PATH_HOPS() == {}


def test_local_prefixes_skips_loopback_and_link_local(monkeypatch):
    monkeypatch.setattr(discovery.socket, "gethostbyname_ex",
                        lambda _h: ("host", [], ["127.0.1.1", "169.254.3.4",
                                                "192.168.50.7"]))
    def probe_fail(*a, **k):
        raise OSError()

    monkeypatch.setattr(discovery.socket.socket, "connect", probe_fail)
    assert discovery._local_prefixes() == ["192.168.50"]


# -- sweep unicast contro un finto LMS su loopback ----------------------------

def _fake_lms_on_loopback(reply=True):
    """A UDP socket bound to 127.0.0.1 that answers one discovery request."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]

    def run():
        sock.settimeout(5.0)
        try:
            data, addr = sock.recvfrom(2048)
            if reply and data[:1] == b"e":
                sock.sendto(b"E" + _tlv(NAME="testlms", JSON="9002"), addr)
        except OSError:
            pass

    threading.Thread(target=run, daemon=True).start()
    return port, sock


def test_unicast_sweep_finds_lms_and_reports_phases():
    port, sock = _fake_lms_on_loopback()
    seen_phases = []
    try:
        servers = discovery.discover_unicast(
            timeout=5.0, port=port, on_progress=seen_phases.append,
            phases=[("local", ["127.0.0"]), ("full", ["127.0.0"])])
    finally:
        sock.close()
    assert servers == [{"ip": "127.0.0.1", "NAME": "testlms", "JSON": "9002"}]
    # Early-exit: trovato nella prima fase, la seconda non parte nemmeno.
    assert seen_phases == ["local"]
    assert discovery.base_url(servers[0]) == "http://127.0.0.1:9002"


def test_unicast_sweep_gives_up_cleanly_when_nobody_answers():
    # Porta effimera senza nessuno in ascolto: lo sweep torna vuoto, senza
    # eccezioni (su Windows l'ICMP port-unreachable emerge come reset in recv).
    probe = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    probe.bind(("127.0.0.1", 0))
    free_port = probe.getsockname()[1]
    probe.close()
    servers = discovery.discover_unicast(
        timeout=1.0, port=free_port, phases=[("local", ["127.0.0"])])
    assert servers == []


def test_discover_base_url_falls_back_to_sweep(monkeypatch):
    monkeypatch.setattr(discovery, "discover", lambda timeout=2.0: [])
    monkeypatch.setattr(
        discovery, "discover_unicast",
        lambda on_progress=None: [{"ip": "192.168.123.72", "JSON": "9000"}])
    phases = []
    url = discovery.discover_base_url(on_progress=phases.append)
    assert url == "http://192.168.123.72:9000"
    assert phases == ["sweep"]


def test_discover_base_url_broadcast_wins_without_sweep(monkeypatch):
    monkeypatch.setattr(discovery, "discover",
                        lambda timeout=2.0: [{"ip": "10.0.0.5", "JSON": "9000"}])
    def boom(**_kw):
        raise AssertionError("sweep must not run when broadcast succeeds")
    monkeypatch.setattr(discovery, "discover_unicast", boom)
    assert discovery.discover_base_url() == "http://10.0.0.5:9000"


# -- l'indirizzo ricordato (riavvii istantanei) -------------------------------

def test_lms_cache_roundtrip(tmp_path):
    data_dir = str(tmp_path)
    assert appdata.remembered_lms(data_dir) == ""     # niente file: nessun URL
    appdata.remember_lms(data_dir, "http://192.168.123.72:9000")
    assert appdata.remembered_lms(data_dir) == "http://192.168.123.72:9000"
    raw = json.loads((tmp_path / "discovery_cache.json").read_text())
    assert raw == {"lms": "http://192.168.123.72:9000", "from_page": False}


def test_where_the_remembered_address_came_from_outlives_the_restart(tmp_path):
    # Without this the box on the setup page laundered an address through a
    # reboot: typed once, an ordinary remembered address the next start, and
    # the reverse proxy pointed at it after all (lmsproxy.browse_path).
    data_dir = str(tmp_path)
    assert appdata.remembered_from_page(data_dir) is False   # no file at all
    appdata.remember_lms(data_dir, "http://192.168.1.50:9000", from_page=True)
    assert appdata.remembered_lms(data_dir) == "http://192.168.1.50:9000"
    assert appdata.remembered_from_page(data_dir) is True
    # Discovery finding it again is provenance of its own, and clears it.
    appdata.remember_lms(data_dir, "http://192.168.1.50:9000")
    assert appdata.remembered_from_page(data_dir) is False


def test_a_file_written_before_provenance_existed_is_not_read_as_typed(tmp_path):
    # An upgrade must not switch the in-page panel off on a household that
    # has been running on a discovered address all along.
    (tmp_path / "discovery_cache.json").write_text(
        json.dumps({"lms": "http://192.168.1.50:9000"}))
    assert appdata.remembered_from_page(str(tmp_path)) is False


def test_lms_cache_tolerates_corruption(tmp_path):
    (tmp_path / "discovery_cache.json").write_text("not json {")
    assert appdata.remembered_lms(str(tmp_path)) == ""
