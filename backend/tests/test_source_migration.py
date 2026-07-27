"""Repointing a followed series at another source.

Sources die constantly, and a follow whose source has gone dark is dead weight:
the user has to unfollow, find the series somewhere else, follow again, and lose
their place. This is the server half of doing it properly.

The constraint that shapes everything: online reading progress for a
non-downloaded remote series does NOT exist on the server. ``ReadingProgress``
and ``ChapterProgress`` key on LOCAL chapter ids; remote progress lives only in
the client's own store. So the endpoint's job is to return a chapter-id remap
(by NUMBER -- the only axis comparable across sources) that the client replays
over its own store, plus to rewrite every server-side row that names the old
(source, series_id).
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session, sessionmaker

from connectors.models import Chapter as ConnectorChapter
from connectors.registry import ConnectorDescriptor
from core.errors import AppError
from database.models import (
    Chapter,
    Library,
    Series,
    SeriesTracker,
    SourceChapterLink,
    UpdateNotification,
)
from database.session import get_db
from main import create_app
from services.update_service import UpdateService

OLD = "deadscans"
NEW = "mangadex"
ADULT = "toonily"


# ---------------------------------------------------------------------------
# Test doubles
# ---------------------------------------------------------------------------


def _chapter(chapter_id: str, number: float | None) -> ConnectorChapter:
    label = "extra" if number is None else f"{number:g}"
    return ConnectorChapter(
        id=chapter_id,
        series_id="s",
        title=f"Chapter {label}",
        number=number,
        page_count=10,
    )


def _descriptor(source_type: str, *, mature: bool = False) -> ConnectorDescriptor:
    return ConnectorDescriptor(
        source_type=source_type,
        name=source_type.title(),
        description="",
        browsable=True,
        supports_import=False,
        mature=mature,
    )


def _fake_list_installed(descriptors: list[ConnectorDescriptor]):
    def _fake(*, browsable_only: bool = False, include_mature: bool = True):
        out = list(descriptors)
        if browsable_only:
            out = [d for d in out if d.browsable]
        if not include_mature:
            out = [d for d in out if not d.mature]
        return out

    return _fake


class _Catalogs:
    """Dispatches ``create_connector(source)`` to a canned chapter list.

    A source mapped to ``None`` raises on ``get_chapters`` -- that is the dead
    source this whole feature exists for.
    """

    def __init__(self, catalogs: dict[str, list[ConnectorChapter] | None]) -> None:
        self._catalogs = catalogs

    def __call__(self, source: str, **_: object):
        chapters = self._catalogs.get(source, [])
        connector = MagicMock()
        connector.is_browsable = True
        connector.is_mature = False
        if chapters is None:
            connector.get_chapters.side_effect = OSError("source is gone")
        else:
            connector.get_chapters.return_value = list(chapters)
        return connector


def _env(
    catalogs: dict[str, list[ConnectorChapter] | None],
    *,
    descriptors: list[ConnectorDescriptor] | None = None,
):
    """Patch the registry + connector factory for the duration of a block."""
    descriptors = descriptors or [_descriptor(OLD), _descriptor(NEW)]
    return (
        patch(
            "services.update_service.list_installed_connectors",
            _fake_list_installed(descriptors),
        ),
        patch("services.update_service.create_connector", _Catalogs(catalogs)),
    )


def _seed_tracker(db: Session, **overrides) -> SeriesTracker:
    fields = {
        "source": OLD,
        "series_id": "old-series",
        "series_title": "Solo Leveling",
        "track_kind": "followed",
        "known_chapter_ids": '["old-1", "old-2", "old-3"]',
    }
    fields.update(overrides)
    row = SeriesTracker(**fields)
    db.add(row)
    db.flush()
    db.commit()
    return row


# Old source: chapters 1, 2, 3. Target: the same three, different ids.
_OLD_CATALOG = [_chapter("old-1", 1.0), _chapter("old-2", 2.0), _chapter("old-3", 3.0)]
_NEW_CATALOG = [_chapter("new-a", 1.0), _chapter("new-b", 2.0), _chapter("new-c", 3.0)]


@pytest.fixture
def db_session(db_engine) -> Session:
    factory = sessionmaker(bind=db_engine, autoflush=False, autocommit=False)
    session = factory()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def service(db_session) -> UpdateService:
    return UpdateService(db_session)


# ---------------------------------------------------------------------------
# Chapter mapping (by number)
# ---------------------------------------------------------------------------


def test_chapter_map_matches_by_number_not_by_id(service, db_session):
    tracker = _seed_tracker(db_session)
    p_installed, p_connector = _env({OLD: _OLD_CATALOG, NEW: _NEW_CATALOG})
    with p_installed, p_connector:
        plan = service.plan_migration(
            tracker.id, target_source=NEW, target_series_id="new-series"
        )

    assert [(e["from_chapter_id"], e["to_chapter_id"], e["match"]) for e in plan["chapter_map"]] == [
        ("old-1", "new-a", "exact"),
        ("old-2", "new-b", "exact"),
        ("old-3", "new-c", "exact"),
    ]
    assert plan["counts"] == {"old": 3, "new": 3, "matched": 3, "dropped": 0}
    assert plan["old_catalog"] == "ok"


def test_decimal_chapters_are_kept_distinct(service, db_session):
    """.5 chapters are real extras; collapsing them onto the integer would move
    the reader's position into a chapter they never opened."""
    tracker = _seed_tracker(db_session)
    old = [_chapter("o1", 1.0), _chapter("o1.5", 1.5), _chapter("o2", 2.0)]
    new = [_chapter("n1", 1.0), _chapter("n1.5", 1.50), _chapter("n2", 2.0)]
    p_installed, p_connector = _env({OLD: old, NEW: new})
    with p_installed, p_connector:
        plan = service.plan_migration(
            tracker.id, target_source=NEW, target_series_id="new-series"
        )

    by_from = {e["from_chapter_id"]: e for e in plan["chapter_map"]}
    assert by_from["o1.5"]["to_chapter_id"] == "n1.5"
    assert by_from["o1.5"]["match"] == "exact"
    assert by_from["o2"]["to_chapter_id"] == "n2"


