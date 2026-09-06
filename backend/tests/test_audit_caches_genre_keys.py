"""AUDIT (caches shard): ``genre`` is an unvalidated, unbounded browse-cache key.

``source_browse_cache`` is keyed ``(source_id, sort, genre, page)`` and the
route hands ``genre`` straight through (routes/sources.py:245 ->
``SourceCacheService.get_browse_page``; ``_normalize_genre`` only strips).

Two gaps, each pinned by one FAILING test:

1. ``BrowseService.list_series`` falls back to ``connector.search_series(genre)``
   when the connector has no ``browse_by_genre`` (browse_service.py:622-631;
   the base class raises ``NotImplementedError`` at connectors/base.py:126 and
   only 26 of 93 registered connectors override it), and
   ``get_browse_page`` then stores that SEARCH result under a browse key --
   while the module docstring (source_cache_service.py:245-247) says search
   results are "deliberately NOT cached: their key cardinality is unbounded".
2. Even where genre browse exists, the caller's string is never checked
   against ``connector.list_genres()``; every distinct value is a new row,
   and the only bound is ``browse_cache_max_rows`` (2000), so 2000 junk
   genres evict every real page.
"""

from __future__ import annotations

from sqlalchemy import func, select

from connectors.models import BrowseMode, PaginatedSeriesList, Series
from database.models import SourceBrowseCache
from services import browse_service as bs
from services.browse_service import BrowseService
from services.source_cache_service import SourceCacheService

SRC = "audit-stub-source"


def _listing(page: int) -> PaginatedSeriesList:
    return PaginatedSeriesList(
        items=[Series(id=f"k{page}-{n}", title=f"Series {page}-{n}") for n in range(3)],
        page=page,
        page_size=3,
        total=30,
    )


class _StubConnector:
    """Just enough surface for ``BrowseService._get_connector``/``list_series``."""

    is_browsable = True
    is_mature = False
    content_kind = "manga"

    def __init__(self, *, genre_browse: bool) -> None:
        self._genre_browse = genre_browse
        self.search_calls: list[tuple[str, int]] = []
        self.genre_calls: list[tuple[str, int]] = []

    def list_browse_modes(self) -> list[BrowseMode]:
        return [BrowseMode(id="default", label="Default")]

    def list_genres(self) -> list[BrowseMode]:
        return [BrowseMode(id="action", label="Action")]

    def get_series_list(self, page: int, *, sort: str | None = None) -> PaginatedSeriesList:
        return _listing(page)

    def search_series(self, query: str, page: int, *, sort: str | None = None) -> PaginatedSeriesList:
        self.search_calls.append((query, page))
        return _listing(page)

    def browse_by_genre(self, genre: str, page: int, *, sort: str | None = None) -> PaginatedSeriesList:
        if not self._genre_browse:
            raise NotImplementedError("no genre browse")  # the base-class default
        self.genre_calls.append((genre, page))
        return _listing(page)


def _cached_genres(db) -> list[str]:
    return sorted(
        db.execute(select(SourceBrowseCache.genre).where(SourceBrowseCache.source_id == SRC))
        .scalars()
        .all()
    )


def test_genre_that_falls_back_to_search_is_not_cached(db_session, monkeypatch):
    stub = _StubConnector(genre_browse=False)
    monkeypatch.setattr(bs, "create_connector", lambda source_id, **_cfg: stub)
    svc = SourceCacheService(db_session, BrowseService(mature_enabled=True))

    svc.get_browse_page(SRC, genre="anything a user typed")

    # Premise: with no genre browse this WAS a search against the connector.
    assert stub.search_calls == [("anything a user typed", 1)]
    # Rule the docstring claims: search results are never cached.
    assert _cached_genres(db_session) == [], (
        "a SEARCH result was stored in source_browse_cache under a browse key"
    )


def test_unadvertised_genre_is_not_a_cache_key(db_session, monkeypatch):
    stub = _StubConnector(genre_browse=True)
    monkeypatch.setattr(bs, "create_connector", lambda source_id, **_cfg: stub)
    svc = SourceCacheService(db_session, BrowseService(mature_enabled=True))

    for n in range(5):
        svc.get_browse_page(SRC, genre=f"junk-{n}")

    total = db_session.execute(select(func.count()).select_from(SourceBrowseCache)).scalar_one()
    assert total == 0, (
        f"{total} rows keyed by genres the connector never advertised "
        f"(list_genres() == ['action']); the only bound on this key space is "
        f"browse_cache_max_rows"
    )
