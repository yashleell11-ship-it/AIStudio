"""``POST /reader/chapters/manifest`` — a bounded WINDOW of chapter manifests.

Spec 2026-09-05-reading-flow-design R2 (Read-all) and R4 (bulk download): both
would otherwise open one manifest per chapter, i.e. 300 round trips to start a
long series and 300 series-page scrapes upstream whenever the chapter-list cache
misses.

The reason this file leads with the gate tests rather than the shape tests: the
bug that shipped here last week was a manifest served from cache bypassing the
18+ gate (commit 1197124). A bulk path is the same trap one layer up — it reads
the same global cache rows on behalf of a per-caller gate — so the invariants
are pinned first and the convenience is tested after.
"""

from __future__ import annotations

import threading

import pytest

import connectors.registry as registry
from connectors.base import SourceConnector
from connectors.models import BrowseMode, Chapter, PaginatedSeriesList, Page, Series
from core.config import get_settings
from core.errors import AppError
from services.browse_service import get_browse_service
from services.reader_service import ReaderService
from tests._fakes import FakeBrowse

SRC = "mangadex"
SERIES = "omniscient-reader"

def fixture() -> dict:
    """A FRESH fixture per call.

    Several tests below mutate the chapter list (a chapter published upstream,
    a series that answers empty). A module-level dict would carry those
    mutations into every later test in the file — ``FakeBrowse`` keeps the dict
    it is handed, it does not copy it.
    """
    return {
        (SRC, SERIES): {
            "meta": {"title": "Omniscient Reader"},
            "chapters": [
                {"id": f"ch-{n}", "number": float(n), "title": f"Episode {n}"}
                for n in range(1, 6)
            ],
            "pages": {
                f"ch-{n}": [
                    {"number": p, "image_url": f"/sources/{SRC}/pages/c{n}p{p}/image"}
                    for p in range(1, 4)
                ]
                for n in range(1, 6)
            },
        }
    }


def _svc(db, browse=None) -> tuple[ReaderService, FakeBrowse]:
    browse = browse or FakeBrowse(fixture())
    return ReaderService(browse, db=db), browse


# ---------------------------------------------------------------------------
# invariant: the 18+ gate
# ---------------------------------------------------------------------------


def test_bulk_manifest_applies_the_18plus_gate_before_reading_the_cache(db_session):
    """The window must 404 ``source_not_found`` for a gated caller — even for
    chapters this very service already cached for someone else.

    This is the regression that shipped on the single manifest: the chapter list
    comes from ``source_series_cache``, whose rows are GLOBAL, while the gate is
    per-(user, profile). Without ``ensure_visible`` first, a gated caller gets
    a window back whose per-item errors distinguish "cached mature source" from
    "source that was never installed" — the exact bit a closed gate exists to
    withhold — and, worse than the single-manifest bug, an ungated *page list*
    for every chapter that happened to resolve.
    """
    src = "toonily"
    fixture = {
        (src, SERIES): {
            "meta": {"title": "Gated"},
            "chapters": [
                {"id": "ch-1", "number": 1.0, "title": "One"},
                {"id": "ch-2", "number": 2.0, "title": "Two"},
            ],
            "pages": {
                "ch-1": [{"number": 1, "image_url": "/a"}],
                "ch-2": [{"number": 1, "image_url": "/b"}],
            },
        }
    }
    browse = FakeBrowse(fixture)
    svc = ReaderService(browse, db=db_session)
    # Gate open: warms source_series_cache exactly as a permitted profile would.
    warm = svc.manifest_batch(src, SERIES, ["ch-1", "ch-2"])
    assert warm["ok_count"] == 2

    browse.mature_sources = {src}
    browse.gate_open = False

    for window in (["ch-1"], ["ch-1", "ch-2"], ["no-such-chapter"], ["ch-1", "nope"]):
        with pytest.raises(AppError) as excinfo:
            svc.manifest_batch(src, SERIES, window)
        assert excinfo.value.status_code == 404
        assert excinfo.value.code == "source_not_found", (
            f"window {window!r} disclosed that the source exists"
        )


