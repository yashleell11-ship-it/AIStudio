"""What the connector HTTP clients may and may not retry.

The perf pass stopped retrying deterministic 4xx responses. That is a change
to *behaviour*, not just to speed: a source that used to succeed on the second
attempt must still succeed, and an error a connector branches on must still
carry the same information. These tests pin both halves.

Measured motivation, so the numbers do not get lost: every Madara series page
probes ``/wp-admin/admin-ajax.php`` before falling back to the per-series AJAX
route. On cocomic, cucumbermanga, lilymanga, manhwatop and manhuanext that
endpoint answers 400/403 — and the old loop spent three round trips plus
0.5 s + 1.0 s of backoff sleep to learn it, on every single series open.
"""

from __future__ import annotations

import time

import httpx
import pytest

from connectors.http.client import (
    MAX_RETRY_AFTER_SECONDS,
    ConnectorHttpError,
    SyncConnectorHttpClient,
    is_retryable,
    status_of,
)


def _client(handler) -> SyncConnectorHttpClient:
    client = SyncConnectorHttpClient("https://example.test", min_interval=0.0)
    client._client = httpx.Client(
        base_url="https://example.test",
        transport=httpx.MockTransport(handler),
        headers=client._client.headers,
    )
    return client


def _counting(status: int, *, body: str = "nope"):
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        return httpx.Response(status, text=body)

    return handler, calls


# --- what must NOT be retried ----------------------------------------------


@pytest.mark.parametrize("status", [400, 401, 403, 404, 410, 422])
def test_deterministic_client_errors_are_requested_once(status: int) -> None:
    """A 4xx that means "no" costs one round trip, not three."""
    handler, calls = _counting(status)
    client = _client(handler)
    try:
        with pytest.raises(ConnectorHttpError):
            client.get_text("/x")
        assert calls["n"] == 1
        calls["n"] = 0
        with pytest.raises(ConnectorHttpError):
            client.get_json("/x")
        assert calls["n"] == 1
        calls["n"] = 0
        with pytest.raises(ConnectorHttpError):
            client.post_text("/x", data={})
        assert calls["n"] == 1
        calls["n"] = 0
        with pytest.raises(ConnectorHttpError):
            client.get_bytes("https://example.test/x")
        assert calls["n"] == 1
    finally:
        client.close()


def test_a_dead_ajax_endpoint_costs_one_request_not_three() -> None:
    """The Madara shape, end to end: 400 then a working fallback = 2 requests."""
    seen: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request.url.path)
        if request.url.path == "/wp-admin/admin-ajax.php":
            return httpx.Response(400, text="0")
        return httpx.Response(200, text="<ul>chapters</ul>")

    client = _client(handler)
    try:
        with pytest.raises(ConnectorHttpError):
            client.post_text("/wp-admin/admin-ajax.php", data={"action": "x"})
        assert client.post_text("/series/a/ajax/chapters/", data={}) == (
            "<ul>chapters</ul>"
        )
    finally:
        client.close()
    assert seen == ["/wp-admin/admin-ajax.php", "/series/a/ajax/chapters/"]


def test_a_dead_endpoint_does_not_sleep() -> None:
    """The backoff sleep is the expensive half; a 4xx must not pay it."""
    handler, _calls = _counting(400)
    client = _client(handler)
    started = time.monotonic()
    try:
        with pytest.raises(ConnectorHttpError):
            client.get_text("/x")
    finally:
        client.close()
    assert time.monotonic() - started < 0.25


# --- what MUST still be retried --------------------------------------------


@pytest.mark.parametrize("status", [408, 429, 500, 502, 503, 504])
def test_overload_and_server_errors_are_still_retried(
    status: int, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(time, "sleep", lambda _s: None)
    handler, calls = _counting(status)
    client = _client(handler)
    try:
        with pytest.raises(ConnectorHttpError):
            client.get_text("/x")
    finally:
        client.close()
    assert calls["n"] == 3


def test_a_transport_failure_is_still_retried(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(time, "sleep", lambda _s: None)
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        raise httpx.ConnectTimeout("boom", request=request)

    client = _client(handler)
    try:
        with pytest.raises(ConnectorHttpError):
            client.get_text("/x")
    finally:
        client.close()
    assert calls["n"] == 3


def test_a_source_that_recovers_on_the_second_attempt_still_succeeds(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The whole point of retries: one 503 blip must not fail the read."""
    monkeypatch.setattr(time, "sleep", lambda _s: None)
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        if calls["n"] == 1:
            return httpx.Response(503, text="try later")
        return httpx.Response(200, text="<html>ok</html>")

    client = _client(handler)
    try:
        assert client.get_text("/x") == "<html>ok</html>"
    finally:
        client.close()
    assert calls["n"] == 2


# --- the status a connector branches on ------------------------------------


def test_a_404_arrives_with_status_code_404() -> None:
    """``exc.status_code == 404`` used to be dead code against this client.

    Only ``RETRYABLE_STATUS`` responses carried a status, so every novel
    connector had to match httpx's message text instead. Both forms now work,
    and the message is preserved so the existing string checks keep passing.
    """
    handler, _calls = _counting(404)
    client = _client(handler)
    try:
        with pytest.raises(ConnectorHttpError) as excinfo:
            client.get_text("/gone")
    finally:
        client.close()
    assert excinfo.value.status_code == 404
    assert "404 Not Found" in str(excinfo.value)


def test_get_bytes_also_reports_the_status() -> None:
    handler, _calls = _counting(404)
    client = _client(handler)
    try:
        with pytest.raises(ConnectorHttpError) as excinfo:
            client.get_bytes("https://example.test/missing.epub")
    finally:
        client.close()
    assert excinfo.value.status_code == 404


# --- the retryable override -------------------------------------------------


def test_a_challenge_403_is_retryable_but_an_origin_403_is_not() -> None:
    """Cloudflare/DDoS-Guard interstitials report 403 and are transient."""
    challenge = ConnectorHttpError("Cloudflare challenge", status_code=403,
                                   retryable=True)
    origin = ConnectorHttpError("Forbidden", status_code=403)
    assert is_retryable(challenge) is True
    assert is_retryable(origin) is False


def test_status_of_reads_both_error_shapes() -> None:
    request = httpx.Request("GET", "https://example.test/x")
    wrapped = httpx.HTTPStatusError(
        "boom", request=request, response=httpx.Response(404, request=request)
    )
    assert status_of(wrapped) == 404
    assert status_of(ConnectorHttpError("x", status_code=429)) == 429
    assert status_of(httpx.ConnectTimeout("t", request=request)) is None
    assert status_of(None) is None


def test_retry_after_cannot_park_a_thread_for_an_hour(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``Retry-After: 3600`` is a hang, not a retry."""
    slept: list[float] = []
    monkeypatch.setattr(time, "sleep", lambda s: slept.append(s))

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(429, headers={"Retry-After": "3600"}, text="slow down")

    client = _client(handler)
    try:
        with pytest.raises(ConnectorHttpError):
            client.get_json("/x")
    finally:
        client.close()
    assert slept, "a 429 should still back off"
    assert max(slept) <= MAX_RETRY_AFTER_SECONDS
