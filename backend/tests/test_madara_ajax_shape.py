"""A Madara site is asked about its AJAX chapter endpoint once, not per series.

Madara ships two chapter-list endpoints and the connector tries both:
``/wp-admin/admin-ajax.php?action=manga_get_chapters`` (older builds) and
``{series}/ajax/chapters/`` (newer ones). Probed from the VPS, five registered
sites answer the first with 400/403 — cocomic, cucumbermanga, lilymanga,
manhwatop, manhuanext — so every series open spent a round trip on an endpoint
that will never work.

Which endpoint a WordPress install serves is a property of the SITE, so the
answer is remembered site-wide. These tests pin the two ways that could go
wrong: the remembered answer must be used (the speedup), and it must never
turn a working series into an empty one (the invariant).
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from connectors.http.client import ConnectorHttpError
from connectors.madara.sites import MADARA_SITES
from connectors.registry import create_connector

SERIES_A = "series-a"
SERIES_B = "series-b"

_DETAIL_NO_INLINE_CHAPTERS = """
<html><head><title>Some Series</title></head><body>
  <div class="post-title"><h1>Some Series</h1></div>
  <div class="summary_image"><img src="https://cdn.example/cover.jpg"></div>
  <div id="manga-chapters-holder" data-id="4242"></div>
  <div class="listing-chapters_wrap"></div>
