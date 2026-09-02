"""OCR: global write, scoped search (spec §3.9, §4.4, §7).

``chapter_ocr`` is one row per chapter, not per user. A search result is only
returned when the caller follows that series in the active profile — so one
profile never sees another's OCR contribution for a series it does not follow.
"""

from __future__ import annotations

import pytest

from services.followed_series_service import FollowedSeriesService
from services.ocr_ingest_service import OcrIngestService
from services.ocr_search import OcrSearchService
from tests._fakes import FakeBrowse

SRC = "mangadex"
SERIES = "the-dragon-king"


@pytest.fixture
def accounts(make_user, make_profile):
    ua, ub = make_user("a"), make_user("b")
    pa = make_profile(ua.id, "A")
    pb = make_profile(ub.id, "B")
    return {"ua": ua.id, "ub": ub.id, "pa": pa.id, "pb": pb.id}


def _search_svc(db, user_id, profile_id):
    followed = FollowedSeriesService(
        db, FakeBrowse(), user_id=user_id, profile_id=profile_id
    )
    return OcrSearchService(db, followed)


def _ingest(db, user_id):
    return OcrIngestService(db, user_id=user_id)


def test_ingest_writes_one_global_row(db_session, accounts):
    r1 = _ingest(db_session, accounts["ua"]).ingest_chapter(
        source_id=SRC,
        series_key=SERIES,
        chapter_key="c1",
        engine="mlkit",
        pages=[{"page": 1, "text": "the dragon king awakened"}],
    )
    # a second contributor for the same chapter replaces, not duplicates
    r2 = _ingest(db_session, accounts["ub"]).ingest_chapter(
        source_id=SRC,
        series_key=SERIES,
        chapter_key="c1",
        engine="apple-vision",
        pages=[{"page": 1, "text": "the dragon king awakened at dawn"}],
    )
    assert r1["source_id"] == r2["source_id"]
    from database.models import ChapterOcr

    rows = db_session.query(ChapterOcr).filter_by(
        source_id=SRC, series_key=SERIES, chapter_key="c1"
    ).all()
    assert len(rows) == 1
    assert rows[0].engine == "apple-vision"  # last engine wins


def test_empty_upload_never_clobbers_a_good_transcript(db_session, accounts):
    ing = _ingest(db_session, accounts["ua"])
    ing.ingest_chapter(
        source_id=SRC, series_key=SERIES, chapter_key="c2",
        engine="mlkit", pages=[{"page": 1, "text": "important dialogue here"}],
    )
    ing.ingest_chapter(
        source_id=SRC, series_key=SERIES, chapter_key="c2",
        engine="mlkit", pages=[{"page": 1, "text": ""}],
    )
    from database.models import ChapterOcr

    row = db_session.query(ChapterOcr).filter_by(chapter_key="c2").one()
    assert row.word_count == 3
    assert "important" in row.full_text


def test_search_is_scoped_to_the_callers_followed_series(
    db_session, accounts, seed_follow
):
    # A follows the series, B does not.
    seed_follow(accounts["ua"], accounts["pa"], source_id=SRC, series_key=SERIES)
    _ingest(db_session, accounts["ua"]).ingest_chapter(
        source_id=SRC, series_key=SERIES, chapter_key="c1",
        engine="mlkit", pages=[{"page": 1, "text": "the crimson dragon roared"}],
    )

    a_hits = _search_svc(db_session, accounts["ua"], accounts["pa"]).search("crimson")
    b_hits = _search_svc(db_session, accounts["ub"], accounts["pb"]).search("crimson")

    assert [h["chapter_key"] for h in a_hits["items"]] == ["c1"]
    assert b_hits["items"] == []  # B does not follow the series


def test_following_the_series_reveals_the_existing_global_ocr(
    db_session, accounts, seed_follow
):
    _ingest(db_session, accounts["ua"]).ingest_chapter(
        source_id=SRC, series_key=SERIES, chapter_key="c1",
        engine="mlkit", pages=[{"page": 1, "text": "a whisper in the dark tower"}],
    )
    # B now follows it → the global row becomes visible to B.
    seed_follow(accounts["ub"], accounts["pb"], source_id=SRC, series_key=SERIES)
    b_hits = _search_svc(db_session, accounts["ub"], accounts["pb"]).search("whisper")
    assert [h["chapter_key"] for h in b_hits["items"]] == ["c1"]


def test_coverage_lists_ocr_chapters_for_a_series(db_session, accounts):
    ing = _ingest(db_session, accounts["ua"])
    for key in ("c1", "c3"):
        ing.ingest_chapter(
            source_id=SRC, series_key=SERIES, chapter_key=key,
            engine="mlkit", pages=[{"page": 1, "text": f"text for {key}"}],
        )
    cov = ing.coverage(SRC, SERIES)
    assert {c["chapter_key"] for c in cov["chapters"]} == {"c1", "c3"}
