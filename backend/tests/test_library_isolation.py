"""Library isolation across accounts AND across profiles of one account.

The owner's #1 requirement: "if someone makes a new account it should have its
own different data ... none data should collide". A library therefore belongs to
BOTH axes -- every read and write is scoped to (user_id, profile_id) -- and the
membership bit lives on ``user_series_state.in_library``, not on the catalog.

These tests drive the real HTTP stack with real sessions, because the leak this
guards against was only visible end to end: the catalog rows are legitimately
shared, so the isolation has to hold at the *response* level, not just in one
query.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import sessionmaker

from core.config import get_settings
from database.models import Chapter, Library, Page, Series
from database.session import get_db
from main import create_app


def _make_client(db_engine) -> TestClient:
    """A client with its own app/cookie jar over the SHARED database, so two
    accounts really do sit on one instance."""
    factory = sessionmaker(bind=db_engine, autoflush=False, autocommit=False)

    def override_get_db():
        db = factory()
        try:
            yield db
        finally:
            db.close()

    app = create_app(run_migrations=False, run_workers=False)
    app.dependency_overrides[get_db] = override_get_db
    return TestClient(app)


def _seed_catalog(db_engine) -> dict[str, int]:
    """Seed catalog rows owned by nobody -- the shared facts both accounts can
    legitimately resolve by id, and which neither may see in the other's shelf."""
    factory = sessionmaker(bind=db_engine, autoflush=False, autocommit=False)
    db = factory()
    try:
        lib = Library(name="Main", root_path="/lib")
        db.add(lib)
        db.flush()
        owned = Series(
            library_id=lib.id,
            title="Solo Leveling",
            folder_path="/lib/solo",
            sort_title="solo leveling",
            author="Chugong",
            content_rating="safe",
        )
        other = Series(
            library_id=lib.id,
            title="Omniscient Reader",
            folder_path="/lib/orv",
            sort_title="omniscient reader",
            author="Sing Shong",
            content_rating="safe",
        )
        db.add_all([owned, other])
        db.flush()
        chapter = Chapter(
            series_id=owned.id, title="Ch1", number=1.0, page_count=10, sort_key="0001"
        )
        db.add(chapter)
        db.flush()
        db.add(Page(chapter_id=chapter.id, number=1, file_path="/lib/solo/1/001.jpg"))
        db.commit()
        return {"series": owned.id, "other": other.id, "chapter": chapter.id}
    finally:
        db.close()


