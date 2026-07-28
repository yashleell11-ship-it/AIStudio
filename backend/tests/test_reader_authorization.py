"""Object-level read authorization on the reader.

Library *listing* was already scoped (``list_series`` INNER JOINs membership) and
the 18+ gate already covered ``get_series``/``get_chapter``. Neither was
authorization: ``get_chapter``/``get_series``/``get_page``/``get_cover_path``
filtered on the row id alone, so any authenticated household member could fetch
any series, chapter, page image or cover by guessing a numeric id. These tests
drive the real HTTP stack because that is the only level the leak was visible at
— the catalog rows are legitimately shared, so the guarantee has to hold at the
*response*.

The rule under test (see core.library_authz) is ACCOUNT-level, not
profile-level, and that is a product decision this file pins down in both
directions: a sibling profile of the account that claimed a series still reads it
(one household, one filesystem, and child safety is the 18+ gate's job), while a
sibling profile on a series *nobody* on the account claimed does not.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session, sessionmaker

from core.config import get_settings
from database.models import (
    Chapter,
    Library,
    Page,
    Series,
    SourceChapterLink,
    User,
    UserSeriesState,
)
from database.session import get_db
from main import create_app
from services.library_service import LibraryService

JPEG_BYTES = b"\xff\xd8\xff\xe0" + b"\x00" * 32 + b"\xff\xd9"


def _make_client(db_engine) -> TestClient:
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


def _seed_catalog(db_engine, root: Path) -> dict[str, int]:
    """Two catalog series with real files on disk, owned by nobody.

    Real bytes matter here: an authorized page/cover read has to come back 200,
    or the test cannot tell "allowed, file missing" apart from "denied".
    """
    factory = sessionmaker(bind=db_engine, autoflush=False, autocommit=False)
    db = factory()
    try:
        lib = Library(name="Main", root_path=str(root))
        db.add(lib)
        db.flush()
        ids: dict[str, int] = {}
        for key, title, folder in (
            ("series", "Solo Leveling", "solo"),
            ("other", "Omniscient Reader", "orv"),
        ):
            page_dir = root / folder / "1"
            page_dir.mkdir(parents=True, exist_ok=True)
            image = page_dir / "001.jpg"
            image.write_bytes(JPEG_BYTES)

            series = Series(
                library_id=lib.id,
                title=title,
                folder_path=str(root / folder),
                sort_title=title.lower(),
                content_rating="safe",
                cover_path=str(image),
            )
            db.add(series)
            db.flush()
            chapter = Chapter(
                series_id=series.id,
                title="Ch1",
                number=1.0,
                page_count=1,
                sort_key="0001",
                folder_path=str(page_dir),
            )
            db.add(chapter)
            db.flush()
            page = Page(chapter_id=chapter.id, number=1, file_path=str(image))
            db.add(page)
            db.flush()
            ids[key] = series.id
            ids[f"{key}_chapter"] = chapter.id
            ids[f"{key}_page"] = page.id
        db.commit()
        return ids
    finally:
        db.close()


@pytest.mark.real_auth
class TestReaderObjectAuthorization:
    @pytest.fixture
    def env(self, db_engine, tmp_path, monkeypatch):
        monkeypatch.setenv("MM_COOKIE_SECURE", "false")
        get_settings.cache_clear()

        root = tmp_path / "library"
        root.mkdir(parents=True, exist_ok=True)

        a = _make_client(db_engine)
        assert a.post(
            "/auth/register", json={"username": "owner", "password": "supersecret"}
        ).status_code in (200, 201)
        alpha = a.post("/profiles", json={"name": "Alpha"}).json()
        beta = a.post("/profiles", json={"name": "Beta"}).json()

        b = _make_client(db_engine)
        assert b.post(
            "/auth/register", json={"username": "newcomer", "password": "supersecret"}
        ).status_code in (200, 201)
        solo = b.post("/profiles", json={"name": "Solo"}).json()

        ids = _seed_catalog(db_engine, root)
        yield {
            "a": a,
            "b": b,
            "ha": {"X-Profile-Id": str(alpha["id"])},
            "ha2": {"X-Profile-Id": str(beta["id"])},
            "hb": {"X-Profile-Id": str(solo["id"])},
            "root": root,
            **ids,
        }
        get_settings.cache_clear()

    # --- helpers -------------------------------------------------------------

    @staticmethod
    def _read_surfaces(env, key: str = "series") -> list[str]:
        """Every route that hands back the series, a chapter, or its bytes."""
        return [
            f"/library/series/{env[key]}",
            f"/library/chapters/{env[f'{key}_chapter']}",
            f"/reader/chapter/{env[f'{key}_chapter']}",
            f"/reader/chapter/{env[f'{key}_chapter']}/adjacent",
            f"/library/pages/{env[f'{key}_page']}/image",
            f"/reader/page/{env[f'{key}_page']}/image",
            f"/library/covers/{env[key]}",
            f"/library/series/{env[key]}/metadata-quality",
        ]

    @staticmethod
    def _statuses(client, paths, headers) -> dict[str, int]:
        return {path: client.get(path, headers=headers).status_code for path in paths}

    # --- the leak, closed -----------------------------------------------------

    def test_owner_reads_every_surface_of_the_series_they_added(self, env):
        a = env["a"]
        assert (
            a.post(f"/library/series/{env['series']}/add", headers=env["ha"]).status_code
            == 200
        )
        assert self._statuses(a, self._read_surfaces(env), env["ha"]) == {
            path: 200 for path in self._read_surfaces(env)
        }

    def test_a_different_account_gets_404_on_every_surface(self, env):
        """The reproduction: B fetched all of these by id and got 200."""
        a, b = env["a"], env["b"]
        a.post(f"/library/series/{env['series']}/add", headers=env["ha"])

        assert self._statuses(b, self._read_surfaces(env), env["hb"]) == {
            path: 404 for path in self._read_surfaces(env)
        }

    def test_a_sibling_profile_gets_404_on_a_series_the_account_never_claimed(self, env):
        """Account-level does not mean unlimited: the second catalog series is
        claimed by no profile on either account, so nobody may open it."""
        a = env["a"]
        a.post(f"/library/series/{env['series']}/add", headers=env["ha"])

        paths = self._read_surfaces(env, "other")
        assert self._statuses(a, paths, env["ha2"]) == {path: 404 for path in paths}
        assert self._statuses(a, paths, env["ha"]) == {path: 404 for path in paths}

    def test_a_sibling_profile_still_reads_what_its_own_account_claimed(self, env):
        """Deliberate, and the reason the predicate ignores profile_id: one
        household shares one filesystem. Denying this would make a downloaded
        series unreadable on the profile that did not press the button, and
        child safety is the (separate, per-profile) 18+ gate's job."""
        a = env["a"]
        a.post(f"/library/series/{env['series']}/add", headers=env["ha"])

        assert self._statuses(a, self._read_surfaces(env), env["ha2"]) == {
            path: 200 for path in self._read_surfaces(env)
        }
        # ...while the sibling's own shelf and state stay separate.
        assert a.get("/library/series", headers=env["ha2"]).json()["total"] == 0
        assert (
            a.get(f"/library/series/{env['series']}", headers=env["ha2"]).json()[
                "is_favorite"
            ]
            is False
        )

    def test_a_request_with_no_active_profile_still_reads_the_accounts_library(self, env):
        """Both clients omit X-Profile-Id during boot and mid-profile-switch, so
        (user, None) is a routine context. A profile-scoped predicate would make
        the whole library unreadable there."""
        a = env["a"]
        a.post(f"/library/series/{env['series']}/add", headers=env["ha"])

        assert self._statuses(a, self._read_surfaces(env), {}) == {
            path: 200 for path in self._read_surfaces(env)
        }

    def test_denial_is_indistinguishable_from_an_id_that_never_existed(self, env):
        """404 not 403, and the SAME code -- an "exists but not yours" code would
        confirm the id, which is the disclosure the gate exists to prevent."""
        a, b = env["a"], env["b"]
        a.post(f"/library/series/{env['series']}/add", headers=env["ha"])

        pairs = [
            (f"/library/series/{env['series']}", "/library/series/999999"),
            (f"/library/chapters/{env['series_chapter']}", "/library/chapters/999999"),
            (f"/reader/chapter/{env['series_chapter']}", "/reader/chapter/999999"),
            (
                f"/reader/page/{env['series_page']}/image",
                "/reader/page/999999/image",
            ),
            (f"/library/covers/{env['series']}", "/library/covers/999999"),
        ]
        for real, absent in pairs:
            denied = b.get(real, headers=env["hb"])
            missing = b.get(absent, headers=env["hb"])
            assert denied.status_code == missing.status_code == 404, real
            assert denied.json()["code"] == missing.json()["code"], real

    # --- claims that are not "in_library" ------------------------------------

    def test_reading_progress_alone_grants_the_read(self, env):
        """Progress recorded from Browse writes NO membership row, yet
        Continue Reading surfaces the series. Denying it would make the home
        screen advertise a title that 404s on tap."""
        b = env["b"]
        saved = b.post(
            "/reader/progress",
            json={
                "series_id": env["series"],
                "chapter_id": env["series_chapter"],
                "last_page": 1,
            },
            headers=env["hb"],
        )
        assert saved.status_code == 200, saved.text

        assert b.get(f"/reader/chapter/{env['series_chapter']}", headers=env["hb"]).status_code == 200
        assert b.get(f"/library/covers/{env['series']}", headers=env["hb"]).status_code == 200

    def test_a_favourite_from_browse_grants_the_read(self, env):
        """toggle_favorite deliberately leaves in_library false, so a predicate
        keyed on the shelf bit would 404 a series the caller just favourited."""
        b = env["b"]
        assert (
            b.post(f"/library/series/{env['series']}/favorite", headers=env["hb"]).status_code
            == 200
        )
        state = (
            b.get(f"/library/series/{env['series']}", headers=env["hb"]).json()
        )
        assert state["is_favorite"] is True
        assert b.get(f"/reader/chapter/{env['series_chapter']}", headers=env["hb"]).status_code == 200

    def test_removing_from_the_library_keeps_the_series_readable(self, env):
        """set_in_library(False) keeps the row on purpose so progress survives a
        remove-and-re-add; the reader must respect that, not the shelf bit."""
        a = env["a"]
        a.post(f"/library/series/{env['series']}/add", headers=env["ha"])
        a.post(
            "/reader/progress",
            json={
                "series_id": env["series"],
                "chapter_id": env["series_chapter"],
                "last_page": 1,
            },
            headers=env["ha"],
        )
        assert a.delete(f"/library/series/{env['series']}/add", headers=env["ha"]).status_code == 200

        assert a.get("/library/series", headers=env["ha"]).json()["total"] == 0
        assert a.get(f"/reader/chapter/{env['series_chapter']}", headers=env["ha"]).status_code == 200

    def test_collecting_a_series_grants_the_read(self, env):
        """add_series_to_collection writes no membership row, and a collection's
        detail lists its series -- so without this arm a collection would render
        covers that 404 when opened."""
        b = env["b"]
        collection_id = b.post(
            "/library/collections", json={"name": "Shelf"}, headers=env["hb"]
        ).json()["id"]
        assert (
            b.post(
                f"/library/collections/{collection_id}/series/{env['series']}",
                headers=env["hb"],
            ).status_code
            == 200
        )

        assert b.get(f"/library/series/{env['series']}", headers=env["hb"]).status_code == 200
        assert b.get(f"/library/covers/{env['series']}", headers=env["hb"]).status_code == 200

    # --- adjacent-chapter walk -----------------------------------------------

    def test_adjacent_chapter_cannot_walk_an_unclaimed_series(self, env):
        a, b = env["a"], env["b"]
        a.post(f"/library/series/{env['series']}/add", headers=env["ha"])

        walk = f"/reader/chapter/{env['series_chapter']}/adjacent"
        assert a.get(walk, headers=env["ha"]).status_code == 200
        assert b.get(walk, headers=env["hb"]).status_code == 404

    # --- the 18+ gate is untouched -------------------------------------------

    def test_the_mature_gate_still_applies_on_top_of_authorization(self, env, db_engine):
        """Authorization is IN ADDITION to the 18+ gate, never instead of it:
        the owner has every claim there is and still cannot see an adult series
        while their profile's gate is closed."""
        a = env["a"]
        a.post(f"/library/series/{env['series']}/add", headers=env["ha"])

        factory = sessionmaker(bind=db_engine, autoflush=False, autocommit=False)
        db = factory()
        try:
            series = db.get(Series, env["series"])
            series.content_rating = "pornographic"
            db.commit()
        finally:
            db.close()

        for path in self._read_surfaces(env):
            assert a.get(path, headers=env["ha"]).status_code == 404, path

    def test_page_images_are_gated_by_the_mature_gate_too(self, env, db_engine):
        """get_page had neither gate. It is the content itself, so it now carries
        both -- an adult page image must not stay fetchable by id while the
        profile's gate hides everything else about the series."""
        a = env["a"]
        a.post(f"/library/series/{env['series']}/add", headers=env["ha"])
        assert a.get(f"/reader/page/{env['series_page']}/image", headers=env["ha"]).status_code == 200

        factory = sessionmaker(bind=db_engine, autoflush=False, autocommit=False)
        db = factory()
        try:
            db.get(Series, env["series"]).content_rating = "hentai"
            db.commit()
        finally:
            db.close()

        assert a.get(f"/reader/page/{env['series_page']}/image", headers=env["ha"]).status_code == 404
        assert a.get(f"/library/pages/{env['series_page']}/image", headers=env["ha"]).status_code == 404

    # --- the unified source reader (/sources/.../reader) ----------------------

    def test_source_reader_serves_the_local_copy_to_the_claiming_account(
        self, env, db_engine
    ):
        a = env["a"]
        a.post(f"/library/series/{env['series']}/add", headers=env["ha"])
        _link_source_chapter(db_engine, env["series_chapter"])

        payload = a.get(
            "/sources/mangadex/series/remote-1/chapters/remote-c1/reader",
            headers=env["ha"],
        )
        assert payload.status_code == 200, payload.text
        assert payload.json()["mode"] == "local"

    def test_source_reader_falls_through_to_the_source_for_a_non_owner(
        self, env, db_engine
    ):
        """Someone else having downloaded the chapter must not take away a read
        that browsing the source always allowed -- the local copy is a shortcut,
        not an entitlement, so a caller with no claim streams from the source
        instead of getting a 404."""
        a, b = env["a"], env["b"]
        a.post(f"/library/series/{env['series']}/add", headers=env["ha"])
        _link_source_chapter(db_engine, env["series_chapter"])

        remote = {"mode": "remote", "id": "remote-c1", "pages": []}
        with patch(
            "services.browse_service.BrowseService.get_reader_chapter",
            return_value=remote,
        ) as fetch:
            response = b.get(
                "/sources/mangadex/series/remote-1/chapters/remote-c1/reader",
                headers=env["hb"],
            )
        assert response.status_code == 200, response.text
        assert response.json()["mode"] == "remote"
        assert fetch.called


