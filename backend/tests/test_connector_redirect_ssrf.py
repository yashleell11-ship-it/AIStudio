"""Connector scrape fetches must validate every redirect hop (SSRF guard).

Audit finding: the scrape clients followed redirects with zero validation, so
any allowlisted upstream could 302 the backend at an arbitrary target —
including plain-HTTP services on the shared docker network. Every hop is now
checked: https only, same-site host only, public address only
(``connectors/http/redirect_policy.py``).
"""

from __future__ import annotations

from unittest.mock import patch

import httpx
import pytest

from connectors.http.client import ConnectorHttpError, SyncConnectorHttpClient
from connectors.http.redirect_policy import (
    allowed_redirect_hosts,
    redirect_rejection_reason,
    send_with_redirect_validation,
)


def _public(*, value: bool = True):
    """Patch the DNS/public-address check where the policy module calls it."""
    return patch(
        "connectors.http.redirect_policy.is_public_address", return_value=value
    )


# ---------------------------------------------------------------------------
# Policy unit tests
# ---------------------------------------------------------------------------


def test_allowed_hosts_derived_from_base_url_strips_www():
    assert allowed_redirect_hosts("https://www.example.com") == frozenset(
        {"example.com"}
    )
    assert allowed_redirect_hosts("https://example.com/path") == frozenset(
        {"example.com"}
    )
    assert allowed_redirect_hosts("") == frozenset()


def test_rejects_http_downgrade():
    with _public():
        reason = redirect_rejection_reason(
            "http://example.com/x", frozenset({"example.com"})
        )
    assert reason is not None and "non-https" in reason


def test_rejects_off_domain_host():
    with _public():
        reason = redirect_rejection_reason(
            "https://headless-bot:8080/x", frozenset({"example.com"})
        )
    assert reason is not None and "off this source's domain" in reason


def test_rejects_lookalike_host_without_dot_boundary():
    with _public():
        reason = redirect_rejection_reason(
            "https://notexample.com/x", frozenset({"example.com"})
        )
    assert reason is not None


def test_rejects_non_public_address_even_on_domain():
    with _public(value=False):
        reason = redirect_rejection_reason(
            "https://internal.example.com/x", frozenset({"example.com"})
        )
    assert reason is not None and "public address" in reason


def test_allows_same_site_https_subdomain():
    with _public():
        assert (
            redirect_rejection_reason(
                "https://cdn.example.com/x", frozenset({"example.com"})
            )
            is None
        )


def test_empty_allowlist_blocks_every_target():
    with _public():
        assert redirect_rejection_reason("https://example.com/x", frozenset()) is not None


# ---------------------------------------------------------------------------
# httpx client (SyncConnectorHttpClient): hop validated before the follow
# ---------------------------------------------------------------------------


def _client_with_transport(handler) -> SyncConnectorHttpClient:
    client = SyncConnectorHttpClient("https://example.com")
    inner = client._client
    client._client = httpx.Client(
        base_url="https://example.com",
        transport=httpx.MockTransport(handler),
        headers=inner.headers,
        follow_redirects=True,
        event_hooks={"response": [client._guard_redirect]},
    )
    inner.close()
    return client


def test_httpx_client_blocks_cross_host_redirect_and_never_fetches_target():
    fetched: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        fetched.append(str(request.url))
        if request.url.host == "example.com":
            return httpx.Response(
                302, headers={"location": "http://headless-bot:8080/steal"}
            )
        return httpx.Response(200, text="internal payload")

    client = _client_with_transport(handler)
    try:
        with _public():
            with pytest.raises(ConnectorHttpError) as exc_info:
                client.get_text("/manga/some-slug/")
    finally:
        client.close()

    assert "Redirect blocked" in str(exc_info.value)
    assert all("headless-bot" not in url for url in fetched)


