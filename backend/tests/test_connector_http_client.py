from __future__ import annotations

import httpx
import pytest

from connectors.http.client import SyncConnectorHttpClient


def test_sync_client_supports_sequential_requests():
    calls = {"count": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["count"] += 1
        if request.url.path == "/first":
            return httpx.Response(200, json={"step": "first"})
        if request.url.path == "/second":
            return httpx.Response(200, json={"step": "second"})
        return httpx.Response(404, json={"error": "not found"})

    transport = httpx.MockTransport(handler)
    client = SyncConnectorHttpClient("https://example.test")
    client._client = httpx.Client(
        base_url="https://example.test",
        transport=transport,
        headers=client._client.headers,
    )

    try:
        first = client.get_json("/first")
        second = client.get_json("/second")
    finally:
        client.close()

    assert calls["count"] == 2
    assert first == {"step": "first"}
    assert second == {"step": "second"}


def _capturing_client(**kwargs) -> tuple[SyncConnectorHttpClient, list[httpx.Request]]:
    """A real ``SyncConnectorHttpClient`` whose requests are recorded, not sent."""
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, text="ok")

    client = SyncConnectorHttpClient("https://example.test", min_interval=0.0, **kwargs)
    client._client = httpx.Client(
        base_url="https://example.test",
        transport=httpx.MockTransport(handler),
        headers=client._client.headers,
    )
    return client, seen


def _raw_names(request: httpx.Request) -> list[str]:
    return [name.decode() for name, _ in request.headers.raw]


#: Lowercasing any ONE of these turns a 200 into a Cloudflare 403 interstitial.
#: Measured from the VPS against elftoon.com and rawkuma.net; see the
#: ``post_text`` docstring. ``Referer``/``Accept-Language``/``X-Requested-With``
#: were indifferent, so this list is the actual finding, not a general rule.
CASE_SENSITIVE_TO_CLOUDFLARE = ("Accept-Encoding", "Connection", "User-Agent", "Accept")


def test_post_text_sends_browser_cased_standard_headers():
    """The bug: ``dict(client.headers)`` is lowercased, and lowercase is a block."""
    client, seen = _capturing_client(
        headers={"Accept": "text/html", "Referer": "https://example.test/"}
    )
    try:
        client.post_text(
            "/wp-admin/admin-ajax.php",
            data={"action": "x"},
            extra_headers={"X-Requested-With": "XMLHttpRequest", "Accept": "*/*"},
        )
    finally:
        client.close()

    names = _raw_names(seen[0])
    for header in CASE_SENSITIVE_TO_CLOUDFLARE:
        assert header in names, f"{header} missing: {names}"
        assert header.lower() not in names, f"{header} sent lowercased: {names}"


def test_post_text_does_not_duplicate_an_overridden_header():
    """``accept`` from the client plus ``Accept`` from the connector is two headers."""
    client, seen = _capturing_client(headers={"Accept": "text/html"})
    try:
        client.post_text("/x", data={}, extra_headers={"Accept": "*/*"})
    finally:
        client.close()

    names = [name.lower() for name in _raw_names(seen[0])]
    assert names.count("accept") == 1, _raw_names(seen[0])
    assert seen[0].headers["Accept"] == "*/*"


def test_post_text_still_sends_the_clients_configured_headers():
    """Dropping the re-supply must not drop the headers themselves."""
    client, seen = _capturing_client(
        headers={"Referer": "https://example.test/"}, user_agent="TestAgent/1.0"
    )
    try:
        client.post_text("/x", data={})
    finally:
        client.close()

    assert seen[0].headers["Referer"] == "https://example.test/"
    assert seen[0].headers["User-Agent"] == "TestAgent/1.0"


def test_post_text_preserves_connector_supplied_header_casing():
    """Laravel wants ``X-CSRF-TOKEN``; canonicalizing names would break doujins."""
    client, seen = _capturing_client()
    try:
        client.post_text("/x", data={}, extra_headers={"X-CSRF-TOKEN": "abc"})
    finally:
        client.close()

    assert "X-CSRF-TOKEN" in _raw_names(seen[0])


def test_get_text_still_sends_browser_cased_standard_headers():
    """``get_text`` never had the bug; pin it so a future edit cannot add it."""
    client, seen = _capturing_client(headers={"Accept": "text/html"})
    try:
        client.get_text("/x")
    finally:
        client.close()

    names = _raw_names(seen[0])
    for header in CASE_SENSITIVE_TO_CLOUDFLARE:
        assert header.lower() not in names, f"{header} sent lowercased: {names}"
