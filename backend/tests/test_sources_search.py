from __future__ import annotations

from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import sessionmaker

from connectors.models import PaginatedSeriesList, Series as ConnectorSeries
from database.models import Library, Series
from database.session import get_db
from main import create_app


# ---------------------------------------------------------------------------
# Test doubles: fake registry descriptors + connectors (never hit the network)
# ---------------------------------------------------------------------------


class _FakeDescriptor:
    def __init__(self, source_type: str, *, mature: bool = False) -> None:
        self.source_type = source_type
        self.name = source_type
        self.mature = mature
        self.browsable = True


class _FakeConnector:
    """Minimal connector stub exposing only ``search_series``."""

    def __init__(
        self,
        items: list[ConnectorSeries],
        *,
        has_more: bool = False,
        raises: Exception | None = None,
    ) -> None:
        self._items = items
        self._has_more = has_more
        self._raises = raises

    def search_series(self, query: str, page: int, *, sort=None):
        if self._raises is not None:
            raise self._raises
        return PaginatedSeriesList(items=self._items, api_has_more=self._has_more)


def _make_list_installed(descriptors: list[_FakeDescriptor]):
    """Mirror the real registry filter: browsable_only + include_mature."""

    def _fake(*, browsable_only: bool = False, include_mature: bool = True):
        out = list(descriptors)
        if browsable_only:
            out = [d for d in out if d.browsable]
        if not include_mature:
            out = [d for d in out if not d.mature]
        return out

    return _fake


def _series(sid: str, title: str, author: str | None = None) -> ConnectorSeries:
    return ConnectorSeries(id=sid, title=title, author=author)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def session_factory(db_engine):
    return sessionmaker(bind=db_engine, autoflush=False, autocommit=False)


@pytest.fixture
def client(db_engine, session_factory):
    def override_get_db():
        db = session_factory()
        try:
            yield db
        finally:
            db.close()

    app = create_app(run_migrations=False, run_workers=False)
    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as test_client:
        yield test_client


def _seed_local_series(session_factory, title: str) -> int:
    db = session_factory()
    try:
        library = Library(name="Main", root_path="/tmp/library")
        db.add(library)
        db.flush()
        series = Series(
            library_id=library.id,
            title=title,
            folder_path=f"/tmp/library/{title}",
        )
        db.add(series)
        db.commit()
        return series.id
    finally:
        db.close()


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_search_merges_local_and_source_items(client, session_factory):
    local_id = _seed_local_series(session_factory, "One Piece")

    descriptors = [_FakeDescriptor("mangadex")]
    connector = _FakeConnector(
        [_series("md-1", "One Piece Colored", author="Oda")],
        has_more=True,
    )

    with patch(
        "services.browse_service.list_installed_connectors",
        _make_list_installed(descriptors),
    ), patch(
        "services.browse_service.create_connector", return_value=connector
    ):
        response = client.get("/sources/search", params={"q": "one piece"})

    assert response.status_code == 200
    payload = response.json()
    assert payload["sources_queried"] == 1
    assert payload["sources_failed"] == 0
    assert payload["page"] == 1
    assert payload["has_more"] is True

    items = payload["items"]
    # Local first, then source.
    assert items[0]["kind"] == "local"
    assert items[0]["source"] is None
    assert items[0]["series_id"] == str(local_id)
    assert items[0]["series_id"].isdigit()
    assert items[0]["cover_url"].startswith("http")
    assert items[0]["cover_url"].endswith(f"/library/covers/{local_id}")

    source_item = next(i for i in items if i["kind"] == "source")
    assert source_item["source"] == "mangadex"
    assert source_item["series_id"] == "md-1"
    assert source_item["author"] == "Oda"
    assert source_item["cover_url"].startswith("http")
    assert "/sources/mangadex/series/md-1/cover" in source_item["cover_url"]


