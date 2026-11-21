"""Squeezebox/LMS LAN discovery (UDP 3483 TLV).

Lets the local server and tools find the LMS server automatically, so the user
doesn't have to know or type its IP address. Squeezer does the same — it's the
expected UX for this ecosystem.

Two strategies, tried in order:

1. ``discover()`` — one broadcast request. Instant on a real LAN interface.
2. ``discover_unicast()`` — LMS answers the same TLV request sent *unicast*
   (verified against LMS 9), so when broadcast gets no reply — inside a Docker
   bridge/NAT the broadcast never leaves the container — we sweep candidate
   private subnets host by host and stop at the first answer. Outbound unicast
   UDP crosses Docker's NAT fine, which keeps `docker compose up` zero-config
   on Docker Desktop too.

Which subnets the sweep tries is the whole cost. The household's subnets are
the ones its routers sit on, and those are on the path out: a few UDP probes
with a growing TTL make each router on the way answer ICMP time-exceeded
(``_path_hops``, tracepath-style, no root). That finds the real LAN from
behind a Docker bridge or WSL2's NAT, where this machine's own address says
nothing about it, and both networks of a router behind the ISP's modem. When
it finds them, the 65k-packet "full" pass over 192.168/16 is skipped, and so
is a "wide" pass over a /16 that is only a virtual network in front of them.
``VIVAVOCE_DISCOVERY_FULL=1`` puts both back.
"""

from __future__ import annotations

import os
import select
import socket
import sys
import time
from typing import Callable, Dict, List, Optional, Tuple

DISCOVERY_PORT = 3483

# Densely-used home /24s, tried before the exhaustive 192.168/16 pass:
# factory defaults of common routers (.0/.1/.2, FRITZ!Box .178/.188,
# some ISP boxes .100) plus the usual 10.x and 172.16 picks.
_COMMON_PREFIXES = [
    "192.168.0", "192.168.1", "192.168.2", "192.168.100",
    "192.168.178", "192.168.188", "10.0.0", "10.0.1", "10.1.1", "172.16.0",
]


def _request() -> bytes:
    fields = [b"NAME", b"IPAD", b"JSON", b"VERS"]
    return b"e" + b"".join(tag + b"\x00" for tag in fields)


def _parse_tlv(buf: bytes) -> Dict[str, str]:
    out: Dict[str, str] = {}
    i = 0
    while i + 5 <= len(buf):
        tag = buf[i : i + 4].decode("ascii", "replace")
        length = buf[i + 4]
        out[tag] = buf[i + 5 : i + 5 + length].decode("utf-8", "replace")
        i += 5 + length
    return out


def _server_from(data: bytes, ip: str) -> Optional[Dict[str, str]]:
    """A ``{'ip', 'NAME', 'JSON', ...}`` record if ``data`` is an LMS reply."""
    if data[:1] != b"E":
        return None
    return {"ip": ip, **_parse_tlv(data[1:])}


def base_url(server: Dict[str, str]) -> str:
    """The HTTP base URL of a discovered server record.

    The port is whatever a UDP reply said, and anything on the LAN can reply.
    It becomes an address that is remembered and written into the page, so a
    value that is not a port is not believed: the LMS default instead.
    """
    port = (server.get("JSON") or "").strip()
    if not (port.isdigit() and 0 < int(port) < 65536):
        port = "9000"
    return f"http://{server['ip']}:{int(port)}"


def discover(timeout: float = 2.0, port: int = DISCOVERY_PORT) -> List[Dict[str, str]]:
    """Broadcast a discovery request and return the LMS servers found on the LAN,
    each as ``{'ip', 'NAME', 'JSON'(port), 'VERS', ...}``. Never raises."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
    sock.settimeout(timeout)
    servers: List[Dict[str, str]] = []
    seen = set()
    try:
        sock.sendto(_request(), ("255.255.255.255", port))
    except OSError:
        sock.close()
        return servers
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            data, addr = sock.recvfrom(2048)
        except (socket.timeout, OSError):
            break
        if addr[0] in seen:
            continue
        srv = _server_from(data, addr[0])
        if srv:
            seen.add(addr[0])
            servers.append(srv)
    sock.close()
    return servers


def _local_prefixes() -> List[str]:
    """/24 prefixes ("192.168.123") of this host's IPv4 interfaces."""
    ips = set()
    # Primary outbound interface: a UDP connect() picks the routing table's
    # answer without sending anything (TEST-NET-1 destination, never reached).
    try:
        probe = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        probe.connect(("192.0.2.1", 9))
        ips.add(probe.getsockname()[0])
        probe.close()
    except OSError:
        pass
    try:
        for ip in socket.gethostbyname_ex(socket.gethostname())[2]:
            ips.add(ip)
    except OSError:
        pass
    prefixes = []
    for ip in sorted(ips):
        if ip.startswith(("127.", "169.254.")):
            continue
        prefix = ip.rsplit(".", 1)[0]
        if prefix not in prefixes:
            prefixes.append(prefix)
    return prefixes


