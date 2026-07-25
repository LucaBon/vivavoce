"""Certificate SAN learning (``server.CertLearner`` + ``tools/make_cert.py``).

Behind bridge/NAT the server can't know the address clients use, so the SANs
of a pre-generated certificate are wrong there. The server learns addresses
from the Host header and re-issues the certificate with the reused local CA.
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(__file__)), "tools"))

import server as srv

make_cert = pytest.importorskip("make_cert")


class FakeCtx:
    def __init__(self):
        self.loads = []

    def load_cert_chain(self, cert, key):
        self.loads.append((cert, key))


@pytest.fixture
def certdir(tmp_path):
    make_cert.issue_cert(str(tmp_path))
    return tmp_path


def _learner(certdir):
    ctx = FakeCtx()
    learner = srv.CertLearner(str(certdir / "cert.pem"), str(certdir / "key.pem"),
                              ctx, 8730)
    return learner, ctx


# -- make_cert helpers ---------------------------------------------------------

def test_issue_cert_includes_extra_hosts_and_dedupes(tmp_path):
    sans, ca_created = make_cert.issue_cert(
        str(tmp_path), ["192.168.9.9", "nas.local", "192.168.9.9", " "])
    assert ca_created is True
    assert "localhost" in sans and "192.168.9.9" in sans and "nas.local" in sans
    assert sans.count("192.168.9.9") == 1
    assert make_cert.cert_sans(str(tmp_path / "cert.pem")) == sans


def test_issue_cert_reuses_the_ca(tmp_path):
    make_cert.issue_cert(str(tmp_path))
    ca_before = (tmp_path / "ca.pem").read_bytes()
    _, ca_created = make_cert.issue_cert(str(tmp_path), ["192.168.9.9"])
    assert ca_created is False
    assert (tmp_path / "ca.pem").read_bytes() == ca_before  # trust preserved


# -- il server impara dall'header Host ------------------------------------------

def test_learns_new_host_reissues_and_reloads(certdir):
    learner, ctx = _learner(certdir)
    # TEST-NET: non può essere tra gli IP locali auto-rilevati nel certificato.
    learner.observe("203.0.113.7:8730")
    assert "203.0.113.7" in make_cert.cert_sans(str(certdir / "cert.pem"))
    assert ctx.loads == [(str(certdir / "cert.pem"), str(certdir / "key.pem"))]
    # Stesso host di nuovo (anche senza porta): nessuna riemissione.
    learner.observe("203.0.113.7")
    learner.observe("203.0.113.7:8730")
    assert len(ctx.loads) == 1


def test_known_sans_never_trigger_a_reissue(certdir):
    learner, ctx = _learner(certdir)
    learner.observe("localhost:8730")
    learner.observe("127.0.0.1:8730")
    assert ctx.loads == []


def test_junk_hosts_are_ignored(certdir):
    learner, ctx = _learner(certdir)
    for junk in ("", None, "not a host!", "évil.example", "[::1]:8730",
                 "fe80::1", "-starts.bad", "a" * 300):
        learner.observe(junk)
    sans = make_cert.cert_sans(str(certdir / "cert.pem"))
    assert ctx.loads == []
    assert all("evil" not in s and "bad" not in s for s in sans)


def test_hostname_learned_as_dns_san(certdir):
    learner, ctx = _learner(certdir)
    learner.observe("MyNas.local:8730")
    assert "mynas.local" in make_cert.cert_sans(str(certdir / "cert.pem"))
    assert len(ctx.loads) == 1


def test_growth_is_capped(certdir):
    learner, ctx = _learner(certdir)
    learner._known = {f"10.0.0.{i}" for i in range(srv.CertLearner.MAX_HOSTS)}
    learner.observe("192.168.77.77:8730")
    assert ctx.loads == []
    assert "192.168.77.77" not in make_cert.cert_sans(str(certdir / "cert.pem"))


def test_unreadable_cert_disables_learning_quietly(tmp_path):
    (tmp_path / "cert.pem").write_text("not a pem")
    (tmp_path / "key.pem").write_text("not a key")
    ctx = FakeCtx()
    learner = srv.CertLearner(str(tmp_path / "cert.pem"),
                              str(tmp_path / "key.pem"), ctx, 8730)
    learner.observe("192.168.1.1:8730")  # non deve sollevare né riemettere
    assert ctx.loads == []
