"""What the LMS client does when the music server is slow, flaky or off.

Every test here is about a sentence somebody spoke. One spoken turn is
several sequential round trips — search, play, then the lookup that names
what started — and each was individually bounded while nothing bounded the
sum. Against a half-dead LMS a single command sat there for twenty-odd
seconds and then answered "server unreachable"; against one that was simply
switched off, it did that again for the next command, and the next.

So: one retry (a dropped packet is not an outage), a budget for the whole
turn, and a breaker so that "the hi-fi is off" is learned once rather than
re-timed-out all evening.
"""

import pytest

import lms as lms_module
from lms import BREAKER_COOLDOWN, BREAKER_THRESHOLD, LMSClient, LMSError, _Breaker


class Clock:
    """A monotonic clock the test moves by hand."""

    def __init__(self):
        self.t = 1000.0

    def __call__(self):
        return self.t

    def advance(self, seconds):
        self.t += seconds


class CountingTransport:
    """Records calls and fails the first ``fail`` of them."""

    def __init__(self, fail=0, result=None):
        self.calls = []
        self.fail = fail
        self.result = {} if result is None else result

    def __call__(self, params):
        self.calls.append(params)
        if len(self.calls) <= self.fail:
            raise LMSError("simulated transport failure")
        return self.result


def client(transport, **kw):
    return LMSClient("http://lms:9000", "aa:bb", transport=transport, **kw)


# -- one retry -----------------------------------------------------------------

def test_a_single_transport_failure_is_retried_and_succeeds():
    # A dropped packet, or an LMS caught mid-restart. Asking twice costs
    # nothing and saves the household a sentence that did not need to fail.
    transport = CountingTransport(fail=1)
    assert client(transport).command("pause") == {}
    assert len(transport.calls) == 2


def test_two_failures_in_a_row_are_reported_rather_than_hammered():
    transport = CountingTransport(fail=99)
    with pytest.raises(LMSError):
        client(transport).command("pause")
    assert len(transport.calls) == 2  # tried twice, not more


def test_a_well_formed_answer_we_dislike_is_not_retried():
    # Retrying is for transport failures. An LMS that answered, with something
    # this client cannot use, will answer exactly the same the second time —
    # and the caller has already been told what it means.
    calls = []

    def not_a_dict(params):
        calls.append(params)
        return ["a list, not a result object"]

    with pytest.raises(LMSError):
        client(not_a_dict).command("status")
    assert len(calls) == 1


# -- the breaker ---------------------------------------------------------------

def test_the_breaker_opens_after_repeated_failures_and_stops_dialling():
    clock = Clock()
    transport = CountingTransport(fail=99)
    c = client(transport)
    c._breaker = _Breaker(now=clock)
    # The breaker counts failed commands, not failed attempts — the retry
    # inside one command is what absorbs a dropped packet, so counting it
    # would open the breaker on half as much evidence as intended.
    for _ in range(BREAKER_THRESHOLD):
        with pytest.raises(LMSError):
            c.command("pause")
    before = len(transport.calls)
    with pytest.raises(LMSError, match="not dialled again"):
        c.command("pause")
    assert len(transport.calls) == before  # the socket was never touched


def test_the_breaker_lets_exactly_one_probe_through_after_the_cooldown():
    clock = Clock()
    transport = CountingTransport(fail=99)
    c = client(transport)
    c._breaker = _Breaker(now=clock)
    for _ in range(BREAKER_THRESHOLD):
        with pytest.raises(LMSError):
            c.command("pause")
    assert c._breaker.open_for() == pytest.approx(BREAKER_COOLDOWN)
    clock.advance(BREAKER_COOLDOWN + 1)
    before = len(transport.calls)
    with pytest.raises(LMSError):
        c.command("pause")
    assert len(transport.calls) > before  # the probe happened
    # ...and, having failed, the breaker is shut again at once: a household
    # that left the hi-fi off does not pay for the timeout twice a minute.
    after = len(transport.calls)
    with pytest.raises(LMSError, match="not dialled again"):
        c.command("pause")
    assert len(transport.calls) == after


def test_one_success_forgets_the_whole_history():
    clock = Clock()
    transport = CountingTransport(fail=1)
    c = client(transport)
    c._breaker = _Breaker(now=clock)
    c.command("pause")  # failed once, retried, succeeded
    assert c._breaker.open_for() == 0
    assert c._breaker._failures == 0


def test_the_breaker_is_shared_by_every_clone_of_a_client():
    # "The music server is not answering" is a fact about the server, not
    # about which clone asked — the same reasoning the search-node cache is
    # built on. A per-clone breaker would let one spoken turn pay the timeout
    # once per room and once per streaming service.
    transport = CountingTransport(fail=99)
    c = client(transport)
    assert c.for_service("qobuz")._breaker is c._breaker
    assert c.for_player("bb:cc")._breaker is c._breaker