def test_bulk_manifest_gate_runs_before_any_upstream_or_cache_read(db_session):
    """Not just "the answer is 404" — nothing may be *read* on the way there.

    A gate applied after the fetch still leaks through timing and still costs
    the upstream site a scrape on behalf of a caller who may not see it.
    """
    src = "toonily"
    fixture = {
        (src, SERIES): {
            "meta": {"title": "Gated"},
            "chapters": [{"id": "ch-1", "number": 1.0, "title": "One"}],
            "pages": {"ch-1": [{"number": 1, "image_url": "/a"}]},
        }
    }
    browse = FakeBrowse(fixture)
    browse.mature_sources = {src}
    browse.gate_open = False
    svc = ReaderService(browse, db=db_session)

    with pytest.raises(AppError):
        svc.manifest_batch(src, SERIES, ["ch-1"])

    assert browse.calls == [], (
        f"the gate must precede every read; connector calls were {browse.calls}"
    )


# ---------------------------------------------------------------------------
# invariant: profile scoping, end to end through the real DI
# ---------------------------------------------------------------------------


STUB_SOURCE = "stubmature"
STUB_SERIES = "gated-series/with-a/slash"


class StubMatureConnector(SourceConnector):
    """A MATURE manga source with canned pages — no network, real registry.

    The FakeBrowse tests above pin the service; this one pins the wiring, which
    is where profile scoping actually lives: ``get_browse_service`` resolves the
    18+ gate from the request's ``(user_id, profile_id)``, and the bulk route
    has to inherit that rather than reading a global setting.
    """

    SOURCE_TYPE = STUB_SOURCE
    DISPLAY_NAME = "Stub Mature"
    DESCRIPTION = "Test-only mature manga source."
    BROWSABLE = True
    SUPPORTS_IMPORT = False
    MATURE = True
    CONTENT_KIND = "manga"

    @property
    def source_type(self) -> str:
        return self.SOURCE_TYPE

    @property
    def display_name(self) -> str:
        return self.DISPLAY_NAME

    def list_browse_modes(self) -> list[BrowseMode]:
        return [BrowseMode(id="default", label="Browse")]

    def get_series_list(self, page: int, *, sort: str | None = None):
        return PaginatedSeriesList(
            items=[Series(id=STUB_SERIES, title="Gated", chapter_count=3)],
            page=page,
            page_size=20,
            total=1,
        )

    def search_series(self, query: str, page: int, *, sort: str | None = None):
        return self.get_series_list(page, sort=sort)

    def get_series(self, series_id: str) -> Series | None:
        if series_id != STUB_SERIES:
            return None
        return Series(id=STUB_SERIES, title="Gated", chapter_count=3)

    def get_chapters(self, series_id: str) -> list[Chapter]:
        if series_id != STUB_SERIES:
            return []
        return [
            Chapter(
                id=f"ch-{n}",
                series_id=STUB_SERIES,
                title=f"Chapter {n}",
                number=float(n),
                page_count=2,
            )
            for n in (1, 2, 3)
        ]

    def get_chapter_pages(self, chapter_id: str) -> list[Page]:
        return [
            Page(id=f"{chapter_id}-p{p}", chapter_id=chapter_id, number=p)
            for p in (1, 2)
        ]

    def find_page(self, page_id: str) -> Page | None:
        return None


@pytest.fixture
def stub_mature_source():
    registry.register_connector(STUB_SOURCE, StubMatureConnector)
    yield
    registry._REGISTRY.pop(STUB_SOURCE, None)
    registry._INSTANCE_CACHE.pop(STUB_SOURCE, None)


