from __future__ import annotations

from unittest.mock import patch

from fastapi.testclient import TestClient

from connectors.asurascans.connector import AsuraScansConnector
from connectors.mangadex.connector import MangaDexConnector
from connectors.mangakatana.connector import MangaKatanaConnector
from main import create_app
from tests.test_asurascans_connector import _load as _load_asura
from tests.test_mangadex_connector import FIXTURES, _load
from tests.test_mangakatana_connector import _load as _load_mk

app = create_app(run_workers=False)
client = TestClient(app)


def test_list_sources():
    response = client.get("/sources")
    assert response.status_code == 200
    payload = response.json()
    assert len(payload) >= 3
    source_ids = {item["id"] for item in payload}
    assert source_ids >= {"asurascans", "mangadex", "mangakatana"}
    assert all(item["browsable"] is True for item in payload)
    assert all("icon_url" in item for item in payload)


def test_list_mangadex_series():
    listing_payload = _load("manga_list.json")
    connector = MangaDexConnector()
    try:
        with patch.object(connector._http, "get_json", return_value=listing_payload):
            with patch("services.browse_service.create_connector", return_value=connector):
                response = client.get("/sources/mangadex/series")
    finally:
        connector._http.close()

    assert response.status_code == 200
    payload = response.json()
    assert payload["total"] == 2
    assert payload["items"][0]["title"] == "Solo Leveling"


def test_search_mangadex_series():
    listing_payload = _load("manga_search.json")
    connector = MangaDexConnector()
    try:
        with patch.object(connector._http, "get_json", return_value=listing_payload):
            with patch("services.browse_service.create_connector", return_value=connector):
                response = client.get("/sources/mangadex/series", params={"query": "Solo"})
    finally:
        connector._http.close()

    assert response.status_code == 200
    payload = response.json()
    assert payload["total"] == 1
    assert payload["items"][0]["title"] == "Solo Leveling"


def test_get_mangadex_reader_chapter():
    feed_payload = _load("chapter_feed.json")
    at_home_payload = _load("at_home.json")
    manga_payload = {
        "result": "ok",
        "data": {
            "id": "32dce569-8fcc-46b6-853c-f956e16ee0bc",
            "type": "manga",
            "attributes": {
                "title": { "en": "Solo Leveling" },
                "status": "completed",
            },
            "relationships": [],
        },
        "included": [],
    }
    chapter_id = "00000000-0000-0000-0000-000000000001"
    series_id = "32dce569-8fcc-46b6-853c-f956e16ee0bc"

    def fake_get_json(path: str, *, params=None):
        if path == f"/manga/{series_id}":
            return manga_payload
        if path.endswith("/feed"):
            return feed_payload
        if path.startswith("/at-home/server/"):
            return at_home_payload
        raise AssertionError(path)

    connector = MangaDexConnector()
    try:
        with patch.object(connector._http, "get_json", side_effect=fake_get_json):
            with patch("services.browse_service.create_connector", return_value=connector):
                response = client.get(
                    f"/sources/mangadex/series/{series_id}/chapters/{chapter_id}/reader"
                )
    finally:
        connector._http.close()

    assert response.status_code == 200
    payload = response.json()
    assert payload["mode"] == "remote"
    assert payload["page_count"] == 2
    assert payload["pages"][0]["image_url"].startswith("/sources/mangadex/pages/")


def test_list_asurascans_series():
    listing_payload = _load_asura("series_list.json")
    connector = AsuraScansConnector()
    try:
        with patch.object(connector._http, "get_json", return_value=listing_payload):
            with patch("services.browse_service.create_connector", return_value=connector):
                response = client.get("/sources/asurascans/series")
    finally:
        connector._http.close()

    assert response.status_code == 200
    payload = response.json()
    assert payload["total"] == 333
    assert payload["total_pages"] == 17
    assert payload["has_more"] is True
    assert payload["items"][0]["title"] == "Return of the Mount Hua Sect"


