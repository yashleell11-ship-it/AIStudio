"""Reading history is *written*, not just read.

The bug behind this file: ``LibraryIntelligenceService.get_reading_history``
(and the calendar, the streak, the velocity, pages-this-week, and the per-series
completed-chapter counts) all read ``reading_sessions`` / ``chapter_progress``
— and nothing in the entire backend ever inserted a row into either table. The
history screen was not broken, it was fed by a table no writer existed for, so
it was permanently empty and always would be.

``ReaderService.save_progress`` is now that writer. The interesting part is not
that it writes, it is that it writes a *bounded* number of rows: the endpoint is
called repeatedly while a chapter is read, so the tests below pin the session
boundary rule (extend the open session for the same chapter, roll over after
``READING_SESSION_IDLE_GAP``) as hard as they pin the scoping and the 18+ gate.
"""

from __future__ import annotations

from datetime import timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session, sessionmaker

from core.config import get_settings
from core.time_utils import utcnow
from database.models import (
    Chapter,
    ChapterProgress,
    Library,
    Page,
    ReadingProfile,
    ReadingSession,
    Series,
    User,
    UserSeriesState,
)
from database.session import get_db
from main import create_app
from services.library_intelligence_service import LibraryIntelligenceService
from services.reader_service import READING_SESSION_IDLE_GAP, ReaderService


@pytest.fixture
def db(db_engine) -> Session:
    factory = sessionmaker(bind=db_engine, autoflush=False, autocommit=False)
    session = factory()
    try:
        yield session
    finally:
        session.close()


def _seed_series(
    db: Session,
    *,
    title: str = "Solo Leveling",
    content_rating: str = "safe",
    page_count: int = 10,
    chapters: int = 1,
) -> tuple[Series, list[Chapter]]:
    library = db.query(Library).first()
    if library is None:
        library = Library(name="Main", root_path="/lib")
        db.add(library)
        db.flush()

    series = Series(
        library_id=library.id,
        title=title,
        sort_title=title.lower(),
        folder_path=f"/lib/{title.lower().replace(' ', '-')}",
        content_rating=content_rating,
    )
    db.add(series)
    db.flush()

    made: list[Chapter] = []
    for index in range(1, chapters + 1):
        chapter = Chapter(
            series_id=series.id,
            title=f"Ch{index}",
            number=float(index),
            folder_path=f"{series.folder_path}/ch{index}",
            page_count=page_count,
            sort_key=f"{index:04d}",
        )
        db.add(chapter)
        db.flush()
        for page in range(1, page_count + 1):
            db.add(
                Page(
                    chapter_id=chapter.id,
                    number=page,
                    file_path=f"{chapter.folder_path}/{page:03d}.jpg",
                )
            )
        made.append(chapter)
    db.commit()
    return series, made


def _seed_account(db: Session, *, username: str = "owner") -> tuple[User, ReadingProfile, ReadingProfile]:
    user = User(username=username, password_hash="x", is_admin=True, is_active=True)
    db.add(user)
    db.flush()
    alpha = ReadingProfile(user_id=user.id, name="Alpha")
    beta = ReadingProfile(user_id=user.id, name="Beta")
    db.add_all([alpha, beta])
    db.commit()
    return user, alpha, beta


def _sessions(db: Session, **filters) -> list[ReadingSession]:
    query = db.query(ReadingSession)
    for column, value in filters.items():
        query = query.filter(getattr(ReadingSession, column) == value)
    return query.order_by(ReadingSession.id.asc()).all()


def _backdate(db: Session, session: ReadingSession, delta: timedelta) -> None:
    """Push a session's clock back so the next post lands outside the gap.

    Rewinding the row rather than freezing ``utcnow`` keeps the test honest
    about what the production code actually compares: the stored timestamps.
    """
    session.started_at = session.started_at - delta
    session.ended_at = (session.ended_at or session.started_at) - delta
    db.commit()


