"""HTTP-level tests for ``routes/reader.py`` (spec §4.1, §7).

manifest, progress (+ furthest-wins), progress/batch, progress/series, history,
bookmarks CRUD — real request/response with ``as_user`` + ``X-Profile-Id``.
"""

from __future__ import annotations

import pytest

from services.browse_service import get_browse_service
from tests._fakes import FakeBrowse

SRC = "mangadex"
SERIES = "the-beginning-after-the-end"

FIXTURE = {
    (SRC, SERIES): {
        "meta": {"title": "TBATE"},
        "chapters": [
            {"id": "c1", "number": 1.0, "title": "One"},
            {"id": "c2", "number": 2.0, "title": "Two"},
            {"id": "c3", "number": 3.0, "title": "Three"},
        ],
        "pages": {
            "c2": [
                {"number": 1, "image_url": "/sources/mangadex/pages/p1/image"},
                {"number": 2, "image_url": "/sources/mangadex/pages/p2/image"},
            ],
        },
    }
}


@pytest.fixture
def acct(make_user, make_profile):
    user = make_user("reader")
    profile = make_profile(user.id, "Main")
    return user.id, profile.id


@pytest.fixture
def api(app, client, acct):
    app.dependency_overrides[get_browse_service] = lambda: FakeBrowse(FIXTURE)
    return client


@pytest.fixture
def h(as_user, acct):
    uid, pid = acct
    return as_user(uid, pid)


# --- manifest --------------------------------------------------------------


def test_manifest_shape_and_neighbours(api, h):
    resp = api.get(
        "/reader/chapter/manifest",
        params={"source": SRC, "series": SERIES, "chapter": "c2"},
        headers=h,
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["chapter_number"] == 2.0
    assert body["page_count"] == 2
    assert body["pages"][0] == {
        "number": 1,
        "url": "/sources/mangadex/pages/p1/image",
        "width": None,
        "height": None,
    }
    assert body["prev"] == "c1"
    assert body["next"] == "c3"


def test_manifest_unknown_chapter_404(api, h):
    resp = api.get(
        "/reader/chapter/manifest",
        params={"source": SRC, "series": SERIES, "chapter": "nope"},
        headers=h,
    )
    assert resp.status_code == 404


# --- progress + furthest-wins -------------------------------------------


def _save(api, h, **over):
    body = {
        "source_id": SRC, "series_key": SERIES, "chapter_key": "c1",
        "chapter_number": 1.0, "last_page": 1, "page_count": 20,
    }
    body.update(over)
    return api.post("/reader/progress", json=body, headers=h)


def test_progress_never_rewinds(api, h):
    assert _save(api, h, last_page=12).json()["last_page"] == 12
    behind = _save(api, h, last_page=4).json()
    assert behind["last_page"] == 12
    assert behind["advanced"] is False
    ahead = _save(api, h, last_page=18).json()
    assert ahead["last_page"] == 18
    assert ahead["advanced"] is True


def test_progress_completion_is_sticky(api, h):
    _save(api, h, last_page=20, is_completed=True)
    again = _save(api, h, last_page=2, is_completed=False).json()
    assert again["is_completed"] is True


def test_progress_batch(api, h):
    _save(api, h, last_page=10)
    resp = api.post(
        "/reader/progress/batch",
        json=[
            {"source_id": SRC, "series_key": SERIES, "chapter_key": "c1",
             "chapter_number": 1.0, "last_page": 3, "page_count": 20},
            {"source_id": SRC, "series_key": SERIES, "chapter_key": "c1",
             "chapter_number": 1.0, "last_page": 15, "page_count": 20},
            {"source_id": SRC, "series_key": SERIES, "chapter_key": "c2",
             "chapter_number": 2.0, "last_page": 1, "page_count": 20},
        ],
        headers=h,
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["saved"] == 3

    series = api.get(
        "/reader/progress/series", params={"source": SRC, "series": SERIES}, headers=h
    ).json()
    by_key = {r["chapter_key"]: r["last_page"] for r in series}
    assert by_key == {"c1": 15, "c2": 1}


def test_progress_batch_requires_profile(api, as_user, acct):
    uid, _pid = acct
    resp = api.post("/reader/progress/batch", json=[], headers=as_user(uid))
    assert resp.status_code == 400
    assert resp.json()["code"] == "profile_required"


def test_history_lists_recent_first(api, h):
    _save(api, h, chapter_key="c1", chapter_number=1.0, last_page=5)
    _save(api, h, chapter_key="c2", chapter_number=2.0, last_page=5)
    hist = api.get("/reader/history", headers=h).json()
    assert [r["chapter_key"] for r in hist] == ["c2", "c1"]


def test_progress_isolated_between_profiles(api, h, as_user, acct, make_profile):
    uid, _pid = acct
    _save(api, h, last_page=7)
    other = make_profile(uid, "Other")
    other_hist = api.get("/reader/history", headers=as_user(uid, other.id)).json()
    assert other_hist == []


# --- bookmarks --------------------------------------------------------


def test_bookmarks_crud(api, h):
    created = api.post(
        "/reader/bookmark",
        json={"source_id": SRC, "series_key": SERIES, "chapter_key": "c1",
              "page": 4, "note": "cool panel"},
        headers=h,
    )
    assert created.status_code == 200, created.text
    bm_id = created.json()["id"]

    listed = api.get("/reader/bookmarks", headers=h).json()
    assert [b["id"] for b in listed] == [bm_id]

    scoped = api.get(
        "/reader/bookmarks", params={"source": SRC, "series": "other"}, headers=h
    ).json()
    assert scoped == []

    assert api.delete(f"/reader/bookmarks/{bm_id}", headers=h).status_code == 204
    assert api.get("/reader/bookmarks", headers=h).json() == []

    assert api.delete("/reader/bookmarks/999999", headers=h).status_code == 404