def _link_source_chapter(db_engine, local_chapter_id: int) -> None:
    factory = sessionmaker(bind=db_engine, autoflush=False, autocommit=False)
    db = factory()
    try:
        db.add(
            SourceChapterLink(
                source="mangadex",
                series_id="remote-1",
                chapter_id="remote-c1",
                local_chapter_id=local_chapter_id,
            )
        )
        db.commit()
    finally:
        db.close()


# ---------------------------------------------------------------------------
# Service level: downloads, and the background/no-context callers
# ---------------------------------------------------------------------------


def _seed_series(db: Session) -> int:
    lib = Library(name="Main", root_path="/lib")
    db.add(lib)
    db.flush()
    series = Series(
        library_id=lib.id,
        title="Solo Leveling",
        folder_path="/lib/solo",
        sort_title="solo leveling",
        content_rating="safe",
    )
    db.add(series)
    db.flush()
    chapter = Chapter(
        series_id=series.id, title="Ch1", number=1.0, page_count=1, sort_key="0001"
    )
    db.add(chapter)
    db.flush()
    db.add(Page(chapter_id=chapter.id, number=1, file_path="/lib/solo/1/001.jpg"))
    db.commit()
    return series.id


def test_a_downloaded_series_is_readable_by_the_profile_that_downloaded_it(
    db_session: Session,
):
    """The membership row a completed download creates (0dd7397) is exactly the
    claim the predicate looks for."""
    series_id = _seed_series(db_session)
    db_session.add(
        UserSeriesState(user_id=7, profile_id=3, series_id=series_id, in_library=True)
    )
    db_session.commit()

    assert LibraryService(db_session, user_id=7, profile_id=3).get_series(series_id)
    # ...and by the account's other profile, which shares the filesystem.
    assert LibraryService(db_session, user_id=7, profile_id=9).get_series(series_id)


