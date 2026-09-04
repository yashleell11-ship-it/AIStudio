"""A Tapas listing costs one request, not one per result.

``search_series`` and the browse landing used to call ``_resolve_numeric_id``
for every item they were about to return — a slug -> numeric-id lookup that is
a separate HTTP request each. Probed from the VPS, a ten-hit search issued
ELEVEN round trips (1.68s), warming ids for nine series the reader was never
going to open; the id is needed only when a series is actually opened, where it
resolves lazily and caches.

The invariant a laziness change can break is the payload: the listing must
still carry the same items, in the same order, with the same ids. Both halves
are pinned here.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest

from connectors.registry import create_connector

_SEARCH_HTML = "".join(
    f'<a data-series-id="{sid}" href="/series/{slug}" '
    f'data-series-title="{title}"></a>'
    for sid, slug, title in (
        (101, "first-series", "First Series"),
        (102, "second-series", "Second Series"),
        (103, "third-series", "Third Series"),
    )
)

# ``url`` (a slug) rather than a bare seriesId is the shape that used to send
# the landing through _resolve_numeric_id, so it is the one worth pinning.
_LANDING_JSON = {
    "data": {
        "items": [
            {
                "seriesId": 201,
                "url": "slug-one",
                "title": "One",
                "assetProperty": {
                    "thumbnailImage": {"path": "https://story-a.tapas.io/1.jpg"}
                },
            },
            {
                "seriesId": 202,
                "url": "slug-two",
                "title": "Two",
                "assetProperty": {
                    "thumbnailImage": {"path": "https://story-a.tapas.io/2.jpg"}
                },
            },
        ]
    }
}


@pytest.fixture
def connector():
    instance = create_connector("tapas")
    instance._numeric_id_cache.clear()
    instance._series_cache.clear()
    yield instance
    instance._numeric_id_cache.clear()
    instance._series_cache.clear()


def test_search_issues_one_request_per_page_not_one_per_hit(connector) -> None:
    html_calls: list[str] = []
    json_calls: list[str] = []

    def get_text(path, *, params=None):
        html_calls.append(path)
        return _SEARCH_HTML

    def get_json(path, *, params=None):
        json_calls.append(path)
        return {"data": {"id": 1}}

    with patch.object(connector._site_html, "get_text", get_text), patch.object(
        connector._site, "get_json", get_json
    ):
        listing = connector.search_series("series", 1)

    assert html_calls == ["/search"]
    assert json_calls == [], "a search result must not be resolved eagerly"
    # The payload is unchanged: same hits, same order, same ids.
    assert [item.id for item in listing.items] == [
        "first-series",
        "second-series",
        "third-series",
    ]
    assert [item.title for item in listing.items] == [
        "First Series",
        "Second Series",
        "Third Series",
    ]


def test_browse_does_not_resolve_ids_for_the_whole_page(connector) -> None:
    json_calls: list[str] = []

    def story_json(path, *, params=None):
        json_calls.append(("story", path))
        return _LANDING_JSON

    def site_json(path, *, params=None):
        json_calls.append(("site", path))
        return {"data": {"id": 7}}

    with patch.object(connector._story_api, "get_json", story_json), patch.object(
        connector._site, "get_json", site_json
    ):
        listing = connector.get_series_list(1)

    assert [kind for kind, _ in json_calls] == ["story"]
    assert [item.id for item in listing.items] == ["slug-one", "slug-two"]


def test_opening_a_series_still_resolves_its_numeric_id(connector) -> None:
    """The lookup did not disappear — it moved to where it is needed."""
    calls: list[str] = []

    def site_json(path, *, params=None):
        calls.append(path)
        return {"data": {"id": 4242, "url": "one-series", "title": "One Series"}}

    with patch.object(connector._site, "get_json", site_json):
        numeric = connector._resolve_numeric_id("one-series")
        again = connector._resolve_numeric_id("one-series")

    assert numeric == 4242
    assert again == 4242
    assert len(calls) == 1, "and it is still cached after the first resolve"
