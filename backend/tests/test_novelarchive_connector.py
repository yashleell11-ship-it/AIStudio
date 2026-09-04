"""Offline tests for the Novel Archive (novelarchive.cc) connector.

Fixtures under ``tests/fixtures/novelarchive/`` are live API responses
captured 2026-09-04 FROM THE VPS (production's exact egress/TLS — the probe
methodology in the novels spec §4). The connector is exercised entirely
against those captures by patching ``self._http.get_json``; no network.

The recent-listing fixture deliberately contains the archive's dirty rows —
scraped block-pages ingested as zero-chapter "novels" ("Situs Terlarang…") —
because dropping them is part of this connector's contract.
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from connectors.http.client import ConnectorHttpError
from connectors.novelarchive.connector import NovelArchiveConnector
from connectors.novelarchive.mappers import (
    paragraphs_from_content,
    parse_chapter,
    parse_detail,
    parse_listing,
)

FIXTURES = Path(__file__).parent / "fixtures" / "novelarchive"

NOVEL_ID = "69faa859a5f4c7d1b734d496"  # Shadow Slave, 3173 chapters


def _load(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


# --- listing / search -------------------------------------------------------


def test_parse_popular_listing():
    listing = parse_listing(_load("novels_popular.json"), page=1)
    assert len(listing.items) == 20
    assert listing.has_more is True
    first = listing.items[0]
    assert first.id == NOVEL_ID
    assert first.title == "Shadow Slave"
    assert first.author == "Guiltythree"
    assert first.chapter_count == 3173
    assert first.cover_url == (
        f"https://novelarchive.cc/api/novels/{NOVEL_ID}/cover?w=640&q=72&format=webp"
    )
    assert "Action" in first.genres


def test_listing_drops_zero_chapter_scrape_junk():
    """The archive ingested blocked-site pages as 'novels' with 0 chapters
    (Indonesian block-page titles). They must never reach a client."""
    payload = _load("novels_recent.json")
    raw_titles = [n["title"] for n in payload["novels"]]
    assert any("Situs" in t for t in raw_titles)  # the junk IS in the capture

    listing = parse_listing(payload, page=1)
    assert listing.items  # real rows survive
    kept_titles = [item.title for item in listing.items]
    assert not any("Situs" in t for t in kept_titles)
    assert all(item.chapter_count > 0 for item in listing.items)


def test_parse_search_results_find_target():
    listing = parse_listing(_load("novels_search.json"), page=1)
    assert listing.items
    assert listing.items[0].title == "Shadow Slave"
    assert listing.total == 46


# --- detail + chapters (one response carries both) --------------------------


def test_parse_detail_metadata_and_full_chapter_list():
    series, chapters = parse_detail(_load("novel_detail.json"), NOVEL_ID)
    assert series is not None
    assert series.title == "Shadow Slave"
    assert series.author == "Guiltythree"
    assert series.status == "ongoing"
    assert series.description and "Nightmare Spell" in series.description
    assert series.chapter_count == 3173
    assert len(chapters) == 3173
    # Chapter identity: 1-based ordinals as opaque string keys, float numbers.
    assert chapters[0].id == "1"
    assert chapters[0].number == 1.0
    assert chapters[-1].id == "3173"
    assert all(c.series_id == NOVEL_ID for c in chapters[:5])
    assert chapters[0].title == "Chapter 1"


# --- chapter text -----------------------------------------------------------


def test_parse_chapter_paragraphs_are_clean_plain_text():
    text = parse_chapter(_load("chapter_1.json"))
    assert text is not None
    assert text.title == "Chapter 1"
    assert text.chapter_number == 1.0
    assert len(text.paragraphs) > 50
    assert text.word_count > 1000
    joined = "\n".join(text.paragraphs)
    assert "Sunny" in joined                    # the story survived
    assert "<" not in joined                    # no markup
    assert "\n\n" not in joined                 # paragraphs are single blocks
    assert all(p == p.strip() and p for p in text.paragraphs)


def test_paragraphs_from_content_strips_promo_lines():
    content = (
        "Real story text here.\n\n"
        "This chapter is updated by freewebnovel.com\n\n"
        "And the story continues."
    )
    assert paragraphs_from_content(content) == [
        "Real story text here.",
        "And the story continues.",
    ]


def test_paragraphs_from_content_sanitizes_stray_html():
    content = (
        "<p>Real story text.</p><script>evil()</script>"
        '<div class="adsbygoogle">ad</div><p>More text.</p>'
    )
    assert paragraphs_from_content(content) == ["Real story text.", "More text."]


# --- connector plumbing -----------------------------------------------------


@pytest.fixture
def connector() -> NovelArchiveConnector:
    return NovelArchiveConnector()


def test_connector_declares_the_novel_contract(connector):
    assert connector.CONTENT_KIND == "novel"
    assert connector.content_kind == "novel"
    assert connector.LANGUAGE == "en"
    assert connector.MATURE is False
    assert connector.get_chapter_pages("anything") == []
    assert connector.find_page("anything") is None
    assert "novelarchive.cc" in connector.allowed_image_hosts


def test_connector_browse_and_search_params(connector):
    calls: list[tuple[str, dict]] = []

    def fake_get_json(path, *, params=None):
        calls.append((path, dict(params or {})))
        return _load("novels_popular.json")

    with patch.object(connector._http, "get_json", side_effect=fake_get_json):
        connector.get_series_list(2, sort="recent")
        connector.search_series("shadow slave", 1)

    assert calls[0] == (
        "/api/novels",
        {"page": 2, "per_page": 20, "sort": "recent"},
    )
    assert calls[1] == (
        "/api/novels",
        {"page": 1, "per_page": 20, "search": "shadow slave"},
    )


def test_connector_series_and_chapters_share_one_fetch(connector):
    calls: list[str] = []

    def fake_get_json(path, *, params=None):
        calls.append(path)
        return _load("novel_detail.json")

    with patch.object(connector._http, "get_json", side_effect=fake_get_json):
        series = connector.get_series(NOVEL_ID)
        chapters = connector.get_chapters(NOVEL_ID)

    assert series is not None and series.title == "Shadow Slave"
    assert len(chapters) == 3173
    assert calls == [f"/api/novels/{NOVEL_ID}"]


def test_connector_chapter_text_end_to_end(connector):
    def fake_get_json(path, *, params=None):
        assert path == f"/api/novels/{NOVEL_ID}/chapters/1"
        return _load("chapter_1.json")

    with patch.object(connector._http, "get_json", side_effect=fake_get_json):
        text = connector.chapter_text(NOVEL_ID, "1")

    assert text is not None
    assert text.chapter_number == 1.0
    assert text.paragraphs


def test_connector_missing_chapter_returns_none(connector):
    """The API 404s out-of-range chapters and 400s malformed ids; both mean
    'does not exist', which the contract spells `None` (the novel service
    then serves stale or 404s)."""

    def fake_get_json(path, *, params=None):
        raise ConnectorHttpError(
            "Client error '404 NOT FOUND' for url", status_code=404
        )

    with patch.object(connector._http, "get_json", side_effect=fake_get_json):
        assert connector.chapter_text(NOVEL_ID, "999999") is None


def test_connector_network_failure_raises(connector):
    def fake_get_json(path, *, params=None):
        raise ConnectorHttpError("Retryable HTTP 503", status_code=503)

    with patch.object(connector._http, "get_json", side_effect=fake_get_json):
        with pytest.raises(ConnectorHttpError):
            connector.chapter_text(NOVEL_ID, "1")


def test_connector_rejects_non_english_chapter(connector):
    payload = {
        "chapter": {
            "content": "重生之最强剑神是一部网络小说。\n\n" * 30,
            "name": "第一章",
            "number": 1,
        },
        "navigation": {"prev": None, "next": 2},
    }

    def fake_get_json(path, *, params=None):
        return payload

    with patch.object(connector._http, "get_json", side_effect=fake_get_json):
        assert connector.chapter_text(NOVEL_ID, "1") is None


def test_registered_and_gated_by_the_novels_flag(monkeypatch):
    import connectors.registry as registry
    from core.config import get_settings

    # Flag off (default): absent from every surface.
    monkeypatch.delenv("MM_NOVELS_ENABLED", raising=False)
    get_settings.cache_clear()
    assert "novelarchive" in registry._REGISTRY
    assert "novelarchive" not in registry.list_connector_types()
    with pytest.raises(ValueError):
        registry.create_connector("novelarchive")

    # Flag on: listed with the novel descriptor fields.
    monkeypatch.setenv("MM_NOVELS_ENABLED", "true")
    get_settings.cache_clear()
    descriptors = {
        d.source_type: d for d in registry.list_installed_connectors()
    }
    assert "novelarchive" in descriptors
    assert descriptors["novelarchive"].content_kind == "novel"
    assert descriptors["novelarchive"].language == "en"
    assert isinstance(
        registry.create_connector("novelarchive"), NovelArchiveConnector
    )
    get_settings.cache_clear()
