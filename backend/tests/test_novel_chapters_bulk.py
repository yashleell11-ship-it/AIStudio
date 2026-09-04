"""``POST /novels/chapters`` — a bounded window of novel chapter text (R5).

Spec 2026-09-05-reading-flow-design R5 is "download a whole novel". Chapter text
is kilobytes, so served one ``GET /novels/chapter`` at a time a 300-chapter web
novel is almost entirely round-trip overhead. This window is the fix — and it
has to be the fix without loosening anything, so the guarantees are pinned
first: the novels flag, the per-caller 18+ gate, ``novel_chapter_cache`` with
its LRU, and the sanitizer/English guard that live inside the connector.
"""

from __future__ import annotations

import json
import threading
from datetime import timedelta

import pytest

import connectors.registry as registry
from connectors.models import NovelChapterText
from core.config import get_settings
from core.errors import AppError
from core.time_utils import utcnow
from database.models import NovelChapterCache
from services.novel_service import NovelService
from services.source_cache_service import SourceCacheService
from tests._fakes import FakeBrowse
from tests.test_novels_flag import CHAPTERS, SERIES, STUB_SOURCE, StubNovelConnector

TEXTS = {
    (SERIES, key): NovelChapterText(
        title=f"Chapter {n}",
        paragraphs=(f"Paragraph one of {n}.", f"Paragraph two of {n}."),
        chapter_number=float(n),
    )
    for n, key in enumerate(CHAPTERS, start=1)
}


@pytest.fixture
def stub_registered():
    registry.register_connector(STUB_SOURCE, StubNovelConnector)
    StubNovelConnector.TEXTS = dict(TEXTS)
    StubNovelConnector.RAISE = None
    yield
    registry._REGISTRY.pop(STUB_SOURCE, None)
    registry._INSTANCE_CACHE.pop(STUB_SOURCE, None)
    StubNovelConnector.TEXTS = {}
    StubNovelConnector.RAISE = None


@pytest.fixture
def novels_on(monkeypatch, stub_registered):
    monkeypatch.setenv("MM_NOVELS_ENABLED", "true")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


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
    chapter_key: str,
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
        prev_key="stale-prev",
        next_key="stale-next",
        fetched_at=utcnow() - timedelta(minutes=age_minutes),
        last_used_at=utcnow() - timedelta(minutes=used_minutes_ago),
    )
    db.add(row)
    db.commit()
    return row


# ---------------------------------------------------------------------------
# invariant: the gates
# ---------------------------------------------------------------------------


def test_bulk_window_applies_the_18plus_gate_before_reading_the_cache(
    db_session, novels_on
):
    """A gated caller gets ``source_not_found`` for the window — including when
    the very rows it asks for are already cached.

    ``novel_chapter_cache`` rows are GLOBAL; whether this caller may see the
    source is not. The single-chapter path 404s here through
    ``_require_novel_connector``; the window has to reach that same check before
    it touches a row, or a closed gate becomes an oracle for "this profile has
    read this mature novel".
    """
    browse = _browse()
    service = _svc(db_session, browse)
    warm = service.get_chapters_bulk(STUB_SOURCE, SERIES, ["ch-1", "ch-2"])
    assert warm["ok_count"] == 2

    browse.mature_sources = {STUB_SOURCE}
    browse.gate_open = False

    for window in (["ch-1"], ["ch-1", "ch-2"], ["no-such-chapter"]):
        with pytest.raises(AppError) as excinfo:
            service.get_chapters_bulk(STUB_SOURCE, SERIES, window)
        assert excinfo.value.status_code == 404
        assert excinfo.value.code == "source_not_found", (
            f"window {window!r} disclosed that the source exists"
        )


def test_bulk_window_gate_precedes_every_read(db_session, novels_on):
    browse = _browse()
    browse.mature_sources = {STUB_SOURCE}
    browse.gate_open = False
    service = _svc(db_session, browse)

    with pytest.raises(AppError):
        service.get_chapters_bulk(STUB_SOURCE, SERIES, ["ch-1"])

    assert browse.calls == [], browse.calls
    assert db_session.get(NovelChapterCache, (STUB_SOURCE, SERIES, "ch-1")) is None


def test_bulk_window_is_404_when_the_novels_flag_is_off(client, stub_registered):
    """The flag is the non-negotiable: with MM_NOVELS_ENABLED off the route is
    not mounted at all, so the window must be a stock 404 like everything else
    under /novels — indistinguishable from a feature that was never built."""
    resp = client.post(
        "/novels/chapters",
        json={
            "source_id": STUB_SOURCE,
            "series_key": SERIES,
            "chapter_keys": ["ch-1"],
        },
    )
    assert resp.status_code == 404
    assert "items" not in resp.json()


