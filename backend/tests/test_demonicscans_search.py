"""DemonicScans search goes through the site's own search endpoint.

Before this, ``search_series`` fetched one fixed ``/advanced.php`` catalog
page and substring-filtered it in Python, so any title not on that page was
unfindable while the call still reported success. These tests pin both halves
of the fix: the search-card markup parses, and the connector actually asks
``/search.php?manga=<q>``.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

from connectors.demonicscans.connector import DemonicScansConnector
from connectors.demonicscans.mappers import (
    SEARCH_PATH,
    parse_search_results,
    search_params,
)

FIXTURES = Path(__file__).parent / "fixtures" / "demonicscans"


def _search_html() -> str:
    return (FIXTURES / "search_dungeon.html").read_text(encoding="utf-8")


def test_parse_search_results_reads_every_hit() -> None:
    listing = parse_search_results(_search_html(), page=1, query="dungeon")

    assert len(listing.items) == 20
    by_id = {item.id: item for item in listing.items}
    assert "Dungeon-Reset" in by_id
    assert by_id["Dungeon-Reset"].title == "Dungeon Reset"
    assert by_id["Dungeon-Reset"].canonical_path == "/manga/Dungeon-Reset"


def test_parse_search_results_decodes_ids_and_encodes_cover_spaces() -> None:
    listing = parse_search_results(_search_html(), page=1, query="dungeon")
    by_id = {item.id: item for item in listing.items}

    # Site hrefs are double-encoded; ids must come back decoded so the detail
    # route can round-trip them.
    blade = by_id["The-Blade-of-Evolution-Walking-Alone-in-the-Dungeon"]
    assert "%25" not in blade.id

    # Thumbnail filenames contain literal spaces. An unencoded URL is one the
    # image proxy cannot fetch, so the cover would silently break.
    assert blade.cover_url is not None
    assert " " not in blade.cover_url
    assert "%20" in blade.cover_url


def test_search_results_are_not_falsely_paginated() -> None:
    """The endpoint returns one block of best matches and no page 2."""
    first = parse_search_results(_search_html(), page=1, query="dungeon")
    assert first.api_has_more is False

    second = parse_search_results(_search_html(), page=2, query="dungeon")
    assert second.items == []


def test_search_series_queries_the_search_endpoint() -> None:
    connector = DemonicScansConnector()
    connector._http = MagicMock()
    connector._http.get_text.return_value = _search_html()

    listing = connector.search_series("dungeon", 1)

    connector._http.get_text.assert_called_once_with(
        SEARCH_PATH, params=search_params("dungeon")
    )
    assert len(listing.items) == 20


def test_empty_query_still_browses_the_catalog() -> None:
    """An empty query is a browse; it must not hit the search endpoint."""
    connector = DemonicScansConnector()
    connector._http = MagicMock()
    connector._http.get_text.return_value = (
        FIXTURES / "browse_latest.html"
    ).read_text(encoding="utf-8")

    connector.search_series("   ", 1)

    called_path = connector._http.get_text.call_args.args[0]
    assert called_path != SEARCH_PATH