def test_nearest_match_only_ever_snaps_backwards(service, db_session):
    """Snapping forward marks unread content as read and cannot be undone from
    the client; snapping back at worst re-shows one chapter."""
    tracker = _seed_tracker(db_session)
    old = [_chapter("o-low", 1.0), _chapter("o-mid", 3.0), _chapter("o-far", 90.0)]
    # Target starts at 2.0 (so 1.0 has nothing at or below it) and has 2.5 but
    # no 3.0 (so 3.0 snaps back to 2.5). 90.0 is far beyond the tolerance.
    new = [_chapter("n-2", 2.0), _chapter("n-2.5", 2.5)]
    p_installed, p_connector = _env({OLD: old, NEW: new})
    with p_installed, p_connector:
        plan = service.plan_migration(
            tracker.id, target_source=NEW, target_series_id="new-series"
        )

    by_from = {e["from_chapter_id"]: e for e in plan["chapter_map"]}
    assert by_from["o-low"]["to_chapter_id"] is None  # never snaps forward to 2.0
    assert by_from["o-low"]["match"] == "none"
    assert (by_from["o-mid"]["to_chapter_id"], by_from["o-mid"]["match"]) == ("n-2.5", "nearest")
    assert by_from["o-far"]["to_chapter_id"] is None  # outside tolerance
    assert plan["counts"]["dropped"] == 2
    assert any("no equivalent" in w for w in plan["warnings"])


def test_unnumbered_chapters_are_reported_not_guessed(service, db_session):
    tracker = _seed_tracker(db_session)
    old = [_chapter("o1", 1.0), _chapter("o-extra", None)]
    p_installed, p_connector = _env({OLD: old, NEW: _NEW_CATALOG})
    with p_installed, p_connector:
        plan = service.plan_migration(
            tracker.id, target_source=NEW, target_series_id="new-series"
        )

    by_from = {e["from_chapter_id"]: e for e in plan["chapter_map"]}
    assert by_from["o-extra"] == {
        "from_chapter_id": "o-extra",
        "number": None,
        "to_chapter_id": None,
        "match": "none",
    }
    assert "o-extra" in plan["unmatched_source_chapters"]


def test_chapter_offset_realigns_a_renumbered_target(service, db_session):
    """The target restarts numbering per season: its 1..3 are the old 101..103."""
    tracker = _seed_tracker(db_session)
    old = [_chapter("o101", 101.0), _chapter("o102", 102.0), _chapter("o103", 103.0)]
    new = [_chapter("n1", 1.0), _chapter("n2", 2.0), _chapter("n3", 3.0)]
    p_installed, p_connector = _env({OLD: old, NEW: new})
    with p_installed, p_connector:
        without = service.plan_migration(
            tracker.id, target_source=NEW, target_series_id="new-series"
        )
        with_offset = service.plan_migration(
            tracker.id,
            target_source=NEW,
            target_series_id="new-series",
            chapter_offset=-100.0,
        )

    assert without["counts"]["matched"] == 0
    assert with_offset["counts"]["matched"] == 3
    assert [e["to_chapter_id"] for e in with_offset["chapter_map"]] == ["n1", "n2", "n3"]


