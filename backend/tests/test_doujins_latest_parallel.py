"""Doujins' "latest" listing is assembled day by day — but not one at a time.

The listing has no paged endpoint: it is built from one ``/folders`` call per
UTC day, walked until eight days are in hand and the catalog is big enough.
Probed from the VPS that was eight serial requests and 2.80s of browse.

The eight are unconditional (the loop's exit test cannot fire before day 8) and
independent, so they now go out together. What must not change is the LISTING:
same series, same order, same first-seen de-duplication — day order decides
which duplicate wins and therefore what page 1 shows.
"""

from __future__ import annotations

import threading

import pytest

from connectors.doujins.mappers import HOME_PAGE_SIZE
from connectors.http.client import ConnectorHttpError
from connectors.registry import create_connector


def _folders(*ids: str) -> dict:
    """A /folders payload in the shape ``series_from_folder_item`` reads."""
    return {
        "folders": [
            {
                "link": f"/gallery/{i}",
                "name": f"Gallery {i}",
                "thumbnail": f"https://cdn.doujins.test/{i}.jpg",
                "objects_count": 12,
            }
            for i in ids
        ]
    }


@pytest.fixture
def connector():
    instance = create_connector("doujins")
    instance._latest_cache.clear()
    instance._top_cache.clear()
    yield instance
    instance._latest_cache.clear()
    instance._top_cache.clear()




def test_the_listing_is_the_same_as_the_serial_walk_produced(connector) -> None:
    """Order and de-duplication both come from day order; both are pinned."""
    # day 0 -> a,b ; day 1 -> b,c (b repeats) ; day 2 -> d ; rest empty
    by_start: dict[int, dict] = {}
    starts: list[int] = []

    def fetch_json(path, *, params=None):
        assert path == "/folders"
        starts.append(params["start"])
        return by_start.get(params["start"], {"folders": []})

    # Learn the eight day windows the connector uses, then answer by window.
    windows = [connector._utc_day_bounds(i)[0] for i in range(8)]
    by_start[windows[0]] = _folders("a", "b")
    by_start[windows[1]] = _folders("b", "c")
    by_start[windows[2]] = _folders("d")

    connector._fetch_json = fetch_json  # type: ignore[method-assign]
    try:
        listing = connector.get_series_list(1)
    finally:
        del connector._fetch_json

    assert [item.id for item in listing.items] == [
        "gallery/a",
        "gallery/b",
        "gallery/c",
        "gallery/d",
    ]


def test_the_eight_unconditional_days_go_out_together(connector) -> None:
    """The point of the change: eight requests, not eight round trips."""
    inflight = {"now": 0, "peak": 0}
    lock = threading.Lock()
    barrier = threading.Barrier(8, timeout=5)

    def fetch_json(path, *, params=None):
        with lock:
            inflight["now"] += 1
            inflight["peak"] = max(inflight["peak"], inflight["now"])
        try:
            barrier.wait()
        except threading.BrokenBarrierError:  # pragma: no cover - timing guard
            pass
        with lock:
            inflight["now"] -= 1
        return {"folders": []}

    connector._fetch_json = fetch_json  # type: ignore[method-assign]
    try:
        connector.get_series_list(1)
    finally:
        del connector._fetch_json

    assert inflight["peak"] == 8


def test_one_failing_day_does_not_empty_the_listing(connector) -> None:
    """A failed day was skipped by the serial loop; it must still be skipped."""
    windows = [connector._utc_day_bounds(i)[0] for i in range(8)]
    good = {windows[0]: _folders("a"), windows[2]: _folders("c")}

    def fetch_json(path, *, params=None):
        if params["start"] == windows[1]:
            raise ConnectorHttpError("Retryable HTTP 503", status_code=503)
        return good.get(params["start"], {"folders": []})

    connector._fetch_json = fetch_json  # type: ignore[method-assign]
    try:
        listing = connector.get_series_list(1)
    finally:
        del connector._fetch_json

    assert [item.id for item in listing.items] == ["gallery/a", "gallery/c"]


def test_a_thin_catalog_keeps_walking_past_the_first_batch(connector) -> None:
    """The early exit needs BOTH day 8 and a full catalog; one is not enough."""
    seen: list[int] = []

    def fetch_json(path, *, params=None):
        seen.append(params["start"])
        return {"folders": []}

    connector._fetch_json = fetch_json  # type: ignore[method-assign]
    try:
        connector.get_series_list(1)
    finally:
        del connector._fetch_json

    assert len(seen) > 8, "an empty catalog must not stop at the parallel batch"


def test_a_full_catalog_stops_at_the_first_batch(connector) -> None:
    """Enough items after eight days: no ninth request."""
    windows = [connector._utc_day_bounds(i)[0] for i in range(8)]
    payload = _folders(*[f"g{i}" for i in range(HOME_PAGE_SIZE * 2)])
    seen: list[int] = []

    def fetch_json(path, *, params=None):
        seen.append(params["start"])
        return payload if params["start"] == windows[0] else {"folders": []}

    connector._fetch_json = fetch_json  # type: ignore[method-assign]
    try:
        listing = connector.get_series_list(1)
    finally:
        del connector._fetch_json

    assert len(seen) == 8
    assert len(listing.items) == HOME_PAGE_SIZE


def test_the_client_burst_matches_the_fan_out_width(connector) -> None:
    from connectors.doujins.connector import _DAY_WORKERS

    assert connector._http._burst == _DAY_WORKERS
