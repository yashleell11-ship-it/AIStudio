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
    # Many officially-licensed MangaDex series host their pages externally, so
    # they list chapters with zero readable pages. Browse popular titles and
    # scan for a chapter that is actually hosted on MangaDex, then exercise the
    # whole read path on it (chapters -> pages -> page image bytes).
    listing = mangadex.get_series_list(1, sort="popular")
    assert listing.items

    readable = None
    pages: list = []
    for item in listing.items[:15]:
        chapters = mangadex.get_chapters(item.id)
        candidate = next((c for c in chapters if c.page_count and c.page_count > 0), None)
        if candidate is None:
            continue
        candidate_pages = mangadex.get_chapter_pages(candidate.id)
        if candidate_pages:
            readable, pages = candidate, candidate_pages
            break

    assert readable is not None, "no popular series exposed a MangaDex-hosted chapter"
    assert pages
    assert pages[0].remote_url is not None

    found = mangadex.find_page(pages[0].id)
    assert found is not None
    assert found.remote_url == pages[0].remote_url

    media_type, content = mangadex._http.get_bytes(pages[0].remote_url)
    assert media_type.startswith("image/")
    assert len(content) > 0
