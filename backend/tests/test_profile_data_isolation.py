"""Per-profile data isolation (Netflix-style profiles on one account).

Drives the real HTTP stack with a real session so the X-Profile-Id enforcement,
per-profile scoping, and cross-account isolation are all exercised end to end.

Two profiles on ONE account must not see each other's follows, reading progress,
bookmarks, or mature toggle; a mutation without a valid active profile is
rejected; and a profile id from another account is treated as not-found.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import sessionmaker

from connectors.registry import ConnectorDescriptor
from core.config import get_settings
from database.models import Chapter, Library, Page, Series, UserSeriesState
from database.session import get_db
from main import create_app

FOLLOW_PATCH = "services.update_service.list_installed_connectors"
# A real descriptor, not a MagicMock: the tracker's resolved rating reads
# ``descriptor.mature``, and a MagicMock answers truthily to that, which would
# make every follow in these tests look 18+ and vanish behind the gate.
_INSTALLED = [
    ConnectorDescriptor(
        source_type="mangadex",
        name="MangaDex",
        description="",
        browsable=True,
        supports_import=False,
        mature=False,
    )
]


def _seed_catalog(factory, *, user_id: int, profile_ids: list[int]) -> dict[str, int]:
    """Seed a shared library with a safe and an adult series + a chapter.

    Both series are put in BOTH profiles' libraries: these tests isolate the
    per-profile mature gate and progress, so library membership must not be the
    variable that differs between them.
    """
    db = factory()
    try:
        lib = Library(name="Main", root_path="/lib")
        db.add(lib)
        db.flush()
        safe = Series(
            library_id=lib.id,
            title="Wholesome Adventure",
            folder_path="/lib/safe",
            sort_title="wholesome adventure",
            content_rating="safe",
        )
        adult = Series(
            library_id=lib.id,
            title="Adults Only",
            folder_path="/lib/adult",
            sort_title="adults only",
            content_rating="pornographic",
        )
        db.add_all([safe, adult])
        db.flush()
        db.add_all(
            UserSeriesState(
                user_id=user_id,
                profile_id=profile_id,
                series_id=series.id,
                in_library=True,
            )
            for profile_id in profile_ids
            for series in (safe, adult)
        )
        chapter = Chapter(
            series_id=safe.id, title="Ch1", number=1.0, page_count=10, sort_key="0001"
        )
        db.add(chapter)
        db.flush()
        db.add(Page(chapter_id=chapter.id, number=1, file_path="/lib/safe/1/001.jpg"))
        db.commit()
        return {"series": safe.id, "adult": adult.id, "chapter": chapter.id}
    finally:
        db.close()


def _make_client(db_engine):
    factory = sessionmaker(bind=db_engine, autoflush=False, autocommit=False)

    def override_get_db():
        db = factory()
        try:
            yield db
        finally:
            db.close()

    app = create_app(run_migrations=False, run_workers=False)
    app.dependency_overrides[get_db] = override_get_db
    return TestClient(app), factory


@pytest.mark.real_auth
class TestProfileDataIsolation:
    @pytest.fixture
    def env(self, db_engine, monkeypatch):
        monkeypatch.setenv("MM_COOKIE_SECURE", "false")
        get_settings.cache_clear()

        client, factory = _make_client(db_engine)
        # First registration => admin/owner, and sets the session cookie.
        reg = client.post(
            "/auth/register", json={"username": "owner", "password": "supersecret"}
        )
        assert reg.status_code in (200, 201), reg.text
        owner_id = reg.json()["user"]["id"]
        p1 = client.post("/profiles", json={"name": "Alpha"}).json()
        p2 = client.post("/profiles", json={"name": "Beta"}).json()

        ids = _seed_catalog(
            factory, user_id=owner_id, profile_ids=[p1["id"], p2["id"]]
        )
        yield {
            "client": client,
            "factory": factory,
            "p1": p1["id"],
            "p2": p2["id"],
            **ids,
        }
        get_settings.cache_clear()

    # --- (a) + (d) + (e): follows -------------------------------------------

    def test_follow_is_per_profile_and_requires_active_profile(self, env):
        client, p1, p2 = env["client"], env["p1"], env["p2"]
        h1 = {"X-Profile-Id": str(p1)}
        h2 = {"X-Profile-Id": str(p2)}
        body = {"source": "mangadex", "series_id": "sx", "series_title": "X"}

        with patch(FOLLOW_PATCH, return_value=_INSTALLED):
            # (d) mutation without a profile header -> 400 profile_required.
            missing = client.post("/updates/trackers/follow", json=body)
            assert missing.status_code == 400
            assert missing.json()["code"] == "profile_required"

            # (e) foreign/unknown profile id -> 404.
            foreign = client.post(
                "/updates/trackers/follow", json=body, headers={"X-Profile-Id": "9999"}
            )
            assert foreign.status_code == 404

            # (a) Profile 1 follows series X.
            r1 = client.post("/updates/trackers/follow", json=body, headers=h1)
            assert r1.status_code == 200, r1.text
            t1 = r1.json()

            # Profile 2 does NOT see X...
            assert client.get("/updates/trackers", headers=h2).json() == []
            assert len(client.get("/updates/trackers", headers=h1).json()) == 1

            # ...and CAN independently follow the same series (own row).
            r2 = client.post("/updates/trackers/follow", json=body, headers=h2)
            assert r2.status_code == 200, r2.text
            t2 = r2.json()

        assert t1["id"] != t2["id"]
        assert len(client.get("/updates/trackers", headers=h1).json()) == 1
        assert len(client.get("/updates/trackers", headers=h2).json()) == 1

    # --- (b): reading progress + bookmarks ----------------------------------

    def test_progress_and_bookmarks_differ_per_profile(self, env):
        client = env["client"]
        p1, p2, series, chapter = env["p1"], env["p2"], env["series"], env["chapter"]
        h1 = {"X-Profile-Id": str(p1)}
        h2 = {"X-Profile-Id": str(p2)}

        saved = client.post(
            "/reader/progress",
            json={"series_id": series, "chapter_id": chapter, "last_page": 7},
            headers=h1,
        )
        assert saved.status_code == 200, saved.text

        # Profile 2 sees no progress for the same series.
        assert client.get(f"/reader/progress/{series}", headers=h2).json() is None
        assert client.get(f"/reader/progress/{series}", headers=h1).json()["last_page"] == 7

        # Profile 2 records its own progress -- no collision.
        client.post(
            "/reader/progress",
            json={"series_id": series, "chapter_id": chapter, "last_page": 2},
            headers=h2,
        )
        assert client.get(f"/reader/progress/{series}", headers=h2).json()["last_page"] == 2
        assert client.get(f"/reader/progress/{series}", headers=h1).json()["last_page"] == 7

        # Bookmarks are per-profile too.
        client.post(
            "/reader/bookmarks",
            json={"series_id": series, "chapter_id": chapter, "page": 3},
            headers=h1,
        )
        assert len(client.get(f"/reader/bookmarks/{series}", headers=h1).json()) == 1
        assert client.get(f"/reader/bookmarks/{series}", headers=h2).json() == []

        # Progress mutation with no active profile is rejected.
        assert (
            client.post(
                "/reader/progress",
                json={"series_id": series, "chapter_id": chapter, "last_page": 1},
            ).status_code
            == 400
        )

    # --- (c): per-profile mature toggle -------------------------------------

    def test_mature_toggle_is_per_profile(self, env):
        client, p1, p2 = env["client"], env["p1"], env["p2"]
        h1 = {"X-Profile-Id": str(p1)}
        h2 = {"X-Profile-Id": str(p2)}

        # Profile 1 opts in; Profile 2 stays off (global default).
        put = client.put("/settings", json={"mature_content_enabled": True}, headers=h1)
        assert put.status_code == 200
        assert put.json()["mature_content_enabled"] is True
        assert client.get("/settings", headers=h1).json()["mature_content_enabled"] is True
        assert client.get("/settings", headers=h2).json()["mature_content_enabled"] is False

        # Discovery reflects each profile's own gate.
        titles_1 = {r["title"] for r in client.get("/library/recently-added", headers=h1).json()}
        titles_2 = {r["title"] for r in client.get("/library/recently-added", headers=h2).json()}
        assert "Adults Only" in titles_1
        assert "Adults Only" not in titles_2
        assert "Wholesome Adventure" in titles_1 and "Wholesome Adventure" in titles_2

    # --- (f): cross-account isolation ---------------------------------------

    def test_cross_account_isolation_still_holds(self, env, db_engine):
        client, p1 = env["client"], env["p1"]
        h1 = {"X-Profile-Id": str(p1)}
        body = {"source": "mangadex", "series_id": "sx", "series_title": "X"}

        # A separate account on the same instance.
        other, _ = _make_client(db_engine)
        other.post("/auth/register", json={"username": "other", "password": "supersecret"})
        other_profile = other.post("/profiles", json={"name": "Solo"}).json()
        ho = {"X-Profile-Id": str(other_profile["id"])}

        with patch(FOLLOW_PATCH, return_value=_INSTALLED):
            client.post("/updates/trackers/follow", json=body, headers=h1)

            # The other account sees none of owner's follows.
            assert other.get("/updates/trackers", headers=ho).json() == []

            # Owner cannot act under the other account's profile id (foreign -> 404).
            assert (
                client.post(
                    "/updates/trackers/follow",
                    json=body,
                    headers={"X-Profile-Id": str(other_profile["id"])},
                ).status_code
                == 404
            )