def test_target_only_chapters_are_reported(service, db_session):
    tracker = _seed_tracker(db_session)
    new = _NEW_CATALOG + [_chapter("new-d", 4.0)]
    p_installed, p_connector = _env({OLD: _OLD_CATALOG, NEW: new})
    with p_installed, p_connector:
        plan = service.plan_migration(
            tracker.id, target_source=NEW, target_series_id="new-series"
        )

    assert plan["target_only_chapters"] == ["new-d"]


# ---------------------------------------------------------------------------
# Dead old source
# ---------------------------------------------------------------------------


def test_dead_old_source_falls_back_to_the_cached_chapter_numbers(service, db_session):
    """The reason ``known_chapters`` exists: the source you are leaving is very
    often the one that has already stopped answering."""
    tracker = _seed_tracker(
        db_session,
        known_chapters='[{"id": "old-1", "number": 1.0}, {"id": "old-2", "number": 2.0}]',
    )
    p_installed, p_connector = _env({OLD: None, NEW: _NEW_CATALOG})
    with p_installed, p_connector:
        plan = service.plan_migration(
            tracker.id, target_source=NEW, target_series_id="new-series"
        )

    assert plan["old_catalog"] == "cached"
    assert [(e["from_chapter_id"], e["to_chapter_id"]) for e in plan["chapter_map"]] == [
        ("old-1", "new-a"),
        ("old-2", "new-b"),
    ]


def test_dead_old_source_with_no_cache_reports_unavailable_and_destroys_nothing(
    service, db_session
):
    tracker = _seed_tracker(db_session)  # known_chapters is NULL
    p_installed, p_connector = _env({OLD: None, NEW: _NEW_CATALOG})
    with p_installed, p_connector:
        plan = service.migrate_tracker(
            tracker.id,
            target_source=NEW,
            target_series_id="new-series",
            dry_run=False,
        )

    assert plan["old_catalog"] == "unavailable"
    assert plan["chapter_map"] == []
    assert any("no reading progress can be remapped" in w for w in plan["warnings"])
    # The repoint still happens -- the follow is the point; the client simply
    # keeps its existing progress keys, which is lossless, not destructive.
    assert plan["applied"] is True
    db_session.refresh(tracker)
    assert (tracker.source, tracker.series_id) == (NEW, "new-series")


def test_an_unreachable_target_is_a_502_not_a_silent_empty_map(service, db_session):
    tracker = _seed_tracker(db_session)
    p_installed, p_connector = _env({OLD: _OLD_CATALOG, NEW: None})
    with p_installed, p_connector, pytest.raises(AppError) as excinfo:
        service.plan_migration(
            tracker.id, target_source=NEW, target_series_id="new-series"
        )
    assert excinfo.value.status_code == 502
    assert excinfo.value.code == "migration_target_unreachable"


# ---------------------------------------------------------------------------
# Applying the migration
# ---------------------------------------------------------------------------


def test_dry_run_writes_nothing(service, db_session):
    tracker = _seed_tracker(db_session)
    p_installed, p_connector = _env({OLD: _OLD_CATALOG, NEW: _NEW_CATALOG})
    with p_installed, p_connector:
        plan = service.migrate_tracker(
            tracker.id, target_source=NEW, target_series_id="new-series", dry_run=True
        )

    assert plan["applied"] is False
    assert plan["counts"]["matched"] == 3
    db_session.refresh(tracker)
    assert (tracker.source, tracker.series_id) == (OLD, "old-series")
    assert tracker.migrated_at is None


def test_commit_rewrites_the_tracker_and_resets_the_known_chapter_set(service, db_session):
    tracker = _seed_tracker(db_session)
    p_installed, p_connector = _env({OLD: _OLD_CATALOG, NEW: _NEW_CATALOG})
    with p_installed, p_connector:
        plan = service.migrate_tracker(
            tracker.id,
            target_source=NEW,
            target_series_id="new-series",
            target_series_title="Solo Leveling (MangaDex)",
            dry_run=False,
        )

    assert plan["applied"] is True
    db_session.refresh(tracker)
    assert (tracker.source, tracker.series_id) == (NEW, "new-series")
    assert tracker.series_title == "Solo Leveling (MangaDex)"
    assert tracker.migrated_from_source == OLD
    assert tracker.migrated_from_series_id == "old-series"
    assert tracker.migrated_at is not None
    # Reset to the TARGET's ids: leaving the old ones here makes the next
    # update check see the entire target catalog as new and emit one
    # notification per chapter.
    assert sorted(__import__("json").loads(tracker.known_chapter_ids)) == [
        "new-a",
        "new-b",
        "new-c",
    ]
    assert tracker.known_chapters is not None


