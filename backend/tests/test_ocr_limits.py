"""POST /ocr/chapter payload bounds (audit finding 13).

The upload used to accept an unbounded body — any number of pages, unbounded
per-page text, and free-form ``list[Any]`` boxes — written into one global
``chapter_ocr`` row plus an FTS reindex. Pages, text, and boxes are now typed
and capped, with a whole-payload text ceiling.
"""

from __future__ import annotations

import pytest

from routes.ocr import (
    OCR_MAX_BOXES_PER_PAGE,
    OCR_MAX_PAGE_TEXT_CHARS,
    OCR_MAX_PAGES,
    OCR_MAX_TOTAL_TEXT_CHARS,
)

SRC = "mangadex"
SERIES = "bounded-series"


@pytest.fixture
def acct(make_user, make_profile):
    user = make_user("ocr-limits")
    profile = make_profile(user.id, "Main")
    return user.id, profile.id


@pytest.fixture
def h(as_user, acct):
    uid, pid = acct
    return as_user(uid, pid)


@pytest.fixture
def follows(seed_follow, acct):
    """Reading a transcript back is follow-scoped; the upload bounds these
    tests are about are not, so the follow is just what makes the read-back
    assertions observable."""
    uid, pid = acct
    seed_follow(uid, pid, source_id=SRC, series_key=SERIES)


def _upload(client, h, pages):
    return client.post(
        "/ocr/chapter",
        json={
            "source_id": SRC,
            "series_key": SERIES,
            "chapter_key": "c1",
            "engine": "mlkit",
            "pages": pages,
        },
        headers=h,
    )


def test_too_many_pages_rejected(client, h):
    pages = [{"page": n + 1, "text": "x"} for n in range(OCR_MAX_PAGES + 1)]
    assert _upload(client, h, pages).status_code == 422


def test_oversized_page_text_rejected(client, h):
    pages = [{"page": 1, "text": "x" * (OCR_MAX_PAGE_TEXT_CHARS + 1)}]
    assert _upload(client, h, pages).status_code == 422


def test_too_many_boxes_rejected(client, h):
    boxes = [{"text": "hi"}] * (OCR_MAX_BOXES_PER_PAGE + 1)
    pages = [{"page": 1, "text": "x", "boxes": boxes}]
    assert _upload(client, h, pages).status_code == 422


def test_total_text_ceiling_rejected(client, h):
    # Each page individually under the per-page cap, but the sum is over the
    # whole-payload ceiling.
    per_page = OCR_MAX_PAGE_TEXT_CHARS
    n_pages = OCR_MAX_TOTAL_TEXT_CHARS // per_page + 1
    assert n_pages <= OCR_MAX_PAGES
    pages = [{"page": n + 1, "text": "x" * per_page} for n in range(n_pages)]
    assert _upload(client, h, pages).status_code == 422


def test_free_form_box_junk_is_dropped_not_stored(client, h, follows):
    """Boxes are a typed shape now: unknown keys and nested JSON are discarded
    before the row is written."""
    pages = [
        {
            "page": 1,
            "text": "the hero spoke",
            "boxes": [
                {
                    "text": "the hero spoke",
                    "x": 1.0,
                    "y": 2.0,
                    "width": 100.0,
                    "height": 20.0,
                    "deeply": {"nested": {"junk": ["x"] * 50}},
                    "huge_extra": "y" * 500,
                }
            ],
        }
    ]
    up = _upload(client, h, pages)
    assert up.status_code == 200, up.text

    got = client.get(
        "/ocr/chapter",
        params={"source": SRC, "series": SERIES, "chapter": "c1"},
        headers=h,
    ).json()
    box = got["page_texts"][0]["boxes"][0]
    assert box["text"] == "the hero spoke"
    assert "deeply" not in box
    assert "huge_extra" not in box


def test_normal_upload_still_works(client, h):
    pages = [
        {"page": 1, "text": "line one", "boxes": [{"text": "line one", "x": 0.0}]},
        {"page": 2, "text": "line two"},
    ]
    up = _upload(client, h, pages)
    assert up.status_code == 200, up.text
    assert up.json()["word_count"] == 4
