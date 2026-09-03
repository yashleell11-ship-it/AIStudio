"""``source_browse_cache``: the browse-listing page cache.

The failure this feature fixes: opening a source took 5-15s because every
browse re-scraped the connector live — only per-series metadata was ever
cached, never the grid itself.

Covered here:
  * fresh hit serves without any connector call (and says so: ``cache.status``)
  * miss / expired refetches live and stores the page
  * connector down serves the last known page flagged ``stale`` — the
    highest-value behaviour: ~6 of 52 sources are dead at any moment
  * the per-caller 18+ gate is applied on every cached read (a mature source's
    cached page must never reach a gated profile — the one way this could leak)
  * a browse write-through populates ``source_series_cache`` without lying
    about chapter freshness
  * eviction bounds the table by oldest ``fetched_at``
  * the background next-page warm (run inline via the module hooks)
"""

from __future__ import annotations

import json
from datetime import timedelta

import pytest

from core.config import get_settings
from core.errors import AppError
from core.time_utils import utcnow
from database.models import SourceBrowseCache, SourceSeriesCache
from services import source_cache_service as scs
from services.source_cache_service import SourceCacheService
from tests._fakes import FakeBrowse

SRC = "asurascans"


def _listing(page: int = 1, *, titles: list[str] | None = None, has_more: bool = True):
    """A serialized paginated listing like ``BrowseService.list_series`` emits."""
    titles = titles if titles is not None else [f"Series {page}-{n}" for n in range(3)]
    return {
        "items": [
            {
                "id": f"key-{page}-{n}",
                "source_id": SRC,
                "title": title,
                "chapter_count": 10,
                "description": f"About {title}",
                "author": "Author",
                "artist": None,
                "status": "ongoing",
                "genres": ["Action"],
                "latest_chapter": "42",
                "cover_url": f"/sources/{SRC}/series/key-{page}-{n}/cover",
            }
            for n, title in enumerate(titles)
        ],
        "page": page,
        "page_size": 3,
        "total": 300,
        "total_pages": 100,
        "has_more": has_more,
    }


def _seed_page(db, *, page: int = 1, sort: str = "", genre: str = "", age_minutes: float = 0.0, listing=None):
    row = SourceBrowseCache(
        source_id=SRC,
        sort=sort,
        genre=genre,
        page=page,
        payload=json.dumps(listing or _listing(page)),
        fetched_at=utcnow() - timedelta(minutes=age_minutes),
    )
    db.add(row)
    db.commit()
    return row


def _svc(db, browse=None, **listings):
    browse = browse or FakeBrowse(listings={(SRC, "", "", 1): _listing(1)})
    return SourceCacheService(db, browse), browse


# ---------------------------------------------------------------------------
# read-through: fresh / miss / expired / force
# ---------------------------------------------------------------------------


def test_miss_fetches_live_stores_the_page_and_says_live(db_session):
    svc, browse = _svc(db_session)

    payload = svc.get_browse_page(SRC)

    assert payload["cache"]["status"] == "live"
    assert payload["cache"]["stale"] is False
    assert payload["items"][0]["title"] == "Series 1-0"
    assert len(browse.calls) == 1
    assert db_session.get(SourceBrowseCache, (SRC, "", "", 1)) is not None


def test_fresh_hit_avoids_the_connector_entirely(db_session):
    _seed_page(db_session, age_minutes=5)
    svc, browse = _svc(db_session)

    payload = svc.get_browse_page(SRC)

    assert browse.calls == []  # the whole point
    assert payload["cache"]["status"] == "fresh"
    assert payload["cache"]["stale"] is False
    assert payload["cache"]["fetched_at"] is not None
    assert payload["items"][0]["title"] == "Series 1-0"


def test_expired_row_is_refetched_live(db_session):
    _seed_page(db_session, age_minutes=999)  # TTL default is 60
    svc, browse = _svc(db_session)

    payload = svc.get_browse_page(SRC)

    assert payload["cache"]["status"] == "live"
    assert len(browse.calls) == 1
    # and the row is fresh again: a second read is a pure cache hit
    browse.calls.clear()
    assert svc.get_browse_page(SRC)["cache"]["status"] == "fresh"
    assert browse.calls == []


def test_force_refetches_even_a_fresh_row(db_session):
    _seed_page(db_session, age_minutes=1)
    svc, browse = _svc(db_session)

    payload = svc.get_browse_page(SRC, force=True)

    assert payload["cache"]["status"] == "live"
    assert len(browse.calls) == 1