def test_the_first_check_after_migrating_reports_no_spurious_new_chapters(
    service, db_session
):
    tracker = _seed_tracker(db_session)
    p_installed, p_connector = _env({OLD: _OLD_CATALOG, NEW: _NEW_CATALOG})
    with p_installed, p_connector:
        service.migrate_tracker(
            tracker.id, target_source=NEW, target_series_id="new-series", dry_run=False
        )
        settings = service.get_global_settings()
        new_count = service._check_tracker(tracker, settings)

    assert new_count == 0
    assert db_session.query(UpdateNotification).count() == 0


def test_notifications_are_remapped_and_dead_ones_are_dropped(service, db_session):
    tracker = _seed_tracker(db_session)
    db_session.add_all(
        [
            UpdateNotification(
                tracker_id=tracker.id,
                source=OLD,
                series_id="old-series",
                series_title="Solo Leveling",
                chapter_id="old-2",
                chapter_title="Chapter 2",
                chapter_number=2,
            ),
            # 90.0 exists only on the old source; its notification would be a
            # dead link that 404s in the reader.
            UpdateNotification(
                tracker_id=tracker.id,
                source=OLD,
                series_id="old-series",
                series_title="Solo Leveling",
                chapter_id="old-orphan",
                chapter_title="Chapter 90",
                chapter_number=90,
            ),
        ]
    )
    db_session.commit()

    old = _OLD_CATALOG + [_chapter("old-orphan", 90.0)]
    p_installed, p_connector = _env({OLD: old, NEW: _NEW_CATALOG})
    with p_installed, p_connector:
        plan = service.migrate_tracker(
            tracker.id, target_source=NEW, target_series_id="new-series", dry_run=False
        )

    assert plan["notifications_rewritten"] == 1
    assert plan["notifications_dropped"] == 1
    rows = db_session.query(UpdateNotification).all()
    assert len(rows) == 1
    assert (rows[0].source, rows[0].series_id, rows[0].chapter_id) == (
        NEW,
        "new-series",
        "new-b",
    )


def test_downloaded_chapters_stay_reachable_via_an_additive_link(service, db_session):
    """Chapters already on disk must not be re-streamed from the network after
    a repoint. The old link is KEPT (it records where the bytes really came
    from) and a second one is added under the new (source, series_id)."""
    lib = Library(name="L", root_path="/l")
    db_session.add(lib)
    db_session.flush()
    series = Series(
        library_id=lib.id, title="S", folder_path="/l/s", sort_title="s"
    )
    db_session.add(series)
    db_session.flush()
    local = Chapter(series_id=series.id, title="Ch2", number=2.0, sort_key="0002")
    db_session.add(local)
    db_session.flush()
    db_session.add(
        SourceChapterLink(
            source=OLD,
            series_id="old-series",
            chapter_id="old-2",
            local_chapter_id=local.id,
        )
    )
    tracker = _seed_tracker(db_session)

    p_installed, p_connector = _env({OLD: _OLD_CATALOG, NEW: _NEW_CATALOG})
    with p_installed, p_connector:
        plan = service.migrate_tracker(
            tracker.id, target_source=NEW, target_series_id="new-series", dry_run=False
        )

    assert plan["downloads_relinked"] == 1
    links = db_session.query(SourceChapterLink).order_by(SourceChapterLink.id).all()
    assert [(l.source, l.series_id, l.chapter_id) for l in links] == [
        (OLD, "old-series", "old-2"),
        (NEW, "new-series", "new-b"),
    ]
    assert {l.local_chapter_id for l in links} == {local.id}


def test_nearest_match_collapsing_two_chapters_never_violates_uq_source_chapter(
    service, db_session
):
    """Two old chapters can map onto one target via nearest-match. Inserting a
    link for each would violate uq_source_chapter (source, series_id,
    chapter_id) and take the whole transaction down with it."""
    lib = Library(name="L", root_path="/l")
    db_session.add(lib)
    db_session.flush()
    series = Series(library_id=lib.id, title="S", folder_path="/l/s", sort_title="s")
    db_session.add(series)
    db_session.flush()
    locals_ = []
    for number in (2.0, 2.5):
        chapter = Chapter(
            series_id=series.id, title=f"Ch{number}", number=number, sort_key="x"
        )
        db_session.add(chapter)
        db_session.flush()
        locals_.append(chapter)
        db_session.add(
            SourceChapterLink(
                source=OLD,
                series_id="old-series",
                chapter_id=f"old-{number:g}",
                local_chapter_id=chapter.id,
            )
        )
    tracker = _seed_tracker(db_session)

    old = [_chapter("old-2", 2.0), _chapter("old-2.5", 2.5)]
    new = [_chapter("new-b", 2.0)]  # no 2.5, so 2.5 snaps back onto 2.0
    p_installed, p_connector = _env({OLD: old, NEW: new})
    with p_installed, p_connector:
        plan = service.migrate_tracker(
            tracker.id, target_source=NEW, target_series_id="new-series", dry_run=False
        )

    assert [e["match"] for e in plan["chapter_map"]] == ["exact", "nearest"]
    assert plan["downloads_relinked"] == 1  # one link per target chapter, not two
    new_links = (
        db_session.query(SourceChapterLink)
        .filter(SourceChapterLink.source == NEW)
        .all()
    )
    assert len(new_links) == 1