def test_bulk_window_rejects_a_manga_source(db_session, novels_on):
    """A manga source reaching the novel window is a 404, not a 400: which
    kinds of source exist here is not disclosed."""
    service = _svc(db_session)
    with pytest.raises(AppError) as excinfo:
        service.get_chapters_bulk("mangadex", SERIES, ["ch-1"])
    assert excinfo.value.status_code == 404
    assert excinfo.value.code == "source_not_found"


# ---------------------------------------------------------------------------
# invariant: the same cache, the same LRU, the same sanitizer
# ---------------------------------------------------------------------------


def test_bulk_item_is_identical_to_the_single_chapter_payload(db_session, novels_on):
    single = _svc(db_session).get_chapter(STUB_SOURCE, SERIES, "ch-2")

    fresh_db_service = _svc(db_session)
    window = fresh_db_service.get_chapters_bulk(STUB_SOURCE, SERIES, ["ch-2"])
    item = window["items"][0]["chapter"]

    # The cache status legitimately differs (the single call above populated the
    # row), so compare everything else field by field.
    assert item["cache"]["status"] == "fresh"
    for field in (
        "source_id",
        "series_key",
        "chapter_key",
        "title",
        "chapter_number",
        "paragraphs",
        "prev",
        "next",
        "word_count",
    ):
        assert item[field] == single[field], field


def test_bulk_window_stores_every_fetched_chapter_in_novel_chapter_cache(
    db_session, novels_on
):
    service = _svc(db_session)
    window = service.get_chapters_bulk(STUB_SOURCE, SERIES, list(CHAPTERS))

    assert window["ok_count"] == 3
    for key in CHAPTERS:
        row = db_session.get(NovelChapterCache, (STUB_SOURCE, SERIES, key))
        assert row is not None, key
        assert json.loads(row.paragraphs)[0].startswith("Paragraph one of")


def test_bulk_window_serves_fresh_rows_without_touching_the_connector(
    db_session, novels_on
):
    """The whole point of the cache: a re-download of a novel the reader
    already has must not scrape the source again."""
    service = _svc(db_session)
    service.get_chapters_bulk(STUB_SOURCE, SERIES, list(CHAPTERS))

    calls: list[str] = []
    original = StubNovelConnector.chapter_text

    def counting(self, series_key, chapter_key):
        calls.append(chapter_key)
        return original(self, series_key, chapter_key)

    StubNovelConnector.chapter_text = counting
    try:
        window = service.get_chapters_bulk(STUB_SOURCE, SERIES, list(CHAPTERS))
    finally:
        StubNovelConnector.chapter_text = original

    assert window["ok_count"] == 3
    assert all(
        item["chapter"]["cache"]["status"] == "fresh" for item in window["items"]
    )
    assert calls == [], f"a fresh window went upstream for {calls}"


def test_bulk_window_fetches_only_the_chapters_that_missed(db_session, novels_on):
    service = _svc(db_session)
    service.get_chapters_bulk(STUB_SOURCE, SERIES, ["ch-2"])

    calls: list[str] = []
    original = StubNovelConnector.chapter_text

    def counting(self, series_key, chapter_key):
        calls.append(chapter_key)
        return original(self, series_key, chapter_key)

    StubNovelConnector.chapter_text = counting
    try:
        window = service.get_chapters_bulk(STUB_SOURCE, SERIES, list(CHAPTERS))
    finally:
        StubNovelConnector.chapter_text = original

    assert window["ok_count"] == 3
    assert sorted(calls) == ["ch-1", "ch-3"]


def test_bulk_window_bumps_the_lru_signal_on_every_served_row(db_session, novels_on):
    """``last_used_at`` is what keeps a chapter the reader keeps returning to
    from being evicted. A window that serves twenty rows and persists none of
    those bumps quietly breaks the eviction policy for bulk readers."""
    row = _seed_row(db_session, chapter_key="ch-2", used_minutes_ago=500)
    before = row.last_used_at

    service = _svc(db_session)
    service.get_chapters_bulk(STUB_SOURCE, SERIES, ["ch-2"])

    db_session.expire_all()
    after = db_session.get(NovelChapterCache, (STUB_SOURCE, SERIES, "ch-2"))
    assert after.last_used_at > before