class TestSessionBoundaries:
    def test_reading_one_chapter_produces_exactly_one_session(self, db: Session):
        """The whole point of the boundary rule. The client posts progress
        repeatedly through a chapter; that must be one history entry, not ten."""
        series, (chapter,) = _seed_series(db, page_count=10)
        service = ReaderService(db)

        for page in range(1, 11):
            service.save_progress(
                series_id=series.id, chapter_id=chapter.id, last_page=page
            )

        rows = _sessions(db)
        assert len(rows) == 1
        assert rows[0].start_page == 1
        assert rows[0].end_page == 10
        assert rows[0].pages_read == 10
        assert rows[0].started_at <= rows[0].ended_at

    def test_paging_backwards_does_not_shrink_or_inflate_the_session(self, db: Session):
        series, (chapter,) = _seed_series(db, page_count=10)
        service = ReaderService(db)

        for page in (5, 6, 7, 6, 5, 8):
            service.save_progress(
                series_id=series.id, chapter_id=chapter.id, last_page=page
            )

        (row,) = _sessions(db)
        assert (row.start_page, row.end_page, row.pages_read) == (5, 8, 4)

    def test_a_long_gap_starts_a_new_session(self, db: Session):
        series, (chapter,) = _seed_series(db, page_count=10)
        service = ReaderService(db)

        service.save_progress(series_id=series.id, chapter_id=chapter.id, last_page=1)
        service.save_progress(series_id=series.id, chapter_id=chapter.id, last_page=2)
        (first,) = _sessions(db)
        _backdate(db, first, READING_SESSION_IDLE_GAP + timedelta(minutes=5))

        service.save_progress(series_id=series.id, chapter_id=chapter.id, last_page=3)

        rows = _sessions(db)
        assert len(rows) == 2
        assert (rows[0].start_page, rows[0].end_page) == (1, 2)
        assert (rows[1].start_page, rows[1].end_page, rows[1].pages_read) == (3, 3, 1)

    def test_a_short_gap_extends_the_same_session(self, db: Session):
        series, (chapter,) = _seed_series(db, page_count=10)
        service = ReaderService(db)

        service.save_progress(series_id=series.id, chapter_id=chapter.id, last_page=1)
        (first,) = _sessions(db)
        _backdate(db, first, READING_SESSION_IDLE_GAP - timedelta(minutes=1))

        service.save_progress(series_id=series.id, chapter_id=chapter.id, last_page=4)

        rows = _sessions(db)
        assert len(rows) == 1
        assert (rows[0].start_page, rows[0].end_page, rows[0].pages_read) == (1, 4, 4)

    def test_each_chapter_gets_its_own_session(self, db: Session):
        series, (ch1, ch2) = _seed_series(db, page_count=5, chapters=2)
        service = ReaderService(db)

        for page in (1, 2, 3):
            service.save_progress(series_id=series.id, chapter_id=ch1.id, last_page=page)
        for page in (1, 2):
            service.save_progress(series_id=series.id, chapter_id=ch2.id, last_page=page)

        rows = _sessions(db)
        assert len(rows) == 2
        assert {r.chapter_id for r in rows} == {ch1.id, ch2.id}

    def test_returning_to_an_earlier_chapter_resumes_its_open_session(self, db: Session):
        """Session lookup is keyed on the chapter, not on "the latest session",
        so flipping back to the previous chapter mid-sitting must not open a
        third row."""
        series, (ch1, ch2) = _seed_series(db, page_count=5, chapters=2)
        service = ReaderService(db)

        service.save_progress(series_id=series.id, chapter_id=ch1.id, last_page=1)
        service.save_progress(series_id=series.id, chapter_id=ch2.id, last_page=1)
        service.save_progress(series_id=series.id, chapter_id=ch1.id, last_page=3)

        rows = _sessions(db)
        assert len(rows) == 2
        first = next(r for r in rows if r.chapter_id == ch1.id)
        assert (first.start_page, first.end_page) == (1, 3)

    def test_write_amplitude_is_bounded_per_chapter(self, db: Session):
        """Fifty posts through one chapter must leave exactly one session row
        and one chapter-progress row behind. This is the regression that keeps
        the history screen from turning into noise (and single-writer SQLite
        from taking an unbounded row count on every page turn)."""
        series, (chapter,) = _seed_series(db, page_count=50)
        service = ReaderService(db)

        for page in range(1, 51):
            service.save_progress(
                series_id=series.id, chapter_id=chapter.id, last_page=page
            )

        assert db.query(ReadingSession).count() == 1
        assert db.query(ChapterProgress).count() == 1


