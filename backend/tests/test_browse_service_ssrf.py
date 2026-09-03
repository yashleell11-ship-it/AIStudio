from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from connectors.base import SourceConnector
from connectors.models import Chapter, Page, PaginatedSeriesList, Series
from core.errors import AppError
from services.browse_service import BrowseService
from services.outbound_security import is_public_address


class _FakeConnector(SourceConnector):
    """Minimal connector stub exposing a fixed image-host allowlist."""

    def __init__(self, allowed_hosts: frozenset[str]) -> None:
        self._allowed_hosts = allowed_hosts

    @property
    def source_type(self) -> str:
        return "fake"

    @property
    def display_name(self) -> str:
        return "Fake"

    @property
    def allowed_image_hosts(self) -> frozenset[str]:
        return self._allowed_hosts

    def get_series_list(self, page: int, *, sort: str | None = None) -> PaginatedSeriesList:
        raise NotImplementedError

    def search_series(self, query: str, page: int, *, sort: str | None = None) -> PaginatedSeriesList:
        raise NotImplementedError

    def get_series(self, series_id: str) -> Series | None:
        raise NotImplementedError

    def get_chapters(self, series_id: str) -> list[Chapter]:
        raise NotImplementedError

    def get_chapter_pages(self, chapter_id: str) -> list[Page]:
        raise NotImplementedError

    def find_page(self, page_id: str) -> Page | None:
        raise NotImplementedError


@pytest.fixture
def service() -> BrowseService:
    return BrowseService()


def _fake_stream(
    *,
    is_redirect: bool = False,
    headers: dict[str, str] | None = None,
    content: bytes = b"",
):
    """A stand-in for ``httpx.stream(...)``: a context manager yielding a
    response-shaped mock (the proxy streams bodies now, with a byte cap)."""
    response = MagicMock()
    response.is_redirect = is_redirect
    response.headers = headers or {}
    response.iter_bytes = lambda: iter([content] if content else [])
    response.raise_for_status = MagicMock()
    cm = MagicMock()
    cm.__enter__ = MagicMock(return_value=response)
    cm.__exit__ = MagicMock(return_value=False)
    return cm



def test_rejects_non_https_scheme(service: BrowseService):
    connector = _FakeConnector(frozenset({"example.com"}))
    with pytest.raises(AppError) as exc_info:
        service._validate_outbound_url("http://example.com/page.jpg", connector)
    assert exc_info.value.code == "ssrf_blocked"


def test_rejects_host_not_on_allowlist(service: BrowseService):
    connector = _FakeConnector(frozenset({"example.com"}))
    with pytest.raises(AppError) as exc_info:
        service._validate_outbound_url("https://internal.evil.test/x.jpg", connector)
    assert exc_info.value.code == "ssrf_blocked"


def test_rejects_localhost_even_if_not_on_allowlist(service: BrowseService):
    connector = _FakeConnector(frozenset())
    with pytest.raises(AppError) as exc_info:
        service._validate_outbound_url("https://127.0.0.1:11434/api", connector)
    assert exc_info.value.code == "ssrf_blocked"


def test_allows_exact_domain_match(service: BrowseService):
    connector = _FakeConnector(frozenset({"mangadex.org"}))
    with patch("services.outbound_security.is_public_address", return_value=True):
        hostname = service._validate_outbound_url("https://mangadex.org/covers/x.jpg", connector)
    assert hostname == "mangadex.org"


def test_allows_subdomain_of_approved_domain(service: BrowseService):
    """MangaDex's @Home CDN uses dynamic node hostnames under mangadex.network."""
    connector = _FakeConnector(frozenset({"mangadex.network"}))
    with patch("services.outbound_security.is_public_address", return_value=True):
        hostname = service._validate_outbound_url(
            "https://na1-uploads.mangadex.network/data/x.jpg", connector
        )
    assert hostname == "na1-uploads.mangadex.network"


def test_rejects_lookalike_domain_not_a_true_subdomain(service: BrowseService):
    """'notmangadex.network' is not a subdomain of 'mangadex.network' — the
    suffix check must require a dot boundary, not a bare string suffix."""
    connector = _FakeConnector(frozenset({"mangadex.network"}))
    with pytest.raises(AppError) as exc_info:
        service._validate_outbound_url("https://notmangadex.network/x.jpg", connector)
    assert exc_info.value.code == "ssrf_blocked"


def test_rejects_domain_that_resolves_to_private_address(service: BrowseService):
    """Defense-in-depth against DNS rebinding: even an allowlisted domain is
    rejected if it currently resolves to a private/loopback address."""
    connector = _FakeConnector(frozenset({"example.com"}))
    with patch("services.outbound_security.is_public_address", return_value=False):
        with pytest.raises(AppError) as exc_info:
            service._validate_outbound_url("https://example.com/x.jpg", connector)
    assert exc_info.value.code == "ssrf_blocked"


def test_fetch_url_never_makes_request_when_host_not_allowed(service: BrowseService):
    connector = _FakeConnector(frozenset({"example.com"}))
    with patch("httpx.stream") as mock_stream:
        with pytest.raises(AppError) as exc_info:
            service._fetch_url("https://attacker.test/x.jpg", connector)
    assert exc_info.value.code == "ssrf_blocked"
    mock_stream.assert_not_called()


def test_fetch_url_does_not_follow_redirects(service: BrowseService):
    """A redirect target could escape the allowlist; redirects must not be
    followed automatically."""
    connector = _FakeConnector(frozenset({"example.com"}))

    with patch("services.outbound_security.is_public_address", return_value=True):
        with patch(
            "httpx.stream", return_value=_fake_stream(is_redirect=True)
        ) as mock_stream:
            with pytest.raises(AppError) as exc_info:
                service._fetch_url("https://example.com/x.jpg", connector)

    assert exc_info.value.code == "ssrf_blocked"
    assert mock_stream.call_args.kwargs["follow_redirects"] is False


def test_fetch_url_succeeds_for_approved_host(service: BrowseService):
    connector = _FakeConnector(frozenset({"example.com"}))
    stream = _fake_stream(
        headers={"content-type": "image/png"}, content=b"fake-bytes"
    )

    with patch("services.outbound_security.is_public_address", return_value=True):
        with patch("httpx.stream", return_value=stream) as mock_stream:
            media_type, data = service._fetch_url("https://example.com/x.png", connector)

    assert media_type == "image/png"
    assert data == b"fake-bytes"
    mock_stream.assert_called_once_with(
        "GET",
        "https://example.com/x.png",
        timeout=30.0,
        follow_redirects=False,
        headers={},
    )


def test_connector_with_no_allowed_hosts_blocks_everything(service: BrowseService):
    """The default (empty) allowlist on the base SourceConnector class must
    deny all outbound fetches — restrictive by default."""
    connector = _FakeConnector(frozenset())
    with patch("services.outbound_security.is_public_address", return_value=True):
        with pytest.raises(AppError) as exc_info:
            service._validate_outbound_url("https://example.com/x.jpg", connector)
    assert exc_info.value.code == "ssrf_blocked"