# -- the turn budget -----------------------------------------------------------

def test_calls_are_unbounded_until_a_turn_says_otherwise():
    c = client(CountingTransport())
    assert c._call_timeout() == c.timeout


def test_a_turn_clamps_every_call_inside_it():
    c = client(CountingTransport())
    with c.turn_deadline(2.0):
        assert c._call_timeout() == pytest.approx(2.0, abs=0.1)
    assert c._call_timeout() == c.timeout  # and gives the budget back


def test_a_nested_turn_never_extends_the_one_around_it():
    c = client(CountingTransport())
    with c.turn_deadline(1.0):
        with c.turn_deadline(60.0):
            assert c._call_timeout() <= 1.0
        assert c._call_timeout() <= 1.0


def test_an_exhausted_turn_fails_at_once_instead_of_waiting(monkeypatch):
    transport = CountingTransport()
    c = client(transport)
    with c.turn_deadline(0.0):
        with pytest.raises(LMSError, match="ran out of time"):
            c.command("pause")
    assert transport.calls == []  # nothing was even attempted


def test_the_retry_is_skipped_once_the_budget_is_gone(monkeypatch):
    # The retry is a kindness, not a promise: it must not be the reason a
    # sentence takes twice as long as the household was told it could.
    clock = Clock()
    monkeypatch.setattr(lms_module.time, "monotonic", clock)
    transport = CountingTransport(fail=99)
    c = client(transport)

    def spend_the_budget(params):
        clock.advance(2.0)  # this attempt used up the whole turn
        return transport(params)

    c._transport = spend_the_budget
    with c.turn_deadline(1.0):
        with pytest.raises(LMSError):
            c.command("pause")
    assert len(transport.calls) == 1  # first attempt only; no time to retry


def test_the_budget_is_per_thread():
    # One Router — and so one client — is shared by every request on a
    # conversation. A budget on the instance would have two phones expiring
    # each other's turns.
    import threading

    c = client(CountingTransport())
    seen = []

    def other_thread():
        seen.append(c._call_timeout())

    with c.turn_deadline(1.0):
        t = threading.Thread(target=other_thread)
        t.start()
        t.join()
    assert seen == [c.timeout]


# -- the search-node cache -----------------------------------------------------

def _home(node=None):
    """A plugin home menu, with or without a search node."""
    rows = [{"id": "7", "type": "search", "name": "Search"}] if node else []
    return {"loop_loop": rows}


def test_a_found_search_node_is_cached_for_the_full_ttl(monkeypatch):
    calls = []

    def transport(params):
        calls.append(params)
        return _home(node=True)

    c = client(transport)
    assert c.search_node_id() == "7"
    assert c.search_node_id() == "7"
    assert len(calls) == 1  # the second answer came from the cache


def test_a_missing_search_node_is_barely_cached_at_all(monkeypatch):
    # The asymmetry that matters: logging TIDAL into LMS and coming straight
    # back must not be answered with "logged out" for another half-minute.
    # A found node saves a round trip that is about to happen anyway; a
    # missing one saves nothing, because the caller gives up rather than
    # asking again.
    assert LMSClient.SEARCH_NODE_MISS_TTL < LMSClient.SEARCH_NODE_TTL / 5

    clock = Clock()
    monkeypatch.setattr(lms_module.time, "monotonic", clock)
    logged_in = []

    def transport(params):
        return _home(node=bool(logged_in))

    c = client(transport)
    assert c.search_node_id() is None
    logged_in.append(1)  # the household logs the plugin in
    clock.advance(LMSClient.SEARCH_NODE_MISS_TTL + 0.1)
    assert c.search_node_id() == "7"


def test_a_search_that_answers_with_nothing_at_all_forgets_the_node(monkeypatch):
    # A plugin logged out since we last looked keeps being handed a node id
    # that no longer means anything, and the miss is then reported as "nothing
    # found" instead of "not connected" — the one distinction can_search
    # exists to make.
    clock = Clock()
    monkeypatch.setattr(lms_module.time, "monotonic", clock)
    state = {"logged_in": True}

    def transport(params):
        cmd = params[1]
        if any(p.startswith("search:") for p in cmd):
            return {"loop_loop": [] if not state["logged_in"] else
                    [{"name": "Songs", "id": "S"}]}
        return _home(node=state["logged_in"])

    c = client(transport)
    assert c.search_categories("time") == {"Songs": "S"}
    state["logged_in"] = False
    assert c.search_categories("time") == {}       # the stale node found nothing
    assert c.can_search() is False                 # ...and we looked again


# -- silence, refusal, and what may be sent twice -------------------------------
# Found in review. The breaker is about reachability and the retry about
# delivery, and both used to read every failure the same way: an expired token
# or three slow searches shut out even «pausa» for 15 s, and a reply lost after
# the LMS had acted sent «volume +5» — or an album to the queue — twice.