def test_bulk_window_honours_the_lru_row_ceiling(db_session, novels_on, monkeypatch):
    monkeypatch.setenv("MM_NOVEL_CACHE_MAX_ROWS", "2")
    get_settings.cache_clear()
    try:
        service = _svc(db_session)
        service.get_chapters_bulk(STUB_SOURCE, SERIES, list(CHAPTERS))
        remaining = db_session.query(NovelChapterCache).count()
        assert remaining <= 2, remaining
    finally:
        get_settings.cache_clear()


def test_bulk_window_commits_once_for_the_whole_window(db_session, novels_on):
    """Twenty write-lock/fsync cycles per request on the single-writer SQLite is
    the batch bug already fixed once on ``POST /reader/progress/batch``."""
    browse = _browse()
    service = _svc(db_session, browse)
    # Warm the chapter-list cache first: its own write-through commit is a
    # once-per-series cost, not a per-chapter one, and counting it here would
    # hide the thing under test.
    SourceCacheService(db_session, browse).get_chapter_list(STUB_SOURCE, SERIES)

    commits = {"n": 0}
    real_commit = db_session.commit

    def counting_commit():
        commits["n"] += 1
        real_commit()

    db_session.commit = counting_commit
    try:
        window = service.get_chapters_bulk(STUB_SOURCE, SERIES, list(CHAPTERS))
    finally:
        db_session.commit = real_commit

    assert window["ok_count"] == 3
    assert commits["n"] == 1, commits["n"]


def test_bulk_window_paragraphs_come_from_the_connector_unaltered(
    db_session, novels_on
):
    """The sanitizer and the English guard live inside ``chapter_text``; the
    window calls it once per chapter and must not reach past it or post-process
    what it returns."""
    service = _svc(db_session)
    window = service.get_chapters_bulk(STUB_SOURCE, SERIES, ["ch-1"])
    served = window["items"][0]["chapter"]
    assert served["paragraphs"] == list(TEXTS[(SERIES, "ch-1")].paragraphs)
    assert served["word_count"] == TEXTS[(SERIES, "ch-1")].word_count


def test_a_chapter_the_guard_rejects_is_a_per_item_404(db_session, novels_on):
    """``chapter_text`` returning None is "gone, unparseable, or not English".
    With nothing cached that is a 404 for that chapter — not for the window."""
    StubNovelConnector.TEXTS = {
        (SERIES, "ch-1"): TEXTS[(SERIES, "ch-1")],
        (SERIES, "ch-2"): None,
        (SERIES, "ch-3"): TEXTS[(SERIES, "ch-3")],
    }
    service = _svc(db_session)
    window = service.get_chapters_bulk(STUB_SOURCE, SERIES, list(CHAPTERS))

    assert window["ok_count"] == 2
    assert window["items"][1]["error"] == {
        "code": "chapter_not_found",
        "status": 404,
        "message": "Chapter not found.",
    }


def test_a_rejected_chapter_with_a_cached_copy_serves_stale(db_session, novels_on):
    """Text is immutable — a cached copy beats an error, exactly as the single
    path decides it."""
    _seed_row(db_session, chapter_key="ch-2", age_minutes=100_000)
    StubNovelConnector.TEXTS = {**TEXTS, (SERIES, "ch-2"): None}

    service = _svc(db_session)
    window = service.get_chapters_bulk(STUB_SOURCE, SERIES, ["ch-2"])

    item = window["items"][0]
    assert item["status"] == "ok"
    assert item["chapter"]["cache"]["stale"] is True
    assert item["chapter"]["paragraphs"] == ["Cached paragraph."]


# ---------------------------------------------------------------------------
# honest degradation
# ---------------------------------------------------------------------------


def test_one_failing_chapter_does_not_sink_the_window(db_session, novels_on):
    original = StubNovelConnector.chapter_text

    def flaky(self, series_key, chapter_key):
        if chapter_key == "ch-2":
            raise RuntimeError("upstream exploded")
        return original(self, series_key, chapter_key)

    StubNovelConnector.chapter_text = flaky
    try:
        window = _svc(db_session).get_chapters_bulk(
            STUB_SOURCE, SERIES, list(CHAPTERS)
        )
    finally:
        StubNovelConnector.chapter_text = original

    assert window["requested"] == 3
    assert window["ok_count"] == 2
    assert window["failed_count"] == 1
    failed = window["items"][1]
    assert failed["chapter"] is None
    assert failed["error"]["code"] == "novel_chapter_unavailable"
    assert failed["error"]["status"] == 502
    assert "exploded" not in failed["error"]["message"]


