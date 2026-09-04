"""Opening a series must cost one fetch of its series page, not two.

Six connectors shared the same shape: ``get_series`` downloaded the series
page, then called ``get_chapters(series_id)``, which downloaded the *same*
page again to read the chapter rows that were already sitting in the first
response. Every series detail open therefore paid two full-page GETs.

The chapter rows now seed ``_chapter_list_cache`` from the document already in
hand, so the ``get_chapters`` call -- on the next line, and again from the
reader a moment later -- is served from cache.

This is a structural invariant, so it is asserted structurally: the HTML is
irrelevant, only the number of times the connector reaches for it matters.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from connectors.models import Chapter, Series
from connectors.registry import create_connector

# source_type -> a series id shaped the way that connector's normalizer expects
CASES = [
    ("comicasura", "some-series"),
    ("demonicscans", "Some-Series"),
    ("elftoon", "some-series"),
    ("galaxymanga", "some-series"),
    ("hentai20", "some-series"),
    ("mangakatana", "some-series.12345"),
]


def _fake_series(series_id: str) -> Series:
    return Series(id=series_id, title="Some Series", canonical_path=f"/{series_id}")


def _fake_chapters(series_id: str) -> list[Chapter]:
    return [
        Chapter(
            id=f"{series_id}/chapter-{n}",
            series_id=series_id,
            title=f"Chapter {n}",
            number=float(n),
            page_count=0,
        )
        for n in (1, 2)
    ]


@pytest.mark.parametrize("source_type,series_id", CASES, ids=[c[0] for c in CASES])
def test_get_series_fetches_the_series_page_once(source_type: str, series_id: str) -> None:
    connector = create_connector(source_type)
    for attr in ("_series_cache", "_chapter_list_cache"):
        getattr(connector, attr).clear()

    module = type(connector).__module__
    get_text = MagicMock(return_value="<html></html>")

    with patch.object(connector._http, "get_text", get_text), patch(
        f"{module}.parse_series_detail", side_effect=lambda html, sid, *a, **k: _fake_series(sid)
    ), patch(
        f"{module}.parse_chapters", side_effect=lambda html, sid, *a, **k: _fake_chapters(sid)
    ):
        series = connector.get_series(series_id)
        chapters_after = connector.get_chapters(series_id)

    for attr in ("_series_cache", "_chapter_list_cache"):
        getattr(connector, attr).clear()

    assert series is not None
    assert series.chapter_count == 2
    assert len(chapters_after) == 2
    assert get_text.call_count == 1, get_text.call_args_list