from lms import LMSRefused, LMSUnreachable, _lms_repeat_safe  # noqa: E402


class FailingWith:
    """Raises ``exc`` on every call, and counts them."""

    def __init__(self, exc):
        self.exc = exc
        self.calls = []

    def __call__(self, params):
        self.calls.append(params)
        raise self.exc


def test_a_refusal_is_never_retried():
    transport = FailingWith(LMSRefused("LMS answered 401"))
    with pytest.raises(LMSRefused):
        client(transport).command("pause", "1")
    assert len(transport.calls) == 1


def test_refusals_never_open_the_breaker():
    # A server that says no is a server that is there.
    transport = FailingWith(LMSRefused("LMS answered 401"))
    c = client(transport)
    c._breaker = _Breaker(now=Clock())
    for _ in range(BREAKER_THRESHOLD + 2):
        with pytest.raises(LMSRefused):
            c.command("pause", "1")
    assert c._breaker.open_for() == 0
    assert len(transport.calls) == BREAKER_THRESHOLD + 2


def test_a_timeout_the_turn_budget_shortened_does_not_count(monkeypatch):
    # Three slow searches inside a turn used to open the breaker, and the
    # next «pausa» on a perfectly healthy LMS was refused for 15 s.
    transport = FailingWith(LMSUnreachable("timed out", delivered=True))
    c = client(transport)
    c._breaker = _Breaker(now=Clock())
    for _ in range(BREAKER_THRESHOLD + 1):
        with c.turn_deadline(1.0):
            with pytest.raises(LMSError):
                c.command("status")
    assert c._breaker.open_for() == 0


def test_a_refused_connection_still_counts_inside_a_turn():
    # Clipping excuses a slow answer, not a server that is off.
    transport = FailingWith(LMSUnreachable("refused", delivered=False))
    c = client(transport)
    c._breaker = _Breaker(now=Clock())
    for _ in range(BREAKER_THRESHOLD):
        with c.turn_deadline(5.0):
            with pytest.raises(LMSError):
                c.command("status")
    assert c._breaker.open_for() > 0


@pytest.mark.parametrize("cmd", [
    ["mixer", "volume", "+5"], ["playlist", "index", "+1"],
    ["playlistcontrol", "cmd:add", "album_id:42"],
    ["tidal", "playlist", "add", "item_id:1"], ["button", "jump_fwd"],
])
def test_a_command_that_moves_is_not_sent_twice_after_a_lost_reply(cmd):
    transport = FailingWith(LMSUnreachable("timed out", delivered=True))
    with pytest.raises(LMSError):
        client(transport).command(*cmd)
    assert len(transport.calls) == 1


@pytest.mark.parametrize("cmd", [
    ["mixer", "volume", "+5"], ["playlistcontrol", "cmd:add", "album_id:42"],
])
def test_anything_is_sent_again_when_it_never_left(cmd):
    # A refused connection reached nobody: there is nothing to double.
    transport = FailingWith(LMSUnreachable("refused", delivered=False))
    with pytest.raises(LMSError):
        client(transport).command(*cmd)
    assert len(transport.calls) == 2


@pytest.mark.parametrize("cmd,safe", [
    (["status", "-", "1"], True), (["pause", "1"], True),
    (["mixer", "volume", "40"], True), (["playlist", "play", "tidal://1"], True),
    (["playlistcontrol", "cmd:load", "album_id:1"], True),
    (["tidal", "items", "0", "20", "search:x"], True),
    (["mixer", "volume", "-5"], False), (["time", "+10"], False),
    (["playlist", "insert", "tidal://1"], False),
])
def test_which_lms_commands_are_safe_to_repeat(cmd, safe):
    assert _lms_repeat_safe(cmd) is safe


def test_the_http_transport_tells_silence_from_refusal(monkeypatch):
    import io
    import urllib.error
    import urllib.request
    c = client(None)

    def raising(exc):
        def urlopen(req, timeout):
            raise exc
        return urlopen

    monkeypatch.setattr(urllib.request, "urlopen", raising(urllib.error.HTTPError(
        "http://lms:9000/jsonrpc.js", 401, "Unauthorized", {}, io.BytesIO())))
    with pytest.raises(LMSRefused):
        c._http_transport(["-", ["status"]])

    monkeypatch.setattr(urllib.request, "urlopen", raising(
        urllib.error.URLError(ConnectionRefusedError(111, "refused"))))
    with pytest.raises(LMSUnreachable) as refused:
        c._http_transport(["-", ["status"]])
    assert refused.value.delivered is False

    monkeypatch.setattr(urllib.request, "urlopen", raising(TimeoutError("timed out")))
    with pytest.raises(LMSUnreachable) as timed_out:
        c._http_transport(["-", ["status"]])
    assert timed_out.value.delivered is True
