"""MM_NOVELS_ENABLED — the one non-negotiable (spec 2026-09-04 §2).

Production must remain a manhwa site: with the flag OFF (the default, and
what the prod compose runs), novel connectors are absent from every registry
surface and ``/novels/*`` is a stock 404 — indistinguishable from routes
that were never built. With the flag ON, the sources listing carries
``content_kind`` / ``language`` and the chapter-text endpoint serves the
spec §3 shape. Both states are exercised here in one process.

The novel source used is a locally-registered stub connector — these tests
pin the FOUNDATION contract every fleet-built connector plugs into, so they
must not depend on any particular site connector existing.
"""

from __future__ import annotations

import pytest

import connectors.registry as registry
from connectors.base import SourceConnector
from connectors.models import (
    BrowseMode,
    Chapter,
    NovelChapterText,
    Page,
    PaginatedSeriesList,
    Series,
)
from core.config import get_settings
from database.session import get_db

STUB_SOURCE = "stubnovel"
SERIES = "stub-series/with-a/slash"
CHAPTERS = ("ch-1", "ch-2", "ch-3")


class StubNovelConnector(SourceConnector):
    """A minimal novel connector: exactly the fleet contract, nothing more."""

    SOURCE_TYPE = STUB_SOURCE
    DISPLAY_NAME = "Stub Novel"
    DESCRIPTION = "Test-only novel source."
    BROWSABLE = True
    SUPPORTS_IMPORT = False
    MATURE = False
    CONTENT_KIND = "novel"
    LANGUAGE = "en"

    #: (series_key, chapter_key) -> NovelChapterText | None; tests mutate.
    TEXTS: dict[tuple[str, str], NovelChapterText | None] = {}
    RAISE: Exception | None = None

    @property
    def source_type(self) -> str:
        return self.SOURCE_TYPE

    @property
    def display_name(self) -> str:
        return self.DISPLAY_NAME

    def list_browse_modes(self) -> list[BrowseMode]:
        return [BrowseMode(id="default", label="Browse")]

    def get_series_list(self, page: int, *, sort: str | None = None) -> PaginatedSeriesList:
        return PaginatedSeriesList(
            items=[Series(id=SERIES, title="Stub Series", chapter_count=3)],
            page=page,
            page_size=20,
            total=1,
        )

    def search_series(self, query: str, page: int, *, sort: str | None = None) -> PaginatedSeriesList:
        return self.get_series_list(page, sort=sort)

    def get_series(self, series_id: str) -> Series | None:
        if series_id != SERIES:
            return None
        return Series(id=SERIES, title="Stub Series", chapter_count=3)

    def get_chapters(self, series_id: str) -> list[Chapter]:
        if series_id != SERIES:
            return []
        return [
            Chapter(
                id=key,
                series_id=SERIES,
                title=f"Chapter {n}",
                number=float(n),
                page_count=0,
            )
            for n, key in enumerate(CHAPTERS, start=1)
        ]

    def get_chapter_pages(self, chapter_id: str) -> list[Page]:
        return []

    def find_page(self, page_id: str) -> Page | None:
        return None

    def chapter_text(self, series_key: str, chapter_key: str) -> NovelChapterText | None:
        if type(self).RAISE is not None:
            raise type(self).RAISE
        return type(self).TEXTS.get((series_key, chapter_key))


@pytest.fixture
def stub_registered():
    """Register the stub for one test; leave the real registry untouched after."""
    registry.register_connector(STUB_SOURCE, StubNovelConnector)
    StubNovelConnector.TEXTS = {
        (SERIES, "ch-2"): NovelChapterText(
            title="Chapter 2",
            paragraphs=("First paragraph.", "Second paragraph."),
            chapter_number=2.0,
        )
    }
    StubNovelConnector.RAISE = None
    yield
    registry._REGISTRY.pop(STUB_SOURCE, None)
    registry._INSTANCE_CACHE.pop(STUB_SOURCE, None)
    StubNovelConnector.TEXTS = {}
    StubNovelConnector.RAISE = None


def _make_app(session_factory):
    from main import create_app

    def override_get_db():
        db = session_factory()
        try:
            yield db
        finally:
            db.close()

    application = create_app(run_migrations=False, run_workers=False)
    application.dependency_overrides[get_db] = override_get_db
    return application


@pytest.fixture
def novels_on(monkeypatch, session_factory, stub_registered):
    """A TestClient against an app built with MM_NOVELS_ENABLED=true."""
    from fastapi.testclient import TestClient

    monkeypatch.setenv("MM_NOVELS_ENABLED", "true")
    get_settings.cache_clear()
    app = _make_app(session_factory)
    with TestClient(app) as test_client:
        yield test_client
    get_settings.cache_clear()


