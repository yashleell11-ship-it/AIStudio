"""BrowseService chapter-list resilience (transient empty vs metadata mismatch)."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from connectors.models import Chapter, Series
from connectors.comicsvalley.connector import ComicsValleyConnector
from services.browse_service import BrowseService


SERIES_ID = "some-series-04cfa291"


@pytest.fixture
def service() -> BrowseService:
    return BrowseService()


def test_get_chapters_retries_after_empty_list_when_series_reports_count(
    service: BrowseService,
):
    connector = ComicsValleyConnector()
    series = Series(
        id=SERIES_ID,
        title="Some Series",
        chapter_count=17,
    )
    chapter = Chapter(
        id=f"{SERIES_ID}/chapter-1",
        series_id=SERIES_ID,
        title="Chapter 1",
        number=1.0,
        page_count=0,
    )
    calls = {"chapters": 0}

    def fake_get_chapters(series_id: str) -> list[Chapter]:
        calls["chapters"] += 1
        if calls["chapters"] == 1:
            return []
        return [chapter]

    try:
        with patch("services.browse_service.get_settings") as mock_settings:
            mock_settings.return_value.mature_content_enabled = True
            with patch("services.browse_service.create_connector", return_value=connector):
                with patch.object(connector, "get_series", return_value=series):
                    with patch.object(connector, "get_chapters", side_effect=fake_get_chapters):
                        items = service.get_chapters("comicsvalley", SERIES_ID)
    finally:
        connector._http.close()

    assert calls["chapters"] == 2
    assert len(items) == 1
    assert items[0]["id"] == chapter.id