def test_key_includes_sort_genre_and_page(db_session):
    listings = {
        (SRC, "", "", 1): _listing(1, titles=["plain"]),
        (SRC, "popular", "", 1): _listing(1, titles=["popular"]),
        (SRC, "", "action", 1): _listing(1, titles=["action"]),
        (SRC, "", "", 2): _listing(2, titles=["page two"]),
    }
    svc, browse = _svc(db_session, FakeBrowse(listings=listings))

    assert svc.get_browse_page(SRC)["items"][0]["title"] == "plain"
    assert svc.get_browse_page(SRC, sort="popular")["items"][0]["title"] == "popular"
    assert svc.get_browse_page(SRC, genre="action")["items"][0]["title"] == "action"
    assert svc.get_browse_page(SRC, page=2)["items"][0]["title"] == "page two"
    assert len(browse.calls) == 4
    # ``sort=default`` is the same facet as no sort — same row, no refetch
    browse.calls.clear()
    assert svc.get_browse_page(SRC, sort="default")["cache"]["status"] == "fresh"
    assert browse.calls == []


# ---------------------------------------------------------------------------
# stale-on-failure — the highest-value behaviour
# ---------------------------------------------------------------------------


def test_connector_down_serves_stale_and_flags_it(db_session):
    _seed_page(db_session, age_minutes=999)  # expired, so a refetch is due
    svc, browse = _svc(db_session)
    browse.down = True

    payload = svc.get_browse_page(SRC)

    assert len(browse.calls) == 1  # it did try
    assert payload["cache"]["status"] == "stale"
    assert payload["cache"]["stale"] is True
    assert payload["cache"]["fetched_at"] is not None  # client can show the age
    assert payload["items"][0]["title"] == "Series 1-0"  # grid, not error screen


def test_connector_down_with_nothing_cached_raises(db_session):
    svc, browse = _svc(db_session)
    browse.down = True

    with pytest.raises((AppError, RuntimeError)):
        svc.get_browse_page(SRC)


def test_force_refresh_against_a_dead_connector_degrades_to_stale(db_session):
    """Pull-to-refresh on a dead source keeps the grid rather than erroring."""
    _seed_page(db_session, age_minutes=1)
    svc, browse = _svc(db_session)
    browse.down = True

    payload = svc.get_browse_page(SRC, force=True)

    assert payload["cache"]["status"] == "stale"
    assert payload["items"]


# ---------------------------------------------------------------------------
# 18+ gate: global rows, per-caller reads (service level; route level below)
# ---------------------------------------------------------------------------


def test_gated_caller_never_sees_a_mature_sources_cached_page(db_session):
    _seed_page(db_session, age_minutes=1)  # someone else's browse cached it
    svc, browse = _svc(db_session)
    browse.mature_sources.add(SRC)
    browse.gate_open = False

    with pytest.raises(AppError) as err:
        svc.get_browse_page(SRC)

    assert err.value.status_code == 404  # existence not disclosed
    assert browse.calls == []


def test_open_caller_is_served_the_same_cached_page(db_session):
    _seed_page(db_session, age_minutes=1)
    svc, browse = _svc(db_session)
    browse.mature_sources.add(SRC)
    browse.gate_open = True

    payload = svc.get_browse_page(SRC)

    assert payload["cache"]["status"] == "fresh"
    assert browse.calls == []


# ---------------------------------------------------------------------------
# write-through into source_series_cache
# ---------------------------------------------------------------------------


def test_browse_write_through_populates_series_cache(db_session):
    svc, _ = _svc(db_session)

    svc.get_browse_page(SRC)

    row = db_session.get(SourceSeriesCache, (SRC, "key-1-0"))
    assert row is not None
    assert row.title == "Series 1-0"
    assert row.cover_url == f"/sources/{SRC}/series/key-1-0/cover"
    assert row.description == "About Series 1-0"
    assert json.loads(row.genres) == ["Action"]
    assert row.chapters is None  # a listing carries no chapter list


def test_browse_write_through_derives_content_rating_from_genres(db_session):
    listing = _listing(1)
    listing["items"][0]["genres"] = ["Adult", "Romance"]
    svc, _ = _svc(db_session, FakeBrowse(listings={(SRC, "", "", 1): listing}))

    svc.get_browse_page(SRC)

    row = db_session.get(SourceSeriesCache, (SRC, "key-1-0"))
    assert row.content_rating == "adult"


def test_partial_series_row_never_satisfies_a_fresh_series_read(db_session):
    """A browse-written row has no chapters; get_series_meta must still fetch
    live rather than serving a silently empty chapter list as 'fresh'."""
    svc, browse = _svc(db_session)
    svc.get_browse_page(SRC)

    fake = FakeBrowse(
        {
            (SRC, "key-1-0"): {
                "meta": {"title": "Series 1-0 (full)"},
                "chapters": [{"id": "c1", "number": 1.0, "title": "Ch 1"}],
            }
        }
    )
    meta = SourceCacheService(db_session, fake).get_series_meta(SRC, "key-1-0")

    assert any(c.startswith("get_series") for c in fake.calls)
    assert len(meta["chapters"]) == 1