@pytest.fixture
def novels_off(monkeypatch, session_factory, stub_registered):
    """A TestClient with the flag at its default (false) — production's state."""
    from fastapi.testclient import TestClient

    monkeypatch.delenv("MM_NOVELS_ENABLED", raising=False)
    get_settings.cache_clear()
    app = _make_app(session_factory)
    with TestClient(app) as test_client:
        yield test_client
    get_settings.cache_clear()


# ---------------------------------------------------------------------------
# Flag OFF — production must remain a manhwa site
# ---------------------------------------------------------------------------


def test_default_is_off():
    get_settings.cache_clear()
    assert get_settings().novels_enabled is False


def test_flag_off_sources_listing_contains_no_novel_source(novels_off):
    rows = novels_off.get("/sources").json()
    assert rows  # the manga sources are all still there
    assert all(row["content_kind"] == "manga" for row in rows)
    assert STUB_SOURCE not in {row["id"] for row in rows}


def test_flag_off_registry_refuses_novel_types(novels_off):
    assert STUB_SOURCE in registry._REGISTRY  # registered...
    assert STUB_SOURCE not in registry.list_connector_types()  # ...but absent
    with pytest.raises(ValueError):
        registry.create_connector(STUB_SOURCE)


def test_flag_off_novel_routes_are_indistinguishable_from_absent(novels_off):
    novel_route = novels_off.get(
        "/novels/chapter",
        params={"source": STUB_SOURCE, "series": SERIES, "chapter": "ch-2"},
    )
    absent_route = novels_off.get("/definitely-not-a-route")
    assert novel_route.status_code == 404
    assert novel_route.json() == absent_route.json()


def test_flag_off_browsing_a_novel_source_is_source_not_found(novels_off):
    response = novels_off.get(f"/sources/{STUB_SOURCE}/series")
    assert response.status_code == 404
    assert response.json()["code"] == "source_not_found"


def test_flag_off_bootstrap_status_says_so(novels_off):
    body = novels_off.get("/auth/bootstrap-status").json()
    assert body["novels_enabled"] is False


def test_flag_off_openapi_has_no_novel_paths(novels_off):
    from main import create_app

    app = create_app(run_migrations=False, run_workers=False)
    assert not [p for p in app.openapi()["paths"] if p.startswith("/novels")]


# ---------------------------------------------------------------------------
# Flag ON — the whole surface appears
# ---------------------------------------------------------------------------


def test_flag_on_sources_listing_carries_content_kind_and_language(novels_on):
    rows = novels_on.get("/sources").json()
    by_id = {row["id"]: row for row in rows}
    assert STUB_SOURCE in by_id
    stub = by_id[STUB_SOURCE]
    assert stub["content_kind"] == "novel"
    assert stub["language"] == "en"
    # The manga sources are implicitly manga and undeclared-language — the
    # base-class default, no churn across the ~50 existing connectors. (Real
    # novel connectors may be registered besides the stub; every one of them
    # must declare English.)
    manga_rows = [row for row in rows if row["content_kind"] == "manga"]
    assert manga_rows
    assert all(row["language"] is None for row in manga_rows)
    novel_rows = [row for row in rows if row["content_kind"] == "novel"]
    assert all(row["language"] == "en" for row in novel_rows)


def test_flag_on_bootstrap_status_says_so(novels_on):
    body = novels_on.get("/auth/bootstrap-status").json()
    assert body["novels_enabled"] is True


def test_flag_on_chapter_endpoint_serves_the_spec_shape(novels_on):
    response = novels_on.get(
        "/novels/chapter",
        params={"source": STUB_SOURCE, "series": SERIES, "chapter": "ch-2"},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["title"] == "Chapter 2"
    assert body["chapter_number"] == 2.0
    assert body["paragraphs"] == ["First paragraph.", "Second paragraph."]
    assert body["prev"] == "ch-1"
    assert body["next"] == "ch-3"
    assert body["word_count"] == 4
    assert body["source_id"] == STUB_SOURCE
    assert body["series_key"] == SERIES
    assert body["chapter_key"] == "ch-2"
    assert body["cache"]["status"] == "live"


def test_flag_on_unknown_chapter_is_404(novels_on):
    response = novels_on.get(
        "/novels/chapter",
        params={"source": STUB_SOURCE, "series": SERIES, "chapter": "nope"},
    )
    assert response.status_code == 404
    assert response.json()["code"] == "chapter_not_found"


def test_flag_on_manga_source_is_not_a_novel_source(novels_on):
    """A manga source on the novel endpoint 404s — kinds are not disclosed."""
    response = novels_on.get(
        "/novels/chapter",
        params={"source": "mangadex", "series": "x", "chapter": "y"},
    )
    assert response.status_code == 404
    assert response.json()["code"] == "source_not_found"


def test_flag_on_unknown_source_is_404(novels_on):
    response = novels_on.get(
        "/novels/chapter",
        params={"source": "no-such-source", "series": "x", "chapter": "y"},
    )
    assert response.status_code == 404


def test_flag_on_missing_params_are_422(novels_on):
    assert novels_on.get("/novels/chapter").status_code == 422