def test_bulk_manifest_is_scoped_to_the_requesting_profile(
    client, as_user, make_user, make_profile, stub_mature_source
):
    """Two profiles of ONE account: 18+ on sees the window, 18+ off gets a 404.

    Same user, same session token, same cached rows — only ``X-Profile-Id``
    differs. If the bulk path ever resolves its gate from ``get_settings()``
    instead of the request's profile (the bug that made the in-app toggle inert
    once before), the two calls return the same thing and this fails.
    """
    user = make_user("reader")
    adult = make_profile(user.id, "Adult", mature_content_enabled=True)
    kid = make_profile(user.id, "Kid", mature_content_enabled=False)
    body = {
        "source_id": STUB_SOURCE,
        "series_key": STUB_SERIES,
        "chapter_keys": ["ch-1", "ch-2"],
    }

    allowed = client.post(
        "/reader/chapters/manifest", json=body, headers=as_user(user.id, adult.id)
    )
    assert allowed.status_code == 200, allowed.text
    assert allowed.json()["ok_count"] == 2

    gated = client.post(
        "/reader/chapters/manifest", json=body, headers=as_user(user.id, kid.id)
    )
    assert gated.status_code == 404, gated.text
    assert gated.json()["code"] == "source_not_found"


def test_bulk_manifest_gate_holds_after_the_permitted_profile_warmed_the_cache(
    client, as_user, make_user, make_profile, stub_mature_source
):
    """Order matters: the gated profile asks SECOND, with the cache hot."""
    user = make_user("reader2")
    adult = make_profile(user.id, "Adult", mature_content_enabled=True)
    kid = make_profile(user.id, "Kid", mature_content_enabled=False)
    body = {
        "source_id": STUB_SOURCE,
        "series_key": STUB_SERIES,
        "chapter_keys": ["ch-1", "ch-2", "ch-3"],
    }

    assert (
        client.post(
            "/reader/chapters/manifest", json=body, headers=as_user(user.id, adult.id)
        ).status_code
        == 200
    )
    gated = client.post(
        "/reader/chapters/manifest", json=body, headers=as_user(user.id, kid.id)
    )
    assert gated.status_code == 404
    assert gated.json()["code"] == "source_not_found"
    assert "items" not in gated.json()


# ---------------------------------------------------------------------------
# the window reuses the single-manifest logic
# ---------------------------------------------------------------------------


def test_bulk_item_manifest_is_identical_to_the_single_manifest(db_session):
    """Per-chapter payloads must come from the same code path, not a copy.

    Clients are written against ``GET /reader/chapter/manifest`` verbatim; a
    second implementation that drifts by one field is a client bug nobody can
    see from the server.
    """
    svc, _ = _svc(db_session)
    single = {key: svc.manifest(SRC, SERIES, key) for key in ("ch-1", "ch-3", "ch-5")}

    svc2, _ = _svc(db_session)
    window = svc2.manifest_batch(SRC, SERIES, ["ch-1", "ch-3", "ch-5"])

    assert [item["chapter_key"] for item in window["items"]] == ["ch-1", "ch-3", "ch-5"]
    for item in window["items"]:
        assert item["status"] == "ok"
        assert item["error"] is None
        assert item["manifest"] == single[item["chapter_key"]]


def test_bulk_manifest_preserves_request_order(db_session):
    svc, _ = _svc(db_session)
    order = ["ch-4", "ch-1", "ch-5", "ch-2"]
    window = svc.manifest_batch(SRC, SERIES, order)
    assert [item["chapter_key"] for item in window["items"]] == order


def test_bulk_manifest_resolves_the_chapter_list_once_for_the_window(db_session):
    """The whole point: N chapters must not cost N series-page scrapes.

    ``BrowseService.get_series`` + ``get_chapters`` are the expensive upstream
    pair (measured at 272-355 ms per call on the VPS against asurascans). A
    window pays for them once; only ``get_chapter_pages`` is genuinely
    per-chapter.
    """
    svc, browse = _svc(db_session)
    svc.manifest_batch(SRC, SERIES, [f"ch-{n}" for n in range(1, 6)])

    kinds = [call.split(":", 1)[0] for call in browse.calls]
    assert kinds.count("get_series") == 1, browse.calls
    assert kinds.count("get_chapters") == 1, browse.calls
    assert kinds.count("get_chapter_pages") == 5, browse.calls


def test_bulk_manifest_uses_the_source_cache_on_the_next_window(db_session):
    """A second window over the same series touches no series page at all."""
    svc, browse = _svc(db_session)
    svc.manifest_batch(SRC, SERIES, ["ch-1", "ch-2"])
    browse.calls.clear()

    svc.manifest_batch(SRC, SERIES, ["ch-3", "ch-4"])

    kinds = {call.split(":", 1)[0] for call in browse.calls}
    assert "get_series" not in kinds, browse.calls
    assert "get_chapters" not in kinds, browse.calls
    assert "get_chapter_pages" in kinds


