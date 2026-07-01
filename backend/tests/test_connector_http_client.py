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