def test_migrating_to_where_it_already_is_is_a_no_op(service, db_session):
    """A client retrying after a dropped response must get the same remap back
    and cause no second set of side effects."""
    tracker = _seed_tracker(db_session)
    p_installed, p_connector = _env({OLD: _OLD_CATALOG, NEW: _NEW_CATALOG})
    with p_installed, p_connector:
        service.migrate_tracker(
            tracker.id, target_source=NEW, target_series_id="new-series", dry_run=False
        )
        first_migrated_at = tracker.migrated_at
        replay = service.migrate_tracker(
            tracker.id, target_source=NEW, target_series_id="new-series", dry_run=False
        )

    assert replay["applied"] is False
    assert replay["counts"]["new"] == 3
    db_session.refresh(tracker)
    assert tracker.migrated_at == first_migrated_at


def test_a_stale_chapter_map_hash_is_refused(service, db_session):
    """The target gained a chapter between preview and confirm: the user must
    not commit a map they were never shown."""
    tracker = _seed_tracker(db_session)
    p_installed, p_connector = _env({OLD: _OLD_CATALOG, NEW: _NEW_CATALOG})
    with p_installed, p_connector:
        preview = service.migrate_tracker(
            tracker.id, target_source=NEW, target_series_id="new-series", dry_run=True
        )

    shifted = [_chapter("new-z", 1.0), _chapter("new-b", 2.0), _chapter("new-c", 3.0)]
    p_installed, p_connector = _env({OLD: _OLD_CATALOG, NEW: shifted})
    with p_installed, p_connector, pytest.raises(AppError) as excinfo:
        service.migrate_tracker(
            tracker.id,
            target_source=NEW,
            target_series_id="new-series",
            dry_run=False,
            expected_chapter_map_hash=preview["chapter_map_hash"],
        )

    assert excinfo.value.status_code == 409
    assert excinfo.value.code == "migration_stale"
    # The refusal carries the fresh preview so the client can re-confirm.
    assert excinfo.value.details["preview"]["chapter_map_hash"] != preview["chapter_map_hash"]
    db_session.refresh(tracker)
    assert tracker.source == OLD


# ---------------------------------------------------------------------------
# The unique constraint on (user_id, profile_id, source, series_id, track_kind)
# ---------------------------------------------------------------------------


def test_migrating_onto_an_already_followed_target_refuses_by_default(service, db_session):
    """Refuse, not merge-by-default. The two rows can carry different notify /
    auto_download / interval settings and different known-chapter sets, and
    silently picking a winner is the kind of invisible decision that resurfaces
    later as "it stopped notifying me"."""
    tracker = _seed_tracker(db_session)
    incumbent = SeriesTracker(
        source=NEW,
        series_id="new-series",
        series_title="Solo Leveling",
        track_kind="followed",
        known_chapter_ids='["new-a"]',
    )
    db_session.add(incumbent)
    db_session.commit()

    p_installed, p_connector = _env({OLD: _OLD_CATALOG, NEW: _NEW_CATALOG})
    with p_installed, p_connector, pytest.raises(AppError) as excinfo:
        service.migrate_tracker(
            tracker.id, target_source=NEW, target_series_id="new-series", dry_run=False
        )

    assert excinfo.value.status_code == 409
    assert excinfo.value.code == "tracker_target_already_followed"
    assert excinfo.value.details["existing_tracker_id"] == incumbent.id
    # Nothing moved.
    db_session.refresh(tracker)
    assert tracker.source == OLD
    assert db_session.query(SeriesTracker).count() == 2


