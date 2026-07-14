"""Offline unit tests for the ComicsValley connector."""

from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
from unittest.mock import patch

from connectors.comicsvalley import mappers
from connectors.comicsvalley.connector import ComicsValleyConnector

FIXTURES = Path(__file__).parent / "fixtures" / "comicsvalley"
SERIES_ID = "the-recruit-blacknwhitecomics"
CHAPTER_ID = f"{SERIES_ID}/the-recruit-1"
READER_SERIES_URL = f"https://allporncomics.co/comic/{SERIES_ID}/"


def _fixture(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


@contextmanager
def _mock_http(connector: ComicsValleyConnector):
    browse_latest = _fixture("browse_latest.html")
    search_html = _fixture("search.html")
    series_detail = _fixture("series_detail.html")
    ajax_chapters = _fixture("ajax_chapters.html")
    chapter_reader = _fixture("chapter_reader.html")

    def fake_get_text(path: str, *, params=None):
        if path == "/":
            return search_html
        if path == f"/manga/{SERIES_ID}/":
            return series_detail
        if path.startswith("https://allporncomics.co/comic/") and path.rstrip("/").endswith(
            "the-recruit-1"
        ):
            return chapter_reader
        if path.startswith("/manga"):
            return browse_latest
        return browse_latest

    def fake_post_text(path: str, *, data=None, extra_headers=None):
        if "ajax/chapters" in path:
            return ajax_chapters
        return ""

    with (
        patch.object(connector._http, "get_text", side_effect=fake_get_text),
        patch.object(connector._http, "post_text", side_effect=fake_post_text),
        patch.object(connector._http, "get_bytes", return_value=("image/jpeg", b"cover")),
    ):
        yield


def test_parse_browse_cards():
    listing = mappers.parse_series_list(_fixture("browse_latest.html"), page=1)
    assert len(listing.items) == 2
    assert listing.items[0].id == SERIES_ID
    assert listing.items[0].title == "The Recruit [BlackNWhiteComics]"
    assert listing.items[0].cover_url.startswith("https://comicsvalley.net/")
    assert listing.has_more is True


def test_parse_search_cards():
    listing = mappers.parse_search_results(
        _fixture("search.html"), page=1, query="recruit"
    )
    assert any(item.id == SERIES_ID for item in listing.items)
    assert all("/" not in item.id for item in listing.items)


def test_parse_series_detail_and_read_online():
    html = _fixture("series_detail.html")
    series = mappers.parse_series_detail(html, SERIES_ID)
    assert series is not None
    assert "The Recruit" in series.title
    assert series.author == "BlackNWhiteComics"
    assert series.artist == "Yair"
    assert series.status == "Completed"
    assert series.genres == ("Western",)
    assert mappers.parse_read_online_url(html, SERIES_ID) == READER_SERIES_URL


def test_parse_ajax_chapters_and_pages():
    chapters = mappers.parse_chapters(_fixture("ajax_chapters.html"), SERIES_ID)
    assert len(chapters) == 1
    assert chapters[0].id == CHAPTER_ID
    assert chapters[0].number == 1.0

    pages = mappers.parse_chapter_pages(_fixture("chapter_reader.html"), CHAPTER_ID)
    assert len(pages) == 3
    assert pages[0].remote_url.startswith("https://allporncomics.co/")
    assert not pages[0].remote_url.startswith(" ")
    assert "data:image" not in pages[2].remote_url


def test_connector_browse_search_read_flow():
    connector = ComicsValleyConnector()
    with _mock_http(connector):
        latest = connector.get_series_list(1, sort="default")
        assert latest.items and latest.items[0].id == SERIES_ID

        search = connector.search_series("recruit", 1)
        assert any(s.id == SERIES_ID for s in search.items)

        series = connector.get_series(SERIES_ID)
        assert series is not None
        assert series.chapter_count == 1
        assert series.latest_chapter

        chapters = connector.get_chapters(SERIES_ID)
        assert len(chapters) == 1
        assert chapters[0].id == CHAPTER_ID
        assert chapters[0].page_count == 3

        pages = connector.get_chapter_pages(CHAPTER_ID)
        assert len(pages) == 3
        assert connector.find_page(pages[0].id) == pages[0]


def test_connector_metadata():
    connector = ComicsValleyConnector()
    assert connector.source_type == "comicsvalley"
    assert connector.display_name == "ComicsValley"
    assert connector.is_mature is True
    assert connector.is_browsable is True
    assert "comicsvalley.net" in connector.allowed_image_hosts
    assert "allporncomics.co" in connector.allowed_image_hosts


def test_fetch_proxied_image_uses_host_referer():
    connector = ComicsValleyConnector()
    cover_url = "https://comicsvalley.net/wp-content/uploads/cover.jpg"
    with patch.object(
        connector._http,
        "get_bytes",
        return_value=("image/jpeg", b"cover"),
    ) as get_bytes:
        result = connector.fetch_proxied_image(cover_url)
    assert result == ("image/jpeg", b"cover")
    get_bytes.assert_called_once_with(
        cover_url,
        extra_headers={"Referer": "https://comicsvalley.net/"},
    )
