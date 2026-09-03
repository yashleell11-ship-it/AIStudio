"""Image proxy hardening (audit findings 10 + 11).

Finding 10: the proxy reflected the upstream ``Content-Type`` verbatim, so a
hostile allowlisted host serving ``text/html`` became stored XSS on the app
origin. Only bitmap types are declared now; everything else is served as
``application/octet-stream``, and the two proxy routes carry
nosniff / CSP-sandbox / Content-Disposition headers.

Finding 11: the body was buffered with no size cap, so a multi-gigabyte
"image" OOM'd the box. Bodies are streamed with a hard byte ceiling
(``MM_IMAGE_PROXY_MAX_BYTES``), honouring Content-Length when declared.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from core.config import get_settings
from core.errors import AppError
from services.browse_service import BrowseService, _safe_image_media_type
from tests.test_browse_service_ssrf import _FakeConnector, _fake_stream


@pytest.fixture
def service() -> BrowseService:
    return BrowseService()


@pytest.fixture
def connector() -> _FakeConnector:
    return _FakeConnector(frozenset({"example.com"}))


def _fetch(service, connector, **stream_kwargs):
    with patch("services.outbound_security.is_public_address", return_value=True):
        with patch("httpx.stream", return_value=_fake_stream(**stream_kwargs)):
            return service._fetch_url("https://example.com/x", connector)


# ---------------------------------------------------------------------------
# Finding 10 — Content-Type allowlist
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "upstream, expected",
    [
        ("image/jpeg", "image/jpeg"),
        ("image/PNG; charset=utf-8", "image/png"),
        ("image/webp", "image/webp"),
        ("text/html", "application/octet-stream"),
        ("text/html; charset=utf-8", "application/octet-stream"),
        ("image/svg+xml", "application/octet-stream"),  # scriptable
        ("application/javascript", "application/octet-stream"),
        ("", "application/octet-stream"),
        (None, "application/octet-stream"),
    ],
)
def test_safe_media_type_only_ever_declares_bitmaps(upstream, expected):
    assert _safe_image_media_type(upstream) == expected


def test_fetch_url_clamps_hostile_html_content_type(service, connector):
    media_type, data = _fetch(
        service,
        connector,
        headers={"content-type": "text/html"},
        content=b"<script>steal()</script>",
    )
    assert media_type == "application/octet-stream"
    assert data == b"<script>steal()</script>"


def test_connector_proxied_fetch_is_clamped_too(service):
    """Connectors that fetch images themselves (fetch_proxied_image) pass the
    upstream content-type through — that path must be clamped identically."""
    connector = _FakeConnector(frozenset({"example.com"}))
    connector.fetch_proxied_image = MagicMock(
        return_value=("text/html", b"<script>x</script>")
    )
    with patch("services.outbound_security.is_public_address", return_value=True):
        media_type, _ = service._fetch_url("https://example.com/x", connector)
    assert media_type == "application/octet-stream"


def test_proxy_routes_send_hardening_headers(client, app):
    from services.browse_service import get_browse_service

    class _Stub:
        def resolve_page_image(self, *a, **kw):  # noqa: ANN002, ANN003, ARG002
            return "image/png", b"page-bytes"

        def resolve_series_cover(self, *a, **kw):  # noqa: ANN002, ANN003, ARG002
            return "image/png", b"cover-bytes"

    app.dependency_overrides[get_browse_service] = _Stub
    try:
        for path in (
            "/sources/mangadex/pages/p1/image",
            "/sources/mangadex/series/solo/cover",
        ):
            response = client.get(path)
            assert response.status_code == 200, path
            assert response.headers["x-content-type-options"] == "nosniff", path
            assert response.headers["content-security-policy"] == "sandbox", path
            assert response.headers["content-disposition"].startswith("inline"), path
    finally:
        app.dependency_overrides.pop(get_browse_service, None)


# ---------------------------------------------------------------------------
# Finding 11 — size cap
# ---------------------------------------------------------------------------


@pytest.fixture
def tiny_cap(monkeypatch):
    monkeypatch.setenv("MM_IMAGE_PROXY_MAX_BYTES", "10")
    get_settings.cache_clear()
    yield 10
    get_settings.cache_clear()


def test_declared_content_length_over_cap_is_rejected(service, connector, tiny_cap):
    with pytest.raises(AppError) as exc_info:
        _fetch(
            service,
            connector,
            headers={"content-type": "image/jpeg", "content-length": "11"},
            content=b"x" * 11,
        )
    assert exc_info.value.code == "image_too_large"


def test_streamed_body_over_cap_aborts_mid_stream(service, connector, tiny_cap):
    """No Content-Length declared (chunked hostile sender): the stream is cut
    off as soon as the ceiling is crossed."""
    with pytest.raises(AppError) as exc_info:
        _fetch(
            service,
            connector,
            headers={"content-type": "image/jpeg"},  # no content-length
            content=b"x" * 11,
        )
    assert exc_info.value.code == "image_too_large"


def test_body_within_cap_passes(service, connector, tiny_cap):
    media_type, data = _fetch(
        service,
        connector,
        headers={"content-type": "image/jpeg", "content-length": "10"},
        content=b"x" * 10,
    )
    assert media_type == "image/jpeg"
    assert data == b"x" * 10


def test_oversized_connector_proxied_body_is_rejected(service, tiny_cap):
    connector = _FakeConnector(frozenset({"example.com"}))
    connector.fetch_proxied_image = MagicMock(return_value=("image/jpeg", b"x" * 11))
    with patch("services.outbound_security.is_public_address", return_value=True):
        with pytest.raises(AppError) as exc_info:
            service._fetch_url("https://example.com/x", connector)
    assert exc_info.value.code == "image_too_large"
