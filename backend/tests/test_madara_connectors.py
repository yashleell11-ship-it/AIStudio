"""Contract tests for Madara-factory connectors (shared HTML fixtures)."""

from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from connectors.base import SourceConnector
from connectors.excluded import EXCLUDED_CONNECTORS
from connectors.http.client import ConnectorHttpError
from connectors.madara.mappers import MadaraHtml
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
# Excluded sources are not registered (create_connector would raise), so skip them.
_MADARA_SAMPLE_IDS = [
    cfg.source_id
    for cfg in MADARA_SITES
    if cfg.url_segment == "manga"
    and not cfg.mature
    and cfg.source_id not in EXCLUDED_CONNECTORS
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
    from connectors.excluded import EXCLUDED_CONNECTORS
    from connectors.registry import list_connector_types

    registered = set(list_connector_types())
    for cfg in MADARA_SITES:
        if cfg.source_id in EXCLUDED_CONNECTORS:
            continue
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


# ---------------------------------------------------------------------------
# AJAX chapter fallback tests
# ---------------------------------------------------------------------------

AJAX_SERIES_ID = "test-series-ajax"
AJAX_CHAPTER_FRAGMENT = """
<ul class="main version-chap">
    <li class="wp-manga-chapter  ">
        <a href="https://example-madara.com/manga/test-series-ajax/chapter-3/">
            Chapter 3
        </a>
    </li>
    <li class="wp-manga-chapter  ">
        <a href="https://example-madara.com/manga/test-series-ajax/chapter-2/">
            Chapter 2
        </a>
    </li>
    <li class="wp-manga-chapter  ">
        <a href="https://example-madara.com/manga/test-series-ajax/chapter-1/">
            Chapter 1
        </a>
    </li>
</ul>
"""

SERIES_HTML_WITH_MANGA_ID = f"""
<html>
<body>
<div class="post-title"><h1>Test Series</h1></div>
<div class="tab-summary">
    <div class="tab-thumb c-image-hover">
        <div class="summary_image">
            <a class="a-h" href="/manga/{AJAX_SERIES_ID}/" data-id="99999">
            </a>
        </div>
    </div>
</div>
<div class="listing-chapters_wrap">
    <!-- No chapter list items – they come from AJAX -->
</div>
</body>
</html>
"""

SERIES_HTML_WITHOUT_MANGA_ID = f"""
<html>
<body>
<div class="post-title"><h1>Test Series</h1></div>
<div class="listing-chapters_wrap">
    <li class="wp-manga-chapter  ">
        <a href="https://example-madara.com/manga/{AJAX_SERIES_ID}/chapter-1/">Chapter 1</a>
    </li>
</div>
</body>
</html>
"""


def test_madara_parse_manga_id_from_data_attribute():
    """parse_manga_id extracts the post ID from a data-id attribute."""
    from connectors.madara.config import MadaraSiteConfig

    cfg = MadaraSiteConfig(
        source_id="test",
        display_name="Test",
        base_url="https://example-madara.com",
        url_segment="manga",
    )
    parser = MadaraHtml(cfg)
    assert parser.parse_manga_id(SERIES_HTML_WITH_MANGA_ID) == "99999"


def test_madara_parse_manga_id_returns_none_when_absent():
    """parse_manga_id returns None when no data-id is in the HTML."""
    from connectors.madara.config import MadaraSiteConfig

    cfg = MadaraSiteConfig(
        source_id="test",
        display_name="Test",
        base_url="https://example-madara.com",
        url_segment="manga",
    )
    parser = MadaraHtml(cfg)
    assert parser.parse_manga_id("<html><body>No manga id here</body></html>") is None


def _fresh_madara_connector():
    """Create a fresh MadaraConnector instance for manhwaclub (bypasses the singleton cache)."""
    from connectors.madara.factory import madara_connector_classes
    from connectors.madara.sites import MADARA_SITES

    cfg = next(c for c in MADARA_SITES if c.source_id == "manhwaclub")
    cls = next(c for c in madara_connector_classes((cfg,)))
    return cls()


def test_madara_ajax_chapter_fallback():
    """Connector falls back to AJAX when HTML has no chapter links."""
    connector = _fresh_madara_connector()

    def fake_get_text(path, *, params=None):
        return SERIES_HTML_WITH_MANGA_ID

    def fake_post_text(path, *, data=None, extra_headers=None):
        assert data == {"action": "manga_get_chapters", "manga": "99999"}
        return AJAX_CHAPTER_FRAGMENT

    with (
        patch.object(connector._http, "get_text", side_effect=fake_get_text),
        patch.object(connector._http, "post_text", side_effect=fake_post_text),
    ):
        chapters = connector.get_chapters(AJAX_SERIES_ID)

    assert len(chapters) == 3
    assert chapters[0].id == f"{AJAX_SERIES_ID}/chapter-1"
    assert chapters[-1].id == f"{AJAX_SERIES_ID}/chapter-3"


def test_madara_ajax_fallback_skipped_when_html_has_chapters():
    """Connector does NOT call AJAX when HTML chapters are already present."""
    connector = _fresh_madara_connector()

    post_called = []

    def fake_get_text(path, *, params=None):
        return SERIES_HTML_WITHOUT_MANGA_ID

    def fake_post_text(path, *, data=None, extra_headers=None):
        post_called.append(path)
        return ""

    with (
        patch.object(connector._http, "get_text", side_effect=fake_get_text),
        patch.object(connector._http, "post_text", side_effect=fake_post_text),
    ):
        chapters = connector.get_chapters(AJAX_SERIES_ID)

    assert len(chapters) == 1
    assert not post_called, "post_text should not be called when HTML has chapters"


def test_madara_ajax_fallback_skipped_when_no_manga_id():
    """Connector does NOT call AJAX when the HTML has no data-id."""
    connector = _fresh_madara_connector()

    post_called = []

    def fake_get_text(path, *, params=None):
        return "<html><body><div class='post-title'><h1>X</h1></div></body></html>"

    def fake_post_text(path, *, data=None, extra_headers=None):
        post_called.append(path)
        return ""

    with (
        patch.object(connector._http, "get_text", side_effect=fake_get_text),
        patch.object(connector._http, "post_text", side_effect=fake_post_text),
    ):
        connector.get_chapters(AJAX_SERIES_ID)

    assert not post_called, "post_text should not be called when no manga_id"


def test_madara_ajax_fallback_on_http_error_returns_empty():
    """Connector returns empty list gracefully when AJAX endpoint fails."""
    connector = _fresh_madara_connector()

    def fake_get_text(path, *, params=None):
        return SERIES_HTML_WITH_MANGA_ID

    def fake_post_text(path, *, data=None, extra_headers=None):
        raise ConnectorHttpError("400 Bad Request", status_code=400)

    with (
        patch.object(connector._http, "get_text", side_effect=fake_get_text),
        patch.object(connector._http, "post_text", side_effect=fake_post_text),
    ):
        chapters = connector.get_chapters(AJAX_SERIES_ID)

    assert chapters == []


def test_madara_image_proxy_sends_referer():
    """MadaraConnector.image_fetch_headers returns the site Referer for CDN hotlink protection."""
    connector = create_connector("manhwaclub")
    headers = connector.image_fetch_headers()
    assert headers.get("Referer") == "https://manhwaclub.net/"

def test_madara_upgrades_http_image_urls_to_https():
    """Madara page/cover URLs that arrive as http:// are upgraded to https://."""
    from connectors.madara.config import MadaraSiteConfig
    from connectors.madara.mappers import MadaraHtml

    cfg = MadaraSiteConfig(
        source_id="manhwaclub",
        display_name="ManhwaClub",
        base_url="https://manhwaclub.net",
        url_segment="manga",
    )
    parser = MadaraHtml(cfg)
    assert parser._upgrade_https("http://cdn.example/a.jpg") == "https://cdn.example/a.jpg"
    assert parser._upgrade_https("https://cdn.example/a.jpg") == "https://cdn.example/a.jpg"

    html = """
    <div class="reading-content">
      <img src="http://manhwaclub.net/wp-content/uploads/page1.jpg" />
    </div>
    """
    pages = parser.parse_chapter_pages(html, "series/chapter-1")
    assert pages
    assert pages[0].remote_url.startswith("https://")