def test_a_legacy_null_profile_download_is_still_readable_by_its_account(
    db_session: Session,
):
    """A download queued before ``downloads.profile_id`` existed files its
    membership at (account, NULL). A profile-scoped predicate would deny every
    profile on the account -- including the person who downloaded it."""
    from core.errors import AppError

    series_id = _seed_series(db_session)
    db_session.add(
        UserSeriesState(user_id=7, profile_id=None, series_id=series_id, in_library=True)
    )
    db_session.commit()

    assert LibraryService(db_session, user_id=7, profile_id=4).get_series(series_id)
    with pytest.raises(AppError) as denied:
        LibraryService(db_session, user_id=8, profile_id=None).get_series(series_id)
    assert denied.value.status_code == 404


def test_the_unscoped_background_caller_still_reads_unowned_content(db_session: Session):
    """The download worker and the update scheduler build services with no user
    context by design. They stay scoped to the NULL bucket rather than exempt."""
    series_id = _seed_series(db_session)
    db_session.add(
        UserSeriesState(
            user_id=None, profile_id=None, series_id=series_id, in_library=True
        )
    )
    db_session.commit()

    assert LibraryService(db_session).get_series(series_id)


def test_the_unscoped_caller_is_scoped_not_exempt(db_session: Session):
    """The failure mode to avoid: implementing the unscoped case as an early
    ``return True`` would look like a passing suite while proving nothing, and
    would hand a bypass to any future path that loses its context."""
    from core.errors import AppError

    series_id = _seed_series(db_session)
    db_session.add(
        UserSeriesState(user_id=5, profile_id=1, series_id=series_id, in_library=True)
    )
    db_session.commit()

    with pytest.raises(AppError) as denied:
        LibraryService(db_session).get_series(series_id)
    assert denied.value.status_code == 404
    assert denied.value.code == "series_not_found"