def test_list_asurascans_browse_modes():
    response = client.get("/sources/asurascans/browse-modes")
    assert response.status_code == 200
    modes = response.json()
    assert any(mode["id"] == "popular" for mode in modes)
    assert any(mode["id"] == "updated" for mode in modes)


def test_list_asurascans_series_with_sort():
    listing_payload = _load_asura("series_list.json")
    connector = AsuraScansConnector()
    try:
        with patch.object(connector._http, "get_json", return_value=listing_payload) as mock_get:
            with patch("services.browse_service.create_connector", return_value=connector):
                response = client.get("/sources/asurascans/series", params={"sort": "popular"})
    finally:
        connector._http.close()

    assert response.status_code == 200
    assert mock_get.call_args.kwargs["params"]["sort"] == "popular"


def test_list_asurascans_series_page_2():
    full = _load_asura("series_list.json")
    page2_item = dict(full["data"][0])
    page2_item.update(
        {
            "id": 9999,
            "slug": "second-page-series",
            "title": "Second Page Series",
            "public_url": "/comics/second-page-series-abc123",
        }
    )
    page2_payload = {
        "data": [page2_item],
        "meta": {"total": 333, "per_page": 20, "has_more": True},
    }
    connector = AsuraScansConnector()
    try:
        with patch.object(connector._http, "get_json", return_value=page2_payload):
            with patch("services.browse_service.create_connector", return_value=connector):
                response = client.get("/sources/asurascans/series", params={"page": 2})
    finally:
        connector._http.close()

    assert response.status_code == 200
    payload = response.json()
    assert payload["page"] == 2
    assert len(payload["items"]) == 1
    assert payload["items"][0]["title"] == "Second Page Series"
    assert payload["has_more"] is True


def test_search_asurascans_series():
    listing_payload = _load_asura("series_search.json")
    connector = AsuraScansConnector()
    try:
        with patch.object(connector._http, "get_json", return_value=listing_payload):
            with patch("services.browse_service.create_connector", return_value=connector):
                response = client.get("/sources/asurascans/series", params={"query": "solo"})
    finally:
        connector._http.close()

    assert response.status_code == 200
    payload = response.json()
    assert payload["total"] >= 1


def test_get_asurascans_reader_chapter():
    detail_payload = _load_asura("series_detail.json")
    chapter_payload = _load_asura("chapter_list.json")
    pages_payload = _load_asura("chapter_pages_mount.json")
    series_id = "return-of-the-mount-hua-sect-30e93729"
    chapter_id = f"{series_id}:168"

    def fake_get_json(path: str, *, params=None):
        if path == f"/api/series/{series_id}":
            return detail_payload
        if path == f"/api/series/{series_id}/chapters":
            return chapter_payload
        if path == f"/api/series/{series_id}/chapters/168":
            return pages_payload
        raise AssertionError(path)

    connector = AsuraScansConnector()
    try:
        with patch.object(connector._http, "get_json", side_effect=fake_get_json):
            with patch("services.browse_service.create_connector", return_value=connector):
                response = client.get(
                    f"/sources/asurascans/series/{series_id}/chapters/{chapter_id}/reader"
                )
    finally:
        connector._http.close()

    assert response.status_code == 200
    payload = response.json()
    assert payload["mode"] == "remote"
    assert payload["page_count"] == 2
    assert payload["pages"][0]["image_url"].startswith("/sources/asurascans/pages/")


def test_list_mangakatana_browse_modes():
    response = client.get("/sources/mangakatana/browse-modes")
    assert response.status_code == 200
    modes = response.json()
    assert any(mode["id"] == "popular" for mode in modes)


def test_list_mangakatana_series():
    connector = MangaKatanaConnector()
    try:
        with patch.object(connector._http, "get_text", return_value=_load_mk("browse_page1.html")):
            with patch("services.browse_service.create_connector", return_value=connector):
                response = client.get("/sources/mangakatana/series", params={"page": 1, "sort": "popular"})
    finally:
        connector._http.close()

    assert response.status_code == 200
    payload = response.json()
    assert len(payload["items"]) >= 10
    assert payload["has_more"] is True
    assert payload["total_pages"] >= 2


