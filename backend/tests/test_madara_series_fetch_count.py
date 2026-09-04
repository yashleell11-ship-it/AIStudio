"""A Madara series detail must fetch its series page exactly once.

Most Madara builds lazy-load the chapter list: the series HTML ships with an
empty ``listing-chapters_wrap`` and the rows arrive over AJAX. ``get_series``
used to handle that by calling ``get_chapters``, which re-downloaded the very
series page ``get_series`` was already holding -- a second full-page fetch on
every detail open. Measured from the VPS the detail stage cost 2.7-3.2s on the
sites that take this branch (manhwatop, manhuanext, lilymanga, cocomic).
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from connectors.madara.sites import MADARA_SITES
from connectors.registry import create_connector

SERIES_ID = "some-series"

# Enough Madara detail markup to parse a title, plus the manga id the AJAX
# chapter endpoint keys off -- and NO inline chapter rows, which is what puts
# get_series on the lazy-load path.
_DETAIL_NO_INLINE_CHAPTERS = """
<html><head><title>Some Series</title></head><body>
  <div class="post-title"><h1>Some Series</h1></div>
  <div class="summary_image"><img src="https://cdn.example/cover.jpg"></div>
  <div id="manga-chapters-holder" data-id="4242"></div>
  <div class="listing-chapters_wrap"></div>
</body></html>
"""

_AJAX_CHAPTERS = f"""
<ul>
  <li class="wp-manga-chapter">
    <a href="/manga/{SERIES_ID}/chapter-1/">Chapter 1</a>
  </li>
  <li class="wp-manga-chapter">
    <a href="/manga/{SERIES_ID}/chapter-2/">Chapter 2</a>
  </li>
</ul>
"""


@pytest.fixture
def connector():
    """A Madara connector with cold caches.

    create_connector hands back a process-wide singleton, so without this the
    second test would read the first test's cached series and assert nothing.
    """
    site = MADARA_SITES[0]
    instance = create_connector(site.source_id)
    for cache in (
        instance._series_cache,
        instance._chapter_list_cache,
        instance._page_cache,
        instance._chapter_page_count_cache,
    ):
        cache.clear()
    yield instance
    for cache in (
        instance._series_cache,
        instance._chapter_list_cache,
        instance._page_cache,
        instance._chapter_page_count_cache,
    ):
        cache.clear()


def test_get_series_does_not_refetch_the_series_page(connector) -> None:
    get_text = MagicMock(return_value=_DETAIL_NO_INLINE_CHAPTERS)
    post_text = MagicMock(return_value=_AJAX_CHAPTERS)

    with patch.object(connector._http, "get_text", get_text), patch.object(
        connector._http, "post_text", post_text
    ):
        series = connector.get_series(SERIES_ID)

    assert series is not None
    # One GET for the series page. Not two.
    assert get_text.call_count == 1, get_text.call_args_list
    # The chapter rows still arrive -- over AJAX, from the HTML already held.
    assert post_text.call_count >= 1
    assert series.chapter_count == 2


def test_chapters_resolved_during_detail_are_reused(connector) -> None:
    """get_chapters straight after get_series must cost nothing."""
    get_text = MagicMock(return_value=_DETAIL_NO_INLINE_CHAPTERS)
    post_text = MagicMock(return_value=_AJAX_CHAPTERS)

    with patch.object(connector._http, "get_text", get_text), patch.object(
        connector._http, "post_text", post_text
    ):
        connector.get_series(SERIES_ID)
        calls_after_detail = get_text.call_count
        chapters = connector.get_chapters(SERIES_ID)

    assert len(chapters) == 2
    assert get_text.call_count == calls_after_detail
