"""Offline unit tests for the Hentai20 connector."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from connectors.hentai20.connector import Hentai20Connector, _cover_from_detail_html

FIXTURES = Path(__file__).parent / "fixtures" / "elftoon"
SERIES_ID = "hypnotized-sex-with-my-brother"


def _fixture(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


def test_connector_metadata():
    connector = Hentai20Connector()
    assert connector.source_type == "hentai20"
    assert connector.display_name == "Hentai20"
    assert connector.is_mature is True
    assert "hentai1.io" in connector.allowed_image_hosts


def test_connector_browse_with_elftoon_fixture():
    connector = Hentai20Connector()
    browse_html = _fixture("browse_update.html")

    with patch.object(connector._http, "get_text", return_value=browse_html):
        listing = connector.get_series_list(1)

    assert listing.items
    assert listing.items[0].id


def test_cover_from_detail_html_uses_thumb_when_og_image_missing():
    detail_html = (
        '<div class="main-info"><div class="info-left">'
        '<div class="thumb"><img src="https://hentai20.io/wp-content/uploads/cover.jpg" '
        'alt="Cover"></div></div></div>'
    )
    assert _cover_from_detail_html(detail_html) == (
        "https://hentai20.io/wp-content/uploads/cover.jpg"
    )


def test_get_series_falls_back_to_thumb_cover():
    connector = Hentai20Connector()
    detail_html = _fixture("series_detail.html")
    chapter_html = _fixture("chapter_reader.html")

    with (
        patch.object(connector._http, "get_text", side_effect=[detail_html, detail_html]),
        patch.object(connector._chapter_list_cache, "get", return_value=None),
        patch.object(connector._series_cache, "get", return_value=None),
    ):
        series = connector.get_series(SERIES_ID)

    assert series is not None
    assert series.cover_url
    assert "wp-content/uploads" in series.cover_url or "hentai20.io" in series.cover_url


def test_fetch_proxied_image_uses_site_referer():
    connector = Hentai20Connector()
    cover_url = "https://hentai20.io/wp-content/uploads/cover.jpg"
    with patch.object(
        connector._image_http,
        "get_bytes",
        return_value=("image/jpeg", b"cover"),
    ) as get_bytes:
        result = connector.fetch_proxied_image(cover_url)
    assert result == ("image/jpeg", b"cover")
    get_bytes.assert_called_once_with(
        cover_url,
        extra_headers={"Referer": "https://hentai20.io/"},
    )


def test_search_paginates_by_path_like_elftoon():
    """Hentai20 is the same WordPress build; ``?page=N`` is ignored there too.

    Measured from the VPS: ``/?s=love&page=2`` repeated page 1's ids, while
    ``/page/2/?s=love`` returned a different set.
    """
    connector = Hentai20Connector()
    page1 = _fixture("search_demon_page1.html")
    page2 = _fixture("search_demon_page2.html")
    captured: list[tuple[str, dict | None]] = []

    def fake_get_text(path: str, *, params=None):
        captured.append((path, params))
        return page2 if path == "/page/2/" else page1

    with patch.object(connector._http, "get_text", side_effect=fake_get_text):
        first = connector.search_series("love", 1)
        second = connector.search_series("love", 2)

    assert captured == [
        ("/", {"s": "love", "post_type": "wp-manga"}),
        ("/page/2/", {"s": "love", "post_type": "wp-manga"}),
    ]
    assert not {item.id for item in first.items} & {item.id for item in second.items}
