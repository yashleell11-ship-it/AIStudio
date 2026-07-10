"""Tests for the mature (18+) content gate (Objective 1).

The gate is enforced in three layers, all driven by a single persisted
preference (``Settings.mature_content_enabled``, default off):

- the connector registry knows which sources are adult (``ConnectorDescriptor.mature``);
- ``BrowseService`` hides adult sources from the catalogue and blocks direct
  access to them; and
- ``LibraryIntelligenceService`` drops adult-rated series from discovery
  surfaces (recommendations, recently-added/updated).

One flag, one connector architecture, no duplicated gating logic.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from connectors.registry import _descriptor_for, list_installed_connectors
from connectors.toonily.connector import ToonilyConnector
from core.config import get_settings, update_persisted_settings
from core.content_rating import MATURE_CONTENT_RATINGS, is_mature_rating
from core.errors import AppError
from database.models import Library, Series
from services.browse_service import BrowseService
from services.library_intelligence_service import LibraryIntelligenceService


@pytest.fixture
def set_mature(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Isolate config/settings.json to a throwaway file (so toggling the gate
    never touches the real settings) and hand back a setter. The whole app
    reads the same cached ``get_settings()``, so flipping it here is observed
    by every layer under test."""
    monkeypatch.setattr("core.config.SETTINGS_PATH", tmp_path / "settings.json")
    get_settings.cache_clear()

    def _set(enabled: bool) -> None:
        update_persisted_settings(mature_content_enabled=enabled)

    yield _set
    get_settings.cache_clear()


# ── content-rating helper ─────────────────────────────────────────────────────


@pytest.mark.parametrize("rating", sorted(MATURE_CONTENT_RATINGS))
def test_known_adult_ratings_are_mature(rating):
    assert is_mature_rating(rating) is True
    assert is_mature_rating(rating.upper()) is True  # case-insensitive


@pytest.mark.parametrize("rating", ["safe", "suggestive", "unknown", "", None])
def test_non_adult_ratings_are_not_mature(rating):
    assert is_mature_rating(rating) is False


# ── registry ──────────────────────────────────────────────────────────────────


def test_toonily_is_flagged_mature_in_the_registry():
    assert _descriptor_for(ToonilyConnector).mature is True


def test_list_installed_can_exclude_mature_sources():
    all_types = {d.source_type for d in list_installed_connectors()}
    without_mature = {
        d.source_type for d in list_installed_connectors(include_mature=False)
    }
    assert "toonily" in all_types
    assert "toonily" not in without_mature
    # Non-mature sources are unaffected by the exclusion.
    assert {"mangadex", "asurascans"} <= without_mature


# ── BrowseService: catalogue + direct-access chokepoints ──────────────────────


def test_sources_list_hides_mature_when_disabled(set_mature):
    set_mature(False)
    ids = {s["id"] for s in BrowseService().list_sources()}
    assert "toonily" not in ids
    assert "mangadex" in ids  # non-mature sources still listed


def test_sources_list_shows_mature_once_enabled(set_mature):
    set_mature(True)
    ids = {s["id"] for s in BrowseService().list_sources()}
    assert "toonily" in ids


def test_direct_access_to_a_mature_source_is_hidden_as_404(set_mature):
    """A mature source is reported not-found (not 'forbidden') so the gate
    doesn't disclose that the source exists at all."""
    set_mature(False)
    with pytest.raises(AppError) as excinfo:
        BrowseService()._get_connector("toonily")
    assert excinfo.value.status_code == 404
    assert excinfo.value.code == "source_not_found"


def test_direct_access_to_a_mature_source_works_when_enabled(set_mature):
    set_mature(True)
    connector = BrowseService()._get_connector("toonily")
    assert connector.source_type == "toonily"


def test_enabling_the_gate_is_a_full_round_trip(set_mature):
    """Persist → next read reveals the source, end to end through the real
    settings mechanism (no per-module monkeypatching)."""
    set_mature(False)
    assert "toonily" not in {s["id"] for s in BrowseService().list_sources()}
    set_mature(True)
    assert "toonily" in {s["id"] for s in BrowseService().list_sources()}
    assert get_settings().mature_content_enabled is True


# ── LibraryIntelligenceService: per-series discovery filter ───────────────────


def _seed_two_series(db) -> None:
    library = Library(name="Test", root_path="/tmp/mm")
    db.add(library)
    db.flush()
    db.add_all(
        [
            Series(
                library_id=library.id,
                title="Wholesome Adventure",
                folder_path="/tmp/mm/wholesome",
                sort_title="wholesome adventure",
                content_rating="safe",
            ),
            Series(
                library_id=library.id,
                title="Adults Only",
                folder_path="/tmp/mm/adults",
                sort_title="adults only",
                content_rating="pornographic",
            ),
        ]
    )
    db.commit()


def test_recently_added_hides_adult_series_when_disabled(db_session, set_mature):
    _seed_two_series(db_session)
    set_mature(False)
    titles = {r["title"] for r in LibraryIntelligenceService(db_session).get_recently_added(limit=10)}
    assert "Wholesome Adventure" in titles
    assert "Adults Only" not in titles


def test_recently_added_shows_adult_series_when_enabled(db_session, set_mature):
    _seed_two_series(db_session)
    set_mature(True)
    titles = {r["title"] for r in LibraryIntelligenceService(db_session).get_recently_added(limit=10)}
    assert "Adults Only" in titles


def test_recommendations_never_surface_adult_series_when_disabled(db_session, set_mature):
    """With no reading profile, recommendations fall back to recently-added;
    the adult series must not leak through that fallback."""
    _seed_two_series(db_session)
    set_mature(False)
    titles = {r["title"] for r in LibraryIntelligenceService(db_session).get_recommendations(limit=10)}
    assert "Adults Only" not in titles