def test_a_connector_failure_with_a_cached_copy_serves_stale(db_session, novels_on):
    _seed_row(db_session, chapter_key="ch-2", age_minutes=100_000)
    StubNovelConnector.RAISE = RuntimeError("source down")
    try:
        window = _svc(db_session).get_chapters_bulk(STUB_SOURCE, SERIES, ["ch-2"])
    finally:
        StubNovelConnector.RAISE = None

    item = window["items"][0]
    assert item["status"] == "ok"
    assert item["chapter"]["cache"]["status"] == "stale"
    assert item["chapter"]["paragraphs"] == ["Cached paragraph."]


def test_window_order_is_preserved_and_repeats_are_fetched_once(
    db_session, novels_on
):
    calls: list[str] = []
    original = StubNovelConnector.chapter_text

    def counting(self, series_key, chapter_key):
        calls.append(chapter_key)
        return original(self, series_key, chapter_key)

    StubNovelConnector.chapter_text = counting
    try:
        window = _svc(db_session).get_chapters_bulk(
            STUB_SOURCE, SERIES, ["ch-3", "ch-1", "ch-3"]
        )
    finally:
        StubNovelConnector.chapter_text = original

    assert [item["chapter_key"] for item in window["items"]] == [
        "ch-3",
        "ch-1",
        "ch-3",
    ]
    assert sorted(calls) == ["ch-1", "ch-3"]


def test_navigation_is_resolved_once_for_the_window(db_session, novels_on):
    """prev/next come from the (cached) chapter list. Resolving it per chapter
    re-reads and re-parses the same row N times."""
    browse = _browse()
    service = _svc(db_session, browse)
    window = service.get_chapters_bulk(STUB_SOURCE, SERIES, list(CHAPTERS))

    assert window["items"][0]["chapter"]["prev"] is None
    assert window["items"][0]["chapter"]["next"] == "ch-2"
    assert window["items"][1]["chapter"]["prev"] == "ch-1"
    assert window["items"][2]["chapter"]["next"] is None

    kinds = [call.split(":", 1)[0] for call in browse.calls]
    assert kinds.count("get_chapters") == 1, browse.calls
    assert kinds.count("get_series") == 1, browse.calls


# ---------------------------------------------------------------------------
# cap + concurrency
# ---------------------------------------------------------------------------


def test_window_over_the_cap_is_413_and_names_the_cap(db_session, novels_on, monkeypatch):
    monkeypatch.setenv("MM_NOVEL_BULK_MAX_CHAPTERS", "2")
    get_settings.cache_clear()
    try:
        with pytest.raises(AppError) as excinfo:
            _svc(db_session).get_chapters_bulk(STUB_SOURCE, SERIES, list(CHAPTERS))
        assert excinfo.value.status_code == 413
        assert excinfo.value.code == "batch_too_large"
        assert excinfo.value.details == {"max_chapters": 2, "received": 3}
        assert db_session.query(NovelChapterCache).count() == 0
    finally:
        get_settings.cache_clear()


def test_every_window_echoes_the_cap(db_session, novels_on):
    window = _svc(db_session).get_chapters_bulk(STUB_SOURCE, SERIES, ["ch-1"])
    assert window["max_chapters"] == get_settings().novel_bulk_max_chapters


def test_fan_out_never_exceeds_the_configured_concurrency(
    db_session, novels_on, monkeypatch
):
    monkeypatch.setenv("MM_BULK_FETCH_CONCURRENCY", "2")
    get_settings.cache_clear()
    try:
        state = {"live": 0, "peak": 0}
        lock = threading.Lock()
        original = StubNovelConnector.chapter_text

        def watched(self, series_key, chapter_key):
            with lock:
                state["live"] += 1
                state["peak"] = max(state["peak"], state["live"])
            try:
                threading.Event().wait(0.02)
                return original(self, series_key, chapter_key)
            finally:
                with lock:
                    state["live"] -= 1

        StubNovelConnector.chapter_text = watched
        try:
            window = _svc(db_session).get_chapters_bulk(
                STUB_SOURCE, SERIES, list(CHAPTERS)
            )
        finally:
            StubNovelConnector.chapter_text = original

        assert window["ok_count"] == 3
        assert state["peak"] <= 2, state["peak"]
    finally:
        get_settings.cache_clear()


