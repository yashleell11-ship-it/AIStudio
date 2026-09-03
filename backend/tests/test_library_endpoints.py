"""HTTP-level tests for ``routes/library.py`` (spec §4.2, §7).

Real request/response against the source-native library router: ``client`` +
``as_user`` bearer + ``X-Profile-Id``, so per-profile scoping and profile
ownership run for real. A stub ``BrowseService`` stands in wherever a follow
would otherwise hit a connector.
"""

from __future__ import annotations

import pytest

from services.browse_service import get_browse_service
from tests._fakes import FakeBrowse

SRC = "mangadex"
S1 = "solo-leveling"
S2 = "omniscient-reader"

FIXTURE = {
    (SRC, S1): {
        "meta": {"title": "Solo Leveling", "genres": ["action", "fantasy"],
                 "cover_url": "http://x/sl.jpg"},
        "chapters": [
            {"id": "sl-1", "number": 1.0, "title": "Ch 1", "release_date": "2026-01-01"},
            {"id": "sl-2", "number": 2.0, "title": "Ch 2", "release_date": "2026-01-02"},
        ],
    },
    (SRC, S2): {
        "meta": {"title": "Omniscient Reader", "genres": ["action", "drama"]},
        "chapters": [
            {"id": "or-1", "number": 1.0, "title": "Prologue", "release_date": "2026-01-01"},
        ],
    },
}


@pytest.fixture
def acct(make_user, make_profile):
    user = make_user("libowner")
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


