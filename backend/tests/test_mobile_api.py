"""Regression tests for mobile-readiness API additions (additive only)."""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session, sessionmaker

from database.models import Chapter, Library, Page, Series
from database.session import get_db
from main import create_app
from utils.api_pagination import HEADER_LIST_TOTAL, HEADER_PROGRESS_FOUND


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


def _seed_series_with_chapter(db: Session, suffix: str = "") -> tuple[int, int]:
    root = f"/tmp/mobile{suffix}"
    library = Library(name=f"Mobile Library{suffix}", root_path=root)
    db.add(library)
    db.flush()
    series = Series(
        library_id=library.id,
        title="Mobile Series",
        folder_path=f"{root}/series",
    )
    db.add(series)
    db.flush()
    chapter = Chapter(
        series_id=series.id,
        title="Chapter 1",
        number=1,
        folder_path=f"{root}/series/ch1",
        page_count=2,
    )
    db.add(chapter)
    db.flush()
    db.add(Page(chapter_id=chapter.id, number=1, file_path=f"{root}/series/ch1/001.jpg"))
    db.add(Page(chapter_id=chapter.id, number=2, file_path=f"{root}/series/ch1/002.jpg"))
    db.commit()
    return series.id, chapter.id


def test_health_endpoint(db_engine) -> None:
    client = _client(db_engine)
    response = client.get("/health")
    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "online"
    assert payload["version"]


def test_unified_settings_endpoint(db_engine) -> None:
    client = _client(db_engine)
    response = client.get("/settings")
    assert response.status_code == 200
    payload = response.json()
    assert "downloads" in payload
    assert "updates" in payload
    assert "ocr" in payload
    assert payload["capabilities"]["continue_reading"] is True


def test_unified_settings_update_downloads(db_engine) -> None:
    client = _client(db_engine)
    response = client.put(
        "/settings",
        json={"download_concurrent_chapters": 2},
    )
    assert response.status_code == 200
    assert response.json()["downloads"]["download_concurrent_chapters"] == 2


def test_list_libraries(db_engine) -> None:
    session_factory = sessionmaker(bind=db_engine, autoflush=False, autocommit=False)
    db = session_factory()
    try:
        db.add(Library(name="Main", root_path="/tmp/main"))
        db.commit()
    finally:
        db.close()

    client = _client(db_engine)
    response = client.get("/library/libraries")
    assert response.status_code == 200
    assert response.headers[HEADER_LIST_TOTAL] == "1"
    payload = response.json()
    assert payload[0]["name"] == "Main"
    assert payload[0]["series_count"] == 0


def test_series_list_includes_cover_url(db_engine, tmp_path: Path) -> None:
    library_root = tmp_path / "Library"
    series_dir = library_root / "Cover Test"
    chapter_dir = series_dir / "Chapter 001"
    chapter_dir.mkdir(parents=True)
    (chapter_dir / "001.jpg").write_bytes(b"fake")

    client = _client(db_engine)
    import_response = client.post(
        "/library/import",
        json={"folder_path": str(library_root.resolve())},
    )
    assert import_response.status_code == 200

    list_response = client.get("/library/series")
    assert list_response.status_code == 200
    item = list_response.json()["items"][0]
    assert item["cover_url"] == f"/library/covers/{item['id']}"


def test_chapter_pages_include_image_url(db_engine, tmp_path: Path) -> None:
    library_root = tmp_path / "Library"
    series_dir = library_root / "Image URL Test"
    chapter_dir = series_dir / "Chapter 001"
    chapter_dir.mkdir(parents=True)
    (chapter_dir / "001.jpg").write_bytes(b"fake")

    client = _client(db_engine)
    client.post("/library/import", json={"folder_path": str(library_root.resolve())})
    series_id = client.get("/library/series").json()["items"][0]["id"]
    chapter_id = client.get(f"/library/series/{series_id}").json()["chapters"][0]["id"]

    chapter = client.get(f"/reader/chapter/{chapter_id}").json()
    assert chapter["pages"][0]["image_url"] == f"/reader/page/{chapter['pages'][0]['id']}/image"