def test_search_mangakatana_series():
    connector = MangaKatanaConnector()
    browse_html = _load_mk("browse_page1.html")
    search_html = _load_mk("search_solo.html")

    def fake_get_text(path: str, *, params=None):
        if path == "/":
            return search_html
        return browse_html

    try:
        with patch.object(connector._http, "get_text", side_effect=fake_get_text):
            with patch("services.browse_service.create_connector", return_value=connector):
                response = client.get("/sources/mangakatana/series", params={"query": "solo leveling"})
    finally:
        connector._http.close()

    assert response.status_code == 200
    payload = response.json()
    assert any("solo" in item["title"].casefold() for item in payload["items"])


# --- opaque keys with slashes reach every route the same way ---------------
#
# Connector keys are opaque strings that contain slashes and percent-encoding.
# The ASGI server percent-decodes before routing, so a ``%2F`` arrives at the
# router as a real ``/``: a plain segment converter simply 404s. These four
# routes used to disagree — three segment, one ``:path`` — so the same key
# worked on the cover and 404'd on the other three.


class _SlashKeyBrowse:
    """Records the key each route handed the service."""

    def __init__(self):
        self.seen: dict[str, str] = {}

    def _gate_open(self) -> bool:
        return False

    def get_series(self, source_id, series_id):
        self.seen["series"] = series_id
        return {"id": series_id, "title": "T"}

    def get_chapters(self, source_id, series_id):
        self.seen["chapters"] = series_id
        return []

    def resolve_series_cover(self, source_id, series_id):
        self.seen["cover"] = series_id
        return "image/png", b"x"

    def get_chapter_pages(self, source_id, chapter_id):
        self.seen["pages"] = chapter_id
        return []

    def resolve_page_image(self, source_id, page_id):
        self.seen["image"] = page_id
        return "image/png", b"x"


class _SlashKeyReader:
    def __init__(self):
        self.seen: tuple[str, str] | None = None

    def resolve_source_chapter(self, source_id, series_id, chapter_id):
        self.seen = (series_id, chapter_id)
        return {"pages": []}


def test_slash_bearing_keys_route_consistently():
    from fastapi.testclient import TestClient

    from main import create_app
    from services.browse_service import get_browse_service
    from services.reader_service import get_reader_service

    browse = _SlashKeyBrowse()
    reader = _SlashKeyReader()
    slash_app = create_app(run_workers=False)
    slash_app.dependency_overrides[get_browse_service] = lambda: browse
    slash_app.dependency_overrides[get_reader_service] = lambda: reader
    slash_client = TestClient(slash_app)

    key = "group/solo-leveling"
    enc = "group%2Fsolo-leveling"
    chapter = "vol/1/ch/2"
    chapter_enc = "vol%2F1%2Fch%2F2"

    assert slash_client.get(f"/sources/mangadex/series/{enc}").status_code == 200
    assert browse.seen["series"] == key

    assert (
        slash_client.get(f"/sources/mangadex/series/{enc}/chapters").status_code == 200
    )
    assert browse.seen["chapters"] == key

    assert slash_client.get(f"/sources/mangadex/series/{enc}/cover").status_code == 200
    assert browse.seen["cover"] == key

    assert (
        slash_client.get(
            f"/sources/mangadex/series/{enc}/chapters/{chapter_enc}/reader"
        ).status_code
        == 200
    )
    assert reader.seen == (key, chapter)

    # The two non-series key routes were already ``:path``; pin them so a future
    # tidy-up cannot quietly narrow them back.
    assert (
        slash_client.get(f"/sources/mangadex/chapters/{chapter_enc}/pages").status_code
        == 200
    )
    assert browse.seen["pages"] == chapter
    assert (
        slash_client.get(f"/sources/mangadex/pages/{chapter_enc}/image").status_code
        == 200
    )
    assert browse.seen["image"] == chapter
