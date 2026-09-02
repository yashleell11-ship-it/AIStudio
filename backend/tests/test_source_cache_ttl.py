"""``source_series_cache`` TTL behaviour (spec §3.10, §7).

Fresh hit → served without a connector call. Stale / missing → refetched.
Connector down with a stale row → stale served. Connector down with nothing
cached → raises.
"""

from __future__ import annotations

from datetime import timedelta

import pytest

from core.errors import AppError
from core.time_utils import utcnow
from database.models import SourceSeriesCache
from services.source_cache_service import SourceCacheService
from tests._fakes import FakeBrowse

SRC = "mangadex"
KEY = "tower-of-god"

_FIXTURE = {
    (SRC, KEY): {
        "meta": {"title": "Tower of God (fresh)", "cover_url": "http://x/c.jpg"},
        "chapters": [
            {"id": "c1", "number": 1.0, "title": "1F"},
            {"id": "c2", "number": 2.0, "title": "2F"},
        ],
    }
}


def _seed_row(db, *, age_hours: float, title: str = "Tower of God (cached)"):
    row = SourceSeriesCache(
        source_id=SRC,
        series_key=KEY,
        title=title,
        fetched_at=utcnow() - timedelta(hours=age_hours),
        chapters="[]",
    )
    db.add(row)
    db.commit()
    return row


def test_fresh_hit_is_served_without_a_connector_call(db_session):
    _seed_row(db_session, age_hours=1)
    browse = FakeBrowse(_FIXTURE)
    svc = SourceCacheService(db_session, browse)

    meta = svc.get_series_meta(SRC, KEY)
    assert meta["title"] == "Tower of God (cached)"
    assert browse.calls == []  # no connector work


def test_stale_row_is_refetched(db_session):
    _seed_row(db_session, age_hours=10)  # TTL default is 6h
    browse = FakeBrowse(_FIXTURE)
    svc = SourceCacheService(db_session, browse)

    meta = svc.get_series_meta(SRC, KEY)
    assert meta["title"] == "Tower of God (fresh)"
    assert any(c.startswith("get_series") for c in browse.calls)
    assert len(meta["chapters"]) == 2

    # row is now fresh — a second read hits cache
    browse.calls.clear()
    svc.get_series_meta(SRC, KEY)
    assert browse.calls == []


def test_missing_row_is_fetched(db_session):
    browse = FakeBrowse(_FIXTURE)
    svc = SourceCacheService(db_session, browse)
    meta = svc.get_series_meta(SRC, KEY)
    assert meta["title"] == "Tower of God (fresh)"
    assert db_session.get(SourceSeriesCache, (SRC, KEY)) is not None


def test_connector_down_serves_a_stale_row(db_session):
    _seed_row(db_session, age_hours=99)
    browse = FakeBrowse(_FIXTURE)
    browse.down = True
    svc = SourceCacheService(db_session, browse)

    meta = svc.get_series_meta(SRC, KEY)
    assert meta["title"] == "Tower of God (cached)"  # stale, but served


def test_connector_down_with_no_cache_raises(db_session):
    browse = FakeBrowse(_FIXTURE)
    browse.down = True
    svc = SourceCacheService(db_session, browse)

    with pytest.raises((AppError, RuntimeError)):
        svc.get_series_meta(SRC, KEY)


def test_force_bypasses_a_fresh_row(db_session):
    _seed_row(db_session, age_hours=1)
    browse = FakeBrowse(_FIXTURE)
    svc = SourceCacheService(db_session, browse)

    meta = svc.get_series_meta(SRC, KEY, force=True)
    assert meta["title"] == "Tower of God (fresh)"
    assert browse.calls