#: Linux constants the socket module does not always export.
_IP_RECVERR = getattr(socket, "IP_RECVERR", 11)
_MSG_ERRQUEUE = getattr(socket, "MSG_ERRQUEUE", 0x2000)
#: How far out to look. A home path is one or two routers (three behind a
#: Docker bridge) before the ISP; past six it is all the provider's.
_MAX_HOPS = 6
#: Never reached — the probes die on the way — but it has to be routable.
_HOP_TARGET = ("1.1.1.1", 33434)


def _is_rfc1918(ip: str) -> bool:
    o = ip.split(".")
    if len(o) != 4 or not all(x.isdigit() for x in o):
        return False
    a, b = int(o[0]), int(o[1])
    return a == 10 or (a == 172 and 16 <= b <= 31) or (a == 192 and b == 168)


def _path_hops(max_hops: int = _MAX_HOPS, timeout: float = 1.0) -> Dict[int, str]:
    """``{ttl: router address}`` for the routers that answered on the path out.

    One UDP socket per TTL, all sent at once; the router where a probe runs
    out of TTL answers ICMP time-exceeded, which Linux queues on that socket
    (IP_RECVERR) for an unprivileged reader. Linux only: anywhere else, and
    on any error at all, ``{}`` — which is "unknown", never "no routers".
    """
    if not sys.platform.startswith("linux") or not hasattr(socket.socket, "recvmsg"):
        return {}
    socks: Dict[int, socket.socket] = {}
    hops: Dict[int, str] = {}
    try:
        for ttl in range(1, max_hops + 1):
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            socks[ttl] = s
            s.setblocking(False)
            s.setsockopt(socket.IPPROTO_IP, socket.IP_TTL, ttl)
            s.setsockopt(socket.IPPROTO_IP, _IP_RECVERR, 1)
            s.sendto(b"vivavoce-hop", (_HOP_TARGET[0], _HOP_TARGET[1] + ttl))
        deadline = time.time() + timeout
        while len(hops) < max_hops and time.time() < deadline:
            for ttl, s in socks.items():
                if ttl in hops:
                    continue
                try:
                    _, anc, _, _ = s.recvmsg(
                        64, 512, _MSG_ERRQUEUE | socket.MSG_DONTWAIT)
                except (BlockingIOError, InterruptedError):
                    continue
                for level, kind, data in anc:
                    # struct sock_extended_err (16 bytes), then the offender's
                    # sockaddr_in: origin 2 is ICMP, type 11 time-exceeded.
                    if (level == socket.IPPROTO_IP and kind == _IP_RECVERR
                            and len(data) >= 24 and data[4] == 2 and data[5] == 11):
                        hops[ttl] = socket.inet_ntoa(data[20:24])
            time.sleep(0.02)
    except OSError:
        return {}  # offline, no route, a sandbox without the option
    finally:
        for s in socks.values():
            s.close()
    return hops


def _router_prefixes(hops: Dict[int, str], limit: int = 4) -> List[str]:
    """The /24s of the household's routers, read off ``_path_hops``.

    Private hops count from the first one up to the first gap or the first
    address that is not RFC1918: past that the path is the provider's, which
    may well be private too (172.16.x inside an ISP is common) and is no place
    to look for a hi-fi. A silent first hop is skipped rather than ending it.
    """
    out: List[str] = []
    for ttl in range(1, max(hops, default=0) + 1):
        ip = hops.get(ttl)
        if not ip:
            if out:
                break
            continue
        if not _is_rfc1918(ip):
            break
        prefix = ip.rsplit(".", 1)[0]
        if prefix not in out:
            out.append(prefix)
        if len(out) >= limit:
            break
    return out


def _full_sweep_forced() -> bool:
    return os.environ.get("VIVAVOCE_DISCOVERY_FULL", "").strip().lower() in (
        "1", "true", "yes")


def _sibling_prefixes(prefixes: List[str]) -> List[str]:
    """Every /24 inside the /16 each local prefix sits in.

    The sweep only ever looked at this host's own /24, which is the right
    guess on the 192.168.x.y networks a home router hands out — and wrong on
    the flat 10.0.0.0/16 or 172.16.0.0/16 a NAS or a managed switch sets up,
    where the LMS is one hop away in a sibling /24 and was simply never
    found. Bounded at 256 prefixes per interface, and only for the RFC1918
    ranges wide enough for this to happen at all.
    """
    out = []
    for prefix in prefixes:
        octets = prefix.split(".")
        if len(octets) != 3:
            continue
        first = octets[0]
        if first != "10" and not (first == "172" and 16 <= int(octets[1]) <= 31):
            continue          # 192.168/16 is already the "full" phase below
        out.extend(f"{octets[0]}.{octets[1]}.{i}" for i in range(256))
    return out