def test_failing_connector_counts_as_failed(client, session_factory):
    descriptors = [_FakeDescriptor("good"), _FakeDescriptor("bad")]

    good = _FakeConnector([_series("g-1", "Good Hit")])
    bad = _FakeConnector([], raises=RuntimeError("cloudflare wall"))

    def _create(source_id: str):
        return good if source_id == "good" else bad

    with patch(
        "services.browse_service.list_installed_connectors",
        _make_list_installed(descriptors),
    ), patch("services.browse_service.create_connector", side_effect=_create):
        response = client.get("/sources/search", params={"q": "anything"})

    assert response.status_code == 200
    payload = response.json()
    assert payload["sources_queried"] == 2
    assert payload["sources_failed"] == 1
    titles = {i["title"] for i in payload["items"]}
    assert "Good Hit" in titles


def test_mature_sources_excluded_when_off(client, session_factory):
    from services.library_intelligence_service import LibraryIntelligenceService

    descriptors = [
        _FakeDescriptor("safe"),
        _FakeDescriptor("adult", mature=True),
    ]

    def _create(source_id: str):
        return _FakeConnector([_series(f"{source_id}-1", f"{source_id} title")])

    with patch.object(
        LibraryIntelligenceService, "_mature_enabled", return_value=False
    ), patch(
        "services.browse_service.list_installed_connectors",
        _make_list_installed(descriptors),
    ), patch("services.browse_service.create_connector", side_effect=_create):
        response = client.get("/sources/search", params={"q": "hit"})

    payload = response.json()
    # Only the non-mature source is queried when mature content is off.
    assert payload["sources_queried"] == 1
    sources = {i["source"] for i in payload["items"] if i["kind"] == "source"}
    assert sources == {"safe"}


def test_mature_sources_included_when_on(client, session_factory):
    from services.library_intelligence_service import LibraryIntelligenceService

    descriptors = [
        _FakeDescriptor("safe"),
        _FakeDescriptor("adult", mature=True),
    ]

    def _create(source_id: str):
        return _FakeConnector([_series(f"{source_id}-1", f"{source_id} title")])

    with patch.object(
        LibraryIntelligenceService, "_mature_enabled", return_value=True
    ), patch(
        "services.browse_service.list_installed_connectors",
        _make_list_installed(descriptors),
    ), patch("services.browse_service.create_connector", side_effect=_create):
        response = client.get("/sources/search", params={"q": "hit"})

    payload = response.json()
    assert payload["sources_queried"] == 2
    sources = {i["source"] for i in payload["items"] if i["kind"] == "source"}
    assert sources == {"safe", "adult"}


def test_empty_query_returns_empty_items_but_queries_sources(client, session_factory):
    descriptors = [_FakeDescriptor("mangadex"), _FakeDescriptor("asura")]

    # create_connector should never be called on empty query, but stub it anyway.
    with patch(
        "services.browse_service.list_installed_connectors",
        _make_list_installed(descriptors),
    ), patch(
        "services.browse_service.create_connector",
        side_effect=AssertionError("should not query connectors on empty query"),
    ):
        response = client.get("/sources/search", params={"q": "   "})

    assert response.status_code == 200
    payload = response.json()
    assert payload["items"] == []
    assert payload["sources_queried"] == 2
    assert payload["sources_failed"] == 0
    assert payload["has_more"] is False


def test_no_matches_returns_empty_items(client, session_factory):
    descriptors = [_FakeDescriptor("mangadex")]
    connector = _FakeConnector([])  # source finds nothing

    with patch(
        "services.browse_service.list_installed_connectors",
        _make_list_installed(descriptors),
    ), patch("services.browse_service.create_connector", return_value=connector):
        response = client.get("/sources/search", params={"q": "zzz-no-such-title"})

    assert response.status_code == 200
    payload = response.json()
    assert payload["items"] == []
    assert payload["sources_queried"] == 1


def test_duplicate_titles_dedupe_local_wins(client, session_factory):
    _seed_local_series(session_factory, "One Piece")
    descriptors = [_FakeDescriptor("mangadex")]
    # Source returns a title that normalizes to the same as the local hit.
    connector = _FakeConnector([_series("md-1", "one piece")])

    with patch(
        "services.browse_service.list_installed_connectors",
        _make_list_installed(descriptors),
    ), patch("services.browse_service.create_connector", return_value=connector):
        response = client.get("/sources/search", params={"q": "one piece"})

    payload = response.json()
    kinds = [i["kind"] for i in payload["items"]]
    # Only the local copy survives the de-dupe.
    assert kinds == ["local"]
