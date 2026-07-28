"""A local series knows where it came from, and whether you follow it.

The gap this pins down, in the owner's words: opening a downloaded chapter and
tapping back lands on the *local* series page, "but there is no follow option on
there". Follow lived only on the source-browse page, so the one series a user
cared enough to download was the one series that got no update checks and no
new-chapter notifications.

The data was always there -- the download pipeline writes ``source_chapter_links``
-- but the detail payload only ever named the source as a side effect of a
successful catalog *fetch*. Dead connector, offline, rate-limited: ``source_id``
came back null and the client had nothing to build a Follow button on. These
tests fix the source identity to the local rows, and fix the follow flag to
(user, profile) so one profile's follow is never rendered as another's.
"""

from __future__ import annotations

import pytest
from sqlalchemy import event
from sqlalchemy.orm import Session, sessionmaker

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
from services.library_intelligence_service import LibraryIntelligenceService
from services.library_service import LibraryService
from services.update_service import UpdateService

# A real, installed, non-mature connector: UpdateService.follow_series refuses
# anything not in the browsable registry, so the follow half of these tests has
# to name a source that actually exists. No network is ever reached -- every
# test that could trigger a catalog fetch stubs SourceService.get_chapters.
SOURCE = "mangadex"
SOURCE_SERIES_ID = "abc-123"


@pytest.fixture
def db(db_engine):
    session_factory = sessionmaker(bind=db_engine, autoflush=False, autocommit=False)
    session = session_factory()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    """No test here may reach a connector.

    The default is the dead-source case on purpose: it is the common one (half
    the registry is dead) and it is exactly the case that used to blank out the
    source identity. Tests that want a live catalog re-stub this themselves.
    """
    from services import source_service

    def _explode(self, series_id, **config):  # noqa: ANN001, ARG001
        raise RuntimeError(f"connector for {self._source_type} is unreachable")

    monkeypatch.setattr(source_service.SourceService, "get_chapters", _explode)


def _seed_user(db: Session, username: str) -> User:
    user = User(username=username, password_hash="x", is_admin=True, is_active=True)
    db.add(user)
    db.flush()
    return user


def _seed_profile(db: Session, user: User, name: str) -> ReadingProfile:
    profile = ReadingProfile(user_id=user.id, name=name)
    db.add(profile)
    db.flush()
    return profile


def _seed_library(db: Session) -> Library:
    lib = Library(name="Main", root_path="/tmp/mm-test")
    db.add(lib)
    db.flush()
    return lib


def _seed_series(
    db: Session,
    lib: Library,
    title: str,
    *,
    owners: list[tuple[int | None, int | None]],
    chapter_count: int = 1,
) -> Series:
    """A catalog series claimed by each (user_id, profile_id) in ``owners``.

    The claim rows matter: object-level read authorization (core.library_authz)
    is what stands between a caller and this payload, and a series nobody on the
    account claimed must stay unreadable -- source identity included.
    """
    series = Series(library_id=lib.id, title=title, folder_path=f"/tmp/mm-test/{title}")
    db.add(series)
    db.flush()
    for index in range(chapter_count):
        db.add(
            Chapter(
                series_id=series.id,
                title=f"Chapter {index + 1}",
                number=index + 1,
                folder_path=f"{series.folder_path}/{index + 1}",
                sort_key=f"{index + 1:04d}.000",
                page_count=2,
            )
        )
    for user_id, profile_id in owners:
        db.add(
            UserSeriesState(
                user_id=user_id,
                profile_id=profile_id,
                series_id=series.id,
                in_library=True,
            )
        )
    db.flush()
    return series


