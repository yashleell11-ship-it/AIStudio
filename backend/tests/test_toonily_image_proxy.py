"""Toonily CDN image proxy requires a site Referer (hotlink protection)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from connectors.models import Page
from connectors.toonily.connector import ToonilyConnector
from connectors.toonily.mappers import SITE_BASE
from core.errors import AppError
from services.browse_service import BrowseService

MINIMAL_PNG = (
    b"\x89PNG\r\n\x1a\n"
    b"\x00\x00\x00\rIHDR"
    b"\x00\x00\x00\x01\x00\x00\x00\x01"
    b"\x08\x02\x00\x00\x00\x90wS\xde"
    b"\x00\x00\x00\x0cIDAT\x08\xd7c\xf8\xff\xff?\x00\x05\xfe\x02\xfe"
    b"\x00\x00\x00\x00IEND\xaeB`\x82"
)


@pytest.fixture
def toonily_connector() -> ToonilyConnector:
    return ToonilyConnector()


@pytest.fixture
def browse_service() -> BrowseService:
    return BrowseService()


def test_toonily_image_fetch_headers_include_referer(toonily_connector: ToonilyConnector):
    headers = toonily_connector.image_fetch_headers()
    assert headers.get("Referer") == f"{SITE_BASE}/"


def test_toonily_allows_data_tnlycdn_host(
    toonily_connector: ToonilyConnector,
    browse_service: BrowseService,
):
    url = "https://data.tnlycdn.com/chapters/example/page.jpg"
    with patch("services.outbound_security.is_public_address", return_value=True):
        hostname = browse_service._validate_outbound_url(url, toonily_connector)
    assert hostname == "data.tnlycdn.com"


def test_toonily_page_proxy_sends_referer_header(
    toonily_connector: ToonilyConnector,
    browse_service: BrowseService,
):
    page = Page(
        id="series/chapter-1:1",
        chapter_id="series/chapter-1",
        number=1,
        remote_url="https://data.tnlycdn.com/chapters/example/page.jpg",
    )
    fake_response = MagicMock()
    fake_response.is_redirect = False
    fake_response.headers = {"content-type": "image/webp"}
    fake_response.iter_bytes = lambda: iter([MINIMAL_PNG])
    fake_response.raise_for_status = MagicMock()
    stream_cm = MagicMock()
    stream_cm.__enter__ = MagicMock(return_value=fake_response)
    stream_cm.__exit__ = MagicMock(return_value=False)

    with patch("services.outbound_security.is_public_address", return_value=True):
        with patch("services.browse_service._image_stream", return_value=stream_cm) as mock_stream:
            media_type, data = browse_service._fetch_remote_image(page, toonily_connector)

    assert media_type == "image/webp"
    assert data == MINIMAL_PNG
    mock_stream.assert_called_once_with(
        "GET",
        page.remote_url,
        timeout=30.0,
        follow_redirects=False,
        headers={"Referer": f"{SITE_BASE}/"},
    )


def test_toonily_proxy_blocks_unapproved_host(
    toonily_connector: ToonilyConnector,
    browse_service: BrowseService,
):
    with patch("services.outbound_security.is_public_address", return_value=True):
        with pytest.raises(AppError) as exc_info:
            browse_service._fetch_url("https://evil.example.com/x.jpg", toonily_connector)
    assert exc_info.value.code == "ssrf_blocked"