def test_merge_true_folds_the_two_follows_into_the_incumbent(service, db_session):
    tracker = _seed_tracker(db_session)
    incumbent = SeriesTracker(
        source=NEW,
        series_id="new-series",
        series_title="Solo Leveling",
        track_kind="followed",
        known_chapter_ids='["seen-only-by-incumbent"]',
    )
    db_session.add(incumbent)
    db_session.flush()
    db_session.add(
        UpdateNotification(
            tracker_id=tracker.id,
            source=OLD,
            series_id="old-series",
            series_title="Solo Leveling",
            chapter_id="old-3",
            chapter_title="Chapter 3",
            chapter_number=3,
        )
    )
    db_session.commit()
    loser_id = tracker.id

    p_installed, p_connector = _env({OLD: _OLD_CATALOG, NEW: _NEW_CATALOG})
    with p_installed, p_connector:
        plan = service.migrate_tracker(
            tracker.id,
            target_source=NEW,
            target_series_id="new-series",
            dry_run=False,
            merge=True,
        )

    assert plan["applied"] is True
    assert plan["merged_into_tracker_id"] == incumbent.id
    assert db_session.get(SeriesTracker, loser_id) is None

    db_session.refresh(incumbent)
    # Known ids are UNIONed, so the first post-merge check does not treat the
    # difference as brand-new chapters.
    known = set(__import__("json").loads(incumbent.known_chapter_ids))
    assert known == {"seen-only-by-incumbent", "new-a", "new-b", "new-c"}
    # The loser's notification was repointed onto the survivor, not cascaded away.
    notes = db_session.query(UpdateNotification).all()
    assert len(notes) == 1
    assert notes[0].tracker_id == incumbent.id
    assert notes[0].chapter_id == "new-c"


def test_merge_does_not_launder_an_18plus_follow_into_a_safe_one(service, db_session):
    tracker = _seed_tracker(db_session, mature_override=True)
    incumbent = SeriesTracker(
        source=NEW,
        series_id="new-series",
        series_title="Solo Leveling",
        track_kind="followed",
    )
    db_session.add(incumbent)
    db_session.commit()

    p_installed, p_connector = _env({OLD: _OLD_CATALOG, NEW: _NEW_CATALOG})
    with p_installed, p_connector:
        service.migrate_tracker(
            tracker.id,
            target_source=NEW,
            target_series_id="new-series",
            dry_run=False,
            merge=True,
        )

    db_session.refresh(incumbent)
    assert bool(incumbent.mature_override) is True


def test_repointing_does_not_clear_an_18plus_marking(service, db_session):
    """Moving an adult follow onto a general-purpose source must not make it
    visible again -- the rating travels with the follow, not with the source."""
    tracker = _seed_tracker(db_session, content_rating="mature")
    p_installed, p_connector = _env({OLD: _OLD_CATALOG, NEW: _NEW_CATALOG})
    with p_installed, p_connector:
        service.migrate_tracker(
            tracker.id, target_source=NEW, target_series_id="new-series", dry_run=False
        )
        db_session.refresh(tracker)
        assert tracker.content_rating == "mature"
        assert service.list_trackers() == []


# ---------------------------------------------------------------------------
# Atomicity
# ---------------------------------------------------------------------------


def test_a_failure_mid_migration_rolls_everything_back(service, db_session):
    """The whole rewrite is one transaction with one commit at the end, so a
    half-migrated follow -- tracker moved but notifications still pointing at a
    source that no longer serves them -- is impossible by construction."""
    lib = Library(name="L", root_path="/l")
    db_session.add(lib)
    db_session.flush()
    series = Series(library_id=lib.id, title="S", folder_path="/l/s", sort_title="s")
    db_session.add(series)
    db_session.flush()
    local = Chapter(series_id=series.id, title="Ch2", number=2.0, sort_key="0002")
    db_session.add(local)
    db_session.flush()
    db_session.add(
        SourceChapterLink(
            source=OLD, series_id="old-series", chapter_id="old-2", local_chapter_id=local.id
        )
    )
    tracker = _seed_tracker(db_session)
    db_session.add(
        UpdateNotification(
            tracker_id=tracker.id,
            source=OLD,
            series_id="old-series",
            series_title="Solo Leveling",
            chapter_id="old-3",
            chapter_title="Chapter 3",
            chapter_number=3,
        )
    )
    db_session.commit()

    p_installed, p_connector = _env({OLD: _OLD_CATALOG, NEW: _NEW_CATALOG})
    # utcnow() is called to stamp migrated_at -- i.e. AFTER the notification
    # rewrite and the additive link insert have already been staged.
    with p_installed, p_connector, patch(
        "services.update_service.utcnow", side_effect=RuntimeError("boom")
    ), pytest.raises(RuntimeError):
        service.migrate_tracker(
            tracker.id, target_source=NEW, target_series_id="new-series", dry_run=False
        )

    # Re-read through a brand-new session: nothing was committed.
    fresh = sessionmaker(bind=db_session.get_bind(), autoflush=False)()
    try:
        row = fresh.get(SeriesTracker, tracker.id)
        assert (row.source, row.series_id) == (OLD, "old-series")
        assert row.migrated_at is None
        assert row.migrated_from_source is None

        notes = fresh.query(UpdateNotification).all()
        assert len(notes) == 1
        assert (notes[0].source, notes[0].chapter_id) == (OLD, "old-3")

        links = fresh.query(SourceChapterLink).all()
        assert [(l.source, l.chapter_id) for l in links] == [(OLD, "old-2")]
    finally:
        fresh.close()