def test_bulk_manifest_fetches_a_repeated_key_once(db_session):
    svc, browse = _svc(db_session)
    window = svc.manifest_batch(SRC, SERIES, ["ch-2", "ch-2", "ch-3"])

    assert [item["chapter_key"] for item in window["items"]] == [
        "ch-2",
        "ch-2",
        "ch-3",
    ]
    fetched = [c for c in browse.calls if c.startswith("get_chapter_pages")]
    assert len(fetched) == 2, fetched


def test_bulk_manifest_refetches_once_for_a_chapter_newer_than_the_cache(db_session):
    """A stale list missing several chapters costs ONE live refetch, not N."""
    svc, browse = _svc(db_session)
    svc.manifest_batch(SRC, SERIES, ["ch-1"])  # cache holds ch-1..ch-5

    for n in (6, 7, 8):
        browse.series[(SRC, SERIES)]["chapters"].append(
            {"id": f"ch-{n}", "number": float(n), "title": f"Episode {n}"}
        )
        browse.series[(SRC, SERIES)]["pages"][f"ch-{n}"] = [
            {"number": 1, "image_url": f"/sources/{SRC}/pages/c{n}p1/image"}
        ]
    browse.calls.clear()

    window = svc.manifest_batch(SRC, SERIES, ["ch-6", "ch-7", "ch-8"])

    assert window["ok_count"] == 3
    assert window["items"][2]["manifest"]["chapter_number"] == 8.0
    kinds = [call.split(":", 1)[0] for call in browse.calls]
    assert kinds.count("get_chapters") == 1, browse.calls


# ---------------------------------------------------------------------------
# honest degradation
# ---------------------------------------------------------------------------


def test_one_failing_chapter_does_not_sink_the_window(db_session):
    """Chapter 3 of 5 fails upstream: four manifests come back, not a 500."""

    class Flaky(FakeBrowse):
        def get_chapter_pages(self, source_id, chapter_key):
            if chapter_key == "ch-3":
                raise RuntimeError("upstream exploded")
            return super().get_chapter_pages(source_id, chapter_key)

    svc, _ = _svc(db_session, Flaky(fixture()))
    window = svc.manifest_batch(SRC, SERIES, [f"ch-{n}" for n in range(1, 6)])

    assert window["requested"] == 5
    assert window["ok_count"] == 4
    assert window["failed_count"] == 1
    failed = window["items"][2]
    assert failed["chapter_key"] == "ch-3"
    assert failed["status"] == "error"
    assert failed["manifest"] is None
    assert failed["error"]["status"] == 502
    # The upstream exception text is a server internal and must not ride along.
    assert "exploded" not in failed["error"]["message"]
    for ok in (0, 1, 3, 4):
        assert window["items"][ok]["status"] == "ok"
        assert window["items"][ok]["manifest"]["page_count"] == 3


def test_a_cloudflare_block_is_reported_per_chapter_in_the_standard_shape(db_session):
    from connectors.http.client import ConnectorHttpError

    class Blocked(FakeBrowse):
        def get_chapter_pages(self, source_id, chapter_key):
            if chapter_key == "ch-2":
                raise ConnectorHttpError("blocked", status_code=403)
            return super().get_chapter_pages(source_id, chapter_key)

    svc, _ = _svc(db_session, Blocked(fixture()))
    window = svc.manifest_batch(SRC, SERIES, ["ch-1", "ch-2"])

    err = window["items"][1]["error"]
    assert err["code"] == "source_unreachable"
    assert err["status"] == 502
    assert "Cloudflare" in err["message"]


def test_an_unknown_chapter_is_a_per_item_404_not_a_window_failure(db_session):
    svc, _ = _svc(db_session)
    window = svc.manifest_batch(SRC, SERIES, ["ch-1", "ch-nope", "ch-2"])

    assert window["ok_count"] == 2
    bad = window["items"][1]
    assert bad["status"] == "error"
    assert bad["error"] == {
        "code": "chapter_not_found",
        "status": 404,
        "message": "Chapter not found.",
    }


