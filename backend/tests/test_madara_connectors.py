"""Contract tests for Madara-factory connectors (shared HTML fixtures)."""

from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
from unittest.mock import patch

import pytest

from connectors.base import SourceConnector
from connectors.madara.sites import MADARA_SITES
from connectors.registry import create_connector
from tests.connector_validation import ConnectorContractCase, validate_connector_contract

ROOT = Path(__file__).parent / "fixtures" / "coffeemanga"

# CoffeeManga uses the same Madara /manga/ markup as most factory sites.
_MADARA_MANGA_FIXTURE = ConnectorContractCase(
    source_type="coffeemanga",  # placeholder; overridden per param
    fixtures_dir=ROOT,
    search_query="abandoned",
    series_id="the-abandoned-princes-ghost-bride",
    reader_chapter_id="the-abandoned-princes-ghost-bride/chapter-1",
    expected_title_substring="Abandoned Prince",
    expected_image_host_substring="coffeemanga.ink",
    expected_latest_first_id="the-abandoned-princes-ghost-bride",
    expected_popular_first_id="solo-leveling-cf01",
    expected_page2_first_id="tower-of-god-cf02",
    expected_search_ids=("the-abandoned-princes-ghost-bride",),
    decimal_chapter_ids=("the-abandoned-princes-ghost-bride/chapter-10-5",),
    ordering_probe_ids=(
        "the-abandoned-princes-ghost-bride/chapter-10",
        "the-abandoned-princes-ghost-bride/chapter-10-5",
        "the-abandoned-princes-ghost-bride/chapter-11",
    ),
    adjacent_pairs=(
        (
            "the-abandoned-princes-ghost-bride/chapter-10",
            "the-abandoned-princes-ghost-bride/chapter-10-5",
        ),
        (
            "the-abandoned-princes-ghost-bride/chapter-10-5",
            "the-abandoned-princes-ghost-bride/chapter-11",
        ),
    ),
    mock=None,
)


@contextmanager
def _mock_coffeemanga_html(connector: SourceConnector):
    """Patch HTTP with CoffeeManga fixtures (Madara /manga/ theme)."""
    host = connector.CONFIG.site_host  # type: ignore[attr-defined]

    def _html(name: str) -> str:
        return (ROOT / name).read_text(encoding="utf-8").replace("coffeemanga.ink", host)

    browse_latest = _html("browse_latest.html")
    browse_popular = _html("browse_popular.html")
    browse_page2 = _html("browse_page2.html")
    search = _html("search.html")
    series_detail = _html("series_detail.html")
    chapter_reader = _html("chapter_reader.html")

    series_id = "the-abandoned-princes-ghost-bride"
    chapter_id = f"{series_id}/chapter-1"
    seg = getattr(getattr(connector, "CONFIG", None), "url_segment", "manga")

    def fake_get_text(path: str, *, params=None):
        if path == "/":
            return search
        if path == f"/{seg}/{series_id}/":
            return series_detail
        if path == f"/{seg}/{chapter_id}/":
            return chapter_reader
        if path.startswith(f"/{seg}/page/2"):
            return browse_page2
        if path.startswith(f"/{seg}"):
            if params and params.get("m_orderby") == "views":
                return browse_popular
            return browse_latest
        return browse_latest

    with patch.object(connector._http, "get_text", side_effect=fake_get_text):
        yield


# Sample every Nth site so the suite stays fast; full list is registered at runtime.
_MADARA_SAMPLE_IDS = [
    cfg.source_id
    for cfg in MADARA_SITES
    if cfg.url_segment == "manga" and not cfg.mature
][::8]  # ~15 connectors


@pytest.mark.parametrize("source_id", _MADARA_SAMPLE_IDS)
def test_madara_factory_connector_contract(source_id: str) -> None:
    connector = create_connector(source_id)
    case = ConnectorContractCase(
        source_type=source_id,
        fixtures_dir=ROOT,
        search_query=_MADARA_MANGA_FIXTURE.search_query,
        series_id=_MADARA_MANGA_FIXTURE.series_id,
        reader_chapter_id=_MADARA_MANGA_FIXTURE.reader_chapter_id,
        expected_title_substring=_MADARA_MANGA_FIXTURE.expected_title_substring,
        expected_image_host_substring=connector.CONFIG.site_host,  # type: ignore[attr-defined]
        expected_latest_first_id=_MADARA_MANGA_FIXTURE.expected_latest_first_id,
        expected_popular_first_id=_MADARA_MANGA_FIXTURE.expected_popular_first_id,
        expected_page2_first_id=_MADARA_MANGA_FIXTURE.expected_page2_first_id,
        expected_search_ids=_MADARA_MANGA_FIXTURE.expected_search_ids,
        decimal_chapter_ids=_MADARA_MANGA_FIXTURE.decimal_chapter_ids,
        ordering_probe_ids=_MADARA_MANGA_FIXTURE.ordering_probe_ids,
        adjacent_pairs=_MADARA_MANGA_FIXTURE.adjacent_pairs,
        mock=_mock_coffeemanga_html,
    )
    validate_connector_contract(case)


def test_madara_sites_registered() -> None:
    from connectors.registry import list_connector_types

    registered = set(list_connector_types())
    for cfg in MADARA_SITES:
        assert cfg.source_id in registered, f"{cfg.source_id} missing from registry"


MANHUAPLUS_ROOT = Path(__file__).parent / "fixtures" / "madara" / "manhuaplus"
MANHUAPLUS_SERIES = "demon-magic-emperor01"
MANHUAPLUS_CHAPTER = f"{MANHUAPLUS_SERIES}/chapter-880"


@contextmanager
def _mock_manhuaplus_live(connector: SourceConnector):
    """Live-captured ManhuaPlus fixtures (2026-07-11)."""

    def _read(name: str) -> str:
        return (MANHUAPLUS_ROOT / name).read_text(encoding="utf-8")

    browse_latest = _read("browse_latest.html")
    browse_page2 = _read("browse_page2.html")
    search = _read("search.html")
    series_detail = _read("series_detail.html")
    chapter_reader = _read("chapter_reader.html")

    def fake_get_text(path: str, *, params=None):
        if path == "/":
            return search
        if path == f"/manga/{MANHUAPLUS_SERIES}/":
            return series_detail
        if path == f"/manga/{MANHUAPLUS_CHAPTER}/":
            return chapter_reader
        if path.startswith("/manga/page/2"):
            return browse_page2
        if path.startswith("/manga"):
            return browse_latest
        return browse_latest

    with patch.object(connector._http, "get_text", side_effect=fake_get_text):
        yield


def test_manhuaplus_live_fixture_contract() -> None:
    """Regression test using HTML captured from the live site (browse/read path)."""
    connector = create_connector("manhuaplus")
    with _mock_manhuaplus_live(connector):
        listing = connector.get_series_list(1)
        assert listing.items
        assert any(s.id == MANHUAPLUS_SERIES for s in listing.items)

        series = connector.get_series(MANHUAPLUS_SERIES)
        assert series is not None
        assert "Magic Emperor" in series.title

        chapters = connector.get_chapters(MANHUAPLUS_SERIES)
        assert chapters
        assert any(c.id == MANHUAPLUS_CHAPTER for c in chapters)

        pages = connector.get_chapter_pages(MANHUAPLUS_CHAPTER)
        assert pages
        assert pages[0].remote_url
        assert "manhuaplus.com" in (pages[0].remote_url or "")

        found = connector.find_page(pages[0].id)
        assert found == pages[0]