def test_no_worker_thread_touches_the_session(db_session, novels_on, monkeypatch):
    """A SQLAlchemy Session is not thread-safe and this one belongs to the
    request thread. Every DB access — cache read, upsert, eviction — must
    happen there; only the upstream fetch fans out."""
    monkeypatch.setenv("MM_BULK_FETCH_CONCURRENCY", "3")
    get_settings.cache_clear()
    try:
        request_thread = threading.current_thread().ident
        offenders: list[str] = []
        original_get = db_session.get
        original_commit = db_session.commit

        def guarded_get(*args, **kwargs):
            if threading.current_thread().ident != request_thread:
                offenders.append("get")
            return original_get(*args, **kwargs)

        def guarded_commit(*args, **kwargs):
            if threading.current_thread().ident != request_thread:
                offenders.append("commit")
            return original_commit(*args, **kwargs)

        db_session.get = guarded_get
        db_session.commit = guarded_commit
        try:
            _svc(db_session).get_chapters_bulk(STUB_SOURCE, SERIES, list(CHAPTERS))
        finally:
            db_session.get = original_get
            db_session.commit = original_commit

        assert offenders == [], offenders
    finally:
        get_settings.cache_clear()


# ---------------------------------------------------------------------------
# the endpoint
# ---------------------------------------------------------------------------


@pytest.fixture
def novel_client(monkeypatch, stub_registered, session_factory):
    """A client whose app was BUILT with the novels flag on (the router is only
    mounted at create_app time)."""
    from database.session import get_db
    from fastapi.testclient import TestClient
    from main import create_app

    monkeypatch.setenv("MM_NOVELS_ENABLED", "true")
    get_settings.cache_clear()
    application = create_app(run_migrations=False, run_workers=False)

    def override_get_db():
        db = session_factory()
        try:
            yield db
        finally:
            db.close()

    application.dependency_overrides[get_db] = override_get_db
    with TestClient(application) as test_client:
        yield test_client
    get_settings.cache_clear()


def test_bulk_window_endpoint_shape(novel_client):
    resp = novel_client.post(
        "/novels/chapters",
        json={
            "source_id": STUB_SOURCE,
            "series_key": SERIES,
            "chapter_keys": ["ch-1", "ch-2", "ch-nope"],
        },
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["source_id"] == STUB_SOURCE
    assert body["series_key"] == SERIES
    assert body["requested"] == 3
    assert body["ok_count"] == 2
    assert body["failed_count"] == 1
    assert isinstance(body["max_chapters"], int)
    assert [item["chapter_key"] for item in body["items"]] == [
        "ch-1",
        "ch-2",
        "ch-nope",
    ]
    first = body["items"][0]["chapter"]
    assert first["paragraphs"] == list(TEXTS[(SERIES, "ch-1")].paragraphs)
    assert first["prev"] is None and first["next"] == "ch-2"
    assert first["cache"]["status"] in {"live", "fresh"}
    assert body["items"][2]["chapter"] is None
    assert body["items"][2]["error"]["status"] == 404


def test_bulk_window_endpoint_rejects_an_over_cap_window(novel_client, monkeypatch):
    monkeypatch.setenv("MM_NOVEL_BULK_MAX_CHAPTERS", "2")
    get_settings.cache_clear()
    try:
        resp = novel_client.post(
            "/novels/chapters",
            json={
                "source_id": STUB_SOURCE,
                "series_key": SERIES,
                "chapter_keys": list(CHAPTERS),
            },
        )
        assert resp.status_code == 413, resp.text
        assert resp.json()["details"]["max_chapters"] == 2
    finally:
        get_settings.cache_clear()


def test_bulk_window_endpoint_rejects_an_empty_window(novel_client):
    resp = novel_client.post(
        "/novels/chapters",
        json={"source_id": STUB_SOURCE, "series_key": SERIES, "chapter_keys": []},
    )
    assert resp.status_code == 422, resp.text


@pytest.mark.rate_limit
def test_bulk_window_endpoint_is_rate_limited_on_the_bulk_bucket(
    novel_client, monkeypatch
):
    monkeypatch.setenv("MM_RATE_LIMIT_BULK", "2/minute")
    get_settings.cache_clear()
    try:
        body = {
            "source_id": STUB_SOURCE,
            "series_key": SERIES,
            "chapter_keys": ["ch-1"],
        }
        codes = [
            novel_client.post("/novels/chapters", json=body).status_code
            for _ in range(3)
        ]
        assert codes[:2] == [200, 200], codes
        assert codes[2] == 429, codes
    finally:
        get_settings.cache_clear()