def _link_to_source(
    db: Session,
    series: Series,
    *,
    source: str = SOURCE,
    source_series_id: str = SOURCE_SERIES_ID,
) -> None:
    """Make ``series`` look downloaded: one source_chapter_links row per chapter.

    This is what the download pipeline writes, and (per alembic
    a7c3e51b90d4 and core.content_rating) the only linkage that is ever written
    -- ``series_trackers.local_series_id`` is not populated by any code path,
    which is why the fallback branch is the one carrying real traffic.
    """
    chapters = db.query(Chapter).filter(Chapter.series_id == series.id).all()
    for index, chapter in enumerate(chapters):
        db.add(
            SourceChapterLink(
                source=source,
                series_id=source_series_id,
                chapter_id=f"src-ch-{index + 1}",
                local_chapter_id=chapter.id,
            )
        )
    db.flush()


class TestSourceIdentityOnTheLocalSeriesPage:
    def test_downloaded_series_reports_its_source(self, db: Session):
        user = _seed_user(db, "owner")
        profile = _seed_profile(db, user, "Main")
        lib = _seed_library(db)
        series = _seed_series(db, lib, "Solo", owners=[(user.id, profile.id)])
        _link_to_source(db, series)

        intel = LibraryIntelligenceService(db, user_id=user.id, profile_id=profile.id)
        detail = intel.get_series_detail(series.id)

        assert detail["source_id"] == SOURCE
        assert detail["source_series_id"] == SOURCE_SERIES_ID
        # Not followed yet -- downloading is not following, which is the whole
        # reason the button has to appear here.
        assert detail["is_followed"] is False
        assert detail["follow_tracker_id"] is None

    def test_hand_imported_folder_reports_no_source(self, db: Session):
        """A CBZ folder dragged in by hand has genuinely nothing to track."""
        user = _seed_user(db, "owner")
        profile = _seed_profile(db, user, "Main")
        lib = _seed_library(db)
        series = _seed_series(db, lib, "Scanned Shelf", owners=[(user.id, profile.id)])

        intel = LibraryIntelligenceService(db, user_id=user.id, profile_id=profile.id)
        detail = intel.get_series_detail(series.id)

        assert detail["source_id"] is None
        assert detail["source_series_id"] is None
        assert detail["is_followed"] is False
        assert detail["follow_tracker_id"] is None

    def test_source_identity_survives_a_dead_source(self, db: Session):
        """The regression this change exists for.

        ``source_id`` used to be a by-product of the catalog merge, so a source
        that was dead, offline or rate-limited -- the autouse stub here -- blanked
        it out and the client could not offer Follow. The link is a local row; it
        must not need the network to be true. Chapters still degrade to local.
        """
        user = _seed_user(db, "owner")
        profile = _seed_profile(db, user, "Main")
        lib = _seed_library(db)
        series = _seed_series(
            db, lib, "Dead Source", owners=[(user.id, profile.id)], chapter_count=3
        )
        _link_to_source(db, series)

        intel = LibraryIntelligenceService(db, user_id=user.id, profile_id=profile.id)
        detail = intel.get_series_detail(series.id)

        assert detail["source_id"] == SOURCE
        assert detail["source_series_id"] == SOURCE_SERIES_ID
        assert len(detail["chapters"]) == 3
        assert all(c["is_downloaded"] for c in detail["chapters"])

    def test_live_source_reports_the_same_identity_it_merges_on(
        self, db: Session, monkeypatch
    ):
        """One resolution, one identity: the merged catalog and the reported
        source id are the same tuple by construction, never two lookups that can
        disagree."""
        from connectors.models import Chapter as ConnectorChapter
        from services import source_service

        def _catalog(self, series_id, **config):  # noqa: ANN001, ARG001
            assert series_id == SOURCE_SERIES_ID
            return [
                ConnectorChapter(
                    id="src-ch-1",
                    series_id=SOURCE_SERIES_ID,
                    title="Chapter 1",
                    number=1.0,
                    page_count=2,
                ),
                ConnectorChapter(
                    id="src-ch-2",
                    series_id=SOURCE_SERIES_ID,
                    title="Chapter 2",
                    number=2.0,
                    page_count=2,
                ),
            ]

        monkeypatch.setattr(source_service.SourceService, "get_chapters", _catalog)

        user = _seed_user(db, "owner")
        profile = _seed_profile(db, user, "Main")
        lib = _seed_library(db)
        series = _seed_series(db, lib, "Live", owners=[(user.id, profile.id)])
        _link_to_source(db, series)

        intel = LibraryIntelligenceService(db, user_id=user.id, profile_id=profile.id)
        detail = intel.get_series_detail(series.id)

        assert detail["source_id"] == SOURCE
        assert detail["source_series_id"] == SOURCE_SERIES_ID
        # The second, undownloaded chapter is only visible via the merge, which
        # proves the merge ran off the same identity that got reported.
        assert [c["is_downloaded"] for c in detail["chapters"]] == [True, False]