class TestChapterProgress:
    def test_chapter_progress_is_upserted_and_tracks_the_last_page(self, db: Session):
        series, (chapter,) = _seed_series(db, page_count=10)
        service = ReaderService(db)

        for page in (1, 2, 3):
            service.save_progress(
                series_id=series.id,
                chapter_id=chapter.id,
                last_page=page,
                scroll_offset_px=page * 100,
            )

        rows = db.query(ChapterProgress).all()
        assert len(rows) == 1
        assert rows[0].last_page == 3
        assert rows[0].scroll_offset_px == 300
        assert not rows[0].is_completed

    def test_reaching_the_last_page_completes_the_chapter(self, db: Session):
        series, (chapter,) = _seed_series(db, page_count=3)
        service = ReaderService(db)

        for page in (1, 2, 3):
            service.save_progress(
                series_id=series.id, chapter_id=chapter.id, last_page=page
            )

        (row,) = db.query(ChapterProgress).all()
        assert row.is_completed
        assert row.completed_at is not None

    def test_completion_is_sticky_when_the_reader_pages_back(self, db: Session):
        series, (chapter,) = _seed_series(db, page_count=3)
        service = ReaderService(db)

        service.save_progress(series_id=series.id, chapter_id=chapter.id, last_page=3)
        service.save_progress(series_id=series.id, chapter_id=chapter.id, last_page=1)

        (row,) = db.query(ChapterProgress).all()
        assert row.is_completed
        assert row.last_page == 1

    def test_unindexed_chapter_is_never_trivially_complete(self, db: Session):
        """A chapter whose pages have not been scanned yet has page_count 0;
        page 1 of 0 must not read as 'finished'."""
        series, (chapter,) = _seed_series(db, page_count=0)
        service = ReaderService(db)

        service.save_progress(series_id=series.id, chapter_id=chapter.id, last_page=1)

        (row,) = db.query(ChapterProgress).all()
        assert not row.is_completed

    def test_completed_chapters_feed_the_per_profile_read_count(self, db: Session):
        """``series.read_chapters`` is a global, scan-recomputed column; the
        number a caller actually sees is derived from chapter_progress. Reading
        a chapter must move that number without anyone writing the denormalized
        one."""
        user, alpha, _ = _seed_account(db)
        series, (chapter,) = _seed_series(db, page_count=2)
        db.add(
            UserSeriesState(
                user_id=user.id, profile_id=alpha.id, series_id=series.id, in_library=True
            )
        )
        db.commit()

        service = ReaderService(db, user_id=user.id, profile_id=alpha.id)
        service.save_progress(series_id=series.id, chapter_id=chapter.id, last_page=2)

        intel = LibraryIntelligenceService(db, user_id=user.id, profile_id=alpha.id)
        assert intel._read_chapter_map({series.id}) == {series.id: 1}
        # The shared catalog column is left exactly as the scan wrote it.
        db.refresh(series)
        assert series.read_chapters == 0


class TestScoping:
    def test_sessions_are_scoped_per_profile(self, db: Session):
        user, alpha, beta = _seed_account(db)
        series, (chapter,) = _seed_series(db, page_count=5)

        alpha_reader = ReaderService(db, user_id=user.id, profile_id=alpha.id)
        for page in range(1, 5):
            alpha_reader.save_progress(
                series_id=series.id, chapter_id=chapter.id, last_page=page
            )

        alpha_history = LibraryIntelligenceService(
            db, user_id=user.id, profile_id=alpha.id
        ).get_reading_history()
        beta_history = LibraryIntelligenceService(
            db, user_id=user.id, profile_id=beta.id
        ).get_reading_history()

        assert len(alpha_history) == 1
        assert alpha_history[0]["pages_read"] == 4
        assert beta_history == []

    def test_a_second_profile_reading_opens_its_own_session(self, db: Session):
        user, alpha, beta = _seed_account(db)
        series, (chapter,) = _seed_series(db, page_count=5)

        ReaderService(db, user_id=user.id, profile_id=alpha.id).save_progress(
            series_id=series.id, chapter_id=chapter.id, last_page=2
        )
        ReaderService(db, user_id=user.id, profile_id=beta.id).save_progress(
            series_id=series.id, chapter_id=chapter.id, last_page=2
        )

        assert len(_sessions(db, profile_id=alpha.id)) == 1
        assert len(_sessions(db, profile_id=beta.id)) == 1
        assert db.query(ChapterProgress).count() == 2

    def test_sessions_are_scoped_per_account(self, db: Session):
        owner, owner_profile, _ = _seed_account(db, username="owner")
        other, other_profile, _ = _seed_account(db, username="other")
        series, (chapter,) = _seed_series(db, page_count=5)

        ReaderService(db, user_id=owner.id, profile_id=owner_profile.id).save_progress(
            series_id=series.id, chapter_id=chapter.id, last_page=3
        )

        other_history = LibraryIntelligenceService(
            db, user_id=other.id, profile_id=other_profile.id
        ).get_reading_history()
        assert other_history == []


