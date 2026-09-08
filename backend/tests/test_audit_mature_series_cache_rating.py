"""AUDIT (shard mature-gate): a series' own stored rating is never consulted on
the browse surface of a GENERAL source.

``source_series_cache.content_rating`` is written (models.py:740) and
``core.content_rating.mature_rating_predicate`` exists for exactly this
column shape, but the only reader of the rating rule is
``mature_tracker_case`` over ``followed_series``. ``SourceCacheService
.get_series_meta`` (and ``BrowseService.get_series`` / ``get_chapters`` /
``get_chapter_pages`` behind ``/sources/{general}/...``) apply the SOURCE gate
only. So the same profile that cannot see its ``smut`` follow in the library
(rating captured at follow time from the genres) is served that series'
metadata, chapter list and pages by the browse routes.

The live DB has exactly this shape today: one ``followed_series`` row with
``content_rating='smut'`` on a general source, and both profiles gated.
"""

from __future__ import annotations

import json

import pytest

from database.models import SourceCoverCache, SourceSeriesCache
from services.source_cache_service import SourceCacheService
from tests._fakes import FakeBrowse

SRC = "mangabuddy"
KEY = "a-smut-series"


def test_cached_series_meta_with_an_adult_rating_is_withheld_from_a_shut_gate(db_session):
    db_session.add(
        SourceSeriesCache(
            source_id=SRC,
            series_key=KEY,
            title="Explicit Title",
            content_rating="smut",
            genres=json.dumps(["Smut", "Romance"]),
            chapters=json.dumps([{"id": "c1", "number": 1}]),
        )
    )
    db_session.commit()

    browse = FakeBrowse({(SRC, KEY): {"meta": {"title": "Explicit Title"}, "chapters": []}})
    browse.gate_open = False  # general source: ensure_visible passes by design
    svc = SourceCacheService(db_session, browse)

    try:
        payload = svc.get_series_meta(SRC, KEY)
    except Exception as exc:  # noqa: BLE001
        payload = {"error": str(exc)}
    assert payload.get("title") != "Explicit Title", payload


# A cover row carries no rating of its own, so a cached HIT has to ask the
# series row beside it. ``BrowseService.resolve_series_cover`` already refused
# an adult row on a MISS, which made the leak a function of whether anyone had
# loaded that grid before.
def test_cached_cover_of_an_adult_series_is_withheld_from_a_shut_gate(db_session):
    db_session.add(
        SourceSeriesCache(
            source_id=SRC,
            series_key=KEY,
            title="Explicit Title",
            content_rating="smut",
            genres=json.dumps(["Smut", "Romance"]),
            chapters=json.dumps([]),
        )
    )
    db_session.add(
        SourceCoverCache(
            source_id=SRC,
            series_key=KEY,
            width=320,
            fmt="jpeg",
            media_type="image/jpeg",
            byte_size=5,
            data=b"BYTES",
        )
    )
    db_session.commit()

    browse = FakeBrowse()
    browse.gate_open = False  # general source: ensure_visible passes by design
    svc = SourceCacheService(db_session, browse)

    try:
        _, data, _ = svc.get_series_cover(SRC, KEY, width=320, fmt="jpeg")
    except Exception:  # noqa: BLE001 - a refusal of any shape is the point
        return
    assert data != b"BYTES", "a cached cover was served to a shut gate"
