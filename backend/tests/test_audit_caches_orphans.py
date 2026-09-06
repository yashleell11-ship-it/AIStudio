"""AUDIT (caches shard): nothing ever removed orphaned or ancient cache rows.

All four cache tables evicted ONLY inside a write, and ONLY past a cap:
``_evict_oldest`` (rows past ``browse_cache_max_rows``/``source_cache_max_rows``),
``NovelService._evict_lru`` (rows past ``novel_cache_max_rows``) and
``_evict_cover_bytes_to_budget`` (bytes past ``cover_cache_max_bytes``).
Neither age nor registry membership was a rule anywhere, and no scheduled job
touched these tables.

Live evidence (read-only, 2026-09-06): ``manhuakey`` was removed from
``connectors/catalog.py`` on 2026-09-04 (its domain registration expired) and
is not in the registry, yet the production DB still held 40
``source_series_cache`` rows and 4 ``source_browse_cache`` rows for it. 1539 of
1550 series rows are browse write-through rows (``chapters`` is NULL) whose
``fetched_at`` is never bumped, so all of them are past the 6 h TTL and would
sit there until the 20 000-row cap was reached -- which, at ~1500 rows after
three days of a few users, it never would be.

``source_cache_service.sweep_cache_retention`` is the policy that was missing,
and ``main`` (boot) plus ``update_scheduler`` (daily) are what run it.
"""

from __future__ import annotations

import json
from datetime import timedelta

from sqlalchemy import select

from core.config import get_settings
from core.connector_directory import descriptor_for_source, known_source_ids
from core.time_utils import utcnow
from database.models import (
    BOOKMARK_MEDIA_NOVEL,
    Bookmark,
    NovelChapterCache,
    SourceBrowseCache,
    SourceCoverCache,
    SourceSeriesCache,
)
from services.bookmark_service import BookmarkService
from services.source_cache_service import sweep_cache_retention
from tests._fakes import FakeBrowse

DEAD = "audit-deregistered-source"  # never in the registry, like manhuakey today
LIVE = "asurascans"

CACHE_MODELS = (SourceSeriesCache, SourceBrowseCache, SourceCoverCache, NovelChapterCache)


def _seed_orphans(db, *, source_id: str = DEAD, age: timedelta | None = None) -> None:
    stamp = utcnow() - (age if age is not None else timedelta(days=400))
    db.add(
        SourceSeriesCache(
            source_id=source_id, series_key="s", title="T", fetched_at=stamp
        )
    )
    db.add(
        SourceBrowseCache(
            source_id=source_id, sort="", genre="", page=1, payload="{}", fetched_at=stamp
        )
    )
    db.add(
        SourceCoverCache(
            source_id=source_id, series_key="s", width=360, fmt="webp",
            media_type="image/webp", byte_size=1, data=b"x",
            fetched_at=stamp, last_used_at=stamp,
        )
    )
    db.add(
        NovelChapterCache(
            source_id=source_id, series_key="s", chapter_key="c1", title="Ch 1",
            paragraphs=json.dumps(["orphaned text"]), word_count=2,
            fetched_at=stamp, last_used_at=stamp,
        )
    )
    db.commit()


def _rows_for(db, source_id: str) -> dict[str, int]:
    return {
        model.__tablename__: len(
            db.execute(select(model).where(model.source_id == source_id)).scalars().all()
        )
        for model in CACHE_MODELS
    }


def test_the_sweep_removes_every_row_of_a_source_that_left_the_registry(db_session):
    assert descriptor_for_source(DEAD) is None  # premise: the source is gone
    _seed_orphans(db_session)

    removed = sweep_cache_retention(db_session)

    left = _rows_for(db_session, DEAD)
    assert not any(left.values()), (
        f"rows for a source that no longer exists survived the sweep: {left}"
    )
    assert set(removed) == {model.__tablename__ for model in CACHE_MODELS}


def test_the_sweep_keeps_rows_of_a_source_that_is_still_installed(db_session):
    assert LIVE in known_source_ids()  # premise: the source is real
    _seed_orphans(db_session, source_id=LIVE, age=timedelta(hours=1))

    sweep_cache_retention(db_session)

    kept = _rows_for(db_session, LIVE)
    assert all(kept.values()), f"a live source's fresh rows were swept: {kept}"


def test_the_sweep_removes_ancient_rows_of_a_live_source(db_session):
    """The other half of the production picture: 1539 browse write-through rows
    whose ``fetched_at`` is never bumped, kept alive only by a cap nobody
    reaches."""
    _seed_orphans(db_session, source_id=LIVE, age=timedelta(days=400))

    sweep_cache_retention(db_session)

    left = _rows_for(db_session, LIVE)
    assert not any(left.values()), f"400-day-old rows of a live source survived: {left}"


def test_the_sweep_enforces_the_row_cap_no_write_path_reached(db_session, monkeypatch):
    """Caps only ever applied inside a write, so a cache that goes quiet stays
    over its ceiling forever -- which is exactly the state a disk-bound VPS
    cares about."""
    monkeypatch.setenv("MM_SOURCE_CACHE_MAX_ROWS", "3")
    get_settings.cache_clear()
    now = utcnow()
    for n in range(10):
        db_session.add(
            SourceSeriesCache(
                source_id=LIVE, series_key=f"s{n}", title=f"T{n}",
                fetched_at=now - timedelta(minutes=n),
            )
        )
    db_session.commit()

    sweep_cache_retention(db_session)

    surviving = db_session.execute(select(SourceSeriesCache)).scalars().all()
    assert len(surviving) == 3, f"row cap not applied: {len(surviving)} rows left"
    # The newest three, i.e. the cap evicts by age like every other sweep here.
    assert sorted(row.series_key for row in surviving) == ["s0", "s1", "s2"]


def test_a_deregistered_adult_sources_cached_text_cannot_outlive_the_sweep(
    db_session, make_user, make_profile
):
    """The orphan is not inert, which is why removing it is the fix.

    ``BookmarkService`` resolves a bookmark's maturity from the registry
    (``descriptor is not None and descriptor.mature``), so a source that has
    LEFT the registry resolves as SAFE and its cached novel text is read
    straight out of ``novel_chapter_cache`` with no ``ensure_visible`` — served
    to a profile whose 18+ gate is closed. The gate cannot classify a source it
    no longer has; the sweep is what makes sure there is nothing left to
    classify.
    """
    user = make_user()
    profile = make_profile(user.id, "Closed", mature_content_enabled=False)
    _seed_orphans(db_session)
    db_session.add(
        Bookmark(
            user_id=user.id, profile_id=profile.id, client_id="b1",
            source_id=DEAD, series_key="s", chapter_key="c1", chapter_number=1.0,
            media_type=BOOKMARK_MEDIA_NOVEL, anchor_index=1, anchor_fraction=0.0, anchor_total=1,
        )
    )
    db_session.commit()

    sweep_cache_retention(db_session)
    items = BookmarkService(
        db_session, user_id=user.id, profile_id=profile.id
    ).list_bookmarks()

    served = [i["snippet"] for i in items if i["snippet"]]
    assert served == [], (
        f"cached chapter text of a source that no longer exists was served to a "
        f"gate-closed profile: {served!r}"
    )
