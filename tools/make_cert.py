#!/usr/bin/env python3
"""Generate the TLS certificate for the local voice server, signed by a local CA.

The browser microphone (Web Speech API) needs a secure context (HTTPS) when the
page is opened from another device (e.g. your phone). This creates in the target
directory (default: the repo root):

- ``ca.pem`` / ``ca-key.pem`` — a private "Vivavoce Local CA", created once and
  **reused** on later runs. Install ``ca.pem`` once on your phone/PC and the
  browser trusts the server for good: green lock, no warning, and the service
  worker/PWA install work (Chrome refuses service workers on untrusted certs,
  even after clicking through the warning). The server offers it at ``/ca.pem``.
- ``cert.pem`` / ``key.pem`` — the server certificate, signed by that CA, with
  the machine's LAN IPs in the Subject Alternative Names. Because the CA is
  reused, re-running with new IPs re-issues the server cert **without** the
  devices having to trust anything again.

    uv run python tools/make_cert.py
    uv run python tools/make_cert.py --out /data --hosts 192.168.1.20,nas.local

``--out`` writes the files somewhere else (the Docker entrypoint uses ``/data``);
``--hosts`` adds extra SANs (IPs or DNS names) for when the auto-detected
addresses aren't the ones clients will use — e.g. a container on a bridge
network only sees its internal IP, not the host's LAN IP.

Installing the CA is optional: without it everything keeps working as before
with the one-time "not private" browser warning (tap "advanced -> proceed"),
except the PWA service worker, which Chrome only enables on trusted HTTPS.
"""

from __future__ import annotations

import argparse
import datetime as _dt
import ipaddress
import os
import socket

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# The CA is a trust anchor installed by hand once, so it may be long-lived:
# 20 years, from a fixed date, keeps its fingerprint stable across
# regenerations of the leaf below.
NOT_BEFORE = _dt.datetime(2024, 1, 1, tzinfo=_dt.timezone.utc)
CA_NOT_AFTER = _dt.datetime(2044, 1, 1, tzinfo=_dt.timezone.utc)

# The SERVER certificate cannot be. Apple refuses any TLS server certificate
# valid for more than 825 days — since iOS 13/macOS 10.15, and regardless of
# whether its CA is trusted. The leaf used to be issued for ten years from a
# fixed date, so every iPhone and Mac in the house rejected it no matter how
# carefully the CA had been installed: the whole certificate-install flow
# ended in a warning it could not clear. 800 days leaves margin under the
# limit and still means re-running this tool roughly every two years.
LEAF_MAX_DAYS = 800
# Backdated a day so a client whose clock runs slightly behind still accepts
# a certificate generated a minute ago.
LEAF_BACKDATE = _dt.timedelta(days=1)


def leaf_validity(now: _dt.datetime = None):
    """``(not_before, not_after)`` for a server certificate issued now."""
    now = now or _dt.datetime.now(_dt.timezone.utc)
    return now - LEAF_BACKDATE, now + _dt.timedelta(days=LEAF_MAX_DAYS)


def local_ipv4s() -> list:
    ips = {"127.0.0.1"}
    try:
        for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            ips.add(info[4][0])
    except OSError:
        pass
    # also the address used to reach the default route
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ips.add(s.getsockname()[0])
        s.close()
    except OSError:
        pass
    return sorted(ips)