class TestHistoryAndStatistics:
    def test_history_is_newest_first(self, db: Session):
        series, (ch1, ch2, ch3) = _seed_series(db, page_count=5, chapters=3)
        service = ReaderService(db)

        for chapter in (ch1, ch2, ch3):
            service.save_progress(
                series_id=series.id, chapter_id=chapter.id, last_page=1
            )

        history = LibraryIntelligenceService(db).get_reading_history()
        assert [row["chapter_title"] for row in history] == ["Ch3", "Ch2", "Ch1"]

    def test_history_carries_series_and_chapter_names(self, db: Session):
        series, (chapter,) = _seed_series(db, title="Omniscient Reader", page_count=5)
        ReaderService(db).save_progress(
            series_id=series.id, chapter_id=chapter.id, last_page=5
        )

        (row,) = LibraryIntelligenceService(db).get_reading_history()
        assert row["series_title"] == "Omniscient Reader"
        assert row["chapter_title"] == "Ch1"
        assert row["started_at"] is not None
        assert row["ended_at"] is not None

    def test_statistics_are_non_zero_after_a_read(self, db: Session):
        user, alpha, _ = _seed_account(db)
        series, (chapter,) = _seed_series(db, page_count=6)
        db.add(
            UserSeriesState(
                user_id=user.id, profile_id=alpha.id, series_id=series.id, in_library=True
            )
        )
        db.commit()

        service = ReaderService(db, user_id=user.id, profile_id=alpha.id)
        for page in range(1, 7):
            service.save_progress(
                series_id=series.id, chapter_id=chapter.id, last_page=page
            )

        intel = LibraryIntelligenceService(db, user_id=user.id, profile_id=alpha.id)
        stats = intel.get_statistics()
        assert stats["pages_read_this_week"] == 6
        assert stats["total_reading_time_estimate_minutes"] > 0
        assert stats["reading_streak_days"] == 1
        assert sum(day["pages_read"] for day in stats["weekly_chart"]) == 6

        calendar = intel.get_reading_calendar(days=7)
        today = next(
            day for day in calendar if day["day"] == utcnow().strftime("%Y-%m-%d")
        )
        assert today["pages_read"] == 6
        assert today["sessions"] == 1

    def test_series_history_only_returns_that_series(self, db: Session):
        first, (ch_a,) = _seed_series(db, title="Alpha Series", page_count=5)
        second, (ch_b,) = _seed_series(db, title="Beta Series", page_count=5)
        service = ReaderService(db)
        service.save_progress(series_id=first.id, chapter_id=ch_a.id, last_page=2)
        service.save_progress(series_id=second.id, chapter_id=ch_b.id, last_page=2)

        rows = LibraryIntelligenceService(db).get_series_reading_history(first.id)
        assert len(rows) == 1
        assert rows[0]["chapter_id"] == ch_a.id


