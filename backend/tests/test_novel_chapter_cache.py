"""``novel_chapter_cache``: the chapter-text cache behind ``/novels/chapter``.

Mirrors the browse-cache guarantees (spec 2026-09-04-novels-design §3):

  * fresh hit serves without a connector call (``cache.status: "fresh"``)
  * miss / expired refetches live and stores the sanitized paragraphs
  * connector down serves the last known text flagged ``stale``
  * connector says gone-upstream (None) still serves stale — text is immutable
  * nothing cached + connector down raises (502 novel_chapter_unavailable)
  * eviction bounds the table by LEAST-RECENTLY-USED (reads keep rows alive —
    the divergence from the browse cache's oldest-fetched sweep, on purpose)
"""

from __future__ import annotations

import json
from datetime import timedelta

import pytest

import connectors.registry as registry
from core.config import get_settings
from core.errors import AppError
from core.time_utils import utcnow
from database.models import NovelChapterCache
from services.novel_service import NovelService
from services.source_cache_service import SourceCacheService
from tests._fakes import FakeBrowse
from tests.test_novels_flag import CHAPTERS, SERIES, STUB_SOURCE, StubNovelConnector
from connectors.models import NovelChapterText

TEXT = NovelChapterText(
    title="Chapter 2",
    paragraphs=("First paragraph.", "Second paragraph."),
    chapter_number=2.0,
)


@pytest.fixture
def novels_on(monkeypatch, stub_registered):
    monkeypatch.setenv("MM_NOVELS_ENABLED", "true")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.fixture
def stub_registered():
    """Same stub the flag tests use, seeded with this module's chapter text."""
    registry.register_connector(STUB_SOURCE, StubNovelConnector)
    StubNovelConnector.TEXTS = {(SERIES, "ch-2"): TEXT}
    StubNovelConnector.RAISE = None
    yield
    registry._REGISTRY.pop(STUB_SOURCE, None)
    registry._INSTANCE_CACHE.pop(STUB_SOURCE, None)
    StubNovelConnector.TEXTS = {}
    StubNovelConnector.RAISE = None


def _browse() -> FakeBrowse:
    return FakeBrowse(
        series={
            (STUB_SOURCE, SERIES): {
                "meta": {"title": "Stub Series"},
                "chapters": [
                    {"id": key, "number": float(n), "title": f"Chapter {n}"}
                    for n, key in enumerate(CHAPTERS, start=1)
                ],
            }
        }
    )


def _svc(db, browse=None) -> NovelService:
    browse = browse or _browse()
    return NovelService(db, browse, SourceCacheService(db, browse))


def _seed_row(
    db,
    *,
    chapter_key: str = "ch-2",
    age_minutes: float = 0.0,
    used_minutes_ago: float = 0.0,
    paragraphs: tuple[str, ...] = ("Cached paragraph.",),
) -> NovelChapterCache:
    row = NovelChapterCache(
        source_id=STUB_SOURCE,
        series_key=SERIES,
        chapter_key=chapter_key,
        title="Cached Title",
        chapter_number=2.0,
        paragraphs=json.dumps(list(paragraphs)),
        word_count=sum(len(p.split()) for p in paragraphs),
        prev_key="ch-1",
        next_key="ch-3",
        fetched_at=utcnow() - timedelta(minutes=age_minutes),
        last_used_at=utcnow() - timedelta(minutes=used_minutes_ago),
    )
    db.add(row)
    db.commit()
    return row


# ---------------------------------------------------------------------------
# read-through
# ---------------------------------------------------------------------------


def test_miss_fetches_live_and_stores(db_session, novels_on):
    service = _svc(db_session)
    payload = service.get_chapter(STUB_SOURCE, SERIES, "ch-2")

    assert payload["cache"]["status"] == "live"
    assert payload["paragraphs"] == ["First paragraph.", "Second paragraph."]
    assert payload["prev"] == "ch-1" and payload["next"] == "ch-3"
    assert payload["word_count"] == 4

    row = db_session.get(NovelChapterCache, (STUB_SOURCE, SERIES, "ch-2"))
    assert row is not None
    assert json.loads(row.paragraphs) == ["First paragraph.", "Second paragraph."]
    assert row.word_count == 4