</body></html>
"""


def _ajax_chapters(series_id: str) -> str:
    return f"""
    <ul>
      <li class="wp-manga-chapter">
        <a href="/manga/{series_id}/chapter-1/">Chapter 1</a>
      </li>
      <li class="wp-manga-chapter">
        <a href="/manga/{series_id}/chapter-2/">Chapter 2</a>
      </li>
    </ul>
    """


@pytest.fixture
def connector():
    """A Madara connector with cold caches (create_connector is a singleton)."""
    site = MADARA_SITES[0]
    instance = create_connector(site.source_id)
    caches = (
        instance._series_cache,
        instance._chapter_list_cache,
        instance._page_cache,
        instance._chapter_page_count_cache,
        instance._ajax_shape,
    )
    for cache in caches:
        cache.clear()
    yield instance
    for cache in caches:
        cache.clear()


def _series_of(path: str, current: dict) -> str:
    """The series a relative-AJAX path belongs to (``/manga/<id>/ajax/chapters/``)."""
    parts = [p for p in path.split("/") if p]
    return parts[1] if len(parts) > 1 else current["id"]


def _post_router(*, admin_status: int | None, relative_ok: bool = True):
    """A ``post_text`` double that answers the two AJAX shapes separately.

    Both shapes answer with rows for the series being asked about — the parser
    drops chapter hrefs that do not belong to the requested series, so a
    fixture that always names one series would look like an empty list and
    send the connector down the fallback path for the wrong reason.
    """
    seen: list[str] = []
    current = {"id": SERIES_A}

    def post_text(path, *, data=None, extra_headers=None):
        seen.append(path)
        if path == "/wp-admin/admin-ajax.php":
            if admin_status is not None:
                raise ConnectorHttpError(
                    f"Client error '{admin_status}' for url", status_code=admin_status
                )
            return _ajax_chapters(current["id"])
        if relative_ok:
            return _ajax_chapters(_series_of(path, current))
        raise ConnectorHttpError("Client error '404 Not Found'", status_code=404)

    return post_text, seen, current


def test_a_dead_admin_ajax_is_probed_once_per_site(connector) -> None:
    post_text, seen, current = _post_router(admin_status=400)
    get_text = MagicMock(return_value=_DETAIL_NO_INLINE_CHAPTERS)

    with patch.object(connector._http, "get_text", get_text), patch.object(
        connector._http, "post_text", post_text
    ):
        first = connector.get_series(SERIES_A)
        connector._series_cache.clear()
        connector._chapter_list_cache.clear()
        current["id"] = SERIES_B
        second = connector.get_series(SERIES_B)

    assert first is not None and second is not None
    assert first.chapter_count == 2 and second.chapter_count == 2
    # The dead endpoint is asked once, for the first series only.
    assert seen.count("/wp-admin/admin-ajax.php") == 1
    assert sum(1 for p in seen if p.endswith("ajax/chapters/")) == 2


def test_a_working_admin_ajax_keeps_being_used_first(connector) -> None:
    post_text, seen, current = _post_router(admin_status=None)
    get_text = MagicMock(return_value=_DETAIL_NO_INLINE_CHAPTERS)

    with patch.object(connector._http, "get_text", get_text), patch.object(
        connector._http, "post_text", post_text
    ):
        connector.get_series(SERIES_A)
        connector._series_cache.clear()
        connector._chapter_list_cache.clear()
        current["id"] = SERIES_B
        connector.get_series(SERIES_B)

    assert seen == ["/wp-admin/admin-ajax.php"] * 2
    assert not any(p.endswith("ajax/chapters/") for p in seen)


def test_a_transient_failure_is_not_remembered_as_a_dead_endpoint(
    connector,
) -> None:
    """A 503 says nothing about the site; caching it would hide the endpoint.

    Both routes fail on the first series, so nothing is learned either way —
    the next series must probe admin-ajax again rather than treating one bad
    minute as "this install does not have that endpoint" for the next hour.
    """
    calls: list[str] = []
    current = {"id": SERIES_A}
    state = {"blip": True}

    def post_text(path, *, data=None, extra_headers=None):
        calls.append(path)
        if state["blip"]:
            raise ConnectorHttpError("Retryable HTTP 503", status_code=503)
        if path == "/wp-admin/admin-ajax.php":
            return _ajax_chapters(current["id"])
        return _ajax_chapters(_series_of(path, current))

    get_text = MagicMock(return_value=_DETAIL_NO_INLINE_CHAPTERS)
    with patch.object(connector._http, "get_text", get_text), patch.object(
        connector._http, "post_text", post_text
    ):
        connector.get_series(SERIES_A)
        state["blip"] = False
        connector._series_cache.clear()
        connector._chapter_list_cache.clear()
        current["id"] = SERIES_B
        second = connector.get_series(SERIES_B)

    assert second is not None and second.chapter_count == 2
    # Asked again after the blip, rather than written off for an hour.
    assert calls.count("/wp-admin/admin-ajax.php") == 2


def test_a_remembered_shape_that_stops_working_falls_back(connector) -> None:
    """The invariant: the memory may cost a request, never a chapter list."""
    state = {"relative_ok": True}
    calls: list[str] = []
    current = {"id": SERIES_A}

    def post_text(path, *, data=None, extra_headers=None):
        calls.append(path)
        if path == "/wp-admin/admin-ajax.php":
            if state["relative_ok"]:
                raise ConnectorHttpError("Client error '400'", status_code=400)
            return _ajax_chapters(current["id"])
        if state["relative_ok"]:
            return _ajax_chapters(_series_of(path, current))
        raise ConnectorHttpError("Client error '404 Not Found'", status_code=404)

    get_text = MagicMock(return_value=_DETAIL_NO_INLINE_CHAPTERS)
    with patch.object(connector._http, "get_text", get_text), patch.object(
        connector._http, "post_text", post_text
    ):
        connector.get_series(SERIES_A)  # learns "relative"
        state["relative_ok"] = False     # the site swaps endpoints
        connector._series_cache.clear()
        connector._chapter_list_cache.clear()
        current["id"] = SERIES_B
        recovered = connector.get_series(SERIES_B)

    assert recovered is not None
    assert recovered.chapter_count == 2, "a stale shape must not lose chapters"


def test_an_empty_admin_ajax_body_counts_as_a_dead_endpoint(connector) -> None:
    """Madara answers 200 "0" for "I do not serve this" — same conclusion."""
    calls: list[str] = []
    current = {"id": SERIES_A}

    def post_text(path, *, data=None, extra_headers=None):
        calls.append(path)
        if path == "/wp-admin/admin-ajax.php":
            return "0"
        return _ajax_chapters(_series_of(path, current))

    get_text = MagicMock(return_value=_DETAIL_NO_INLINE_CHAPTERS)
    with patch.object(connector._http, "get_text", get_text), patch.object(
        connector._http, "post_text", post_text
    ):
        connector.get_series(SERIES_A)
        connector._series_cache.clear()
        connector._chapter_list_cache.clear()
        current["id"] = SERIES_B
        connector.get_series(SERIES_B)

    assert calls.count("/wp-admin/admin-ajax.php") == 1
