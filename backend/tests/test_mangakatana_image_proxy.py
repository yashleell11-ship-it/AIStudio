from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from connectors.mangakatana.connector import MangaKatanaConnector
from connectors.models import Page
from core.errors import AppError
from services.browse_service import BrowseService
from services.download_support import fetch_image_resumable

MINIMAL_PNG = (
    b"\x89PNG\r\n\x1a\n"
    b"\x00\x00\x00\rIHDR"
    b"\x00\x00\x00\x01\x00\x00\x00\x01"
    b"\x08\x02\x00\x00\x00\x90wS\xde"
    b"\x00\x00\x00\x0cIDAT\x08\xd7c\xf8\xff\xff?\x00\x05\xfe\x02\xfe"
    b"\x00\x00\x00\x00IEND\xaeB`\x82"
)


@pytest.fixture
def mangakatana_connector() -> MangaKatanaConnector:
    return MangaKatanaConnector()


@pytest.fixture
def browse_service() -> BrowseService:
    return BrowseService()


def test_mangakatana_allowed_image_hosts_cover_domain(mangakatana_connector: MangaKatanaConnector):
    hosts = mangakatana_connector.allowed_image_hosts
    assert "mangakatana.com" in hosts


def test_mangakatana_cover_proxy_allows_cover_host(
    mangakatana_connector: MangaKatanaConnector,
    browse_service: BrowseService,
):
    cover_url = "https://mangakatana.com/imgs/cover/04e/36/39bbc.jpg"
    with patch("services.outbound_security.is_public_address", return_value=True):
        hostname = browse_service._validate_outbound_url(cover_url, mangakatana_connector)
    assert hostname == "mangakatana.com"


def test_mangakatana_reader_proxy_allows_cdn_subdomain(
    mangakatana_connector: MangaKatanaConnector,
    browse_service: BrowseService,
):
    page_url = "https://i1.mangakatana.com/token/example/0.jpg"
    with patch("services.outbound_security.is_public_address", return_value=True):
        hostname = browse_service._validate_outbound_url(page_url, mangakatana_connector)
    assert hostname == "i1.mangakatana.com"


def test_mangakatana_cover_proxy_fetches_approved_host(
    mangakatana_connector: MangaKatanaConnector,
    browse_service: BrowseService,
):
    cover_url = "https://mangakatana.com/imgs/cover/04e/36/39bbc.jpg"
    fake_response = MagicMock()
    fake_response.is_redirect = False
    fake_response.headers = {"content-type": "image/jpeg"}
    fake_response.content = MINIMAL_PNG
    fake_response.raise_for_status = MagicMock()

    with patch("services.outbound_security.is_public_address", return_value=True):
        with patch("httpx.get", return_value=fake_response) as mock_get:
            media_type, data = browse_service._fetch_url(cover_url, mangakatana_connector)

    assert media_type == "image/jpeg"
    assert data == MINIMAL_PNG
    mock_get.assert_called_once_with(cover_url, timeout=30.0, follow_redirects=False)


def test_mangakatana_reader_proxy_fetches_cdn_host(
    mangakatana_connector: MangaKatanaConnector,
    browse_service: BrowseService,
):
    page = Page(
        id="series/c1:1",
        chapter_id="series/c1",
        number=1,
        remote_url="https://i1.mangakatana.com/token/example/0.jpg",
    )
    fake_response = MagicMock()
    fake_response.is_redirect = False
    fake_response.headers = {"content-type": "image/jpeg"}
    fake_response.content = MINIMAL_PNG
    fake_response.raise_for_status = MagicMock()

    with patch("services.outbound_security.is_public_address", return_value=True):
        with patch("httpx.get", return_value=fake_response):
            media_type, data = browse_service._fetch_remote_image(page, mangakatana_connector)

    assert media_type == "image/jpeg"
    assert data == MINIMAL_PNG


def test_mangakatana_proxy_blocks_unapproved_host(
    mangakatana_connector: MangaKatanaConnector,
    browse_service: BrowseService,
):
    with patch("services.outbound_security.is_public_address", return_value=True):
        with pytest.raises(AppError) as exc_info:
            browse_service._fetch_url("https://evil.example.com/x.jpg", mangakatana_connector)
    assert exc_info.value.code == "ssrf_blocked"


def test_download_fetch_rejects_unapproved_host(mangakatana_connector: MangaKatanaConnector, tmp_path: Path):
    final_path = tmp_path / "001.jpg"
    partial_path = tmp_path / "001.jpg.partial"

    with patch("httpx.stream") as mock_stream:
        with pytest.raises(RuntimeError, match="approved domain"):
            fetch_image_resumable(
                "https://attacker.test/page.jpg",
                connector=mangakatana_connector,
                final_path=final_path,
                partial_path=partial_path,
                max_retries=1,
            )
    mock_stream.assert_not_called()


def test_download_fetch_rejects_redirect(mangakatana_connector: MangaKatanaConnector, tmp_path: Path):
    final_path = tmp_path / "001.jpg"
    partial_path = tmp_path / "001.jpg.partial"
    url = "https://i1.mangakatana.com/token/example/0.jpg"

    fake_response = MagicMock()
    fake_response.is_redirect = True
    fake_response.status_code = 302

    with patch("services.outbound_security.is_public_address", return_value=True):
        with patch("httpx.stream", return_value=fake_response):
            with pytest.raises(RuntimeError, match="redirect"):
                fetch_image_resumable(
                    url,
                    connector=mangakatana_connector,
                    final_path=final_path,
                    partial_path=partial_path,
                    max_retries=1,
                )


def test_download_fetch_succeeds_for_approved_host(
    mangakatana_connector: MangaKatanaConnector,
    tmp_path: Path,
):
    final_path = tmp_path / "001.jpg"
    partial_path = tmp_path / "001.jpg.partial"
    url = "https://i1.mangakatana.com/token/example/0.jpg"

    fake_response = MagicMock()
    fake_response.is_redirect = False
    fake_response.status_code = 200
    fake_response.iter_bytes.return_value = [MINIMAL_PNG]
    fake_response.__enter__ = MagicMock(return_value=fake_response)
    fake_response.__exit__ = MagicMock(return_value=False)

    with patch("services.outbound_security.is_public_address", return_value=True):
        with patch("httpx.stream", return_value=fake_response):
            content = fetch_image_resumable(
                url,
                connector=mangakatana_connector,
                final_path=final_path,
                partial_path=partial_path,
                max_retries=1,
            )

    assert content == MINIMAL_PNG
    assert final_path.is_file()
    assert final_path.read_bytes() == MINIMAL_PNG


def test_download_fetch_rejects_http_scheme(mangakatana_connector: MangaKatanaConnector, tmp_path: Path):
    with pytest.raises(RuntimeError, match="HTTPS"):
        fetch_image_resumable(
            "http://mangakatana.com/imgs/cover/x.jpg",
            connector=mangakatana_connector,
            final_path=tmp_path / "001.jpg",
            partial_path=tmp_path / "001.jpg.partial",
            max_retries=1,
        )


def test_download_fetch_rejects_private_dns(mangakatana_connector: MangaKatanaConnector, tmp_path: Path):
    url = "https://mangakatana.com/imgs/cover/x.jpg"
    with patch("services.outbound_security.is_public_address", return_value=False):
        with pytest.raises(RuntimeError, match="public address"):
            fetch_image_resumable(
                url,
                connector=mangakatana_connector,
                final_path=tmp_path / "001.jpg",
                partial_path=tmp_path / "001.jpg.partial",
                max_retries=1,
            )
