"""Cross-site protection for the local web app. Stdlib only.

This server has no accounts and no auth: it is on the LAN, it answers whoever
asks, and that is the whole design. What it does *not* want is to answer a
page the household never opened. Without any check, a site loaded on a phone
on the same Wi-Fi could quietly POST ``/player`` (volume 100), ``/command``
or ``/kidsafe`` — including ``enable`` with a PIN of its choosing while none
exists yet, which locks the parent out of the feature meant to protect their
child. None of that needs a reply to be read back, so the same-origin policy
never gets in the way; only these checks do.

Three of them, cheapest first:

1. **Content-Type** on the JSON routes. A cross-origin ``fetch`` may send
   ``text/plain`` (or a form encoding) with no preflight at all — a "simple
   request". Insisting on ``application/json`` forces a preflight, which this
   server answers with 405, so the real request is never sent.
2. **Origin vs Host.** When the browser tells us where the page came from, it
   has to be this server.
3. **Host allow-list.** DNS rebinding beats (1) and (2) — the attacker's own
   name resolves to the LAN address, so Origin and Host agree and both say
   ``evil.example``. A Host that is a bare IP literal can't be rebound, and
   neither can an mDNS/LAN name; a public DNS name reaching us is not
   something a household setup produces. ``VIVAVOCE_ALLOWED_HOSTS`` (comma
   separated) is the escape hatch for anyone fronting this with a real name.
"""

from __future__ import annotations

import ipaddress
import socket
from typing import Optional, Sequence

# The routes that take a JSON body and change something. GET routes are not
# listed: cross-site, they are safe to *trigger*, because the answer cannot be
# read. That reasoning covers checks 1 and 2 and not check 3 — under DNS
# rebinding the attacker's page is same-origin with us and reads everything it
# asks for, which is why reads are held to the Host allow-list as well (see
# httpbase._reject_bad_host).
JSON_ROUTES = frozenset({"/api/v1/command", "/command", "/kidsafe",
                         "/license", "/player"})

# Suffixes that only ever resolve on the local network, so they cannot be
# pointed at us by an attacker who controls a public zone.
_LOCAL_SUFFIXES = (".local", ".lan", ".home", ".home.arpa", ".internal",
                   ".localdomain")


def _split_host(value: str) -> str:
    """The hostname part of a ``Host`` header, lowercased, port removed."""
    value = (value or "").strip().lower()
    if value.startswith("["):                      # [::1]:8730
        return value.partition("]")[0][1:]
    return value.rsplit(":", 1)[0] if value.count(":") == 1 else value


def _is_ip_literal(host: str) -> bool:
    try:
        ipaddress.ip_address(host)
        return True
    except ValueError:
        return False


def parse_hosts(value: Optional[str]) -> list:
    """``"a.example, b.example"`` -> ``["a.example", "b.example"]``."""
    return [h.strip() for h in (value or "").split(",") if h.strip()]


class HostPolicy:
    """Which ``Host`` values this server will act on.

    Accepts IP literals (unrebindable), ``localhost``, this machine's own
    name, and mDNS/LAN suffixes. ``extra`` — from ``VIVAVOCE_ALLOWED_HOSTS``
    or the caller — adds names verbatim.
    """

    def __init__(self, extra: Optional[Sequence[str]] = None) -> None:
        self.extra = {h.strip().lower() for h in (extra or []) if h and h.strip()}
        names = {"localhost"}
        try:
            hostname = socket.gethostname().lower()
            names.add(hostname)
            names.add(hostname.split(".", 1)[0])
        except OSError:
            pass
        self.names = names

    def allows(self, host_header: str) -> bool:
        host = _split_host(host_header)
        if not host:
            return False           # HTTP/1.1 requires a Host; a missing one is odd
        if host in self.extra or host in self.names:
            return True
        if _is_ip_literal(host):
            return True
        return host.endswith(_LOCAL_SUFFIXES)


def cross_site_reason(headers, host_policy: HostPolicy,
                      require_json: bool = False) -> Optional[str]:
    """Why this request must not act, or ``None`` when it may.

    ``headers`` is the request's header mapping (``self.headers``).
    """
    if require_json:
        ctype = (headers.get("Content-Type") or "").split(";", 1)[0].strip().lower()
        if ctype != "application/json":
            return "content_type"
    # Sec-Fetch-Site is sent by every current browser and is the clearest
    # statement of intent there is; absent (curl, older browsers) it simply
    # doesn't participate.
    site = (headers.get("Sec-Fetch-Site") or "").strip().lower()
    if site and site not in ("same-origin", "none"):
        return "cross_site"
    host = _split_host(headers.get("Host") or "")
    origin = headers.get("Origin")
    if origin and origin.lower() != "null":
        from urllib.parse import urlsplit
        parsed = urlsplit(origin)
        origin_host = (parsed.hostname or "").lower()
        if origin_host != host:
            return "cross_site"
    if not host_policy.allows(headers.get("Host") or ""):
        return "bad_host"
    return None
