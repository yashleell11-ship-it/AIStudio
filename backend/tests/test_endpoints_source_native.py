"""Endpoint-level smoke for the source-native library / reader / updates API.

Uses the ``as_user`` bearer resolver + real seeded profiles so ``X-Profile-Id``
ownership and per-profile scoping run for real.
"""

from __future__ import annotations

import pytest

from services.browse_service import get_browse_service
from tests._fakes import FakeBrowse

SRC = "mangadex"
SERIES = "solo-leveling"

FIXTURE = {
    (SRC, SERIES): {
        "meta": {"title": "Solo Leveling", "genres": ["action"], "cover_url": "http://x/c"},
        "chapters": [
            {"id": "ch-1", "number": 1.0, "title": "1", "release_date": "2026-01-01"},
            {"id": "ch-2", "number": 2.0, "title": "2", "release_date": "2026-01-02"},
        ],
        "pages": {
            "ch-1": [{"number": n, "image_url": f"/i/{n}"} for n in (1, 2, 3)],
        },
    }
}


@pytest.fixture
def acct(make_user, make_profile):
    user = make_user("owner")
    profile = make_profile(user.id, "Main")
    return user.id, profile.id


@pytest.fixture
def api(app, client, acct):
    app.dependency_overrides[get_browse_service] = lambda: FakeBrowse(FIXTURE)
    return client


def test_follow_then_list_and_unfollow(api, as_user, acct):
    uid, pid = acct
    h = as_user(uid, pid)

    follow = api.post(
        "/library/follow", json={"source_id": SRC, "series_key": SERIES}, headers=h
    )
    assert follow.status_code == 200, follow.text
    followed_id = follow.json()["id"]
    assert follow.json()["title"] == "Solo Leveling"

    listing = api.get("/library/series", headers=h).json()
    assert [s["series_key"] for s in listing["items"]] == [SERIES]

    assert api.delete(f"/library/follow/{followed_id}", headers=h).status_code == 204
    assert api.get("/library/series", headers=h).json()["items"] == []


def test_progress_batch_applies_furthest_wins_per_item(api, as_user, acct):
    uid, pid = acct
    h = as_user(uid, pid)

    api.post(
        "/reader/progress",
        json={
            "source_id": SRC, "series_key": SERIES, "chapter_key": "ch-1",
            "chapter_number": 1.0, "last_page": 10, "page_count": 20,
        },
        headers=h,
    )
    resp = api.post(
        "/reader/progress/batch",
        json=[
            {"source_id": SRC, "series_key": SERIES, "chapter_key": "ch-1",
             "chapter_number": 1.0, "last_page": 3, "page_count": 20},   # behind
            {"source_id": SRC, "series_key": SERIES, "chapter_key": "ch-1",
             "chapter_number": 1.0, "last_page": 17, "page_count": 20},  # ahead
        ],
        headers=h,
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["saved"] == 2

    series_progress = api.get(
        "/reader/progress/series", params={"source": SRC, "series": SERIES}, headers=h
    ).json()
    assert series_progress[0]["last_page"] == 17


def test_cover_fallback_url_encodes_series_key_with_slashes(
    db_session, make_user, make_profile, seed_follow
):
    from services.followed_series_service import FollowedSeriesService

    user = make_user()
    profile = make_profile(user.id, "P")
    row = seed_follow(
        user.id, profile.id, source_id=SRC, series_key="group/solo-leveling", cover_url=None
    )
    svc = FollowedSeriesService(
        db_session, FakeBrowse(), user_id=user.id, profile_id=profile.id
    )
    serialized = svc.serialize(row)
    assert (
        serialized["cover_url"]
        == f"/sources/{SRC}/series/group%2Fsolo-leveling/cover"
    )


def test_progress_batch_requires_a_profile(api, as_user, acct):
    uid, _pid = acct
    # account owns a profile but no X-Profile-Id header → 400
    resp = api.post("/reader/progress/batch", json=[], headers=as_user(uid))
    assert resp.status_code == 400
    assert resp.json()["code"] == "profile_required"