def _follow(api, h, series_key=S1):
    resp = api.post(
        "/library/follow", json={"source_id": SRC, "series_key": series_key}, headers=h
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


# --- follow / list / patch / unfollow ------------------------------------


def test_follow_unfollow_round_trip(api, h):
    row = _follow(api, h)
    assert row["title"] == "Solo Leveling"
    assert row["chapter_count"] == 2

    listing = api.get("/library/series", headers=h).json()
    assert [s["series_key"] for s in listing["items"]] == [S1]

    # idempotent re-follow returns the same row
    again = api.post(
        "/library/follow", json={"source_id": SRC, "series_key": S1}, headers=h
    ).json()
    assert again["id"] == row["id"]

    assert api.delete(f"/library/follow/{row['id']}", headers=h).status_code == 204
    assert api.get("/library/series", headers=h).json()["items"] == []


def test_patch_series_favorite_status_notify(api, h):
    row = _follow(api, h)
    resp = api.patch(
        f"/library/series/{row['id']}",
        json={"is_favorite": True, "reading_status": "completed", "notify": False},
        headers=h,
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["is_favorite"] is True
    assert body["reading_status"] == "completed"
    assert body["notify"] is False


def test_patch_series_rejects_unknown_status(api, h):
    row = _follow(api, h)
    resp = api.patch(
        f"/library/series/{row['id']}",
        json={"reading_status": "banana"},
        headers=h,
    )
    assert resp.status_code == 422
    assert resp.json()["code"] == "invalid_reading_status"


def test_list_filters_and_sort(api, h):
    a = _follow(api, h, S1)
    _follow(api, h, S2)
    api.patch(f"/library/series/{a['id']}", json={"is_favorite": True}, headers=h)

    favs = api.get("/library/series", params={"is_favorite": True}, headers=h).json()
    assert [s["series_key"] for s in favs["items"]] == [S1]

    desc = api.get("/library/series", params={"sort": "-title"}, headers=h).json()
    assert [s["series_key"] for s in desc["items"]] == [S1, S2]  # S..l > O..r


def test_get_series_detail_and_404(api, h):
    row = _follow(api, h)
    detail = api.get(f"/library/series/{row['id']}", headers=h).json()
    assert detail["id"] == row["id"]
    assert "chapters" in detail
    assert detail["progress"] == {}

    missing = api.get("/library/series/999999", headers=h)
    assert missing.status_code == 404
    assert missing.json()["code"] == "series_not_found"

    patch_missing = api.patch(
        "/library/series/999999", json={"notify": False}, headers=h
    )
    assert patch_missing.status_code == 404


def test_follow_requires_profile_when_account_has_profiles(api, as_user, acct):
    uid, _pid = acct
    resp = api.post(
        "/library/follow", json={"source_id": SRC, "series_key": S1},
        headers=as_user(uid),
    )
    assert resp.status_code == 400
    assert resp.json()["code"] == "profile_required"


def test_series_are_isolated_between_profiles(api, h, as_user, acct, make_profile):
    uid, _pid = acct
    _follow(api, h)
    other = make_profile(uid, "Other")
    other_list = api.get("/library/series", headers=as_user(uid, other.id)).json()
    assert other_list["items"] == []


# --- strips / stats -----------------------------------------------------


def test_statistics_and_strips(api, h):
    row = _follow(api, h)
    api.patch(
        f"/library/series/{row['id']}",
        json={"is_favorite": True, "reading_status": "reading"},
        headers=h,
    )

    stats = api.get("/library/statistics", headers=h).json()
    assert stats["followed_total"] == 1
    assert stats["favorites"] == 1
    assert stats["by_reading_status"]["reading"] == 1

    for path in ("/library/continue-reading", "/library/recently-updated",
                 "/library/recommendations"):
        resp = api.get(path, headers=h)
        assert resp.status_code == 200, (path, resp.text)
        assert isinstance(resp.json(), list)

    recent = api.get("/library/recently-updated", headers=h).json()
    assert [s["series_key"] for s in recent] == [S1]  # follow stamped last_checked_at


def test_search_over_followed_set(api, h):
    _follow(api, h, S1)
    _follow(api, h, S2)
    hits = api.get("/library/search", params={"q": "omni"}, headers=h).json()
    assert [s["series_key"] for s in hits["items"]] == [S2]

    assert api.get("/library/search", params={"q": ""}, headers=h).status_code == 422


# --- collections ------------------------------------------------------


def test_collections_crud_and_series_membership(api, h):
    created = api.post(
        "/library/collections", json={"name": "Weekend", "description": "sat reads"},
        headers=h,
    )
    assert created.status_code == 200, created.text
    cid = created.json()["id"]

    assert [c["id"] for c in api.get("/library/collections", headers=h).json()] == [cid]

    renamed = api.patch(
        f"/library/collections/{cid}", json={"name": "Weekday", "sort_order": 3},
        headers=h,
    ).json()
    assert renamed["name"] == "Weekday"
    assert renamed["sort_order"] == 3

    add = api.post(
        f"/library/collections/{cid}/series",
        json={"source_id": SRC, "series_key": S1},
        headers=h,
    )
    assert add.status_code == 200, add.text
    assert add.json()["series"][0]["series_key"] == S1

    detail = api.get(f"/library/collections/{cid}", headers=h).json()
    assert detail["series_count"] == 1

    removed = api.request(
        "DELETE", f"/library/collections/{cid}/series",
        json={"source_id": SRC, "series_key": S1}, headers=h,
    )
    assert removed.status_code == 204
    assert api.get(f"/library/collections/{cid}", headers=h).json()["series_count"] == 0

    assert api.delete(f"/library/collections/{cid}", headers=h).status_code == 204
    assert api.get("/library/collections", headers=h).json() == []

    assert api.get("/library/collections/999999", headers=h).status_code == 404


# --- tags -------------------------------------------------------------


def test_tags_and_series_tags(api, h):
    tag = api.post(
        "/library/tags", json={"name": "Peak", "category": "quality", "color": "#fff"},
        headers=h,
    )
    assert tag.status_code == 200, tag.text
    tid = tag.json()["id"]

    listed = api.get("/library/tags", headers=h).json()
    assert tid in [t["id"] for t in listed]
    assert api.get("/library/tags", params={"category": "nope"}, headers=h).json() == []

    attach = api.post(
        "/library/series-tags",
        json={"source_id": SRC, "series_key": S1, "tag_id": tid},
        headers=h,
    )
    assert attach.status_code == 200, attach.text

    detach = api.request(
        "DELETE", "/library/series-tags",
        json={"source_id": SRC, "series_key": S1, "tag_id": tid}, headers=h,
    )
    assert detach.status_code == 204

    assert api.delete(f"/library/tags/{tid}", headers=h).status_code == 204
    assert tid not in [t["id"] for t in api.get("/library/tags", headers=h).json()]