def test_an_unresolvable_series_fails_the_whole_window(db_session):
    """Series-level failures ARE window-level: without the chapter list nothing
    can be identified, and that is exactly what the single manifest says too."""
    browse = FakeBrowse(fixture())
    browse.series[(SRC, SERIES)]["chapters"] = []
    svc = ReaderService(browse, db=db_session)

    with pytest.raises(AppError) as excinfo:
        svc.manifest_batch(SRC, SERIES, ["ch-1", "ch-2"])
    assert excinfo.value.code == "series_not_found"
    assert excinfo.value.status_code == 404


def test_chapter_keys_tolerate_surrounding_slashes_like_the_single_manifest(db_session):
    svc, _ = _svc(db_session)
    window = svc.manifest_batch(SRC, SERIES, ["/ch-2", "ch-3/"])
    assert window["ok_count"] == 2
    assert window["items"][0]["manifest"]["chapter_number"] == 2.0
    assert window["items"][1]["manifest"]["chapter_number"] == 3.0


# ---------------------------------------------------------------------------
# the cap
# ---------------------------------------------------------------------------


def test_window_over_the_cap_is_413_and_names_the_cap(db_session, monkeypatch):
    monkeypatch.setenv("MM_READER_BULK_MAX_CHAPTERS", "3")
    get_settings.cache_clear()
    try:
        svc, browse = _svc(db_session)
        with pytest.raises(AppError) as excinfo:
            svc.manifest_batch(SRC, SERIES, ["ch-1", "ch-2", "ch-3", "ch-4"])
        assert excinfo.value.status_code == 413
        assert excinfo.value.code == "batch_too_large"
        assert excinfo.value.details == {"max_chapters": 3, "received": 4}
        assert browse.calls == [], "an over-cap window must cost nothing upstream"
    finally:
        get_settings.cache_clear()


def test_every_window_echoes_the_cap_so_clients_can_page(db_session):
    svc, _ = _svc(db_session)
    window = svc.manifest_batch(SRC, SERIES, ["ch-1"])
    assert window["max_chapters"] == get_settings().reader_bulk_max_chapters
    assert window["max_chapters"] >= 1


def test_a_window_at_exactly_the_cap_is_accepted(db_session, monkeypatch):
    monkeypatch.setenv("MM_READER_BULK_MAX_CHAPTERS", "3")
    get_settings.cache_clear()
    try:
        svc, _ = _svc(db_session)
        window = svc.manifest_batch(SRC, SERIES, ["ch-1", "ch-2", "ch-3"])
        assert window["ok_count"] == 3
        assert window["max_chapters"] == 3
    finally:
        get_settings.cache_clear()


# ---------------------------------------------------------------------------
# bounded concurrency
# ---------------------------------------------------------------------------


def test_fan_out_never_exceeds_the_configured_concurrency(db_session, monkeypatch):
    """Two vCPU, and Toonily/Bbato are already Cloudflare-blocked at this
    egress: a window must overlap round trips, never burst."""
    monkeypatch.setenv("MM_BULK_FETCH_CONCURRENCY", "2")
    get_settings.cache_clear()
    try:
        state = {"live": 0, "peak": 0}
        lock = threading.Lock()

        class Counting(FakeBrowse):
            def get_chapter_pages(self, source_id, chapter_key):
                with lock:
                    state["live"] += 1
                    state["peak"] = max(state["peak"], state["live"])
                try:
                    threading.Event().wait(0.02)
                    return super().get_chapter_pages(source_id, chapter_key)
                finally:
                    with lock:
                        state["live"] -= 1

        svc, _ = _svc(db_session, Counting(fixture()))
        window = svc.manifest_batch(SRC, SERIES, [f"ch-{n}" for n in range(1, 6)])

        assert window["ok_count"] == 5
        assert state["peak"] <= 2, f"peak in-flight was {state['peak']}"
    finally:
        get_settings.cache_clear()