def _load_or_create_ca(out_dir: str):
    """Return ``(ca_cert, ca_key)``, creating and persisting them on first run.

    Reusing the CA is the whole point: devices that installed ``ca.pem`` keep
    trusting every server cert we issue later (new IPs, new reinstalls)."""
    ca_cert_path = os.path.join(out_dir, "ca.pem")
    ca_key_path = os.path.join(out_dir, "ca-key.pem")
    if os.path.exists(ca_cert_path) and os.path.exists(ca_key_path):
        with open(ca_cert_path, "rb") as f:
            ca_cert = x509.load_pem_x509_certificate(f.read())
        with open(ca_key_path, "rb") as f:
            ca_key = serialization.load_pem_private_key(f.read(), password=None)
        return ca_cert, ca_key, False

    ca_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "Vivavoce Local CA")])
    ca_cert = (
        x509.CertificateBuilder()
        .subject_name(name)
        .issuer_name(name)
        .public_key(ca_key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(NOT_BEFORE)
        .not_valid_after(CA_NOT_AFTER)
        # Android accetta come CA installabile solo certificati con
        # basicConstraints CA:TRUE (critical) e keyCertSign.
        .add_extension(x509.BasicConstraints(ca=True, path_length=0), critical=True)
        .add_extension(
            x509.KeyUsage(
                digital_signature=False, content_commitment=False,
                key_encipherment=False, data_encipherment=False,
                key_agreement=False, key_cert_sign=True, crl_sign=True,
                encipher_only=False, decipher_only=False,
            ),
            critical=True,
        )
        # SKI/AKI: OpenSSL 3 in modalità strict rifiuta la catena senza gli
        # identificatori di chiave che legano leaf e CA.
        .add_extension(
            x509.SubjectKeyIdentifier.from_public_key(ca_key.public_key()),
            critical=False,
        )
        .sign(ca_key, hashes.SHA256())
    )
    # 0600: this is the key that signs certificates every device in the house
    # trusts. It sits in the same directory the server publishes /ca.pem from.
    with open(os.open(ca_key_path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC,
                      0o600), "wb") as f:
        f.write(
            ca_key.private_bytes(
                serialization.Encoding.PEM,
                serialization.PrivateFormat.TraditionalOpenSSL,
                serialization.NoEncryption(),
            )
        )
    with open(ca_cert_path, "wb") as f:
        f.write(ca_cert.public_bytes(serialization.Encoding.PEM))
    return ca_cert, ca_key, True


def _renewal_verdict(out_dir: str, within_days: int):
    """Whether the certificate in ``out_dir`` still has to be reissued.

    ``(False, reason)`` to leave it alone, ``(True, reason)`` to reissue.
    Called only with ``--renew-within``, i.e. from an unattended start, where
    "do nothing" has to be the answer for anything this tool did not write.
    """
    cert_path = os.path.join(out_dir, "cert.pem")
    key_path = os.path.join(out_dir, "key.pem")
    if not (os.path.exists(cert_path) and os.path.exists(key_path)):
        return True, "non c'è ancora un certificato"
    try:
        with open(cert_path, "rb") as f:
            cert = x509.load_pem_x509_certificate(f.read())
    except (OSError, ValueError):
        return True, "il certificato presente non è leggibile"

    # Somebody else's certificate — a real one from a public CA, mounted into
    # this directory — must not be replaced by a self-signed one just because
    # it is close to its own renewal. Ours is the one our CA signed.
    ca_path = os.path.join(out_dir, "ca.pem")
    try:
        with open(ca_path, "rb") as f:
            ca_cert = x509.load_pem_x509_certificate(f.read())
    except (OSError, ValueError):
        return False, "non c'è la CA locale: il certificato non è nostro"
    if cert.issuer != ca_cert.subject:
        return False, "il certificato presente non è firmato dalla CA locale"

    try:
        expires = cert.not_valid_after_utc
    except AttributeError:  # cryptography < 42
        expires = cert.not_valid_after.replace(tzinfo=_dt.timezone.utc)
    left = (expires - _dt.datetime.now(_dt.timezone.utc)).days
    if left > within_days:
        return False, f"valido ancora {left} giorni"
    return True, f"scade fra {left} giorni"


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Genera la CA locale (riusata) e il certificato del server "
                    "vocale firmato da quella.")
    ap.add_argument("--out", default=ROOT, metavar="DIR",
                    help="directory dove scrivere ca.pem/cert.pem/key.pem "
                         "(default: la radice del repo)")
    ap.add_argument("--hosts", default="", metavar="H1,H2,...",
                    help="SAN aggiuntivi, separati da virgola: IP o nomi DNS "
                         "(es. l'IP LAN dell'host quando si genera in un container)")
    ap.add_argument("--renew-within", type=int, default=None, metavar="GIORNI",
                    help="non fare niente se il certificato esistente è nostro "
                         "e scade fra più di GIORNI giorni; serve agli avvii "
                         "automatici (container), che altrimenti non "
                         "rinnoverebbero mai niente")
    args = ap.parse_args()

    os.makedirs(args.out, exist_ok=True)
    cert_path = os.path.join(args.out, "cert.pem")
    key_path = os.path.join(args.out, "key.pem")

    if args.renew_within is not None:
        renew, why = _renewal_verdict(args.out, args.renew_within)
        if not renew:
            print(f"Certificato del server invariato: {why}.")
            return 0
        print(f"Rinnovo il certificato del server: {why}.")

    ca_cert, ca_key, ca_created = _load_or_create_ca(args.out)

    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    leaf_not_before, leaf_not_after = leaf_validity()

    ips = local_ipv4s()
    hosts = [h.strip() for h in args.hosts.split(",") if h.strip()]
    sans = [x509.DNSName("localhost")]
    for ip in ips:
        try:
            sans.append(x509.IPAddress(ipaddress.ip_address(ip)))
        except ValueError:
            pass
    for host in hosts:
        try:
            sans.append(x509.IPAddress(ipaddress.ip_address(host)))
        except ValueError:
            sans.append(x509.DNSName(host))  # non è un IP: lo trattiamo come nome DNS

    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "vivavoce-locale")])
    cert = (
        x509.CertificateBuilder()
        .subject_name(name)
        .issuer_name(ca_cert.subject)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(leaf_not_before)
        .not_valid_after(leaf_not_after)
        .add_extension(x509.SubjectAlternativeName(sans), critical=False)
        .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
        .add_extension(
            x509.KeyUsage(
                digital_signature=True, content_commitment=False,
                key_encipherment=True, data_encipherment=False,
                key_agreement=False, key_cert_sign=False, crl_sign=False,
                encipher_only=False, decipher_only=False,
            ),
            critical=True,
        )
        .add_extension(
            x509.ExtendedKeyUsage([ExtendedKeyUsageOID.SERVER_AUTH]), critical=False
        )
        .add_extension(
            x509.SubjectKeyIdentifier.from_public_key(key.public_key()),
            critical=False,
        )
        .add_extension(
            x509.AuthorityKeyIdentifier.from_issuer_public_key(ca_key.public_key()),
            critical=False,
        )
        .sign(ca_key, hashes.SHA256())
    )

    with open(os.open(key_path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC,
                      0o600), "wb") as f:
        f.write(
            key.private_bytes(
                serialization.Encoding.PEM,
                serialization.PrivateFormat.TraditionalOpenSSL,
                serialization.NoEncryption(),
            )
        )
    with open(cert_path, "wb") as f:
        f.write(cert.public_bytes(serialization.Encoding.PEM))

    print(f"CA locale: {os.path.join(args.out, 'ca.pem')}"
          + ("  (creata ora)" if ca_created else "  (riusata)"))
    print(f"Creati:\n  {cert_path}\n  {key_path}")
    print(f"Il certificato del server scade il "
          f"{leaf_not_after.date().isoformat()} "
          f"({LEAF_MAX_DAYS} giorni: iOS e macOS rifiutano di più). "
          "Rilancia questo comando per rinnovarlo — la CA resta la stessa, "
          "quindi non si reinstalla niente sui telefoni.")
    print("SAN (host validi):", ", ".join(ips + hosts + ["localhost"]))
    print("Suggerimento: installa ca.pem sul telefono/PC (una volta sola) per il "
          "lucchetto verde e l'app installabile; il server la offre su /ca.pem.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
