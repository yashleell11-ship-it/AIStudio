from __future__ import annotations

from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import sessionmaker

from connectors.mangakatana.connector import MangaKatanaConnector
from database.session import get_db
from main import create_app
from tests.test_mangakatana_connector import _load


@pytest.fixture
def client(db_engine):
    session_factory = sessionmaker(bind=db_engine, autoflush=False, autocommit=False)

    def override_get_db():
        db = session_factory()
        try:
            yield db
        finally:
            db.close()

    app = create_app(run_migrations=False, run_workers=False)
    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as test_client:
        yield test_client


def _mangakatana_http_side_effect(series_id: str):
    detail_html = _load("series_detail.html")
    chapter_html = _load("chapter_reader.html")
    search_html = _load("search_solo.html")
    browse_html = _load("browse_page1.html")

    def fake_get_text(path: str, *, params=None):
        if path == "/":
            return search_html
        if path == f"/manga/{series_id}":
            return detail_html
        if path == f"/manga/{series_id}/c1":
            return chapter_html
        if path.startswith("/manga/page/"):
            return browse_html
        raise AssertionError(f"unexpected path: {path}")

    return fake_get_text


def test_search_open_series_open_chapter_reader_loads_pages(client: TestClient):
    """Search -> series -> chapter reader must work with slash-containing chapter IDs."""
    series_id = "aishiteru-uso-dakedo.10797"
    chapter_id = f"{series_id}/c1"
    connector = MangaKatanaConnector()

    with patch.object(
        connector._http,
        "get_text",
        side_effect=_mangakatana_http_side_effect(series_id),
    ):
        with patch("services.browse_service.create_connector", return_value=connector):
            search = client.get(
                "/sources/mangakatana/series",
                params={"query": "solo leveling"},
            )
            assert search.status_code == 200
            assert search.json()["items"]

            series = client.get(f"/sources/mangakatana/series/{series_id}")
            assert series.status_code == 200
            assert series.json()["id"] == series_id

            chapters = client.get(f"/sources/mangakatana/series/{series_id}/chapters")
            assert chapters.status_code == 200
            chapter_payload = chapters.json()
            assert len(chapter_payload) >= 1
            assert all(item["id"].startswith(f"{series_id}/") for item in chapter_payload)
            assert chapter_payload[0]["id"] == chapter_id

            reader = client.get(
                f"/sources/mangakatana/series/{series_id}/chapters/{chapter_id}/reader",
            )

    assert reader.status_code == 200
    payload = reader.json()
    assert payload["mode"] == "remote"
    assert payload["id"] == chapter_id
    assert payload["page_count"] >= 2
    assert len(payload["pages"]) >= 2
    assert payload["pages"][0]["image_url"].startswith("/sources/mangakatana/pages/")


def test_chapters_api_reports_cached_page_count_after_reader_fetch(client: TestClient):
    series_id = "aishiteru-uso-dakedo.10797"
    chapter_id = f"{series_id}/c1"
    connector = MangaKatanaConnector()

    with patch.object(
        connector._http,
        "get_text",
        side_effect=_mangakatana_http_side_effect(series_id),
    ):
        with patch("services.browse_service.create_connector", return_value=connector):
            chapters_before = client.get(f"/sources/mangakatana/series/{series_id}/chapters")
            assert chapters_before.status_code == 200
            before_by_id = {item["id"]: item for item in chapters_before.json()}
            assert before_by_id[chapter_id]["page_count"] == 0

            reader = client.get(
                f"/sources/mangakatana/series/{series_id}/chapters/{chapter_id}/reader",
            )
            assert reader.status_code == 200
            expected_count = reader.json()["page_count"]

            chapters_after = client.get(f"/sources/mangakatana/series/{series_id}/chapters")
            assert chapters_after.status_code == 200
            after_by_id = {item["id"]: item for item in chapters_after.json()}

    assert expected_count >= 2
    assert after_by_id[chapter_id]["page_count"] == expected_count


def test_reader_returns_chapter_not_found_for_unknown_chapter_not_route_404(client: TestClient):
    """Slash-containing chapter IDs must reach chapter lookup, not fail route matching."""
    series_id = "lookism.693"
    chapter_id = f"{series_id}/c1"
    connector = MangaKatanaConnector()
    detail_html = _load("series_detail.html")

    def fake_get_text(path: str, *, params=None):
        if path == f"/manga/{series_id}":
            return detail_html
        raise AssertionError(f"unexpected path: {path}")

    with patch.object(connector._http, "get_text", side_effect=fake_get_text):
        with patch("services.browse_service.create_connector", return_value=connector):
            response = client.get(
                f"/sources/mangakatana/series/{series_id}/chapters/{chapter_id}/reader",
            )

    assert response.status_code == 404
    assert response.json()["code"] == "chapter_not_found"


def test_chapter_pages_endpoint_accepts_slash_id(client: TestClient):
    series_id = "aishiteru-uso-dakedo.10797"
    chapter_id = f"{series_id}/c1"
    connector = MangaKatanaConnector()

    with patch.object(
        connector._http,
        "get_text",
        side_effect=_mangakatana_http_side_effect(series_id),
    ):
        with patch("services.browse_service.create_connector", return_value=connector):
            response = client.get(
                f"/sources/mangakatana/chapters/{chapter_id}/pages",
            )

    assert response.status_code == 200
    pages = response.json()
    assert len(pages) >= 2
    assert pages[0]["chapter_id"] == chapter_id