def test_fan_out_is_actually_parallel(db_session, monkeypatch):
    """Not merely bounded — a window of 4 with concurrency 4 must overlap."""
    monkeypatch.setenv("MM_BULK_FETCH_CONCURRENCY", "4")
    get_settings.cache_clear()
    try:
        barrier = threading.Barrier(4, timeout=10)

        class Overlapping(FakeBrowse):
            def get_chapter_pages(self, source_id, chapter_key):
                barrier.wait()  # deadlocks unless four run at once
                return super().get_chapter_pages(source_id, chapter_key)

        svc, _ = _svc(db_session, Overlapping(fixture()))
        window = svc.manifest_batch(SRC, SERIES, ["ch-1", "ch-2", "ch-3", "ch-4"])
        assert window["ok_count"] == 4
    finally:
        get_settings.cache_clear()


def test_concurrency_of_one_runs_sequentially_without_threads(db_session, monkeypatch):
    monkeypatch.setenv("MM_BULK_FETCH_CONCURRENCY", "1")
    get_settings.cache_clear()
    try:
        seen: list[str] = []

        class Naming(FakeBrowse):
            def get_chapter_pages(self, source_id, chapter_key):
                seen.append(threading.current_thread().name)
                return super().get_chapter_pages(source_id, chapter_key)

        svc, _ = _svc(db_session, Naming(fixture()))
        svc.manifest_batch(SRC, SERIES, ["ch-1", "ch-2", "ch-3"])
        assert set(seen) == {threading.current_thread().name}
    finally:
        get_settings.cache_clear()


# ---------------------------------------------------------------------------
# the endpoint
# ---------------------------------------------------------------------------


def test_bulk_manifest_endpoint_shape(app, client):
    app.dependency_overrides[get_browse_service] = lambda: FakeBrowse(fixture())
    resp = client.post(
        "/reader/chapters/manifest",
        json={
            "source_id": SRC,
            "series_key": SERIES,
            "chapter_keys": ["ch-1", "ch-2", "ch-nope"],
        },
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["source_id"] == SRC
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
    first = body["items"][0]["manifest"]
    assert first["page_count"] == 3
    assert first["prev"] is None and first["next"] == "ch-2"
    assert body["items"][2]["error"]["code"] == "chapter_not_found"


def test_bulk_manifest_endpoint_rejects_an_over_cap_window(app, client, monkeypatch):
    monkeypatch.setenv("MM_READER_BULK_MAX_CHAPTERS", "2")
    get_settings.cache_clear()
    try:
        app.dependency_overrides[get_browse_service] = lambda: FakeBrowse(fixture())
        resp = client.post(
            "/reader/chapters/manifest",
            json={
                "source_id": SRC,
                "series_key": SERIES,
                "chapter_keys": ["ch-1", "ch-2", "ch-3"],
            },
        )
        assert resp.status_code == 413, resp.text
        payload = resp.json()
        assert payload["code"] == "batch_too_large"
        assert payload["details"]["max_chapters"] == 2
    finally:
        get_settings.cache_clear()


def test_bulk_manifest_endpoint_rejects_an_empty_window(app, client):
    app.dependency_overrides[get_browse_service] = lambda: FakeBrowse(fixture())
    resp = client.post(
        "/reader/chapters/manifest",
        json={"source_id": SRC, "series_key": SERIES, "chapter_keys": []},
    )
    assert resp.status_code == 422, resp.text


@pytest.mark.rate_limit
def test_bulk_manifest_endpoint_is_rate_limited_on_its_own_bucket(
    app, client, monkeypatch
):
    """One bulk call is worth ~``max_chapters`` single manifests upstream, so it
    must not be charged from the (much looser) ``sources`` bucket."""
    monkeypatch.setenv("MM_RATE_LIMIT_BULK", "2/minute")
    get_settings.cache_clear()
    try:
        app.dependency_overrides[get_browse_service] = lambda: FakeBrowse(fixture())
        body = {
            "source_id": SRC,
            "series_key": SERIES,
            "chapter_keys": ["ch-1"],
        }
        codes = [
            client.post("/reader/chapters/manifest", json=body).status_code
            for _ in range(3)
        ]
        assert codes[:2] == [200, 200], codes
        assert codes[2] == 429, codes
    finally:
        get_settings.cache_clear()
