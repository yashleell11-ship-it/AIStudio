from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session, sessionmaker

from database.models import Chapter, Library, Page, PageText, Series
from database.session import get_db
from main import create_app


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


def _build_solo_leveling_series(series_dir: Path) -> None:
    for episode in ["Episode 0", "Episode 1", "Episode 2", "Episode 3"]:
        chapter_dir = series_dir / episode
        chapter_dir.mkdir(parents=True, exist_ok=True)
        (chapter_dir / "001.jpg").write_bytes(b"fake-image")
        (chapter_dir / "002.jpg").write_bytes(b"fake-image-2")

def test_health(client: TestClient):
    response = client.get("/")
    assert response.status_code == 200
    assert response.json()["status"] == "online"


def test_import_and_list_series(client: TestClient, tmp_path: Path):
    library_root = tmp_path / "Library"
    series_dir = library_root / "Solo Leveling"
    chapter_dir = series_dir / "Chapter 001"
    chapter_dir.mkdir(parents=True)
    (chapter_dir / "001.jpg").write_bytes(b"fake-image")
    (chapter_dir / "002.jpg").write_bytes(b"fake-image-2")

    import_response = client.post(
        "/library/import",
        json={"folder_path": str(library_root.resolve())},
    )
    assert import_response.status_code == 200
    payload = import_response.json()
    assert payload["series_count"] == 1
    assert payload["chapter_count"] == 1
    assert payload["page_count"] == 2

    list_response = client.get("/library/series")
    assert list_response.status_code == 200
    items = list_response.json()["items"]
    assert len(items) == 1
    assert items[0]["title"] == "Solo Leveling"
    assert items[0]["chapter_count"] == 1
    assert items[0]["page_count"] == 2

    series_id = items[0]["id"]
    chapter_id = items[0]["first_chapter_id"]
    assert chapter_id is not None

    chapter_response = client.get(f"/reader/chapter/{chapter_id}")
    assert chapter_response.status_code == 200
    chapter = chapter_response.json()
    assert len(chapter["pages"]) == 2

    progress_response = client.post(
        "/reader/progress",
        json={
            "series_id": series_id,
            "chapter_id": chapter_id,
            "last_page": 2,
        },
    )
    assert progress_response.status_code == 200
    assert progress_response.json()["last_page"] == 2

    continue_response = client.get("/library/continue-reading")
    assert continue_response.status_code == 200
    assert len(continue_response.json()) == 1


def test_import_single_series_with_episodes(client: TestClient, tmp_path: Path):
    series_dir = tmp_path / "Solo Leveling"
    _build_solo_leveling_series(series_dir)

    import_response = client.post(
        "/library/import",
        json={"folder_path": str(series_dir.resolve())},
    )
    assert import_response.status_code == 200
    payload = import_response.json()
    assert payload["series_count"] == 1
    assert payload["chapter_count"] == 4
    assert payload["page_count"] == 8

    list_response = client.get("/library/series")
    items = list_response.json()["items"]
    assert len(items) == 1
    assert items[0]["title"] == "Solo Leveling"
    assert items[0]["chapter_count"] == 4

    series_id = items[0]["id"]
    detail_response = client.get(f"/library/series/{series_id}")
    assert detail_response.status_code == 200
    chapters = detail_response.json()["chapters"]
    assert [chapter["title"] for chapter in chapters] == [
        "Episode 0",
        "Episode 1",
        "Episode 2",
        "Episode 3",
    ]


def test_import_merges_orphan_series_and_preserves_progress(
    client: TestClient,
    db_session: Session,
    tmp_path: Path,
):
    series_dir = tmp_path / "Solo Leveling"
    _build_solo_leveling_series(series_dir)
    _seed_all_orphan_episodes(db_session, series_dir)

    import_response = client.post(
        "/library/import",
        json={"folder_path": str(series_dir.resolve())},
    )
    assert import_response.status_code == 200
    assert import_response.json()["removed_orphans"] >= 4

    list_response = client.get("/library/series")
    items = list_response.json()["items"]
    assert len(items) == 1
    assert items[0]["title"] == "Solo Leveling"
    assert items[0]["chapter_count"] == 4

    detail = client.get(f"/library/series/{items[0]['id']}").json()
    assert [chapter["title"] for chapter in detail["chapters"]] == [
        "Episode 0",
        "Episode 1",
        "Episode 2",
        "Episode 3",
    ]


