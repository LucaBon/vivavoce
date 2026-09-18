"""``tools/make_cert.py --renew-within``: the unattended renewal decision.

The server certificate is issued for 800 days — Apple refuses any TLS server
certificate valid for longer, whatever its CA — where it used to run to a
fixed 2034 date. That turned "generate it if the files are missing" from a
first-run condition into a time bomb: a container install stopped being
reachable over HTTPS after a little over two years, with nothing anywhere
that would renew it.

So the container now runs this tool on every boot, and the tool decides. What
it decides is the whole of this test: renewing a certificate that does not
need it churns the key for no reason, and renewing one this tool never issued
would replace a household's real certificate with a self-signed one.
"""

import datetime as dt
import importlib.util
import os
import subprocess
import sys

import pytest

pytest.importorskip("cryptography",
                    reason="cryptography not installed (extra: tls)")

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _make_cert():
    spec = importlib.util.spec_from_file_location(
        "make_cert", os.path.join(ROOT, "tools", "make_cert.py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def make_cert():
    return _make_cert()


@pytest.fixture(scope="module")
def issued(tmp_path_factory):
    """A real certificate from the real tool, CA and all."""
    out = tmp_path_factory.mktemp("certs")
    proc = subprocess.run(
        [sys.executable, "tools/make_cert.py", "--out", str(out)],
        cwd=ROOT, capture_output=True, text=True)
    assert proc.returncode == 0, proc.stderr[-500:]
    return out


def test_nothing_yet_means_generate(make_cert, tmp_path):
    renew, why = make_cert._renewal_verdict(str(tmp_path), 30)
    assert renew is True
    assert "non c'è" in why


def test_a_fresh_certificate_is_left_alone(make_cert, issued):
    renew, why = make_cert._renewal_verdict(str(issued), 30)
    assert renew is False
    assert "valido ancora" in why


def test_an_expiring_certificate_is_renewed(make_cert, issued):
    # The whole 800-day window, minus a day, is "expiring" — which is how the
    # boot after day 770 sees a certificate issued on day 1.
    renew, why = make_cert._renewal_verdict(
        str(issued), make_cert.LEAF_MAX_DAYS + 1)
    assert renew is True
    assert "scade fra" in why


def test_somebody_elses_certificate_is_not_replaced(make_cert, issued, tmp_path):
    # A household fronting this with a real certificate mounts it here. Ours
    # is the one our CA signed; anything else is left exactly where it is,
    # however close to its own renewal it happens to be.
    for name in ("cert.pem", "key.pem"):
        (tmp_path / name).write_bytes((issued / name).read_bytes())
    renew, why = make_cert._renewal_verdict(str(tmp_path), 10_000)
    assert renew is False
    assert "non è nostro" in why

    # ...and the same with a CA sitting there that did not sign it.
    (tmp_path / "ca.pem").write_bytes(
        (issued / "cert.pem").read_bytes())  # a certificate, just not the issuer
    renew, why = make_cert._renewal_verdict(str(tmp_path), 10_000)
    assert renew is False
    assert "non è firmato dalla CA locale" in why


@pytest.fixture
def own_copy(issued, tmp_path):
    """A private copy of the issued set, for the tests that rewrite it."""
    import shutil

    out = tmp_path / "certs"
    shutil.copytree(str(issued), str(out))
    return out


def test_the_renewal_reuses_the_ca_so_no_phone_reinstalls_anything(own_copy):
    issued = own_copy
    ca_before = (issued / "ca.pem").read_bytes()
    cert_before = (issued / "cert.pem").read_bytes()
    proc = subprocess.run(
        [sys.executable, "tools/make_cert.py", "--out", str(issued),
         "--renew-within", "10000"],
        cwd=ROOT, capture_output=True, text=True)
    assert proc.returncode == 0, proc.stderr[-500:]
    assert (issued / "ca.pem").read_bytes() == ca_before, (
        "the renewal replaced the CA every device in the house installed")
    assert (issued / "cert.pem").read_bytes() != cert_before


def test_a_valid_certificate_survives_an_unattended_boot(own_copy):
    issued = own_copy
    cert_before = (issued / "cert.pem").read_bytes()
    proc = subprocess.run(
        [sys.executable, "tools/make_cert.py", "--out", str(issued),
         "--renew-within", "30"],
        cwd=ROOT, capture_output=True, text=True)
    assert proc.returncode == 0, proc.stderr[-500:]
    assert (issued / "cert.pem").read_bytes() == cert_before, (
        "every boot reissued the certificate, and the key with it")


def test_the_issued_certificate_stays_under_the_apple_limit(make_cert, issued):
    from cryptography import x509

    with open(issued / "cert.pem", "rb") as f:
        cert = x509.load_pem_x509_certificate(f.read())
    try:
        expires = cert.not_valid_after_utc
        starts = cert.not_valid_before_utc
    except AttributeError:  # cryptography < 42
        expires = cert.not_valid_after.replace(tzinfo=dt.timezone.utc)
        starts = cert.not_valid_before.replace(tzinfo=dt.timezone.utc)
    assert (expires - starts).days <= 825, (
        "iOS 13+/macOS 10.15+ refuse a server certificate valid this long, "
        "trusted CA or not")


# -- the renewal must not be able to destroy what it is renewing ---------------

def test_the_pair_is_swapped_not_rewritten_in_place(own_copy):
    # The renewal runs on every container boot now. The old code opened
    # key.pem O_TRUNC and rewrote it where it lay, so a process killed
    # mid-write left a truncated key next to a certificate that no longer
    # matched — and the entrypoint, seeing both files present, started the
    # server on it. Nothing is written in place any more: both files are
    # built aside and published by rename.
    before = os.stat(own_copy / "key.pem").st_ino
    proc = subprocess.run(
        [sys.executable, "tools/make_cert.py", "--out", str(own_copy),
         "--renew-within", "10000"],
        cwd=ROOT, capture_output=True, text=True)
    assert proc.returncode == 0, proc.stderr[-500:]
    assert os.stat(own_copy / "key.pem").st_ino != before, (
        "key.pem was rewritten in place instead of replaced")


@pytest.mark.skipif(os.name == "nt",
                    reason="POSIX permission bits; Windows os.chmod only "
                           "toggles read-only, so 0600 is not representable "
                           "and st_mode comes back 0666")
def test_the_renewed_key_is_still_unreadable_by_others(own_copy):
    # The renewal writes the key through a temp file now, and a temp file is
    # created 0600 by mkstemp but published by rename — so the mode has to be
    # set on it deliberately, and this is what says so.
    proc = subprocess.run(
        [sys.executable, "tools/make_cert.py", "--out", str(own_copy),
         "--renew-within", "10000"],
        cwd=ROOT, capture_output=True, text=True)
    assert proc.returncode == 0, proc.stderr[-500:]
    assert oct(os.stat(own_copy / "key.pem").st_mode)[-3:] == "600"


def test_a_key_left_over_from_an_interrupted_renewal_is_repaired(make_cert,
                                                                 own_copy):
    # A crash between the two renames leaves a new key beside the old
    # certificate. The server cannot start on that pair, and no boot would
    # ever fix it while the only question asked was "has it expired?".
    other = own_copy.parent / "other"
    proc = subprocess.run(
        [sys.executable, "tools/make_cert.py", "--out", str(other)],
        cwd=ROOT, capture_output=True, text=True)
    assert proc.returncode == 0, proc.stderr[-500:]
    (own_copy / "key.pem").write_bytes((other / "key.pem").read_bytes())

    renew, why = make_cert._renewal_verdict(str(own_copy), 30)
    assert renew is True
    assert "non corrisponde" in why


def test_an_unreadable_certificate_is_left_where_it_is(make_cert, tmp_path):
    # Unreadable and ours-but-corrupt look identical from here, and a
    # third-party cert.pem this container simply cannot open (root-owned
    # 0600, DER, a symlink out of the mount) is the case that must not be
    # overwritten with a self-signed one.
    (tmp_path / "cert.pem").write_bytes(b"not a certificate")
    (tmp_path / "key.pem").write_bytes(b"nor is this")
    renew, why = make_cert._renewal_verdict(str(tmp_path), 30)
    assert renew is False
    assert "non lo tocco" in why


# -- dove la CA locale può firmare ---------------------------------------------
#
# ca-key.pem sta nella directory da cui il server pubblica /ca.pem, quindi
# viaggia in ogni backup di quella directory. Senza Name Constraints è una
# chiave che firma per qualunque dominio verso tutti i dispositivi di casa che
# hanno installato la CA (SEC-2). Questi test fissano il confine; che un
# client lo applichi davvero è stato verificato con `openssl verify`, che
# risponde «permitted subtree violation» per un nome fuori dai permessi.

def _ca(path):
    from cryptography import x509
    with open(path, "rb") as f:
        return x509.load_pem_x509_certificate(f.read())


def test_the_ca_says_where_it_may_sign_and_says_it_critically(issued):
    from cryptography import x509

    ca = _ca(issued / "ca.pem")
    ext = ca.extensions.get_extension_for_class(x509.NameConstraints)
    assert ext.critical, "RFC 5280 la vuole critica, e un client che non la "\
                         "legge deve rifiutare la CA invece di fidarsi"
    names = [s.value for s in ext.value.permitted_subtrees
             if isinstance(s, x509.DNSName)]
    nets = [str(s.value) for s in ext.value.permitted_subtrees
            if isinstance(s, x509.IPAddress)]
    assert "local" in names and "localhost" in names
    assert "192.168.0.0/16" in nets and "10.0.0.0/8" in nets
    assert "0.0.0.0/0" not in nets


def test_the_permitted_names_are_the_ones_the_server_answers_for(make_cert):
    # La stessa lista di webguard._LOCAL_SUFFIXES: i nomi che risolvono solo
    # su una LAN. Sono duplicati perché questo è un tool e il core non è sul
    # suo path — quindi la parità la tiene questo test, non l'import.
    sys.path.insert(0, os.path.join(ROOT, "localvoice"))
    try:
        import webguard
    finally:
        sys.path.pop(0)
    local = {s.lstrip(".") for s in webguard._LOCAL_SUFFIXES}
    assert local <= set(make_cert.CA_PERMITTED_SUFFIXES)


def test_a_public_name_is_outside_what_the_ca_may_sign(make_cert, issued):
    from cryptography import x509

    ca = _ca(issued / "ca.pem")
    sans = [x509.DNSName("nas.example.com"),
            x509.IPAddress(__import__("ipaddress").ip_address("8.8.8.8"))]
    assert make_cert.unsignable_sans(sans, ca) == ["nas.example.com", "8.8.8.8"]


def test_what_the_house_actually_uses_is_inside_it(make_cert, issued):
    from cryptography import x509
    import ipaddress

    ca = _ca(issued / "ca.pem")
    sans = [x509.DNSName("localhost"), x509.DNSName("casa.local"),
            x509.IPAddress(ipaddress.ip_address("192.168.1.50")),
            x509.IPAddress(ipaddress.ip_address("127.0.0.1"))]
    assert make_cert.unsignable_sans(sans, ca) == []


def test_a_name_asked_for_by_hand_is_permitted_when_the_ca_is_created(tmp_path):
    # --hosts esiste perché gli indirizzi che i client usano non sono sempre
    # quelli che questa macchina vede. Se la CA non potesse firmarli, il
    # certificato sarebbe rifiutato proprio dai dispositivi che hanno fatto
    # tutto il giro dell'installazione.
    from cryptography import x509

    proc = subprocess.run(
        [sys.executable, "tools/make_cert.py", "--out", str(tmp_path),
         "--hosts", "nas.example.com"],
        cwd=ROOT, capture_output=True, text=True)
    assert proc.returncode == 0, proc.stderr[-500:]
    assert "Attenzione" not in proc.stdout
    ca = _ca(tmp_path / "ca.pem")
    ext = ca.extensions.get_extension_for_class(x509.NameConstraints)
    assert x509.DNSName("nas.example.com") in ext.value.permitted_subtrees


def test_an_address_the_ca_cannot_vouch_for_is_said_out_loud(own_copy):
    # Emesso comunque — senza la CA installata funziona come sempre — ma
    # detto, perché altrimenti si scopre da un handshake che non spiega
    # niente.
    (own_copy / "cert.pem").unlink()
    (own_copy / "key.pem").unlink()
    proc = subprocess.run(
        [sys.executable, "tools/make_cert.py", "--out", str(own_copy),
         "--hosts", "nas.example.com"],
        cwd=ROOT, capture_output=True, text=True)
    assert proc.returncode == 0, proc.stderr[-500:]
    assert "non può firmare per nas.example.com" in proc.stdout
    assert (own_copy / "cert.pem").exists()


def test_a_ca_made_before_the_constraints_is_reported_not_replaced(make_cert,
                                                                   own_copy):
    """La CA è l'impronta che ogni telefono di casa ha installato: sostituirla
    da sotto trasforma un lucchetto verde in un avviso, su tutti i dispositivi
    insieme. Quindi si riusa e si dice; cancellare i due file è il modo in cui
    un operatore chiede una CA nuova (DEPLOY.md).
    """
    unconstrained = _unconstrained_ca(own_copy)
    assert make_cert.ca_is_constrained(unconstrained) is False
    before = (own_copy / "ca.pem").read_bytes()
    said = []
    _cert, _key, created = make_cert._load_or_create_ca(
        str(own_copy), warn=said.append)
    assert created is False, "ha creato una CA nuova al posto di quella installata"
    assert (own_copy / "ca.pem").read_bytes() == before, "ha sostituito la CA"
    assert said and "Name Constraints" in said[0]
    assert "cancella ca.pem e ca-key.pem" in said[0]


def _unconstrained_ca(out_dir):
    """A CA exactly like the ones this tool used to make: no constraints."""
    import datetime as _dt
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import rsa
    from cryptography.x509.oid import NameOID

    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME,
                                         "Vivavoce Local CA")])
    now = _dt.datetime.now(_dt.timezone.utc)
    cert = (x509.CertificateBuilder()
            .subject_name(name).issuer_name(name)
            .public_key(key.public_key())
            .serial_number(x509.random_serial_number())
            .not_valid_before(now - _dt.timedelta(days=1))
            .not_valid_after(now + _dt.timedelta(days=365))
            .add_extension(x509.BasicConstraints(ca=True, path_length=0),
                           critical=True)
            .sign(key, hashes.SHA256()))
    (out_dir / "ca.pem").write_bytes(
        cert.public_bytes(serialization.Encoding.PEM))
    (out_dir / "ca-key.pem").write_bytes(key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.TraditionalOpenSSL,
        serialization.NoEncryption()))
    return cert


def test_the_ca_no_longer_runs_to_2044(make_cert, issued):
    # Era la finestra in cui una ca-key.pem trapelata resta creduta.
    ca = _ca(issued / "ca.pem")
    try:
        expires = ca.not_valid_after_utc
    except AttributeError:      # cryptography < 42
        expires = ca.not_valid_after.replace(tzinfo=dt.timezone.utc)
    years = (expires - dt.datetime.now(dt.timezone.utc)).days / 365.0
    assert make_cert.CA_YEARS - 0.1 <= years <= make_cert.CA_YEARS + 0.1

