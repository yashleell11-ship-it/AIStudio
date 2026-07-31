"""The NAS browse mode: what a source has already put on this server."""

from __future__ import annotations

import pytest

from database.models import Download
from services.nas_listing import nas_listing, nas_series_rows


def _download(
    *,
    source: str = "asurascans",
    series_id: str = "series-a",
    chapter_id: str = "ch-1",
    series_title: str = "Series A",
    status: str = "completed",
    user_id: int | None = 1,
    profile_id: int | None = 1,
) -> Download:
    return Download(
        source=source,
        series_id=series_id,
        chapter_id=chapter_id,
        series_title=series_title,
        chapter_title=chapter_id,
        status=status,
        user_id=user_id,
        profile_id=profile_id,
    )


@pytest.fixture
def seeded(db_session):
    db_session.add_all(
        [
            # Two series from asurascans, one with three chapters.
            _download(series_id="alpha", series_title="Alpha", chapter_id="c1"),
            _download(series_id="alpha", series_title="Alpha", chapter_id="c2"),
            _download(series_id="alpha", series_title="Alpha", chapter_id="c3"),
            _download(series_id="beta", series_title="Beta", chapter_id="c1"),
            # A different source entirely.
            _download(source="toonily", series_id="gamma", series_title="Gamma"),
        ]
    )
    db_session.commit()
    return db_session


def test_groups_chapters_into_one_row_per_series(seeded):
    rows, total = nas_series_rows(
        seeded, source_id="asurascans", user_id=1, profile_id=1, page=1
    )

    assert total == 2
    assert [r.series_id for r in rows] == ["alpha", "beta"]
    # Three downloaded chapters, one catalog entry.
    assert rows[0].chapter_count == 3
    assert rows[1].chapter_count == 1


def test_listing_is_scoped_to_the_source(seeded):
    rows, _ = nas_series_rows(
        seeded, source_id="toonily", user_id=1, profile_id=1, page=1
    )

    # The whole point of the view: each connector shows only its own.
    assert [r.series_id for r in rows] == ["gamma"]


def test_only_completed_downloads_appear(db_session):
    db_session.add_all(
        [
            _download(series_id="done", series_title="Done", status="completed"),
            _download(series_id="pending", series_title="Pending", status="queued"),
            _download(series_id="broken", series_title="Broken", status="failed"),
        ]
    )
    db_session.commit()

    rows, total = nas_series_rows(
        db_session, source_id="asurascans", user_id=1, profile_id=1, page=1
    )

    # A queued or failed chapter is not something the reader has; listing it
    # would claim otherwise.
    assert total == 1
    assert [r.series_id for r in rows] == ["done"]


def test_another_profile_on_the_same_account_sees_nothing(seeded):
    rows, total = nas_series_rows(
        seeded, source_id="asurascans", user_id=1, profile_id=2, page=1
    )

    # Downloads belong to the profile that queued them, exactly like library
    # membership.
    assert total == 0
    assert rows == []


def test_another_account_sees_nothing(seeded):
    _, total = nas_series_rows(
        seeded, source_id="asurascans", user_id=2, profile_id=1, page=1
    )

    assert total == 0


def test_absent_context_returns_empty_not_everything(seeded):
    # Failing closed: an unscoped listing would leak one reader's shelf to
    # whoever asked without context.
    rows, total = nas_series_rows(
        seeded, source_id="asurascans", user_id=None, profile_id=None, page=1
    )

    assert (rows, total) == ([], 0)


def test_paginates_with_a_stable_order(db_session):
    for index in range(5):
        db_session.add(
            _download(series_id=f"s{index}", series_title=f"Series {index}")
        )
    db_session.commit()

    first, total = nas_series_rows(
        db_session, source_id="asurascans", user_id=1, profile_id=1, page=1, page_size=2
    )
    second, _ = nas_series_rows(
        db_session, source_id="asurascans", user_id=1, profile_id=1, page=2, page_size=2
    )

    assert total == 5
    assert [r.series_id for r in first] == ["s0", "s1"]
    assert [r.series_id for r in second] == ["s2", "s3"]


def test_ordering_is_case_insensitive(db_session):
    db_session.add_all(
        [
            _download(series_id="lower", series_title="apple"),
            _download(series_id="upper", series_title="Banana"),
            _download(series_id="mixed", series_title="cherry"),
        ]
    )
    db_session.commit()

    rows, _ = nas_series_rows(
        db_session, source_id="asurascans", user_id=1, profile_id=1, page=1
    )

    # A plain string sort puts every uppercase title before every lowercase
    # one, which reads as random to someone scanning the list.
    assert [r.title for r in rows] == ["apple", "Banana", "cherry"]


def test_query_filters_locally_by_title(db_session):
    db_session.add_all(
        [
            _download(series_id="a", series_title="Solo Leveling"),
            _download(series_id="b", series_title="Tower of God"),
            _download(series_id="c", series_title="solo-ish Spinoff"),
        ]
    )
    db_session.commit()

    rows, total = nas_series_rows(
        db_session,
        source_id="asurascans",
        user_id=1,
        profile_id=1,
        page=1,
        query="solo",
    )

    # Filtered here rather than upstream: the connector would happily return
    # series this server does not have, which is the opposite of the question.
    assert total == 2
    assert {r.series_id for r in rows} == {"a", "c"}


def test_query_is_case_insensitive(seeded):
    rows, _ = nas_series_rows(
        seeded, source_id="asurascans", user_id=1, profile_id=1, page=1, query="ALPHA"
    )

    assert [r.series_id for r in rows] == ["alpha"]


def test_listing_reports_local_chapter_count_not_the_source_catalog(seeded):
    listing = nas_listing(
        seeded, source_id="asurascans", user_id=1, profile_id=1, page=1
    )

    alpha = next(item for item in listing.items if item.id == "alpha")
    # What is on this server, which is the question this view answers.
    assert alpha.chapter_count == 3
    assert listing.total == 2
    assert listing.page == 1


def test_listing_pagination_metadata_matches_a_catalog_page(db_session):
    for index in range(30):
        db_session.add(
            _download(series_id=f"s{index:02d}", series_title=f"Series {index:02d}")
        )
    db_session.commit()

    listing = nas_listing(
        db_session, source_id="asurascans", user_id=1, profile_id=1, page=1
    )

    # Same shape a connector returns, so every client renders it unchanged.
    assert listing.total == 30
    assert listing.has_more is True
    assert listing.total_pages == 2
