"""Live integration checks against the MangaDex API.

Run with: pytest tests/test_mangadex_integration.py -q
"""

from __future__ import annotations

import pytest

from connectors.mangadex.connector import MangaDexConnector

pytestmark = pytest.mark.integration


@pytest.fixture(scope="module")
def mangadex() -> MangaDexConnector:
    return MangaDexConnector()


def test_live_browse(mangadex: MangaDexConnector):
    listing = mangadex.get_series_list(1)
    assert listing.total > 0
    assert len(listing.items) > 0
    assert listing.items[0].title


def test_live_search(mangadex: MangaDexConnector):
    listing = mangadex.search_series("Solo Leveling", 1)
    assert listing.total > 0
    assert any("solo" in item.title.casefold() for item in listing.items)


def test_live_read_flow(mangadex: MangaDexConnector):
    listing = mangadex.search_series("Solo Leveling", 1)
    assert listing.items
    series = mangadex.get_series(listing.items[0].id)
    assert series is not None
    chapters = mangadex.get_chapters(series.id)
    assert chapters
    readable = next((chapter for chapter in chapters if chapter.page_count > 0), chapters[0])
    pages = mangadex.get_chapter_pages(readable.id)
    assert pages
    assert pages[0].remote_url is not None
    found = mangadex.find_page(pages[0].id)
    assert found is not None
    assert found.remote_url == pages[0].remote_url

    media_type, content = mangadex._http.get_bytes(pages[0].remote_url)
    assert media_type.startswith("image/")
    assert len(content) > 0
