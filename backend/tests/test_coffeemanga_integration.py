"""Live integration smoke test for the CoffeeManga connector.

Excluded from the default suite (``addopts = -m 'not integration'``); run with
``pytest -m integration tests/test_coffeemanga_integration.py``. Hits the real
coffeemanga.ink through Cloudflare, so it is skipped (not failed) when the site
is unreachable or its layout has drifted — a hard failure here would only mean
"the third-party site changed", which the offline contract test already guards
the parsing logic against.
"""

from __future__ import annotations

from urllib.parse import urlparse

import pytest

from connectors.coffeemanga.connector import CoffeeMangaConnector
from connectors.http.client import ConnectorHttpError

pytestmark = pytest.mark.integration


@pytest.fixture(scope="module")
def connector() -> CoffeeMangaConnector:
    return CoffeeMangaConnector()


def _skip_on_network(exc: Exception) -> None:
    pytest.skip(f"coffeemanga.ink unreachable/changed: {exc!r}")


def test_live_browse_returns_series(connector: CoffeeMangaConnector):
    try:
        listing = connector.get_series_list(1, sort="popular")
    except ConnectorHttpError as exc:
        _skip_on_network(exc)
    assert listing.items, "expected a non-empty popular listing"
    first = listing.items[0]
    assert first.id and first.title
    assert first.cover_url and first.cover_url.startswith("http")


def test_live_read_flow(connector: CoffeeMangaConnector):
    """Browse -> series metadata -> chapters -> first chapter's pages, live."""
    try:
        listing = connector.get_series_list(1, sort="popular")
    except ConnectorHttpError as exc:
        _skip_on_network(exc)
    if not listing.items:
        pytest.skip("no series returned from live browse")

    # Find a series that exposes chapters (scan a few to tolerate odd entries).
    for candidate in listing.items[:5]:
        try:
            series = connector.get_series(candidate.id)
            chapters = connector.get_chapters(candidate.id)
        except ConnectorHttpError as exc:
            _skip_on_network(exc)
            return
        if series and chapters:
            break
    else:
        pytest.skip("no browsable series with chapters found live")

    assert series is not None
    assert series.title
    # chapters ascending by number
    numbers = [c.number for c in chapters if c.number is not None]
    assert numbers == sorted(numbers)

    # Read the first chapter's pages and validate the image-host contract.
    try:
        pages = connector.get_chapter_pages(chapters[0].id)
    except ConnectorHttpError as exc:
        _skip_on_network(exc)
        return
    if not pages:
        pytest.skip(f"no pages returned for {chapters[0].id} (site layout may have drifted)")

    assert pages[0].number == 1
    for page in pages:
        assert page.remote_url, "page missing remote_url"
        # the leading-space quirk must be stripped for the proxy to accept it
        assert page.remote_url == page.remote_url.strip()
        parsed = urlparse(page.remote_url)
        assert parsed.scheme == "https"
        assert parsed.hostname in connector.allowed_image_hosts, (
            f"page host {parsed.hostname} not in allowlist {connector.allowed_image_hosts}"
        )