def test_a_series_with_no_claim_at_all_is_readable_by_nobody(db_session: Session):
    from core.errors import AppError

    series_id = _seed_series(db_session)
    for user_id in (None, 1, 2):
        with pytest.raises(AppError):
            LibraryService(db_session, user_id=user_id).get_series(series_id)


def test_auto_download_queues_as_the_follower_not_as_nobody(db_session: Session):
    """P1. The tracker row is the only place the follower's identity survives
    into the scheduler; without it the Download is (NULL, NULL), the worker files
    membership in the unowned bucket, and every auto-downloaded chapter -- the
    entire point of following a series -- lands in nobody's library."""
    from connectors.models import Chapter as ConnectorChapter
    from database.models import Download, ReadingProfile, SeriesTracker
    from services.update_auto_download import auto_download_new_chapters

    user = User(username="follower", password_hash="x")
    db_session.add(user)
    db_session.flush()
    profile = ReadingProfile(user_id=user.id, name="Main", sort_order=0)
    db_session.add(profile)
    db_session.flush()
    tracker = SeriesTracker(
        user_id=user.id,
        profile_id=profile.id,
        source="mangadex",
        series_id="series-1",
        series_title="Series",
        track_kind="followed",
        known_chapter_ids='["ch-1"]',
        auto_download=True,
    )
    db_session.add(tracker)
    db_session.commit()

    connector = MagicMock()
    connector.is_browsable = True
    connector.is_mature = False
    connector.get_chapters.return_value = []
    chapters = [
        ConnectorChapter(
            id="ch-2", series_id="series-1", number=2.0, title="Ch2", page_count=3
        )
    ]
    with patch(
        "services.download_service.create_connector", return_value=connector
    ):
        auto_download_new_chapters(db_session, tracker, chapters)

    downloads = db_session.query(Download).all()
    assert len(downloads) == 1
    assert downloads[0].user_id == user.id
    assert downloads[0].profile_id == profile.id