def _seed_all_orphan_episodes(db: Session, series_dir: Path) -> None:
    library = Library(
        name=series_dir.name,
        root_path=str(series_dir.resolve()),
    )
    db.add(library)
    db.flush()

    parent = Series(
        library_id=library.id,
        title="Solo Leveling",
        folder_path=str(series_dir.resolve()),
    )
    db.add(parent)
    db.flush()

    for episode in ["Episode 0", "Episode 1", "Episode 2", "Episode 3"]:
        episode_path = series_dir / episode
        orphan = Series(
            library_id=library.id,
            title=episode,
            folder_path=str(episode_path.resolve()),
        )
        db.add(orphan)
        db.flush()
        chapter = Chapter(
            series_id=orphan.id,
            title="Chapter 1",
            number=1,
            folder_path=str(episode_path.resolve()),
            page_count=1,
        )
        db.add(chapter)
        db.flush()
        db.add(
            Page(
                chapter_id=chapter.id,
                number=1,
                file_path=str(episode_path / "001.jpg"),
            )
        )

    db.commit()


def test_reimport_same_folder_does_not_duplicate(
    client: TestClient,
    tmp_path: Path,
):
    series_dir = tmp_path / "Solo Leveling"
    _build_solo_leveling_series(series_dir)
    folder = str(series_dir.resolve())

    first = client.post("/library/import", json={"folder_path": folder})
    assert first.status_code == 200

    progress = client.post(
        "/reader/progress",
        json={
            "series_id": client.get("/library/series").json()["items"][0]["id"],
            "chapter_id": client.get("/library/series").json()["items"][0]["first_chapter_id"],
            "last_page": 1,
        },
    )
    assert progress.status_code == 200

    second = client.post("/library/import", json={"folder_path": folder})
    assert second.status_code == 200

    items = client.get("/library/series").json()["items"]
    assert len(items) == 1
    assert items[0]["chapter_count"] == 4

    series_id = items[0]["id"]
    saved = client.get(f"/reader/progress/{series_id}").json()
    assert saved is not None
    assert saved["last_page"] == 1

    third = client.post("/library/import", json={"folder_path": folder})
    assert third.status_code == 200
    assert len(client.get("/library/series").json()["items"]) == 1


def test_list_series_returns_mobile_summary_fields(client: TestClient, tmp_path: Path):
    """GET /library/series must expose fields mobile clients need (not stripped by response_model)."""
    series_dir = tmp_path / "Solo Leveling"
    _build_solo_leveling_series(series_dir)
    import_response = client.post(
        "/library/import",
        json={"folder_path": str(series_dir.resolve())},
    )
    assert import_response.status_code == 200

    series_id = client.get("/library/series").json()["items"][0]["id"]
    favorite_response = client.post(f"/library/series/{series_id}/favorite")
    assert favorite_response.status_code == 200

    item = client.get("/library/series").json()["items"][0]
    assert item["is_favorite"] is True
    assert item["sort_title"]
    assert item["reading_status"]
    assert item["first_chapter_id"] is not None
    assert item["ocr_summary"]["total"] == item["chapter_count"]


def test_reimport_after_ocr_succeeds(client: TestClient, tmp_path: Path, db_session: Session):
    """Rescanning a chapter with OCR text must not hit PageText FK violations."""
    series_dir = tmp_path / "Solo Leveling"
    _build_solo_leveling_series(series_dir)
    folder = str(series_dir.resolve())

    import_response = client.post("/library/import", json={"folder_path": folder})
    assert import_response.status_code == 200

    series_id = client.get("/library/series").json()["items"][0]["id"]
    chapter = (
        db_session.query(Chapter)
        .filter(Chapter.series_id == series_id)
        .order_by(Chapter.number.asc())
        .first()
    )
    assert chapter is not None
    page = db_session.query(Page).filter(Page.chapter_id == chapter.id).first()
    assert page is not None
    db_session.add(PageText(page_id=page.id, text="sample ocr", engine="tesseract"))
    db_session.commit()

    reimport = client.post("/library/import", json={"folder_path": folder})
    assert reimport.status_code == 200
    assert len(client.get("/library/series").json()["items"]) == 1