@pytest.mark.real_auth
class TestLibraryIsolation:
    @pytest.fixture
    def env(self, db_engine, monkeypatch):
        monkeypatch.setenv("MM_COOKIE_SECURE", "false")
        get_settings.cache_clear()

        # Account A registers first, so it is the admin/owner and claims any
        # pre-existing NULL-owned rows. Account B is a brand-new second account.
        a = _make_client(db_engine)
        assert a.post(
            "/auth/register", json={"username": "owner", "password": "supersecret"}
        ).status_code in (200, 201)
        a1 = a.post("/profiles", json={"name": "Alpha"}).json()
        a2 = a.post("/profiles", json={"name": "Beta"}).json()

        b = _make_client(db_engine)
        assert b.post(
            "/auth/register", json={"username": "newcomer", "password": "supersecret"}
        ).status_code in (200, 201)
        b1 = b.post("/profiles", json={"name": "Solo"}).json()

        ids = _seed_catalog(db_engine)
        yield {
            "a": a,
            "b": b,
            "ha": {"X-Profile-Id": str(a1["id"])},
            "ha2": {"X-Profile-Id": str(a2["id"])},
            "hb": {"X-Profile-Id": str(b1["id"])},
            **ids,
        }
        get_settings.cache_clear()

    # --- helpers -------------------------------------------------------------

    @staticmethod
    def _fill_library(client: TestClient, headers: dict[str, str], env) -> None:
        """A adds a series, favourites it, and reads a page of it."""
        added = client.post(f"/library/series/{env['series']}/add", headers=headers)
        assert added.status_code == 200, added.text
        assert added.json() == {"series_id": env["series"], "in_library": True}

        fav = client.post(f"/library/series/{env['series']}/favorite", headers=headers)
        assert fav.status_code == 200, fav.text
        assert fav.json()["is_favorite"] is True

        progress = client.post(
            "/reader/progress",
            json={
                "series_id": env["series"],
                "chapter_id": env["chapter"],
                "last_page": 7,
            },
            headers=headers,
        )
        assert progress.status_code == 200, progress.text

    # --- membership ----------------------------------------------------------

    def test_a_sees_only_what_a_added_and_b_sees_nothing(self, env):
        a, b = env["a"], env["b"]
        self._fill_library(a, env["ha"], env)

        mine = a.get("/library/series", headers=env["ha"]).json()
        assert mine["total"] == 1
        assert [item["title"] for item in mine["items"]] == ["Solo Leveling"]

        theirs = b.get("/library/series", headers=env["hb"]).json()
        assert theirs["total"] == 0
        assert theirs["items"] == []

    def test_catalog_series_nobody_added_is_in_no_library(self, env):
        """The second catalog series is added by neither account, so the
        membership bit -- not the mere existence of a state row -- is what
        decides the grid."""
        a, b = env["a"], env["b"]
        self._fill_library(a, env["ha"], env)

        # A favourites the never-added series: that writes a state row with
        # in_library still false, which must not put it on the shelf.
        a.post(f"/library/series/{env['other']}/favorite", headers=env["ha"])

        titles = {
            item["title"] for item in a.get("/library/series", headers=env["ha"]).json()["items"]
        }
        assert titles == {"Solo Leveling"}
        assert b.get("/library/series", headers=env["hb"]).json()["total"] == 0

    def test_remove_clears_membership_but_keeps_the_shelf_state(self, env):
        a = env["a"]
        self._fill_library(a, env["ha"], env)

        removed = a.delete(f"/library/series/{env['series']}/add", headers=env["ha"])
        assert removed.status_code == 200, removed.text
        assert removed.json() == {"series_id": env["series"], "in_library": False}
        assert a.get("/library/series", headers=env["ha"]).json()["total"] == 0

        # Re-adding restores the favourite and the progress, not a blank row.
        a.post(f"/library/series/{env['series']}/add", headers=env["ha"])
        item = a.get("/library/series", headers=env["ha"]).json()["items"][0]
        assert item["is_favorite"] is True
        assert item["reading_progress"]["last_page"] == 7

    def test_add_requires_an_active_profile(self, env):
        a = env["a"]
        missing = a.post(f"/library/series/{env['series']}/add")
        assert missing.status_code == 400
        assert missing.json()["code"] == "profile_required"

        foreign = a.post(
            f"/library/series/{env['series']}/add", headers={"X-Profile-Id": "9999"}
        )
        assert foreign.status_code == 404

    def test_filters_and_sorts_stay_per_caller(self, env):
        """The membership join must not inflate ``total`` or duplicate rows, and
        the is_favorite / reading_status filters must read the caller's state
        rather than the shared catalog columns."""
        a, b = env["a"], env["b"]
        self._fill_library(a, env["ha"], env)
        a.post(f"/library/series/{env['other']}/add", headers=env["ha"])
        collection_id = a.post(
            "/library/collections", json={"name": "Shelf"}, headers=env["ha"]
        ).json()["id"]
        a.post(
            f"/library/collections/{collection_id}/series/{env['series']}",
            headers=env["ha"],
        )
        a.patch(
            f"/library/series/{env['series']}",
            json={"reading_status": "reading"},
            headers=env["ha"],
        )

        cases = [
            ({}, 2),
            ({"is_favorite": "true"}, 1),
            ({"reading_status": "reading"}, 1),
            ({"collection_id": collection_id}, 1),
            ({"sort": "recent"}, 2),
            ({"status": "reading"}, 1),
        ]
        for params, expected in cases:
            mine = a.get("/library/series", params=params, headers=env["ha"]).json()
            assert mine["total"] == expected, (params, mine["total"])
            assert len(mine["items"]) == expected, params
            theirs = b.get("/library/series", params=params, headers=env["hb"]).json()
            assert theirs["total"] == 0, params
            assert theirs["items"] == [], params

    # --- state: favourite, progress ------------------------------------------

    def test_b_toggling_favorite_never_flips_a_s_flag(self, env):
        """The exact regression: ``series.is_favorite = not series.is_favorite``
        on the shared catalog row meant B's first toggle turned A's favourite
        OFF."""
        a, b = env["a"], env["b"]
        self._fill_library(a, env["ha"], env)

        toggled = b.post(f"/library/series/{env['series']}/favorite", headers=env["hb"])
        assert toggled.status_code == 200, toggled.text
        assert toggled.json()["is_favorite"] is True  # B's own first toggle

        assert a.get("/library/series", headers=env["ha"]).json()["items"][0][
            "is_favorite"
        ] is True

    def test_series_detail_leaks_neither_favourite_nor_progress(self, env):
        a, b = env["a"], env["b"]
        self._fill_library(a, env["ha"], env)

        mine = a.get(f"/library/series/{env['series']}", headers=env["ha"]).json()
        assert mine["is_favorite"] is True
        assert mine["reading_progress"]["last_page"] == 7

        theirs = b.get(f"/library/series/{env['series']}", headers=env["hb"]).json()
        assert theirs["is_favorite"] is False
        assert theirs["reading_progress"] is None
        assert theirs["reading_status"] == "unread"

    def test_patch_reading_status_is_per_account(self, env):
        a, b = env["a"], env["b"]
        self._fill_library(a, env["ha"], env)

        patched = a.patch(
            f"/library/series/{env['series']}",
            json={"reading_status": "completed"},
            headers=env["ha"],
        )
        assert patched.status_code == 200, patched.text
        assert patched.json()["reading_status"] == "completed"

        theirs = b.get(f"/library/series/{env['series']}", headers=env["hb"]).json()
        assert theirs["reading_status"] == "unread"

    # --- discovery surfaces ---------------------------------------------------

    def test_search_is_scoped(self, env):
        a, b = env["a"], env["b"]
        self._fill_library(a, env["ha"], env)

        mine = a.get("/library/search", params={"q": "Solo"}, headers=env["ha"]).json()
        assert mine["total"] == 1

        theirs = b.get("/library/search", params={"q": "Solo"}, headers=env["hb"]).json()
        assert theirs["total"] == 0
        assert theirs["items"] == []

    def test_statistics_are_scoped(self, env):
        a, b = env["a"], env["b"]
        self._fill_library(a, env["ha"], env)

        mine = a.get("/library/statistics", headers=env["ha"]).json()
        assert mine["total_series"] == 1
        assert mine["favorites"] == 1
        assert mine["total_chapters"] == 1
        assert [row["author"] for row in mine["top_authors"]] == ["Chugong"]

        theirs = b.get("/library/statistics", headers=env["hb"]).json()
        assert theirs["total_series"] == 0
        assert theirs["favorites"] == 0
        assert theirs["total_chapters"] == 0
        assert theirs["top_authors"] == []

    def test_discovery_strips_are_scoped(self, env):
        a, b = env["a"], env["b"]
        self._fill_library(a, env["ha"], env)

        for path in ("/library/recently-added", "/library/recently-updated"):
            assert [r["title"] for r in a.get(path, headers=env["ha"]).json()] == [
                "Solo Leveling"
            ]
            assert b.get(path, headers=env["hb"]).json() == []

        assert b.get("/library/recommendations", headers=env["hb"]).json() == []

    def test_similar_series_never_reaches_into_another_library(self, env):
        """A's two series share nothing but both being A's; B, whose library is
        empty, must get no candidates at all."""
        a, b = env["a"], env["b"]
        a.post(f"/library/series/{env['series']}/add", headers=env["ha"])
        a.post(f"/library/series/{env['other']}/add", headers=env["ha"])

        assert (
            b.get(f"/library/series/{env['series']}/similar", headers=env["hb"]).json()
            == []
        )

    # --- collections ----------------------------------------------------------

    def test_collections_are_invisible_and_unreadable_across_accounts(self, env):
        a, b = env["a"], env["b"]
        self._fill_library(a, env["ha"], env)

        created = a.post(
            "/library/collections",
            json={"name": "Owner Private List"},
            headers=env["ha"],
        )
        assert created.status_code == 200, created.text
        collection_id = created.json()["id"]
        a.post(
            f"/library/collections/{collection_id}/series/{env['series']}",
            headers=env["ha"],
        )

        # Not listed, not readable by id, and not named on the shared series.
        assert b.get("/library/collections", headers=env["hb"]).json() == []
        denied = b.get(f"/library/collections/{collection_id}", headers=env["hb"])
        assert denied.status_code == 404
        assert denied.json()["code"] == "collection_not_found"

        detail = b.get(f"/library/series/{env['series']}", headers=env["hb"]).json()
        assert detail["collections"] == []

        # A still sees its own.
        mine = a.get(f"/library/series/{env['series']}", headers=env["ha"]).json()
        assert [c["name"] for c in mine["collections"]] == ["Owner Private List"]

    # --- second axis: two profiles of ONE account -----------------------------

    def test_two_profiles_of_one_account_are_separated(self, env):
        a = env["a"]
        alpha, beta = env["ha"], env["ha2"]
        self._fill_library(a, alpha, env)

        # Beta is the same account, but a different shelf.
        assert a.get("/library/series", headers=beta).json()["total"] == 0
        assert a.get("/library/statistics", headers=beta).json()["total_series"] == 0
        assert a.get("/library/search", params={"q": "Solo"}, headers=beta).json()[
            "total"
        ] == 0

        beta_detail = a.get(f"/library/series/{env['series']}", headers=beta).json()
        assert beta_detail["is_favorite"] is False
        assert beta_detail["reading_progress"] is None

        # Beta adds the SAME series independently -- its own row, no collision.
        assert (
            a.post(f"/library/series/{env['series']}/add", headers=beta).status_code
            == 200
        )
        assert a.get("/library/series", headers=beta).json()["total"] == 1
        assert a.get("/library/series", headers=beta).json()["items"][0][
            "is_favorite"
        ] is False
        assert a.get("/library/series", headers=alpha).json()["items"][0][
            "is_favorite"
        ] is True

    def test_collections_are_separated_between_profiles(self, env):
        a = env["a"]
        alpha, beta = env["ha"], env["ha2"]
        created = a.post(
            "/library/collections", json={"name": "Alpha Only"}, headers=alpha
        )
        assert created.status_code == 200, created.text

        assert a.get("/library/collections", headers=beta).json() == []
        assert (
            a.get(
                f"/library/collections/{created.json()['id']}", headers=beta
            ).status_code
            == 404
        )