def test_fresh_hit_never_calls_the_connector(db_session, novels_on):
    _seed_row(db_session)
    # A connector call would raise loudly if it happened.
    StubNovelConnector.RAISE = AssertionError("connector must not be called")
    service = _svc(db_session)

    payload = service.get_chapter(STUB_SOURCE, SERIES, "ch-2")

    assert payload["cache"]["status"] == "fresh"
    assert payload["paragraphs"] == ["Cached paragraph."]
    assert payload["title"] == "Cached Title"


def test_expired_row_refetches_live(db_session, novels_on):
    ttl = get_settings().novel_cache_ttl_minutes
    _seed_row(db_session, age_minutes=ttl + 5)
    service = _svc(db_session)

    payload = service.get_chapter(STUB_SOURCE, SERIES, "ch-2")

    assert payload["cache"]["status"] == "live"
    assert payload["paragraphs"] == ["First paragraph.", "Second paragraph."]


def test_connector_down_serves_stale(db_session, novels_on):
    ttl = get_settings().novel_cache_ttl_minutes
    _seed_row(db_session, age_minutes=ttl + 5)
    StubNovelConnector.RAISE = RuntimeError("connector down")
    service = _svc(db_session)

    payload = service.get_chapter(STUB_SOURCE, SERIES, "ch-2")

    assert payload["cache"]["status"] == "stale"
    assert payload["cache"]["stale"] is True
    assert payload["paragraphs"] == ["Cached paragraph."]


def test_chapter_gone_upstream_still_serves_stale(db_session, novels_on):
    ttl = get_settings().novel_cache_ttl_minutes
    _seed_row(db_session, age_minutes=ttl + 5)
    StubNovelConnector.TEXTS = {}  # connector answers, chapter is gone
    service = _svc(db_session)

    payload = service.get_chapter(STUB_SOURCE, SERIES, "ch-2")

    assert payload["cache"]["status"] == "stale"
    assert payload["paragraphs"] == ["Cached paragraph."]


def test_connector_down_with_nothing_cached_raises(db_session, novels_on):
    StubNovelConnector.RAISE = RuntimeError("connector down")
    service = _svc(db_session)

    with pytest.raises(AppError) as excinfo:
        service.get_chapter(STUB_SOURCE, SERIES, "ch-2")
    assert excinfo.value.code == "novel_chapter_unavailable"
    assert excinfo.value.status_code == 502


def test_prev_next_fall_back_to_row_snapshot_when_list_unavailable(
    db_session, novels_on
):
    _seed_row(db_session)
    browse = _browse()
    browse.down = True  # chapter list fetch fails; nothing else cached
    service = _svc(db_session, browse=browse)

    payload = service.get_chapter(STUB_SOURCE, SERIES, "ch-2")

    assert payload["cache"]["status"] == "fresh"
    assert payload["prev"] == "ch-1"
    assert payload["next"] == "ch-3"


# ---------------------------------------------------------------------------
# LRU bound
# ---------------------------------------------------------------------------


def test_eviction_is_least_recently_used(db_session, novels_on, monkeypatch):
    monkeypatch.setenv("MM_NOVEL_CACHE_MAX_ROWS", "2")
    get_settings.cache_clear()

    # ch-old was fetched long ago but READ recently; ch-idle is newer but idle.
    _seed_row(db_session, chapter_key="ch-old", age_minutes=500, used_minutes_ago=1)
    _seed_row(db_session, chapter_key="ch-idle", age_minutes=100, used_minutes_ago=300)

    service = _svc(db_session)
    service.get_chapter(STUB_SOURCE, SERIES, "ch-2")  # live fetch -> 3rd row

    keys = {
        row.chapter_key
        for row in db_session.query(NovelChapterCache).all()
    }
    # The least-recently-USED row went, not the oldest-fetched one.
    assert keys == {"ch-old", "ch-2"}


def test_reads_keep_rows_alive(db_session, novels_on):
    row = _seed_row(db_session, used_minutes_ago=300)
    before = row.last_used_at
    service = _svc(db_session)

    service.get_chapter(STUB_SOURCE, SERIES, "ch-2")

    db_session.refresh(row)
    assert row.last_used_at > before


def test_cap_zero_disables_the_ceiling(db_session, novels_on, monkeypatch):
    monkeypatch.setenv("MM_NOVEL_CACHE_MAX_ROWS", "0")
    get_settings.cache_clear()
    for n in range(5):
        _seed_row(db_session, chapter_key=f"ch-seed-{n}")

    service = _svc(db_session)
    service.get_chapter(STUB_SOURCE, SERIES, "ch-2")

    assert db_session.query(NovelChapterCache).count() == 6