class TestFollowState:
    def test_following_shows_up_on_the_local_series_page(self, db: Session):
        user = _seed_user(db, "owner")
        profile = _seed_profile(db, user, "Main")
        lib = _seed_library(db)
        series = _seed_series(db, lib, "Solo", owners=[(user.id, profile.id)])
        _link_to_source(db, series)

        intel = LibraryIntelligenceService(db, user_id=user.id, profile_id=profile.id)
        assert intel.get_series_detail(series.id)["is_followed"] is False

        tracker = UpdateService(db, user_id=user.id, profile_id=profile.id).follow_series(
            source=SOURCE, series_id=SOURCE_SERIES_ID, series_title="Solo"
        )

        detail = intel.get_series_detail(series.id)
        assert detail["is_followed"] is True
        # The tracker id ships with the flag so Unfollow
        # (DELETE /updates/trackers/{id}) costs no extra round trip.
        assert detail["follow_tracker_id"] == tracker["id"]

    def test_follow_is_scoped_per_profile(self, db: Session):
        """One account, two profiles, one downloaded series.

        Follows are per-(user, profile) -- uq_series_tracker says so and the
        notification the check produces is stamped with the tracker's own owner.
        Reporting profile A's follow to profile B would show B an Unfollow button
        for something it never followed and will never be notified about.
        """
        user = _seed_user(db, "owner")
        kid = _seed_profile(db, user, "Kid")
        grown = _seed_profile(db, user, "Grown")
        lib = _seed_library(db)
        series = _seed_series(
            db, lib, "Solo", owners=[(user.id, kid.id), (user.id, grown.id)]
        )
        _link_to_source(db, series)

        UpdateService(db, user_id=user.id, profile_id=kid.id).follow_series(
            source=SOURCE, series_id=SOURCE_SERIES_ID, series_title="Solo"
        )

        kid_detail = LibraryIntelligenceService(
            db, user_id=user.id, profile_id=kid.id
        ).get_series_detail(series.id)
        grown_detail = LibraryIntelligenceService(
            db, user_id=user.id, profile_id=grown.id
        ).get_series_detail(series.id)

        assert kid_detail["is_followed"] is True
        assert grown_detail["is_followed"] is False
        assert grown_detail["follow_tracker_id"] is None
        # Both still see where the series came from: the origin is a property of
        # the series, not of who is looking at it.
        assert grown_detail["source_id"] == SOURCE
        assert grown_detail["source_series_id"] == SOURCE_SERIES_ID

    def test_follow_is_scoped_per_account(self, db: Session):
        """Two accounts that both claimed the same catalog series."""
        alice = _seed_user(db, "alice")
        bob = _seed_user(db, "bob")
        alice_profile = _seed_profile(db, alice, "Main")
        bob_profile = _seed_profile(db, bob, "Main")
        lib = _seed_library(db)
        series = _seed_series(
            db,
            lib,
            "Solo",
            owners=[(alice.id, alice_profile.id), (bob.id, bob_profile.id)],
        )
        _link_to_source(db, series)

        UpdateService(db, user_id=alice.id, profile_id=alice_profile.id).follow_series(
            source=SOURCE, series_id=SOURCE_SERIES_ID, series_title="Solo"
        )

        bob_detail = LibraryIntelligenceService(
            db, user_id=bob.id, profile_id=bob_profile.id
        ).get_series_detail(series.id)
        assert bob_detail["is_followed"] is False
        assert bob_detail["follow_tracker_id"] is None

    def test_a_downloaded_tracker_is_not_a_follow(self, db: Session):
        """``sync_downloaded_trackers`` writes a ``downloaded`` tracker for every
        downloaded series. If track_kind were ignored, every downloaded series
        would render as already-followed -- hiding the button on exactly the
        series this field exists to surface it for."""
        user = _seed_user(db, "owner")
        profile = _seed_profile(db, user, "Main")
        lib = _seed_library(db)
        series = _seed_series(db, lib, "Solo", owners=[(user.id, profile.id)])
        _link_to_source(db, series)
        db.add(
            SeriesTracker(
                user_id=user.id,
                profile_id=profile.id,
                source=SOURCE,
                series_id=SOURCE_SERIES_ID,
                series_title="Solo",
                track_kind="downloaded",
            )
        )
        db.flush()

        intel = LibraryIntelligenceService(db, user_id=user.id, profile_id=profile.id)
        detail = intel.get_series_detail(series.id)
        assert detail["is_followed"] is False
        assert detail["follow_tracker_id"] is None


