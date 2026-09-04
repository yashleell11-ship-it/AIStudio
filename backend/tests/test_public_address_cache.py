"""Caching the SSRF resolver verdict must not weaken the guard.

``is_public_address`` sits on the image proxy's PER-IMAGE path. A chapter is
20-100 images off one CDN hostname and each one paid a blocking
``getaddrinfo``; measured from the production container that is ~1.2 ms median
but 117 ms at p95 and 163 ms at worst, serialized ahead of the fetch.

Caching a security verdict is exactly the kind of speedup that turns into a
hole, so these tests state what must remain true: a private address is still
refused, a failure to resolve is still refused, the verdict expires, and the
allowlist — the control that actually decides which hosts reach the resolver —
is untouched.
"""

from __future__ import annotations

import socket

import pytest

from connectors.http import redirect_policy as rp


@pytest.fixture(autouse=True)
def _clean_cache():
    rp.reset_public_address_cache()
    yield
    rp.reset_public_address_cache()


def _resolver(mapping: dict[str, str], calls: list[str]):
    def fake_getaddrinfo(host, *args, **kwargs):
        calls.append(host)
        if host not in mapping:
            raise socket.gaierror(-2, "Name or service not known")
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (mapping[host], 0))]

    return fake_getaddrinfo


def test_a_repeated_host_resolves_once(monkeypatch) -> None:
    calls: list[str] = []
    monkeypatch.setattr(
        socket, "getaddrinfo", _resolver({"cdn.example.com": "93.184.216.34"}, calls)
    )
    for _ in range(50):
        assert rp.is_public_address("cdn.example.com") is True
    assert calls == ["cdn.example.com"]


def test_a_private_address_is_still_refused(monkeypatch) -> None:
    calls: list[str] = []
    monkeypatch.setattr(
        socket, "getaddrinfo", _resolver({"evil.example.com": "10.0.0.5"}, calls)
    )
    assert rp.is_public_address("evil.example.com") is False
    assert rp.is_public_address("evil.example.com") is False


@pytest.mark.parametrize(
    "address",
    ["127.0.0.1", "10.1.2.3", "192.168.1.10", "169.254.1.1", "0.0.0.0", "224.0.0.1"],
)
def test_every_non_public_class_is_refused(monkeypatch, address: str) -> None:
    monkeypatch.setattr(socket, "getaddrinfo", _resolver({"h": address}, []))
    assert rp.is_public_address("h") is False


def test_a_host_that_does_not_resolve_is_refused(monkeypatch) -> None:
    monkeypatch.setattr(socket, "getaddrinfo", _resolver({}, []))
    assert rp.is_public_address("nope.example.com") is False


def test_a_cached_verdict_expires(monkeypatch) -> None:
    """A minute is the whole promise; it has to actually end."""
    calls: list[str] = []
    monkeypatch.setattr(
        socket, "getaddrinfo", _resolver({"cdn.example.com": "93.184.216.34"}, calls)
    )
    clock = {"t": 1000.0}
    monkeypatch.setattr(rp.time, "monotonic", lambda: clock["t"])

    assert rp.is_public_address("cdn.example.com") is True
    clock["t"] += rp.PUBLIC_ADDRESS_TTL_SECONDS - 1
    assert rp.is_public_address("cdn.example.com") is True
    assert len(calls) == 1

    clock["t"] += 2
    assert rp.is_public_address("cdn.example.com") is True
    assert len(calls) == 2


def test_a_host_that_turns_private_is_refused_after_the_ttl(monkeypatch) -> None:
    """The rebinding case, stated explicitly."""
    mapping = {"cdn.example.com": "93.184.216.34"}
    monkeypatch.setattr(socket, "getaddrinfo", _resolver(mapping, []))
    clock = {"t": 500.0}
    monkeypatch.setattr(rp.time, "monotonic", lambda: clock["t"])

    assert rp.is_public_address("cdn.example.com") is True
    mapping["cdn.example.com"] = "127.0.0.1"
    clock["t"] += rp.PUBLIC_ADDRESS_TTL_SECONDS + 1
    assert rp.is_public_address("cdn.example.com") is False


def test_two_hosts_keep_separate_verdicts(monkeypatch) -> None:
    monkeypatch.setattr(
        socket,
        "getaddrinfo",
        _resolver({"good.example.com": "93.184.216.34", "bad.example.com": "10.0.0.1"}, []),
    )
    assert rp.is_public_address("good.example.com") is True
    assert rp.is_public_address("bad.example.com") is False
    assert rp.is_public_address("good.example.com") is True


def test_the_cache_is_bounded(monkeypatch) -> None:
    monkeypatch.setattr(rp, "_PUBLIC_ADDRESS_MAX_HOSTS", 4)
    monkeypatch.setattr(
        socket,
        "getaddrinfo",
        lambda host, *a, **k: [
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 0))
        ],
    )
    for i in range(20):
        rp.is_public_address(f"h{i}.example.com")
    with rp._public_address_lock:
        assert len(rp._public_address_cache) <= 4


def test_the_allowlist_still_decides_which_hosts_reach_the_resolver() -> None:
    """The primary control is unchanged and is checked BEFORE the resolver."""
    allowed = frozenset({"example.com"})
    assert rp.host_matches_allowlist("cdn.example.com", allowed) is True
    assert rp.host_matches_allowlist("example.com", allowed) is True
    assert rp.host_matches_allowlist("notexample.com", allowed) is False
    assert rp.host_matches_allowlist("example.com.evil.test", allowed) is False


def test_a_redirect_to_a_private_host_is_still_rejected(monkeypatch) -> None:
    monkeypatch.setattr(
        socket, "getaddrinfo", _resolver({"cdn.example.com": "10.0.0.9"}, [])
    )
    reason = rp.redirect_rejection_reason(
        "https://cdn.example.com/x.jpg", frozenset({"example.com"})
    )
    assert reason is not None