def test_partial_series_row_is_still_the_stale_fallback(db_session):
    """...but when the connector is down, the browse-written metadata beats an
    error: title/cover render, chapters just come back empty."""
    svc, _ = _svc(db_session)
    svc.get_browse_page(SRC)

    fake = FakeBrowse()
    fake.down = True
    meta = SourceCacheService(db_session, fake).get_series_meta(SRC, "key-1-0")

    assert meta["title"] == "Series 1-0"
    assert meta["chapters"] == []


def test_browse_write_through_does_not_extend_a_complete_rows_freshness(db_session):
    """Metadata-only writes must not bump fetched_at on an existing row, or
    grids would keep postponing the chapter refetch the series screen needs."""
    old = utcnow() - timedelta(hours=5)
    db_session.add(
        SourceSeriesCache(
            source_id=SRC,
            series_key="key-1-0",
            title="Old title",
            chapters="[]",
            fetched_at=old,
        )
    )
    db_session.commit()

    svc, _ = _svc(db_session)
    svc.get_browse_page(SRC)

    row = db_session.get(SourceSeriesCache, (SRC, "key-1-0"))
    assert row.title == "Series 1-0"  # metadata refreshed
    assert row.fetched_at == old  # freshness NOT extended


# ---------------------------------------------------------------------------
# eviction bounds the table
# ---------------------------------------------------------------------------


def test_eviction_bounds_the_browse_table_oldest_first(db_session, monkeypatch):
    monkeypatch.setenv("MM_BROWSE_CACHE_MAX_ROWS", "3")
    get_settings.cache_clear()

    listings = {(SRC, "", "", p): _listing(p) for p in range(1, 5)}
    svc, _ = _svc(db_session, FakeBrowse(listings=listings))
    for p in range(1, 5):
        svc.get_browse_page(SRC, page=p)

    rows = db_session.query(SourceBrowseCache).all()
    assert len(rows) == 3
    # page 1 was the oldest write; it is the one that went
    assert {row.page for row in rows} == {2, 3, 4}


def test_eviction_bounds_the_series_table_too(db_session, monkeypatch):
    monkeypatch.setenv("MM_SOURCE_CACHE_MAX_ROWS", "4")
    get_settings.cache_clear()

    listings = {(SRC, "", "", p): _listing(p) for p in range(1, 4)}
    svc, _ = _svc(db_session, FakeBrowse(listings=listings))
    for p in range(1, 4):  # 3 pages x 3 items = 9 series rows written
        svc.get_browse_page(SRC, page=p)

    assert db_session.query(SourceSeriesCache).count() <= 4


# ---------------------------------------------------------------------------
# background next-page warm (run inline via the module hooks)
# ---------------------------------------------------------------------------


@pytest.fixture
def inline_warm(monkeypatch, session_factory):
    """Run warms synchronously against the test engine, prefetch enabled."""
    monkeypatch.setenv("MM_BROWSE_PREFETCH_ENABLED", "true")
    get_settings.cache_clear()
    monkeypatch.setattr(scs, "_spawn_warm", lambda work: work())
    monkeypatch.setattr(scs, "_open_warm_session", session_factory)
    yield


def test_warm_populates_the_next_page(db_session, inline_warm, monkeypatch):
    listings = {
        (SRC, "", "", 1): _listing(1),
        (SRC, "", "", 2): _listing(2),
    }
    warm_browse = FakeBrowse(listings=listings)
    monkeypatch.setattr(scs, "_build_warm_browse", lambda db, gate: warm_browse)
    svc, browse = _svc(db_session, FakeBrowse(listings=listings))

    svc.get_browse_page(SRC, warm_next=True)

    assert db_session.get(SourceBrowseCache, (SRC, "", "", 2)) is not None
    # paging forward is now a pure cache hit
    browse.calls.clear()
    payload = svc.get_browse_page(SRC, page=2)
    assert payload["cache"]["status"] == "fresh"
    assert browse.calls == []


def test_no_warm_when_the_next_page_is_already_fresh(db_session, inline_warm, monkeypatch):
    _seed_page(db_session, page=1, age_minutes=1)
    _seed_page(db_session, page=2, age_minutes=1)
    spawned = []
    monkeypatch.setattr(scs, "_spawn_warm", lambda work: spawned.append(work))
    svc, _ = _svc(db_session)

    svc.get_browse_page(SRC, warm_next=True)

    assert spawned == []