class TestMatureGate:
    """The 18+ gate must still hide an adult series' history. History carries
    the series *title*, so a leak here names every adult series the profile has
    read while the grid pretends they do not exist."""

    def test_gate_hides_adult_history_and_restores_it(self, db: Session):
        user, alpha, _ = _seed_account(db)
        adult, (adult_ch,) = _seed_series(
            db, title="Adults Only", content_rating="pornographic", page_count=5
        )
        safe, (safe_ch,) = _seed_series(db, title="Wholesome", page_count=5)

        service = ReaderService(db, user_id=user.id, profile_id=alpha.id)
        service.save_progress(series_id=adult.id, chapter_id=adult_ch.id, last_page=3)
        service.save_progress(series_id=safe.id, chapter_id=safe_ch.id, last_page=3)

        intel = LibraryIntelligenceService(db, user_id=user.id, profile_id=alpha.id)
        assert not alpha.mature_content_enabled
        titles = {row["series_title"] for row in intel.get_reading_history()}
        assert titles == {"Wholesome"}
        assert intel.get_series_reading_history(adult.id) == []

        alpha.mature_content_enabled = True
        db.commit()
        titles = {row["series_title"] for row in intel.get_reading_history()}
        assert titles == {"Wholesome", "Adults Only"}
        assert len(intel.get_series_reading_history(adult.id)) == 1

    def test_gate_hides_history_but_never_deletes_the_rows(self, db: Session):
        user, alpha, _ = _seed_account(db)
        adult, (adult_ch,) = _seed_series(
            db, title="Adults Only", content_rating="hentai", page_count=5
        )

        ReaderService(db, user_id=user.id, profile_id=alpha.id).save_progress(
            series_id=adult.id, chapter_id=adult_ch.id, last_page=2
        )

        intel = LibraryIntelligenceService(db, user_id=user.id, profile_id=alpha.id)
        assert intel.get_reading_history() == []
        assert db.query(ReadingSession).count() == 1


@pytest.mark.real_auth
class TestOverHttp:
    """One end-to-end pass over the real stack: the reader posts progress with
    an active profile, and the history endpoint the app calls comes back with
    it. The service tests above cover the rules; this proves the wiring."""

    @pytest.fixture
    def env(self, db_engine, monkeypatch):
        monkeypatch.setenv("MM_COOKIE_SECURE", "false")
        get_settings.cache_clear()

        factory = sessionmaker(bind=db_engine, autoflush=False, autocommit=False)

        def override_get_db():
            session = factory()
            try:
                yield session
            finally:
                session.close()

        app = create_app(run_migrations=False, run_workers=False)
        app.dependency_overrides[get_db] = override_get_db
        client = TestClient(app)

        registration = client.post(
            "/auth/register", json={"username": "owner", "password": "supersecret"}
        )
        assert registration.status_code in (200, 201), registration.text
        user_id = registration.json()["user"]["id"]
        alpha = client.post("/profiles", json={"name": "Alpha"}).json()
        beta = client.post("/profiles", json={"name": "Beta"}).json()

        session = factory()
        try:
            series, (chapter,) = _seed_series(session, page_count=8)
            session.add_all(
                UserSeriesState(
                    user_id=user_id,
                    profile_id=profile_id,
                    series_id=series.id,
                    in_library=True,
                )
                for profile_id in (alpha["id"], beta["id"])
            )
            session.commit()
            ids = {"series": series.id, "chapter": chapter.id}
        finally:
            session.close()

        yield {
            "client": client,
            "factory": factory,
            "alpha": alpha["id"],
            "beta": beta["id"],
            **ids,
        }
        get_settings.cache_clear()

    def test_progress_posts_become_one_history_entry_for_that_profile(self, env):
        client = env["client"]
        alpha = {"X-Profile-Id": str(env["alpha"])}
        beta = {"X-Profile-Id": str(env["beta"])}

        for page in range(1, 9):
            response = client.post(
                "/reader/progress",
                json={
                    "series_id": env["series"],
                    "chapter_id": env["chapter"],
                    "last_page": page,
                },
                headers=alpha,
            )
            assert response.status_code == 200, response.text

        history = client.get("/library/reading-history", headers=alpha)
        assert history.status_code == 200, history.text
        rows = history.json()
        assert len(rows) == 1
        assert rows[0]["pages_read"] == 8
        assert rows[0]["chapter_id"] == env["chapter"]

        assert client.get("/library/reading-history", headers=beta).json() == []

    def test_statistics_endpoint_reports_the_read(self, env):
        client = env["client"]
        alpha = {"X-Profile-Id": str(env["alpha"])}

        for page in range(1, 5):
            client.post(
                "/reader/progress",
                json={
                    "series_id": env["series"],
                    "chapter_id": env["chapter"],
                    "last_page": page,
                },
                headers=alpha,
            )

        stats = client.get("/library/statistics", headers=alpha)
        assert stats.status_code == 200, stats.text
        assert stats.json()["pages_read_this_week"] == 4