class TestResolverParity:
    """The detail path resolves the source link with the intelligence service's
    own resolver (it reuses the chapters already loaded, and importing
    LibraryService here is the cycle the duplicated helpers exist to dodge).
    Two resolvers that can disagree about where a series came from is the bug
    this project keeps re-growing, so pin them against each other: the cover
    route (image_service -> LibraryService.resolve_source_link) and the series
    page must never name different origins.
    """

    def _both(self, db: Session, series: Series) -> tuple[object, object]:
        intel = LibraryIntelligenceService(db)
        chapters = db.query(Chapter).filter(Chapter.series_id == series.id).all()
        return (
            intel._resolve_source_link(series, chapters),
            LibraryService(db).resolve_source_link(series.id),
        )

    def test_agree_on_a_chapter_linked_series(self, db: Session):
        lib = _seed_library(db)
        series = _seed_series(db, lib, "Solo", owners=[(None, None)], chapter_count=2)
        _link_to_source(db, series)
        intel_result, library_result = self._both(db, series)
        assert intel_result == library_result == (SOURCE, SOURCE_SERIES_ID)

    def test_agree_on_a_tracker_linked_series(self, db: Session):
        lib = _seed_library(db)
        series = _seed_series(db, lib, "Solo", owners=[(None, None)])
        db.add(
            SeriesTracker(
                source="other-source",
                series_id="tracker-999",
                series_title="Solo",
                track_kind="followed",
                local_series_id=series.id,
            )
        )
        db.flush()
        intel_result, library_result = self._both(db, series)
        assert intel_result == library_result == ("other-source", "tracker-999")

    def test_agree_that_a_hand_imported_series_has_no_source(self, db: Session):
        lib = _seed_library(db)
        series = _seed_series(db, lib, "Scanned Shelf", owners=[(None, None)])
        intel_result, library_result = self._both(db, series)
        assert intel_result is library_result is None


