"""The source-link/follow contract, proved over the real HTTP API.

Companion to ``test_series_source_link.py``, which covers the same behaviour at
the *service* level. This file drives real registration, real reading profiles
and the real route handlers, so what is pinned here is the wire contract the web
and Flutter clients actually call -- including the ``source_id``->``source`` /
``source_series_id``->``series_id`` rename that ``POST /updates/trackers/follow``
requires, which a service-level test cannot exercise.

Deliberately does NOT share helpers with its service-level sibling: if both were
wrong in the same way, sharing the seeding would hide it.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session, sessionmaker

from core.config import get_settings
from database.models import (
    Chapter,
    Library,
    ReadingProfile,
    Series,
    SeriesTracker,
    SourceChapterLink,
    User,
    UserSeriesState,
)
from database.session import get_db
from main import create_app

pytestmark = pytest.mark.real_auth

SOURCE = "mangadex"
SRC_SERIES = "abc-123"


@pytest.fixture
def client(db_engine, monkeypatch):
    monkeypatch.setenv("MM_COOKIE_SECURE", "false")
    get_settings.cache_clear()
    session_factory = sessionmaker(bind=db_engine, autoflush=False, autocommit=False)

    def override_get_db():
        db = session_factory()
        try:
            yield db
        finally:
            db.close()

    app = create_app(run_migrations=False, run_workers=False)
    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as c:
        yield c
    get_settings.cache_clear()


@pytest.fixture
def db(db_engine):
    session_factory = sessionmaker(bind=db_engine, autoflush=False, autocommit=False)
    s = session_factory()
    try:
        yield s
    finally:
        s.close()


@pytest.fixture(autouse=True)
def dead_source(monkeypatch):
    """Every connector is unreachable. The source identity must survive it."""
    from services import source_service

    def _explode(self, series_id, **cfg):  # noqa: ANN001, ARG001
        raise RuntimeError("connector unreachable")

    monkeypatch.setattr(source_service.SourceService, "get_chapters", _explode)


def _register(client: TestClient, username: str) -> int:
    r = client.post(
        "/auth/register", json={"username": username, "password": "supersecret1"}
    )
    assert r.status_code in (200, 201), r.text
    return r.json()["user"]["id"] if "user" in r.json() else r.json()["id"]


def _seed_series(
    db: Session, title: str, *, rating: str = "safe", linked: bool
) -> int:
    lib = db.query(Library).first()
    if lib is None:
        lib = Library(name="Main", root_path="/tmp/mm-verify")
        db.add(lib)
        db.flush()
    s = Series(
        library_id=lib.id,
        title=title,
        sort_title=title.lower(),
        folder_path=f"/tmp/mm-verify/{title}",
        content_rating=rating,
    )
    db.add(s)
    db.flush()
    ch = Chapter(
        series_id=s.id,
        title="Chapter 1",
        number=1.0,
        folder_path=f"/tmp/mm-verify/{title}/c1",
        page_count=3,
    )
    db.add(ch)
    db.flush()
    if linked:
        # Exactly what the download pipeline writes.
        db.add(
            SourceChapterLink(
                source=SOURCE,
                series_id=SRC_SERIES,
                chapter_id="ch-1",
                local_chapter_id=ch.id,
            )
        )
    db.flush()
    return s.id


def _claim(db: Session, series_id: int, user_id: int) -> None:
    db.add(
        UserSeriesState(
            user_id=user_id, profile_id=None, series_id=series_id, in_library=True
        )
    )
    db.commit()


def _profiles(client: TestClient) -> list[int]:
    ids = []
    for name in ("Alpha", "Beta"):
        r = client.post("/profiles", json={"name": name})
        assert r.status_code == 201, r.text
        ids.append(r.json()["id"])
    return ids


def _detail(client: TestClient, series_id: int, profile_id: int):
    return client.get(
        f"/library/series/{series_id}", headers={"X-Profile-Id": str(profile_id)}
    )


# ---------------------------------------------------------------- REQ 3


def test_downloaded_series_reports_identity_and_follow_flips(
    client: TestClient, db: Session
):
    owner = _register(client, "owner")
    a, b = _profiles(client)
    downloaded = _seed_series(db, "Downloaded", linked=True)
    handmade = _seed_series(db, "HandImported", linked=False)
    _claim(db, downloaded, owner)
    _claim(db, handmade, owner)

    # (a) downloaded series names its source, with every connector dead.
    r = _detail(client, downloaded, a)
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["source_id"] == SOURCE
    assert d["source_series_id"] == SRC_SERIES
    assert d["is_followed"] is False
    assert d["follow_tracker_id"] is None

    # (b) hand-imported folder reports null.
    r = _detail(client, handmade, a)
    assert r.status_code == 200, r.text
    h = r.json()
    assert h["source_id"] is None
    assert h["source_series_id"] is None
    assert h["is_followed"] is False
    assert h["follow_tracker_id"] is None

    # (c) follow via the REAL endpoint, using the renamed fields.
    r = client.post(
        "/updates/trackers/follow",
        json={
            "source": d["source_id"],
            "series_id": d["source_series_id"],
            "series_title": d["title"],
            "genres": [],
        },
        headers={"X-Profile-Id": str(a)},
    )
    assert r.status_code in (200, 201), r.text
    tracker_id = r.json()["id"]

    # (d) detail flips to followed and names that exact tracker.
    d2 = _detail(client, downloaded, a).json()
    assert d2["is_followed"] is True
    assert d2["follow_tracker_id"] == tracker_id
    assert d2["source_id"] == SOURCE

    # (e) REQ 5 — profile B on the SAME account is unaffected...
    d3 = _detail(client, downloaded, b).json()
    assert d3["is_followed"] is False, "profile A's follow leaked to profile B"
    assert d3["follow_tracker_id"] is None
    # ...but still sees where the series came from (identity is account-level).
    assert d3["source_id"] == SOURCE
    assert d3["source_series_id"] == SRC_SERIES

    # (f) unfollow through the real endpoint flips it back.
    r = client.delete(
        f"/updates/trackers/{tracker_id}", headers={"X-Profile-Id": str(a)}
    )
    assert r.status_code == 200, r.text
    d4 = _detail(client, downloaded, a).json()
    assert d4["is_followed"] is False
    assert d4["follow_tracker_id"] is None
    assert d4["source_id"] == SOURCE


def test_downloaded_tracker_is_not_a_follow(client: TestClient, db: Session):
    """sync_downloaded_trackers writes one of these for EVERY downloaded series."""
    owner = _register(client, "owner")
    a, _ = _profiles(client)
    sid = _seed_series(db, "Downloaded", linked=True)
    _claim(db, sid, owner)
    db.add(
        SeriesTracker(
            user_id=owner,
            profile_id=a,
            source=SOURCE,
            series_id=SRC_SERIES,
            series_title="Downloaded",
            track_kind="downloaded",
        )
    )
    db.commit()

    d = _detail(client, sid, a).json()
    assert d["source_id"] == SOURCE
    assert d["is_followed"] is False, "a downloaded tracker was counted as a follow"
    assert d["follow_tracker_id"] is None


# ---------------------------------------------------------------- REQ 4


def test_stranger_gets_no_payload_and_no_identity(client: TestClient, db: Session):
    owner = _register(client, "owner")
    sid = _seed_series(db, "Downloaded", linked=True)
    _claim(db, sid, owner)

    stranger = TestClient(client.app)
    stranger.cookies.clear()
    r = stranger.post(
        "/auth/register", json={"username": "stranger", "password": "supersecret1"}
    )
    assert r.status_code in (200, 201), r.text

    r = stranger.get(f"/library/series/{sid}")
    assert r.status_code == 404, r.text
    body = r.text
    assert "series_not_found" in body
    assert SOURCE not in body, "source identity leaked in the 404 body"
    assert SRC_SERIES not in body

    # PATCH is the other entrance onto the same serializer.
    r = stranger.patch(f"/library/series/{sid}", json={"title": "pwned"})
    assert r.status_code == 404, r.text
    assert SOURCE not in r.text


def test_mature_gate_hides_the_series_and_its_identity(client: TestClient, db: Session):
    owner = _register(client, "owner")
    a, _ = _profiles(client)
    sid = _seed_series(db, "Adult", rating="pornographic", linked=True)
    _claim(db, sid, owner)

    prof = db.get(ReadingProfile, a)
    prof.mature_content_enabled = False
    db.commit()

    r = _detail(client, sid, a)
    assert r.status_code == 404, r.text
    assert SOURCE not in r.text, "adult series' source identity leaked through the gate"

    # Same profile, gate on -> readable, and the identity is there.
    prof = db.get(ReadingProfile, a)
    prof.mature_content_enabled = True
    db.commit()
    r = _detail(client, sid, a)
    assert r.status_code == 200, r.text
    assert r.json()["source_id"] == SOURCE


# ---------------------------------------------------------------- REQ 5 (cross-account)


def test_follow_is_scoped_per_account(client: TestClient, db: Session):
    owner = _register(client, "owner")
    a, _ = _profiles(client)
    sid = _seed_series(db, "Downloaded", linked=True)
    _claim(db, sid, owner)

    r = client.post(
        "/updates/trackers/follow",
        json={"source": SOURCE, "series_id": SRC_SERIES, "series_title": "Downloaded"},
        headers={"X-Profile-Id": str(a)},
    )
    assert r.status_code in (200, 201), r.text
    assert _detail(client, sid, a).json()["is_followed"] is True

    other = TestClient(client.app)
    other.cookies.clear()
    other.post(
        "/auth/register", json={"username": "sibling", "password": "supersecret1"}
    )
    # The sibling account must have its OWN claim on the series, otherwise this
    # would prove nothing beyond the authz 404 the stranger test already covers.
    sibling = db.query(User).filter(User.username == "sibling").first()
    _claim(db, sid, sibling.id)
    r = other.post("/profiles", json={"name": "Gamma"})
    assert r.status_code == 201, r.text
    g = r.json()["id"]

    d = other.get(
        f"/library/series/{sid}", headers={"X-Profile-Id": str(g)}
    ).json()
    assert d["source_id"] == SOURCE
    assert d["is_followed"] is False, "owner's follow leaked to another account"


def test_owner_can_still_patch_their_own_series(client: TestClient, db: Session):
    """The new PATCH gate must not overshoot and block legitimate edits."""
    owner = _register(client, "owner")
    a, _ = _profiles(client)
    sid = _seed_series(db, "Downloaded", linked=True)
    _claim(db, sid, owner)

    r = client.patch(
        f"/library/series/{sid}",
        json={"title": "Renamed By Owner", "author": "Chugong"},
        headers={"X-Profile-Id": str(a)},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["title"] == "Renamed By Owner"
    assert body["author"] == "Chugong"
    # And the PATCH response carries the same source identity the GET does.
    assert body["source_id"] == SOURCE
    assert body["source_series_id"] == SRC_SERIES
    assert body["is_followed"] is False