def test_no_warm_past_the_last_page(db_session, inline_warm, monkeypatch):
    spawned = []
    monkeypatch.setattr(scs, "_spawn_warm", lambda work: spawned.append(work))
    listing = _listing(1, has_more=False)
    svc, _ = _svc(db_session, FakeBrowse(listings={(SRC, "", "", 1): listing}))

    svc.get_browse_page(SRC, warm_next=True)

    assert spawned == []


def test_no_warm_after_a_stale_serve(db_session, inline_warm, monkeypatch):
    """A stale serve means the connector is down — do not pile on."""
    spawned = []
    monkeypatch.setattr(scs, "_spawn_warm", lambda work: spawned.append(work))
    _seed_page(db_session, age_minutes=999)
    svc, browse = _svc(db_session)
    browse.down = True

    payload = svc.get_browse_page(SRC, warm_next=True)

    assert payload["cache"]["status"] == "stale"
    assert spawned == []


# ---------------------------------------------------------------------------
# route level: the gate and the cache block on the wire
# ---------------------------------------------------------------------------
#
# These go through the real BrowseService/ProfileContext stack — only the
# connector registry is faked — because the leak this guards against lives in
# the wiring: a mature source's GLOBAL cache row being served to a profile
# whose own 18+ gate is closed.

from unittest.mock import patch

from connectors.models import PaginatedSeriesList, Series as ConnectorSeries


class _RouteConnector:
    """Registry-level fake: visible to ``_get_connector``, counts fetches."""

    is_browsable = True

    def __init__(self, *, mature: bool = False, listing=None) -> None:
        self.is_mature = mature
        self._listing = listing
        self.calls = 0

    def get_series_list(self, page: int, *, sort=None) -> PaginatedSeriesList:
        self.calls += 1
        if self._listing is None:
            raise AssertionError("connector must not be reached on a cache hit")
        return self._listing

    def search_series(self, query: str, page: int, *, sort=None) -> PaginatedSeriesList:
        self.calls += 1
        return PaginatedSeriesList(
            items=[ConnectorSeries(id="s-1", title="Found live")], api_has_more=False
        )


def test_route_gated_profile_gets_404_despite_a_cached_mature_page(
    app, client, as_user, make_user, make_profile, db_session
):
    _seed_page(db_session, age_minutes=1)  # cached by some open profile earlier
    user = make_user("prude2")
    profile = make_profile(user.id, "SFW", mature_content_enabled=False)
    connector = _RouteConnector(mature=True)

    with patch("services.browse_service.create_connector", return_value=connector):
        response = client.get(
            f"/sources/{SRC}/series", headers=as_user(user.id, profile.id)
        )

    assert response.status_code == 404  # not 403: existence is not disclosed
    assert connector.calls == 0
    body = response.text
    assert "Series 1-0" not in body  # nothing of the cached page leaks


def test_route_open_profile_is_served_the_cached_mature_page(
    app, client, as_user, make_user, make_profile, db_session
):
    _seed_page(db_session, age_minutes=1)
    user = make_user("adult2")
    profile = make_profile(user.id, "NSFW", mature_content_enabled=True)
    connector = _RouteConnector(mature=True)

    with patch("services.browse_service.create_connector", return_value=connector):
        response = client.get(
            f"/sources/{SRC}/series", headers=as_user(user.id, profile.id)
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["cache"]["status"] == "fresh"
    assert payload["items"][0]["title"] == "Series 1-0"
    assert connector.calls == 0  # cache hit: the connector was never touched


def test_route_search_bypasses_the_cache_and_reports_live(
    app, client, as_user, make_user, make_profile, db_session
):
    _seed_page(db_session, age_minutes=1)  # a cached page must not answer a search
    user = make_user("searcher")
    profile = make_profile(user.id, "P")
    connector = _RouteConnector(mature=False)

    with patch("services.browse_service.create_connector", return_value=connector):
        response = client.get(
            f"/sources/{SRC}/series",
            params={"query": "solo"},
            headers=as_user(user.id, profile.id),
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["cache"]["status"] == "live"
    assert payload["items"][0]["title"] == "Found live"
    assert connector.calls == 1


def test_route_refresh_param_forces_a_live_refetch(
    app, client, as_user, make_user, make_profile, db_session
):
    _seed_page(db_session, age_minutes=1)
    user = make_user("refresher")
    profile = make_profile(user.id, "P")
    live = PaginatedSeriesList(
        items=[ConnectorSeries(id="n-1", title="Fresh off the wire")],
        api_has_more=False,
    )
    connector = _RouteConnector(listing=live)

    with patch("services.browse_service.create_connector", return_value=connector):
        response = client.get(
            f"/sources/{SRC}/series",
            params={"refresh": "true"},
            headers=as_user(user.id, profile.id),
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["cache"]["status"] == "live"
    assert payload["items"][0]["title"] == "Fresh off the wire"
    assert connector.calls == 1