def _candidate_phases() -> List[Tuple[str, List[str]]]:
    """Ordered sweep phases as ``(name, [/24 prefixes])``, no duplicates:
    local interfaces first, then the routers' subnets on the path out, then
    common home subnets, then the rest of a wide local range (10.x/16,
    172.16-31.x/16), then all of 192.168/16.

    The last two only while the routers are unknown (see the module
    docstring). Once they are known, "wide" survives only for a local /16
    with a router in ANOTHER /24 of it — the flat 10.0/16 it was written
    for; a Docker bridge or WSL's NAT has its gateway in our own /24."""
    seen: set = set()
    phases: List[Tuple[str, List[str]]] = []
    local = _local_prefixes()
    routers = _router_prefixes(_path_hops())
    plan = [("local", local), ("routers", routers), ("common", _COMMON_PREFIXES)]
    if not routers or _full_sweep_forced():
        plan += [
            ("wide", _sibling_prefixes(local)),
            ("full", [f"192.168.{i}" for i in range(256)]),
        ]
    else:
        def flat(p: str) -> bool:
            slash16 = p.rsplit(".", 1)[0]
            return any(r != p and r.rsplit(".", 1)[0] == slash16
                       for r in routers)
        plan.append(("wide", _sibling_prefixes([p for p in local if flat(p)])))
    for name, prefixes in plan:
        fresh = [p for p in prefixes if p not in seen]
        seen.update(fresh)
        if fresh:
            phases.append((name, fresh))
    return phases


def discover_unicast(
    timeout: float = 30.0,
    port: int = DISCOVERY_PORT,
    on_progress: Optional[Callable[[str], None]] = None,
    phases: Optional[List[Tuple[str, List[str]]]] = None,
) -> List[Dict[str, str]]:
    """Sweep candidate subnets with unicast discovery requests and return the
    first LMS that answers (as a one-element list; empty if none). Never raises.

    ``on_progress`` (if given) is called with the phase name ("local",
    "routers", "common", "full"...) as each begins. Replies are polled every few dozen
    packets — early exit on the first valid answer, so on a typical network
    this returns in well under a second once the right subnet is reached.

    When the socket's send buffer fills (a full 192.168/16 pass is ~65k
    packets — through Docker/WSL NAT the kernel drains slower than we send),
    we wait for writability and retry instead of dropping: a silent drop here
    once cost the one packet that mattered. This self-paces the sweep to
    whatever the network layer actually sustains.
    """
    if phases is None:
        phases = _candidate_phases()
    request = _request()
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setblocking(False)
    for opt in (socket.SO_SNDBUF, socket.SO_RCVBUF):
        try:
            sock.setsockopt(socket.SOL_SOCKET, opt, 1 << 20)
        except OSError:
            pass
    deadline = time.time() + timeout
    found: List[Dict[str, str]] = []

    def _poll(wait: float) -> None:
        end = time.time() + wait
        while not found and time.time() < end:
            ready, _, _ = select.select([sock], [], [], max(0.0, end - time.time()))
            if not ready:
                return
            while True:
                try:
                    data, addr = sock.recvfrom(2048)
                except (BlockingIOError, InterruptedError):
                    break
                except OSError:
                    # Windows surfaces ICMP port-unreachable from swept hosts
                    # as ConnectionResetError on recv: ignore and keep reading.
                    continue
                srv = _server_from(data, addr[0])
                if srv:
                    found.append(srv)
                    return

    def _send(dest: Tuple[str, int]) -> None:
        while time.time() < deadline and not found:
            try:
                sock.sendto(request, dest)
                return
            except BlockingIOError:
                # Send buffer full: drain any replies, then wait until the
                # kernel is ready to take more packets. Never drop.
                _poll(0.002)
                select.select([], [sock], [], 0.05)
            except OSError:
                return  # unroutable address: skip it

    try:
        sent = 0
        for name, prefixes in phases:
            if on_progress:
                on_progress(name)
            for prefix in prefixes:
                for host in range(1, 255):
                    _send((f"{prefix}.{host}", port))
                    sent += 1
                    if sent % 64 == 0:
                        _poll(0.002)
                if found or time.time() > deadline:
                    return found
        # Stragglers: the last bursts' replies may still be in flight.
        _poll(min(1.5, max(0.0, deadline - time.time())))
        return found
    finally:
        sock.close()


def discover_base_url(
    timeout: float = 2.0,
    on_progress: Optional[Callable[[str], None]] = None,
) -> Optional[str]:
    """The HTTP base URL (``http://<ip>:<port>``) of the first LMS found, or
    None. Tries broadcast first, then the unicast sweep (``on_progress`` gets
    "sweep" before it starts, then the sweep's phase names)."""
    servers = discover(timeout)
    if not servers:
        if on_progress:
            on_progress("sweep")
        servers = discover_unicast(on_progress=on_progress)
    if not servers:
        return None
    return base_url(servers[0])
