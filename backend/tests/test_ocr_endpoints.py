"""HTTP-level tests for ``routes/ocr.py`` (spec §4.4, §7).

All four endpoints end to end: upload a transcript, read it back, list coverage,
and search — with search scoped to the caller's followed series.
"""

from __future__ import annotations

import pytest

from services.browse_service import get_browse_service
from tests._fakes import FakeBrowse

SRC = "mangadex"
SERIES = "the-max-level-hero"


@pytest.fixture
def acct(make_user, make_profile):
    user = make_user("ocr")
    profile = make_profile(user.id, "Main")
    return user.id, profile.id


@pytest.fixture
def h(as_user, acct):
    uid, pid = acct
    return as_user(uid, pid)


@pytest.fixture
def api(app, client, acct):
    app.dependency_overrides[get_browse_service] = lambda: FakeBrowse()
    return client


def _upload(api, h, chapter_key, text, engine="mlkit"):
    return api.post(
        "/ocr/chapter",
        json={
            "source_id": SRC, "series_key": SERIES, "chapter_key": chapter_key,
            "chapter_number": 1.0, "language": "en", "engine": engine,
            "pages": [{"page": 1, "text": text}],
        },
        headers=h,
    )


def test_upload_get_coverage_roundtrip(api, h):
    up = _upload(api, h, "c1", "the hero swung his blade")
    assert up.status_code == 200, up.text
    assert up.json()["word_count"] == 5

    got = api.get(
        "/ocr/chapter", params={"source": SRC, "series": SERIES, "chapter": "c1"},
        headers=h,
    )
    assert got.status_code == 200, got.text
    assert got.json()["page_texts"][0]["text"] == "the hero swung his blade"

    missing = api.get(
        "/ocr/chapter", params={"source": SRC, "series": SERIES, "chapter": "zzz"},
        headers=h,
    )
    assert missing.status_code == 404

    _upload(api, h, "c3", "another chapter of dialogue")
    cov = api.get(
        "/ocr/coverage", params={"source": SRC, "series": SERIES}, headers=h
    ).json()
    assert {c["chapter_key"] for c in cov["chapters"]} == {"c1", "c3"}


def test_empty_upload_does_not_clobber(api, h):
    _upload(api, h, "c1", "important spoken line")
    _upload(api, h, "c1", "")
    got = api.get(
        "/ocr/chapter", params={"source": SRC, "series": SERIES, "chapter": "c1"},
        headers=h,
    ).json()
    assert got["word_count"] == 3


def test_search_is_scoped_to_followed_series(api, h, acct, seed_follow):
    uid, pid = acct
    _upload(api, h, "c1", "the crimson knight bellowed a challenge")

    # not following yet → no hit
    assert api.get("/ocr/search", params={"q": "crimson"}, headers=h).json()["items"] == []

    seed_follow(uid, pid, source_id=SRC, series_key=SERIES)
    hits = api.get("/ocr/search", params={"q": "crimson"}, headers=h).json()
    assert [hit["chapter_key"] for hit in hits["items"]] == ["c1"]
    assert "<mark>" in hits["items"][0]["snippet"]


def test_search_blank_query_is_empty(api, h):
    assert api.get("/ocr/search", params={"q": "   "}, headers=h).json()["items"] == []