# ---------------------------------------------------------------------------
# Guards
# ---------------------------------------------------------------------------


def test_a_downloaded_tracker_cannot_be_migrated(service, db_session):
    """sync_downloaded_trackers would simply recreate it at the old source from
    the Download rows, so migrating it is meaningless rather than merely risky."""
    tracker = _seed_tracker(db_session, track_kind="downloaded")
    p_installed, p_connector = _env({OLD: _OLD_CATALOG, NEW: _NEW_CATALOG})
    with p_installed, p_connector, pytest.raises(AppError) as excinfo:
        service.plan_migration(
            tracker.id, target_source=NEW, target_series_id="new-series"
        )
    assert excinfo.value.status_code == 400
    assert excinfo.value.code == "migration_track_kind_unsupported"


def test_sibling_trackers_are_listed_so_the_client_can_offer_the_other_one(
    service, db_session
):
    tracker = _seed_tracker(db_session)
    sibling = SeriesTracker(
        source=OLD,
        series_id="old-series",
        series_title="Solo Leveling",
        track_kind="downloaded",
    )
    db_session.add(sibling)
    db_session.commit()

    p_installed, p_connector = _env({OLD: _OLD_CATALOG, NEW: _NEW_CATALOG})
    with p_installed, p_connector:
        plan = service.plan_migration(
            tracker.id, target_source=NEW, target_series_id="new-series"
        )
    assert plan["sibling_trackers"] == [{"id": sibling.id, "track_kind": "downloaded"}]


def test_migration_cannot_be_used_as_a_back_door_onto_an_18plus_source(
    service, db_session
):
    tracker = _seed_tracker(db_session)
    descriptors = [_descriptor(OLD), _descriptor(NEW), _descriptor(ADULT, mature=True)]
    p_installed, p_connector = _env(
        {OLD: _OLD_CATALOG, ADULT: _NEW_CATALOG}, descriptors=descriptors
    )
    with p_installed, p_connector, pytest.raises(AppError) as excinfo:
        service.plan_migration(
            tracker.id, target_source=ADULT, target_series_id="adult-series"
        )
    assert excinfo.value.status_code == 400


def test_another_profiles_tracker_is_not_migratable(db_engine):
    """Ownership is re-checked through _require_tracker, which scopes to
    (user_id, profile_id) and 404s rather than disclosing existence."""
    factory = sessionmaker(bind=db_engine, autoflush=False, autocommit=False)
    db = factory()
    try:
        tracker = SeriesTracker(
            user_id=1,
            profile_id=1,
            source=OLD,
            series_id="old-series",
            series_title="Theirs",
            track_kind="followed",
        )
        db.add(tracker)
        db.commit()

        intruder = UpdateService(db, user_id=1, profile_id=2)
        p_installed, p_connector = _env({OLD: _OLD_CATALOG, NEW: _NEW_CATALOG})
        with p_installed, p_connector, pytest.raises(AppError) as excinfo:
            intruder.plan_migration(
                tracker.id, target_source=NEW, target_series_id="new-series"
            )
        assert excinfo.value.status_code == 404
    finally:
        db.close()


# ---------------------------------------------------------------------------
# HTTP surface
# ---------------------------------------------------------------------------


@pytest.fixture
def client(db_engine):
    factory = sessionmaker(bind=db_engine, autoflush=False, autocommit=False)

    def override_get_db():
        db = factory()
        try:
            yield db
        finally:
            db.close()

    app = create_app(run_migrations=False, run_workers=False)
    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as test_client:
        yield test_client, factory
    app.dependency_overrides.clear()


