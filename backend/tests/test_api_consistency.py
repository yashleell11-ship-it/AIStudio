"""Regression tests for cross-endpoint API consistency (additive metadata only)."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient
from sqlalchemy.orm import sessionmaker

from database.models import Chapter, ChapterText, Library, Series, UserSeriesState
from database.session import get_db
from main import create_app
from tests.test_mangadex_connector import FIXTURES, _load
from utils.api_pagination import (
    HEADER_LIST_TOTAL,
    HEADER_PROGRESS_FOUND,
    enrich_pagination_aliases,
)


def test_enrich_pagination_aliases_library_style() -> None:
    payload = enrich_pagination_aliases(
        {
            "items": [],
            "total": 100,
            "page": 2,
            "per_page": 40,
            "has_next": True,
        }
    )
    assert payload["page_size"] == 40
    assert payload["has_more"] is True
    assert payload["total_pages"] == 3
    assert payload["offset"] == 40
    assert payload["limit"] == 40


def test_enrich_pagination_aliases_source_style() -> None:
    payload = enrich_pagination_aliases(
        {
            "items": [],
            "total": 50,
            "page": 1,
            "page_size": 24,
            "total_pages": 3,
            "has_more": True,
        }
    )
    assert payload["per_page"] == 24
    assert payload["has_next"] is True


def test_enrich_pagination_aliases_ocr_offset_style() -> None:
    payload = enrich_pagination_aliases(
        {
            "items": [],
            "total": 45,
            "offset": 20,
            "limit": 20,
            "has_more": True,
        }
    )
    assert payload["page"] == 2
    assert payload["per_page"] == 20
    assert payload["page_size"] == 20
    assert payload["has_next"] is True
    assert payload["total_pages"] == 3


def _client(db_engine):
    session_factory = sessionmaker(bind=db_engine, autoflush=False, autocommit=False)

    def override_get_db():
        db = session_factory()
        try:
            yield db
        finally:
            db.close()

    app = create_app(run_migrations=False, run_workers=False)
    app.dependency_overrides[get_db] = override_get_db
    return TestClient(app)


def test_library_series_list_includes_pagination_aliases(db_engine) -> None:
    session_factory = sessionmaker(bind=db_engine, autoflush=False, autocommit=False)
    db = session_factory()
    try:
        lib = Library(name="Test", root_path="/tmp/test")
        db.add(lib)
        db.flush()
        for index in range(3):
            series = Series(
                library_id=lib.id,
                title=f"Series {index}",
                folder_path=f"/tmp/test/s{index}",
            )
            db.add(series)
            db.flush()
            # Library reads are scoped by (user_id, profile_id) + in_library;
            # the default test session is the unscoped (NULL, NULL) owner.
            db.add(
                UserSeriesState(
                    user_id=None,
                    profile_id=None,
                    series_id=series.id,
                    in_library=True,
                )
            )
        db.commit()
    finally:
        db.close()

    client = _client(db_engine)
    response = client.get("/library/series", params={"page": 1, "per_page": 2})
    assert response.status_code == 200
    payload = response.json()
    assert payload["per_page"] == 2
    assert payload["page_size"] == 2
    assert payload["has_next"] is True
    assert payload["has_more"] is True
    assert payload["total_pages"] == 2
    assert len(payload["items"]) == 2


def test_library_search_includes_pagination_aliases(db_engine) -> None:
    session_factory = sessionmaker(bind=db_engine, autoflush=False, autocommit=False)
    db = session_factory()
    try:
        lib = Library(name="Test", root_path="/tmp/test")
        db.add(lib)
        db.flush()
        series = Series(
            library_id=lib.id,
            title="Solo Leveling",
            folder_path="/tmp/test/solo",
        )
        db.add(series)
        db.flush()
        db.add(
            UserSeriesState(
                user_id=None, profile_id=None, series_id=series.id, in_library=True
            )
        )
        db.commit()
    finally:
        db.close()

    client = _client(db_engine)
    response = client.get("/library/search", params={"q": "Solo", "page": 1, "per_page": 10})
    assert response.status_code == 200
    payload = response.json()
    assert payload["page_size"] == 10
    assert payload["has_more"] is False
    assert payload["total_pages"] == 1


def test_source_series_list_includes_pagination_aliases() -> None:
    listing_payload = _load("manga_list.json")
    connector_path = "services.browse_service.create_connector"
    from connectors.mangadex.connector import MangaDexConnector

    connector = MangaDexConnector()
    app = create_app(run_workers=False)
    client = TestClient(app)
    try:
        with patch.object(connector._http, "get_json", return_value=listing_payload):
            with patch(connector_path, return_value=connector):
                response = client.get("/sources/mangadex/series")
    finally:
        connector._http.close()

    assert response.status_code == 200
    payload = response.json()
    assert payload["page_size"] == payload["per_page"]
    assert payload["has_more"] == payload["has_next"]
    assert "total_pages" in payload


def test_sources_list_has_total_header_and_source_id_alias() -> None:
    client = TestClient(create_app(run_workers=False))
    response = client.get("/sources")
    assert response.status_code == 200
    assert response.headers[HEADER_LIST_TOTAL] == str(len(response.json()))
    assert all("source_id" in item for item in response.json())
    assert all(item["source_id"] == item["id"] for item in response.json())


def test_bare_list_endpoints_expose_total_header(db_engine) -> None:
    client = _client(db_engine)
    endpoints = [
        "/downloads",
        "/updates/trackers",
        "/updates/notifications",
        "/updates/runs",
        "/ocr/jobs",
        "/library/collections",
        "/library/tags",
    ]
    for path in endpoints:
        response = client.get(path)
        assert response.status_code == 200, path
        assert HEADER_LIST_TOTAL in response.headers, path


def test_reader_progress_header_when_missing(db_engine) -> None:
    session_factory = sessionmaker(bind=db_engine, autoflush=False, autocommit=False)
    db = session_factory()
    try:
        lib = Library(name="Test", root_path="/tmp/test")
        db.add(lib)
        db.flush()
        series = Series(library_id=lib.id, title="Test", folder_path="/tmp/test/s")
        db.add(series)
        db.commit()
        series_id = series.id
    finally:
        db.close()

    client = _client(db_engine)
    response = client.get(f"/reader/progress/{series_id}")
    assert response.status_code == 200
    assert response.json() is None
    assert response.headers[HEADER_PROGRESS_FOUND] == "false"


def test_reader_progress_header_when_present(db_engine) -> None:
    session_factory = sessionmaker(bind=db_engine, autoflush=False, autocommit=False)
    db = session_factory()
    try:
        lib = Library(name="Test", root_path="/tmp/test")
        db.add(lib)
        db.flush()
        series = Series(library_id=lib.id, title="Test", folder_path="/tmp/test/s")
        db.add(series)
        db.flush()
        chapter = Chapter(
            series_id=series.id,
            title="Ch1",
            number=1,
            folder_path="/tmp/test/s/c1",
        )
        db.add(chapter)
        db.commit()
        series_id = series.id
        chapter_id = chapter.id
    finally:
        db.close()

    client = _client(db_engine)
    save = client.post(
        "/reader/progress",
        json={"series_id": series_id, "chapter_id": chapter_id, "last_page": 2},
    )
    assert save.status_code == 200

    response = client.get(f"/reader/progress/{series_id}")
    assert response.status_code == 200
    assert response.json() is not None
    assert response.headers[HEADER_PROGRESS_FOUND] == "true"


def test_ocr_search_includes_offset_and_page_aliases(db_engine) -> None:
    session_factory = sessionmaker(bind=db_engine, autoflush=False, autocommit=False)
    db = session_factory()
    try:
        lib = Library(name="Test", root_path="/tmp/test")
        db.add(lib)
        db.flush()
        series = Series(library_id=lib.id, title="Test Series", folder_path="/tmp/test/s")
        db.add(series)
        db.flush()
        chapter = Chapter(
            series_id=series.id,
            title="Ch1",
            number=1,
            folder_path="/tmp/test/s/c1",
        )
        db.add(chapter)
        db.flush()
        db.add(
            ChapterText(
                chapter_id=chapter.id,
                full_text="The quick brown fox jumps over the lazy dog.",
                word_count=9,
            )
        )
        db.commit()
    finally:
        db.close()

    client = _client(db_engine)
    response = client.get("/ocr/search", params={"q": "fox", "limit": 10, "offset": 0})
    assert response.status_code == 200
    payload = response.json()
    assert payload["page"] == 1
    assert payload["per_page"] == 10
    assert payload["page_size"] == 10
    assert payload["has_next"] is False
    assert payload["has_more"] is False


def test_error_envelope_shape() -> None:
    client = TestClient(create_app(run_workers=False))
    response = client.get("/sources/unknown-source/series")
    assert response.status_code == 404
    body = response.json()
    assert set(body.keys()) >= {"code", "message"}
    assert body["code"] == "source_not_found"


def test_import_library_series_list_preserves_desktop_fields(
    db_engine, tmp_path: Path
) -> None:
    library_root = tmp_path / "Library"
    series_dir = library_root / "Solo Leveling"
    chapter_dir = series_dir / "Chapter 001"
    chapter_dir.mkdir(parents=True)
    (chapter_dir / "001.jpg").write_bytes(b"fake-image")

    client = _client(db_engine)
    import_response = client.post(
        "/library/import",
        json={"folder_path": str(library_root.resolve())},
    )
    assert import_response.status_code == 200

    list_response = client.get("/library/series")
    assert list_response.status_code == 200
    payload = list_response.json()
    assert "per_page" in payload
    assert "has_next" in payload
    assert payload["items"][0]["title"] == "Solo Leveling"