def test_continue_reading_includes_cover_url_and_scroll_offset(db_engine) -> None:
    session_factory = sessionmaker(bind=db_engine, autoflush=False, autocommit=False)
    db = session_factory()
    try:
        series_id, chapter_id = _seed_series_with_chapter(db)
    finally:
        db.close()

    client = _client(db_engine)
    save = client.post(
        "/reader/progress",
        json={
            "series_id": series_id,
            "chapter_id": chapter_id,
            "last_page": 1,
            "scroll_offset_px": 480,
        },
    )
    assert save.status_code == 200
    assert save.json()["scroll_offset_px"] == 480

    response = client.get("/library/continue-reading")
    assert response.status_code == 200
    item = response.json()[0]
    assert item["cover_url"] == f"/library/covers/{series_id}"
    assert item["scroll_offset_px"] == 480


def test_delete_reading_progress(db_engine) -> None:
    session_factory = sessionmaker(bind=db_engine, autoflush=False, autocommit=False)
    db = session_factory()
    try:
        series_id, chapter_id = _seed_series_with_chapter(db)
    finally:
        db.close()

    client = _client(db_engine)
    client.post(
        "/reader/progress",
        json={"series_id": series_id, "chapter_id": chapter_id, "last_page": 1},
    )

    delete = client.delete(f"/reader/progress/{series_id}")
    assert delete.status_code == 204

    progress = client.get(f"/reader/progress/{series_id}")
    assert progress.status_code == 200
    assert progress.json() is None
    assert progress.headers[HEADER_PROGRESS_FOUND] == "false"


def test_delete_bookmark(db_engine) -> None:
    session_factory = sessionmaker(bind=db_engine, autoflush=False, autocommit=False)
    db = session_factory()
    try:
        series_id, chapter_id = _seed_series_with_chapter(db)
    finally:
        db.close()

    client = _client(db_engine)
    create = client.post(
        "/reader/bookmarks",
        json={"series_id": series_id, "chapter_id": chapter_id, "page": 1},
    )
    assert create.status_code == 200
    bookmark_id = create.json()["id"]

    delete = client.delete(f"/reader/bookmarks/{bookmark_id}")
    assert delete.status_code == 204

    bookmarks = client.get(f"/reader/bookmarks/{series_id}").json()
    assert bookmarks == []


def test_list_all_bookmarks_includes_series_and_chapter_titles(db_engine) -> None:
    session_factory = sessionmaker(bind=db_engine, autoflush=False, autocommit=False)
    db = session_factory()
    try:
        series_id, chapter_id = _seed_series_with_chapter(db)
    finally:
        db.close()

    client = _client(db_engine)
    client.post(
        "/reader/bookmarks",
        json={"series_id": series_id, "chapter_id": chapter_id, "page": 2, "note": "cliffhanger"},
    )

    response = client.get("/reader/bookmarks")
    assert response.status_code == 200
    assert response.headers[HEADER_LIST_TOTAL] == "1"

    bookmark = response.json()[0]
    assert bookmark["series_id"] == series_id
    assert bookmark["series_title"] == "Mobile Series"
    assert bookmark["chapter_id"] == chapter_id
    assert bookmark["chapter_title"] == "Chapter 1"
    assert bookmark["page"] == 2
    assert bookmark["note"] == "cliffhanger"


def test_list_all_bookmarks_spans_multiple_series(db_engine) -> None:
    session_factory = sessionmaker(bind=db_engine, autoflush=False, autocommit=False)
    db = session_factory()
    try:
        series_a, chapter_a = _seed_series_with_chapter(db, suffix="-a")
        series_b, chapter_b = _seed_series_with_chapter(db, suffix="-b")
    finally:
        db.close()

    client = _client(db_engine)
    client.post("/reader/bookmarks", json={"series_id": series_a, "chapter_id": chapter_a, "page": 1})
    client.post("/reader/bookmarks", json={"series_id": series_b, "chapter_id": chapter_b, "page": 1})

    response = client.get("/reader/bookmarks")
    assert response.status_code == 200
    series_ids = {item["series_id"] for item in response.json()}
    assert series_ids == {series_a, series_b}

    # Per-series listing still only returns that series' bookmark -- the new
    # global endpoint is additive, not a replacement.
    only_a = client.get(f"/reader/bookmarks/{series_a}").json()
    assert len(only_a) == 1
    assert only_a[0]["series_id"] == series_a


def test_delete_bookmark_not_found(db_engine) -> None:
    client = _client(db_engine)
    response = client.delete("/reader/bookmarks/99999")
    assert response.status_code == 404
    assert response.json()["code"] == "bookmark_not_found"