def test_httpx_client_still_follows_same_site_redirect():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/old":
            return httpx.Response(302, headers={"location": "https://example.com/new"})
        if request.url.path == "/new":
            return httpx.Response(200, text="real content")
        return httpx.Response(404)

    client = _client_with_transport(handler)
    try:
        with _public():
            body = client.get_text("/old")
    finally:
        client.close()

    assert body == "real content"


def test_httpx_client_blocks_https_to_http_downgrade_on_own_host():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(302, headers={"location": "http://example.com/plain"})

    client = _client_with_transport(handler)
    try:
        with _public():
            with pytest.raises(ConnectorHttpError):
                client.get_text("/x")
    finally:
        client.close()


# ---------------------------------------------------------------------------
# curl_cffi-style clients: the manual loop in send_with_redirect_validation
# ---------------------------------------------------------------------------


class _FakeCurlResponse:
    def __init__(self, url: str, status_code: int, *, location: str | None = None, text: str = ""):
        self.url = url
        self.status_code = status_code
        self.headers = {"location": location} if location else {}
        self.text = text
        self.reason = ""


class _FakeCurlSession:
    """Records every request; serves scripted responses per URL."""

    def __init__(self, script: dict[str, _FakeCurlResponse]):
        self._script = script
        self.requested: list[tuple[str, str]] = []

    def request(self, method, url, *, params=None, data=None, headers=None, timeout=None, allow_redirects=None):  # noqa: ANN001, ARG002
        assert allow_redirects is False, "manual loop must never let libcurl follow"
        self.requested.append((method, url))
        return self._script[url]


def test_curl_loop_blocks_cross_host_redirect():
    session = _FakeCurlSession(
        {
            "https://example.com/page": _FakeCurlResponse(
                "https://example.com/page",
                301,
                location="http://tree-bot:8081/admin",
            ),
        }
    )
    with _public():
        with pytest.raises(ConnectorHttpError) as exc_info:
            send_with_redirect_validation(
                session,
                "GET",
                "https://example.com/page",
                allowed_hosts=frozenset({"example.com"}),
            )
    assert "Redirect blocked" in str(exc_info.value)
    assert session.requested == [("GET", "https://example.com/page")]


def test_curl_loop_follows_same_site_hops_and_relative_locations():
    session = _FakeCurlSession(
        {
            "https://example.com/a": _FakeCurlResponse(
                "https://example.com/a", 302, location="/b"
            ),
            "https://example.com/b": _FakeCurlResponse(
                "https://example.com/b", 200, text="done"
            ),
        }
    )
    with _public():
        response = send_with_redirect_validation(
            session,
            "GET",
            "https://example.com/a",
            allowed_hosts=frozenset({"example.com"}),
        )
    assert response.text == "done"
    assert [u for _, u in session.requested] == [
        "https://example.com/a",
        "https://example.com/b",
    ]


def test_curl_loop_gives_up_after_max_hops():
    session = _FakeCurlSession(
        {
            "https://example.com/loop": _FakeCurlResponse(
                "https://example.com/loop", 302, location="/loop"
            ),
        }
    )
    with _public():
        with pytest.raises(ConnectorHttpError) as exc_info:
            send_with_redirect_validation(
                session,
                "GET",
                "https://example.com/loop",
                allowed_hosts=frozenset({"example.com"}),
                max_hops=3,
            )
    assert "Too many redirects" in str(exc_info.value)


def test_cf_client_get_text_blocks_cross_host_redirect():
    from connectors.http.cf_client import CfSyncHttpClient

    client = CfSyncHttpClient("https://example.com", max_retries=1, min_interval=0.0)
    client._session = _FakeCurlSession(
        {
            "https://example.com/manga/x/": _FakeCurlResponse(
                "https://example.com/manga/x/",
                302,
                location="https://cloudflared:2000/metrics",
            ),
        }
    )
    with _public():
        with pytest.raises(ConnectorHttpError) as exc_info:
            client.get_text("/manga/x/")
    assert "Redirect blocked" in str(exc_info.value)
    assert all("cloudflared" not in url for _, url in client._session.requested)