def test_migrate_endpoint_previews_then_commits(client):
    test_client, factory = client
    db = factory()
    try:
        tracker = _seed_tracker(db)
        tracker_id = tracker.id
    finally:
        db.close()

    p_installed, p_connector = _env({OLD: _OLD_CATALOG, NEW: _NEW_CATALOG})
    with p_installed, p_connector:
        preview = test_client.post(
            f"/updates/trackers/{tracker_id}/migrate",
            json={"target_source": NEW, "target_series_id": "new-series"},
        )
        assert preview.status_code == 200, preview.text
        body = preview.json()
        assert body["applied"] is False
        assert body["to"] == {"source": NEW, "series_id": "new-series"}

        committed = test_client.post(
            f"/updates/trackers/{tracker_id}/migrate",
            json={
                "target_source": NEW,
                "target_series_id": "new-series",
                "dry_run": False,
                "expected_chapter_map_hash": body["chapter_map_hash"],
            },
        )
    assert committed.status_code == 200, committed.text
    assert committed.json()["applied"] is True

    listed = test_client.get("/updates/trackers").json()
    assert listed[0]["source"] == NEW
    assert listed[0]["migrated_from_source"] == OLD


def test_migration_candidates_reuse_the_federated_fan_out(client):
    """No second search implementation: the endpoint wraps federated_search,
    drops the local group and the source being left, and keeps the best hit per
    remaining source."""
    test_client, factory = client
    db = factory()
    try:
        tracker_id = _seed_tracker(db).id
    finally:
        db.close()

    async def _fake_search(self, query, **kwargs):
        assert query == "Solo Leveling"  # defaults to the followed title
        return {
            "groups": [
                {"source": None, "source_name": "My Library", "items": [{"title": "local"}]},
                {
                    "source": OLD,
                    "source_name": "Deadscans",
                    "items": [{"series_id": "old-series", "title": "Solo Leveling"}],
                },
                {
                    "source": NEW,
                    "source_name": "MangaDex",
                    "icon_url": "/i.png",
                    "items": [
                        {
                            "series_id": "sl-1",
                            "title": "Solo Leveling",
                            "cover_url": "/c.png",
                            "author": "Chugong",
                            "chapter_count": 200,
                        },
                        {"series_id": "sl-2", "title": "Solo Leveling Ragnarok"},
                    ],
                },
            ],
            "sources_queried": 40,
            "sources_failed": 12,
        }

    p_installed, p_connector = _env({OLD: _OLD_CATALOG, NEW: _NEW_CATALOG})
    with p_installed, p_connector, patch(
        "services.browse_service.BrowseService.federated_search", _fake_search
    ):
        response = test_client.get(
            f"/updates/trackers/{tracker_id}/migration-candidates"
        )

    assert response.status_code == 200, response.text
    payload = response.json()
    # The local library and the source being migrated away from are both gone;
    # one candidate per remaining source, best hit first.
    assert [c["source"] for c in payload["candidates"]] == [NEW]
    assert payload["candidates"][0]["series_id"] == "sl-1"
    assert payload["candidates"][0]["chapter_count"] == 200
    # Partial failure is normal on a registry this size, and is reported rather
    # than turned into an error.
    assert payload["sources_failed"] == 12


@pytest.mark.real_auth
def test_migrate_requires_an_active_profile(db_engine, monkeypatch):
    monkeypatch.setenv("MM_COOKIE_SECURE", "false")
    factory = sessionmaker(bind=db_engine, autoflush=False, autocommit=False)

    def override_get_db():
        db = factory()
        try:
            yield db
        finally:
            db.close()

    app = create_app(run_migrations=False, run_workers=False)
    app.dependency_overrides[get_db] = override_get_db
    test_client = TestClient(app)
    reg = test_client.post(
        "/auth/register", json={"username": "owner", "password": "supersecret"}
    )
    assert reg.status_code in (200, 201), reg.text
    owner_id = reg.json()["user"]["id"]
    profile = test_client.post("/profiles", json={"name": "Alpha"}).json()

    db = factory()
    try:
        tracker = SeriesTracker(
            user_id=owner_id,
            profile_id=profile["id"],
            source=OLD,
            series_id="old-series",
            series_title="Solo Leveling",
            track_kind="followed",
        )
        db.add(tracker)
        db.commit()
        tracker_id = tracker.id
    finally:
        db.close()

    body = {"target_source": NEW, "target_series_id": "new-series"}
    p_installed, p_connector = _env({OLD: _OLD_CATALOG, NEW: _NEW_CATALOG})
    with p_installed, p_connector:
        missing = test_client.post(f"/updates/trackers/{tracker_id}/migrate", json=body)
        assert missing.status_code == 400
        assert missing.json()["code"] == "profile_required"

        foreign = test_client.post(
            f"/updates/trackers/{tracker_id}/migrate",
            json=body,
            headers={"X-Profile-Id": "9999"},
        )
        assert foreign.status_code == 404

        ok = test_client.post(
            f"/updates/trackers/{tracker_id}/migrate",
            json=body,
            headers={"X-Profile-Id": str(profile["id"])},
        )
        assert ok.status_code == 200, ok.text
