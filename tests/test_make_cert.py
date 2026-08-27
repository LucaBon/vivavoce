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
