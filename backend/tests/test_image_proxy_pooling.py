"""The image proxy must reuse connections across page images.

Every page image used to go out through the module-level ``httpx.stream()``,
which constructs and discards an entire ``httpx.Client`` per call. That is a
fresh DNS lookup, TCP connect and TLS handshake for each of the 20-200 images
in a chapter; measured from the VPS it cost 2.6s instead of 0.09s for six
MangaDex pages. These tests pin the pooling so it cannot silently regress
back to a per-request client.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import httpx
import pytest

import services.browse_service as browse_service
from connectors.base import SourceConnector
from services.browse_service import BrowseService


class _FakeConnector(SourceConnector):
    @property
    def source_type(self) -> str:
        return "fake"

    @property
    def display_name(self) -> str:
        return "Fake"

    @property
    def allowed_image_hosts(self) -> frozenset[str]:
        return frozenset({"example.com"})

    def get_series_list(self, page, *, sort=None):  # pragma: no cover - unused
        raise NotImplementedError

    def search_series(self, query, page, *, sort=None):  # pragma: no cover
        raise NotImplementedError

    def get_series(self, series_id):  # pragma: no cover - unused
        raise NotImplementedError

    def get_chapters(self, series_id):  # pragma: no cover - unused
        raise NotImplementedError

    def get_chapter_pages(self, chapter_id):  # pragma: no cover - unused
        raise NotImplementedError


@pytest.fixture(autouse=True)
def _reset_pool():
    """Each test starts from a cold pool and leaves no client behind."""
    browse_service._image_http_client = None
    yield
    client = browse_service._image_http_client
    if client is not None:
        client.close()
    browse_service._image_http_client = None


def _fake_stream(content: bytes = b"bytes"):
    response = MagicMock()
    response.is_redirect = False
    response.headers = {"content-type": "image/png"}
    response.iter_bytes = lambda: iter([content])
    response.raise_for_status = MagicMock()
    cm = MagicMock()
    cm.__enter__ = MagicMock(return_value=response)
    cm.__exit__ = MagicMock(return_value=False)
    return cm


def test_image_client_is_reused_across_calls() -> None:
    first = browse_service._image_client()
    second = browse_service._image_client()
    assert first is second


def test_image_client_keeps_connections_alive_and_refuses_redirects() -> None:
    client = browse_service._image_client()
    # A redirect target can escape the SSRF allowlist, so the pooled client
    # must carry the same refusal the per-request one did.
    assert client.follow_redirects is False
    assert isinstance(client, httpx.Client)


def test_image_client_is_rebuilt_if_it_was_closed() -> None:
    first = browse_service._image_client()
    first.close()
    second = browse_service._image_client()
    assert second is not first
    assert not second.is_closed


def test_every_image_is_streamed_from_the_shared_client() -> None:
    """Two proxied images must issue two requests on ONE client."""
    service = BrowseService.__new__(BrowseService)
    connector = _FakeConnector()
    fake_client = MagicMock()
    fake_client.stream.side_effect = lambda *a, **k: _fake_stream()

    with patch("services.outbound_security.is_public_address", return_value=True):
        with patch.object(browse_service, "_image_client", return_value=fake_client):
            service._fetch_url("https://example.com/1.png", connector)
            service._fetch_url("https://example.com/2.png", connector)

    assert fake_client.stream.call_count == 2
    for call in fake_client.stream.call_args_list:
        assert call.args[0] == "GET"
        assert call.kwargs["follow_redirects"] is False
