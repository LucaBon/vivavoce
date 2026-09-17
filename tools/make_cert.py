#!/usr/bin/env python3
"""Generate the TLS certificate for the local voice server, signed by a local CA.

The browser microphone (Web Speech API) needs a secure context (HTTPS) when the
page is opened from another device (e.g. your phone). This creates in the target
directory (default: the repo root):

- ``ca.pem`` / ``ca-key.pem`` — a private "Vivavoce Local CA", created once and
  **reused** on later runs. It carries Name Constraints, so it can only ever
  vouch for private addresses and local names: ``ca-key.pem`` is a key to the
  hi-fi at home, not a key to the web. Keep it out of backups anyway —
  everything that installed ``ca.pem`` believes whoever holds it. Install ``ca.pem`` once on your phone/PC and the
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
import tempfile

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# The CA is a trust anchor installed by hand once, so it has to outlive the
# hardware it is installed on — but not by much. It used to be issued to 2044
# from a fixed date, which nothing asked for: this is the window in which a
# leaked ca-key.pem is still believed by every phone in the house, and ten
# years already means nobody reinstalls anything for the life of the box.
# Relative to creation, so a household setting up in 2033 gets ten years too
# rather than whatever was left of a date compiled in here. The fingerprint
# stays stable the only way that matters — the CA is created once and reused,
# and it is the leaf below that gets reissued.
CA_YEARS = 10
CA_BACKDATE = _dt.timedelta(days=1)

# Where this CA's authority stops, and the answer to "what is ca-key.pem worth
# if somebody copies it". It sits in the directory the server publishes
# /ca.pem from, so it travels in every backup of that directory; without the
# extension below it is a key that can sign `google.com` for every device in
# the house. With it, a stolen key is worth a MITM on names that only resolve
# at home — which whoever is at home could reach anyway — and nothing else.
#
# The suffixes are ``webguard._LOCAL_SUFFIXES`` (the names that only ever
# resolve on a LAN) plus `localhost`. Written out instead of imported because
# this is a tool and the core is not on its path; a test holds the two lists
# to each other. An RFC 5280 dNSName constraint matches the name itself and
# anything under it, so "local" covers "casa.local".
CA_PERMITTED_SUFFIXES = ("localhost", "local", "lan", "home", "home.arpa",
                         "internal", "localdomain")

# RFC 1918, loopback and link-local, with their IPv6 equivalents.
CA_PERMITTED_NETWORKS = ("10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16",
                         "127.0.0.0/8", "169.254.0.0/16",
                         "::1/128", "fc00::/7", "fe80::/10")

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


def ca_validity(now: _dt.datetime = None):
    """``(not_before, not_after)`` for a CA created now (see :data:`CA_YEARS`)."""
    now = now or _dt.datetime.now(_dt.timezone.utc)
    return now - CA_BACKDATE, now + _dt.timedelta(days=365 * CA_YEARS)


def _dns_under(name: str, constraint: str) -> bool:
    """RFC 5280 dNSName matching: the constraint is the name, or a suffix."""
    name, constraint = name.lower().rstrip("."), constraint.lower().rstrip(".")
    return name == constraint or name.endswith("." + constraint)


def _ip_under(addr, network) -> bool:
    return addr.version == network.version and addr in network


def permitted_subtrees(hosts=()) -> list:
    """What the CA is allowed to sign for: home, plus whatever was asked for.

    ``hosts`` is ``--hosts``, which exists because the addresses clients use
    are not always the ones this machine can see. A name or address outside
    the local set has to be permitted by name, or the certificate this CA
    signs for it is one every device that installed the CA will refuse —
    silently widening the constraint is the only alternative to a padlock
    that stays red for a reason no browser explains.
    """
    subtrees = [x509.DNSName(s) for s in CA_PERMITTED_SUFFIXES]
    subtrees += [x509.IPAddress(ipaddress.ip_network(n))
                 for n in CA_PERMITTED_NETWORKS]
    for host in hosts:
        try:
            addr = ipaddress.ip_address(host)
        except ValueError:
            if not any(_dns_under(host, s) for s in CA_PERMITTED_SUFFIXES):
                subtrees.append(x509.DNSName(host))
            continue
        if not any(_ip_under(addr, ipaddress.ip_network(n))
                   for n in CA_PERMITTED_NETWORKS):
            subtrees.append(x509.IPAddress(ipaddress.ip_network(addr)))
    return subtrees


def unsignable_sans(sans, ca_cert) -> list:
    """The SANs this CA may not sign for, as strings; ``[]`` when all are fine.

    Exactly the check a device that installed the CA performs, performed here
    so that "your CA cannot vouch for this address" is a line of output at
    issue time instead of a failed handshake later. A CA with no constraints
    at all — one made before they existed — is constrained by nothing, and
    answers ``[]``.
    """
    try:
        constraints = ca_cert.extensions.get_extension_for_class(
            x509.NameConstraints).value
    except x509.ExtensionNotFound:
        return []
    permitted = list(constraints.permitted_subtrees or [])
    networks = [p.value for p in permitted if isinstance(p, x509.IPAddress)]
    names = [p.value for p in permitted if isinstance(p, x509.DNSName)]
    refused = []
    for san in sans:
        if isinstance(san, x509.IPAddress):
            if not any(_ip_under(san.value, n) for n in networks):
                refused.append(str(san.value))
        elif isinstance(san, x509.DNSName):
            if not any(_dns_under(san.value, n) for n in names):
                refused.append(san.value)
    return refused


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


def ca_is_constrained(ca_cert) -> bool:
    """Whether this CA says in itself where it may sign."""
    try:
        ca_cert.extensions.get_extension_for_class(x509.NameConstraints)
    except x509.ExtensionNotFound:
        return False
    return True


#: What to say about a CA created before the constraints existed. Not replaced
#: automatically, ever: the fingerprint is what every phone in the house
#: installed, and swapping it under them turns a green padlock into a warning
#: nobody asked for, on every device at once. Deleting the two files is how an
#: operator asks for a new one — and then reinstalls it.
UNCONSTRAINED_CA_WARNING = (
    "Attenzione: la CA locale in {path} è stata creata senza Name Constraints, "
    "quindi ca-key.pem può firmare per QUALUNQUE dominio verso i dispositivi "
    "che l'hanno installata.\n"
    "  Per passare a una CA vincolata: cancella ca.pem e ca-key.pem, rilancia "
    "questo comando, e reinstalla la nuova ca.pem sui dispositivi (la vecchia "
    "va rimossa dalle credenziali attendibili).\n"
    "  Fino ad allora tieni ca-key.pem fuori dai backup: vedi DEPLOY.md.")


def _load_or_create_ca(out_dir: str, hosts=(), warn=print):
    """Return ``(ca_cert, ca_key)``, creating and persisting them on first run.

    Reusing the CA is the whole point: devices that installed ``ca.pem`` keep
    trusting every server cert we issue later (new IPs, new reinstalls). Which
    is also why one created before :func:`permitted_subtrees` existed is
    reused as it is and merely reported: see
    :data:`UNCONSTRAINED_CA_WARNING`."""
    ca_cert_path = os.path.join(out_dir, "ca.pem")
    ca_key_path = os.path.join(out_dir, "ca-key.pem")
    if os.path.exists(ca_cert_path) and os.path.exists(ca_key_path):
        with open(ca_cert_path, "rb") as f:
            ca_cert = x509.load_pem_x509_certificate(f.read())
        with open(ca_key_path, "rb") as f:
            ca_key = serialization.load_pem_private_key(f.read(), password=None)
        if not ca_is_constrained(ca_cert):
            warn(UNCONSTRAINED_CA_WARNING.format(path=ca_cert_path))
        return ca_cert, ca_key, False

    ca_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    ca_not_before, ca_not_after = ca_validity()
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "Vivavoce Local CA")])
    ca_cert = (
        x509.CertificateBuilder()
        .subject_name(name)
        .issuer_name(name)
        .public_key(ca_key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(ca_not_before)
        .not_valid_after(ca_not_after)
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
        # Critica, come vuole la RFC 5280 per questa estensione: un client che
        # non sapesse leggerla deve rifiutare la CA invece di fidarsi senza
        # confini. Se un dispositivo in casa la rifiutasse, resta la strada
        # che c'era prima della CA — l'avviso «non privato» da superare una
        # volta, con tutto funzionante tranne il service worker.
        .add_extension(x509.NameConstraints(
            permitted_subtrees=permitted_subtrees(hosts),
            excluded_subtrees=None), critical=True)
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


def _write_atomically(path: str, data: bytes, mode: int) -> str:
    """Write ``data`` to a temp file next to ``path``; return the temp path.

    Nothing is published here — the caller renames, so that a whole set of
    files becomes visible in two adjacent `os.replace` calls rather than over
    the course of writing them. This matters now that the container renews on
    every boot: the old code opened key.pem O_TRUNC and rewrote it in place,
    so a process killed mid-write (a full volume, a `docker stop` on the boot
    that happened to renew) left a truncated key beside a cert that no longer
    matched it — and the entrypoint, seeing both files present, started the
    server on the wreckage.
    """
    directory = os.path.dirname(os.path.abspath(path)) or "."
    fd, tmp = tempfile.mkstemp(dir=directory, prefix=".", suffix=".tmp")
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(data)
            f.flush()
            os.fsync(f.fileno())
        os.chmod(tmp, mode)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise
    return tmp


def _key_matches(cert, key_path: str) -> bool:
    """Does ``key_path`` hold the private half of ``cert``'s public key?"""
    try:
        with open(key_path, "rb") as f:
            key = serialization.load_pem_private_key(f.read(), password=None)
    except (OSError, ValueError, TypeError):
        return False
    return (key.public_key().public_bytes(
                serialization.Encoding.DER,
                serialization.PublicFormat.SubjectPublicKeyInfo)
            == cert.public_key().public_bytes(
                serialization.Encoding.DER,
                serialization.PublicFormat.SubjectPublicKeyInfo))


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
        # Unreadable is not the same as ours-and-broken, and there is no way
        # to tell them apart without parsing it: a third-party cert.pem this
        # container cannot open (root-owned 0600, a DER file, a symlink out of
        # the mount) reads exactly like a corrupt one. Overwriting what we
        # cannot identify is the one outcome worth avoiding, so say so and
        # stop — deleting the file is the operator's way of asking for a new
        # one.
        return False, "il certificato presente non è leggibile: non lo tocco"

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

    # Ours, so it is safe to repair: a key that does not belong to this
    # certificate is what a renewal interrupted between its two renames
    # leaves behind, and the server cannot start on it.
    if not _key_matches(cert, key_path):
        return True, "la chiave non corrisponde al certificato"

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

    # Read before the CA, because a CA created now is created around them:
    # what --hosts names is what this household's clients will ask for, and
    # the CA has to be allowed to sign for it (see permitted_subtrees).
    hosts = [h.strip() for h in args.hosts.split(",") if h.strip()]
    ca_cert, ca_key, ca_created = _load_or_create_ca(args.out, hosts)

    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    leaf_not_before, leaf_not_after = leaf_validity()

    ips = local_ipv4s()
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

    # Said now, not discovered later: a device that installed the CA will
    # refuse this certificate for any address the CA may not sign for, and it
    # will refuse it with a handshake error that names nothing.
    refused = unsignable_sans(sans, ca_cert)
    if refused:
        print("Attenzione: la CA locale non può firmare per "
              + ", ".join(refused)
              + ".\n  Il certificato viene emesso comunque, ma i dispositivi "
              "che hanno installato ca.pem lo rifiuteranno per quegli "
              "indirizzi.\n  Rilancia con --hosts che li includa dopo aver "
              "cancellato ca.pem e ca-key.pem (e reinstalla la nuova CA), "
              "oppure usali senza installare la CA.")

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

    # Both written aside in full, then published with two adjacent renames:
    # the pair is only ever swapped, never rewritten in place. A crash can
    # still land between the two renames, leaving a new key beside the old
    # certificate — which is why _renewal_verdict checks that they match and
    # reissues when they don't, so the next boot repairs it by itself.
    tmp_key = _write_atomically(key_path, key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.TraditionalOpenSSL,
        serialization.NoEncryption(),
    ), 0o600)
    try:
        tmp_cert = _write_atomically(
            cert_path, cert.public_bytes(serialization.Encoding.PEM), 0o644)
    except BaseException:
        try:
            os.unlink(tmp_key)
        except OSError:
            pass
        raise
    os.replace(tmp_key, key_path)
    os.replace(tmp_cert, cert_path)

    print(f"CA locale: {os.path.join(args.out, 'ca.pem')}"
          + ("  (creata ora)" if ca_created else "  (riusata)"))
    if ca_created:
        print(f"  Vale {CA_YEARS} anni e può firmare solo per indirizzi "
              "privati e nomi locali (Name Constraints): se ca-key.pem "
              "finisce in mani altrui, non serve a fingersi un sito.")
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