class TestCost:
    def test_detail_query_count_does_not_grow_with_chapters(self, db: Session):
        """resolve-the-source hits source_chapter_links; it must stay one probe
        for the series, not one per chapter."""
        user = _seed_user(db, "owner")
        profile = _seed_profile(db, user, "Main")
        lib = _seed_library(db)
        small = _seed_series(db, lib, "Small", owners=[(user.id, profile.id)], chapter_count=1)
        big = _seed_series(db, lib, "Big", owners=[(user.id, profile.id)], chapter_count=40)
        _link_to_source(db, small)
        _link_to_source(db, big, source_series_id="big-1")
        db.commit()

        intel = LibraryIntelligenceService(db, user_id=user.id, profile_id=profile.id)

        def _statements(series_id: int) -> list[str]:
            recorded: list[str] = []

            def _record(conn, cursor, statement, *args):  # noqa: ANN001, ARG001
                recorded.append(statement)

            db.expire_all()
            event.listen(db.get_bind(), "after_cursor_execute", _record)
            try:
                intel.get_series_detail(series_id)
            finally:
                event.remove(db.get_bind(), "after_cursor_execute", _record)
            return recorded

        one_chapter = _statements(small.id)
        forty_chapters = _statements(big.id)
        assert len(one_chapter) == len(forty_chapters)

        # And the shape of that constant: source_chapter_links is probed once for
        # the whole series (an IN over the chapters already loaded), not once per
        # chapter and not a second time inside the catalog merge -- the merge is
        # handed the identity the payload already resolved.
        assert sum("source_chapter_links" in s for s in forty_chapters) == 1
        # Two tracker reads at most: the resolver's first branch, then the
        # (user, profile) follow lookup. Never one per chapter.
        assert sum("series_trackers" in s for s in forty_chapters) <= 2


class TestAuthorization:
    """The source identity is part of the payload the object-level read check
    (core.library_authz) and the 18+ gate guard. Neither may be weakened by
    adding a field, and both entrances to the serializer are covered -- GET and
    the PATCH that returns the same detail body.
    """

    def _foreign_reader(self, db: Session, series: Series) -> LibraryIntelligenceService:
        stranger = _seed_user(db, "stranger")
        stranger_profile = _seed_profile(db, stranger, "Main")
        return LibraryIntelligenceService(
            db, user_id=stranger.id, profile_id=stranger_profile.id
        )

    def test_unclaimed_caller_gets_no_source_identity(self, db: Session):
        from core.errors import AppError

        owner = _seed_user(db, "owner")
        owner_profile = _seed_profile(db, owner, "Main")
        lib = _seed_library(db)
        series = _seed_series(db, lib, "Solo", owners=[(owner.id, owner_profile.id)])
        _link_to_source(db, series)

        with pytest.raises(AppError) as excinfo:
            self._foreign_reader(db, series).get_series_detail(series.id)
        assert excinfo.value.status_code == 404
        assert excinfo.value.code == "series_not_found"

    def test_patch_is_not_a_side_door_onto_the_source_identity(self, db: Session):
        """``update_series_metadata`` ends by returning the same detail body, so
        it carries the same fields and needs the same gate."""
        from core.errors import AppError

        owner = _seed_user(db, "owner")
        owner_profile = _seed_profile(db, owner, "Main")
        lib = _seed_library(db)
        series = _seed_series(db, lib, "Solo", owners=[(owner.id, owner_profile.id)])
        _link_to_source(db, series)

        with pytest.raises(AppError) as excinfo:
            self._foreign_reader(db, series).update_series_metadata(
                series.id, title="Renamed"
            )
        assert excinfo.value.status_code == 404
        assert excinfo.value.code == "series_not_found"

    def test_mature_gate_still_hides_the_series_whole(self, db: Session):
        from core.errors import AppError

        owner = _seed_user(db, "owner")
        owner_profile = _seed_profile(db, owner, "Main")  # mature off by default
        lib = _seed_library(db)
        series = _seed_series(db, lib, "Adult", owners=[(owner.id, owner_profile.id)])
        series.content_rating = "mature"
        _link_to_source(db, series)
        db.flush()

        intel = LibraryIntelligenceService(db, user_id=owner.id, profile_id=owner_profile.id)
        with pytest.raises(AppError) as excinfo:
            intel.get_series_detail(series.id)
        assert excinfo.value.status_code == 404

        owner_profile.mature_content_enabled = True
        db.flush()
        detail = intel.get_series_detail(series.id)
        assert detail["source_id"] == SOURCE
