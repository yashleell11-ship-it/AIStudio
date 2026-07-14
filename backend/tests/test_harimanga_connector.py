"""Offline unit tests for the HariManga connector."""

from __future__ import annotations

from unittest.mock import patch

from connectors.harimanga.connector import HariMangaConnector, parse_json_chapters

SERIES_ID = "kaijin-kaihatsubu-no-kuroitsu-san"
CHAPTER_ID = f"{SERIES_ID}/chapter-17"

DETAIL_HTML = f"""
<html><body class="postid-91664">
<script>
window.getChaptersUrl = 'https://www.harimanga.vip/api/comics/{SERIES_ID}/chapters';
</script>
<div class="listing-chapters_wrap"><div class="chapters-loading">Loading chapters...</div></div>
</body></html>
"""

CHAPTERS_JSON = {
    "success": True,
    "data": {
        "chapters": [
            {
                "chapter_slug": "chapter-16",
                "chapter_num": 16,
                "chapter_name": "Chapter 16",
            },
            {
                "chapter_slug": "chapter-17",
                "chapter_num": 17,
                "chapter_name": "Chapter 17",
            },
        ]
    },
}

READER_HTML = """
<html><body>
<img class='wp-manga-chapter-img' src='https://img-r2.2xstorage.com/kaijin/17/0.webp'
     data-src='https://img-r2.2xstorage.com/kaijin/17/0.webp'>
<img class='wp-manga-chapter-img' src='https://img-r2.2xstorage.com/kaijin/17/1.webp'
     data-src='https://img-r2.2xstorage.com/kaijin/17/1.webp'>
</body></html>
"""

BROWSE_HTML = """
<div class="page-item-detail manga">
  <div class="item-thumb">
    <a href=https://www.harimanga.vip/manga/kaijin-kaihatsubu-no-kuroitsu-san title="Read Kaijin Kaihatsubu no Kuroitsu-san">
      <img src="https://img-r2.2xstorage.com/thumb/kaijin-kaihatsubu-no-kuroitsu-san.webp">
    </a>
  </div>
</div>
"""


def test_parse_json_chapters():
    chapters = parse_json_chapters(CHAPTERS_JSON, SERIES_ID)
    assert len(chapters) == 2
    assert chapters[0].id == f"{SERIES_ID}/chapter-16"
    assert chapters[1].number == 17.0


def test_connector_chapters_and_pages_flow():
    connector = HariMangaConnector()

    def fake_get_text(path: str, *, params=None):
        if path == f"/manga/{SERIES_ID}/":
            return DETAIL_HTML
        if path == f"/manga/{SERIES_ID}/chapter-17/":
            return READER_HTML
        if path == "/manga/":
            return BROWSE_HTML
        return ""

    def fake_get_json(path: str, *, params=None):
        if path == f"/api/comics/{SERIES_ID}/chapters":
            return CHAPTERS_JSON
        raise AssertionError(f"unexpected json path {path}")

    with (
        patch.object(connector._http, "get_text", side_effect=fake_get_text),
        patch.object(connector._http, "get_json", side_effect=fake_get_json),
        patch.object(
            connector._image_http,
            "get_bytes",
            return_value=("image/webp", b"cover"),
        ),
    ):
        listing = connector.get_series_list(1)
        assert len(listing.items) == 1
        assert listing.items[0].id == SERIES_ID

        chapters = connector.get_chapters(SERIES_ID)
        assert len(chapters) == 2
        assert chapters[-1].id == CHAPTER_ID

        pages = connector.get_chapter_pages(CHAPTER_ID)
        assert len(pages) == 2
        assert pages[0].remote_url.startswith("https://img-r2.2xstorage.com/")

        proxied = connector.fetch_proxied_image(
            "https://img-r2.2xstorage.com/thumb/kaijin-kaihatsubu-no-kuroitsu-san.webp"
        )
        assert proxied == ("image/webp", b"cover")


def test_connector_metadata():
    connector = HariMangaConnector()
    assert connector.source_type == "harimanga"
    assert connector.display_name == "HariManga"
    assert "img-r2.2xstorage.com" in connector.allowed_image_hosts
    assert connector.image_fetch_headers()["Referer"] == "https://www.harimanga.vip/"
