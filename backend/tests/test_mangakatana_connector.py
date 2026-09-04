from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from connectors.mangakatana.connector import MangaKatanaConnector
from connectors.mangakatana.mappers import parse_chapter_pages, parse_chapters, parse_series_list
from connectors.registry import create_connector, list_installed_connectors

FIXTURES = Path(__file__).parent / "fixtures" / "mangakatana"


def _load(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


@pytest.fixture
def mangakatana_connector() -> MangaKatanaConnector:
    return MangaKatanaConnector()


def test_registry_lists_mangakatana():
    browsable = [item.source_type for item in list_installed_connectors(browsable_only=True)]
    assert "mangakatana" in browsable


def test_parse_series_list_from_fixture():
    html = _load("browse_page1.html")
    listing = parse_series_list(html, page=1)
    assert len(listing.items) >= 10
    assert listing.has_more is True
    assert listing.items[0].id
    assert listing.items[0].cover_url


def test_browse_page_2_differs_from_page_1(mangakatana_connector: MangaKatanaConnector):
    page1 = _load("browse_page1.html")
    page2 = _load("browse_page2.html")

    def fake_get_text(path: str, *, params=None):
        if path.endswith("/page/2"):
            return page2
        return page1

    with patch.object(mangakatana_connector._http, "get_text", side_effect=fake_get_text):
        first = mangakatana_connector.get_series_list(1)
        second = mangakatana_connector.get_series_list(2)

    assert first.items[0].id != second.items[0].id
    assert first.has_more is True


def test_browse_uses_page_path_and_filter(mangakatana_connector: MangaKatanaConnector):
    html = _load("browse_page1.html")
    captured: list[tuple[str, dict | None]] = []

    def fake_get_text(path: str, *, params=None):
        captured.append((path, params))
        return html

    with patch.object(mangakatana_connector._http, "get_text", side_effect=fake_get_text):
        mangakatana_connector.get_series_list(1)
        mangakatana_connector.get_series_list(2, sort="popular")

    assert captured[0][0] == "/manga/page/1"
    assert captured[0][1] == {"filter": 1, "order": "latest"}
    assert captured[1][0] == "/manga/page/2"
    assert captured[1][1] == {"filter": 1, "order": "numc"}


def test_each_browse_mode_requests_a_distinct_order_value(
    mangakatana_connector: MangaKatanaConnector,
):
    """Regression test for the sort bug: MangaKatana silently ignores `order`
    unless `filter=1` is also present, so every mode fell back to the same
    default listing. Each of the four exposed modes must now request a
    genuinely distinct `order` value, always alongside `filter=1`."""
    html = _load("browse_page1.html")
    captured: list[dict | None] = []

    def fake_get_text(path: str, *, params=None):
        captured.append(params)
        return html

    with patch.object(mangakatana_connector._http, "get_text", side_effect=fake_get_text):
        mangakatana_connector.get_series_list(1, sort="default")
        mangakatana_connector.get_series_list(1, sort="latest")
        mangakatana_connector.get_series_list(1, sort="popular")
        mangakatana_connector.get_series_list(1, sort="rating")

    assert all(params is not None and params.get("filter") == 1 for params in captured)
    order_values = [params["order"] for params in captured]
    assert order_values == ["latest", "new", "numc", "az"]
    # All four must be distinct -- this is the exact condition that was
    # broken (every mode used to collapse onto the same request).
    assert len(set(order_values)) == 4


def test_browse_modes_parse_into_different_series_lists():
    """End-to-end regression test using real captured HTML: two distinct
    `order` values must yield different first-page series lists, not just
    different request params. This is what actually caught the original bug
    -- the old code sent different `filter` values that the site silently
    ignored, so every mode parsed to the same series list."""
    latest_html = _load("browse_order_latest.html")
    numc_html = _load("browse_order_numc.html")

    latest_listing = parse_series_list(latest_html, page=1)
    numc_listing = parse_series_list(numc_html, page=1)

    latest_ids = [item.id for item in latest_listing.items]
    numc_ids = [item.id for item in numc_listing.items]

    assert latest_ids
    assert numc_ids
    assert latest_ids[0] != numc_ids[0]
    assert set(latest_ids[:5]).isdisjoint(set(numc_ids[:5]))


def test_search_finds_titles_not_on_browse_page_1(mangakatana_connector: MangaKatanaConnector):
    browse_html = _load("browse_page1.html")
    search_html = _load("search_solo.html")

    def fake_get_text(path: str, *, params=None):
        if path == "/":
            return search_html
        return browse_html

    with patch.object(mangakatana_connector._http, "get_text", side_effect=fake_get_text):
        browse = mangakatana_connector.get_series_list(1)
        search = mangakatana_connector.search_series("solo leveling", 1)

    browse_ids = {item.id for item in browse.items}
    assert search.items
    assert any("solo" in item.title.casefold() for item in search.items)
    assert any(item.id not in browse_ids for item in search.items)

def test_parse_chapter_pages_extracts_script_urls():
    html = _load("chapter_reader.html")
    pages = parse_chapter_pages(html, "aishiteru-uso-dakedo.10797/c1")
    assert len(pages) >= 2
    assert all(page.remote_url and "mangakatana.com" in page.remote_url for page in pages)


def test_chapter_pages_ask_for_the_fast_image_server():
    """MangaKatana's three image hosts are interchangeable but not equally fast.

    Measured from the production container across four chapters, each probed
    in a different server order so a warm origin could not be mistaken for a
    fast host, three sampled pages cost 10.9-19.3s on the default server and
    0.3-1.3s on server 3. The reader page must therefore be requested with the
    `sv=3` switch, not bare.
    """
    connector = MangaKatanaConnector()
    captured: list[tuple[str, dict | None]] = []
    html = _load("chapter_reader_sv3.html")

    def fake_get_text(path: str, *, params=None):
        captured.append((path, params))
        return html

    with patch.object(connector._http, "get_text", side_effect=fake_get_text):
        pages = connector.get_chapter_pages("aishiteru-uso-dakedo.10797/c1")

    assert captured == [("/manga/aishiteru-uso-dakedo.10797/c1", {"sv": "3"})]
    assert pages
    assert all("i6.mangakatana.com" in page.remote_url for page in pages)


def test_fast_server_serves_the_identical_page_set():
    """Recorded from the same chapter on both servers: switching hosts must
    change only which box the bytes come from."""
    default_pages = parse_chapter_pages(_load("chapter_reader.html"), "x/c1")
    fast_pages = parse_chapter_pages(_load("chapter_reader_sv3.html"), "x/c1")

    assert len(fast_pages) == len(default_pages) > 0
    assert [page.remote_url.rsplit("/", 1)[-1] for page in fast_pages] == [
        page.remote_url.rsplit("/", 1)[-1] for page in default_pages
    ]
    assert all("i1.mangakatana.com" in page.remote_url for page in default_pages)
    assert all("i6.mangakatana.com" in page.remote_url for page in fast_pages)


def test_chapter_missing_from_the_fast_server_falls_back_to_the_default():
    """A chapter server 3 has not mirrored must stay readable, not merely slow."""
    connector = MangaKatanaConnector()
    captured: list[dict | None] = []

    def fake_get_text(path: str, *, params=None):
        captured.append(params)
        if params:
            return "<html><body>no reader script here</body></html>"
        return _load("chapter_reader.html")

    with patch.object(connector._http, "get_text", side_effect=fake_get_text):
        pages = connector.get_chapter_pages("aishiteru-uso-dakedo.10797/c1")

    assert captured == [{"sv": "3"}, None]
    assert pages
    assert all("i1.mangakatana.com" in page.remote_url for page in pages)


def test_parse_chapters_filters_by_series():
    html = _load("series_detail.html")
    chapters = parse_chapters(html, "aishiteru-uso-dakedo.10797")
    assert len(chapters) == 2
    assert chapters[0].series_id == "aishiteru-uso-dakedo.10797"


def test_create_mangakatana_connector():
    connector = create_connector("mangakatana")
    assert connector.source_type == "mangakatana"


def test_list_browse_modes(mangakatana_connector: MangaKatanaConnector):
    modes = mangakatana_connector.list_browse_modes()
    mode_ids = {mode.id for mode in modes}
    assert "popular" in mode_ids
    assert "latest" in mode_ids


# --- Image proxy media type -------------------------------------------------


def test_page_images_are_relabelled_from_octet_stream(
    mangakatana_connector: MangaKatanaConnector,
):
    """Regression: the token CDN serves JPEGs as application/octet-stream.

    The image proxy clamps unrecognised types to application/octet-stream and
    sends X-Content-Type-Options: nosniff, so a mislabelled page reaches the
    browser as bytes it is explicitly told not to render. Every page of every
    chapter was affected while browse/detail/chapters/pages all passed.
    """
    jpeg = b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01" + b"\x00" * 64

    with patch.object(
        mangakatana_connector._http,
        "get_bytes",
        return_value=("application/octet-stream", jpeg),
    ):
        media_type, body = mangakatana_connector.fetch_proxied_image(
            "https://i1.mangakatana.com/token/abc/0.jpg"
        )

    assert media_type == "image/jpeg"
    assert body == jpeg


def test_declared_image_type_is_not_overridden(
    mangakatana_connector: MangaKatanaConnector,
):
    """A correct upstream label must win over the sniffer."""
    png = b"\x89PNG\r\n\x1a\n" + b"\x00" * 32

    with patch.object(
        mangakatana_connector._http, "get_bytes", return_value=("image/png", png)
    ):
        media_type, _ = mangakatana_connector.fetch_proxied_image(
            "https://mangakatana.com/imgs/cover/x.png"
        )

    assert media_type == "image/png"


def test_non_image_bytes_are_not_promoted_to_an_image_type(
    mangakatana_connector: MangaKatanaConnector,
):
    """Sniffing must not launder an error page into an image/* label."""
    with patch.object(
        mangakatana_connector._http,
        "get_bytes",
        return_value=("application/octet-stream", b"<!DOCTYPE html><html>403"),
    ):
        media_type, _ = mangakatana_connector.fetch_proxied_image(
            "https://i1.mangakatana.com/token/abc/0.jpg"
        )

    assert media_type == "application/octet-stream"
    assert not media_type.startswith("image/")
